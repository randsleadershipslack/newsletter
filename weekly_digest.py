#! /usr/bin/env python3

import argparse
import datetime
from slackclient import SlackClient
import os
import re
import sys
import textwrap
import time


class ApiWrapper:
    """
    Consolidates API calls, error handling
    """

    def __init__(self, options):
        self.options = options
        self.slack = SlackClient(os.environ.get('API_TOKEN', "garbage"))

    def call(self, *args, **kwargs):
        tries = 0;
        while tries < 3:
            response = self.slack.api_call(*args, **kwargs)
            if response['ok']:
                return response
            if 'error' not in response or 'ratelimited' not in response['error']:
                print(response)
                raise RuntimeError
            else:
                tries += 1
                time.sleep(tries)
        raise RuntimeError("Rate limited three times in a row")

    def get_channels(self):
        response = self.call("channels.list", exclude_archived=True, exclude_members=True)
        channels = []
        for channel in response["channels"]:
            name = channel['name']
            channel_id = channel['id']
            channels.append(Channel(api=self, channel_id=channel_id, name=name))
        return channels


def valid_date(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


class Options(argparse.ArgumentParser):
    """
    Consolidates our argument handling.
    """

    def __init__(self):
        super().__init__(description='Create a digest of reacted-to posts from a given week.')
        self.parsed_args = None
        self.start_date = datetime.date.today()
        self.end_date = datetime.date.today()
        self.start_timestamp = datetime.datetime.now()
        self.end_timestamp = datetime.datetime.now()
        self._whitelist = []
        self._blacklist = []
        self.debug = False

        self.add_argument("--week", type=int, default=1, metavar="N",
                          help="Fetch messages from N weeks ago (default: %(default)s)")
        self.add_argument("--start", type=valid_date, metavar="YYYY-MM-DD",
                          help="Fetch messages from the given date.  Overrides week start.")
        self.add_argument("--end", type=valid_date, metavar="YYYY-MM-DD",
                          help="Fetch messages up to the given date.  Overrides week end.")
        self.add_argument("--channel", "--channels", nargs='+', metavar="CHANNEL",
                          help="Only examine the given channel(s) (regular expressions allowed)")
        self.add_argument("--channel-list", metavar="FILE",
                          help="Only examine the channel(s) given in the file (regular expressions allowed)")
        self.add_argument("--reactions", type=int, default=3, metavar="THRESHOLD",
                          help="The number of reactions necessary for retaining in the digest (default: %(default)s)")
        self.add_argument("--replies", type=int, default=10, metavar="THRESHOLD", dest='reply_threshold',
                          help="The number of replies necessary for retaining a thread in the digest " +
                               "(default: %(default)s)")
        self.add_argument("--thread-reactions", type=int, metavar="THRESHOLD", dest='thread_reply_threshold',
                          help="The number of in-thread reactions necessary for retaining a thread in the digest " +
                               "(default: twice the reactions threshold)")
        self.add_argument("--exclude", nargs='+', metavar="CHANNEL",
                          help="Specifically exclude the given channel(s) (regular expressions allowed)")
        self.add_argument("--exclude-list", metavar="FILE",
                          help="Specifically exclude the channel(s) given in the file (regular expressions allowed)")
        self.add_argument("--split-by-channels", action='store_true', dest='split_by_channels',
                          help="Split the results by channel rather than consolidating messages and threads.  " +
                               "Default false.")
        self.add_argument("-d", "--debug", action='store_true', dest='debug',
                          help="Enable more thorough debugging messages.")

    def store_args(self):
        self.parsed_args = self.parse_args()
        self._extract_dates()
        self._compile_lists()
        self.debug = self.parsed_args.debug

    @property
    def thread_reactions(self):
        if self.parsed_args.thread_reply_threshold:
            return self.parsed_args.thread_reply_threshold
        return self.parsed_args.reactions * 2

    @staticmethod
    def _find_week(week):
        ago = datetime.date.today() - datetime.timedelta(week * 7)
        if ago.weekday() == 6:
            start_date = ago
        else:
            start_date = ago - datetime.timedelta(7 - ((6 - ago.weekday()) % 7))
        end_date = start_date + datetime.timedelta(7)
        return start_date, end_date

    def _extract_dates(self):
        # Work in dates to force the beginning of the day
        if self.parsed_args.week:
            self.start_date, self.end_date = Options._find_week(self.parsed_args.week)

        if self.parsed_args.start:
            self.start_date = self.parsed_args.start

        if self.parsed_args.end:
            self.end_date = self.parsed_args.end

        if self.start_date > self.end_date:
            raise ValueError

        self.start_timestamp = datetime.datetime.combine(self.start_date, datetime.time())
        self.end_timestamp = datetime.datetime.combine(self.end_date, datetime.time())

        # Return datetimes to allow easy timestamp conversion
        return self.start_timestamp, self.end_timestamp

    def _compile_lists(self):
        self._add_command_line_channels()
        self._add_channels_from_file()
        self._add_command_line_exclusions()
        self._exclude_channels_from_file()

    def _add_command_line_channels(self):
        if self.parsed_args.channel:
            for chan in self.parsed_args.channel:
                self._whitelist.append(re.compile(chan))

    def _add_command_line_exclusions(self):
        if self.parsed_args.exclude:
            for chan in self.parsed_args.exclude:
                self._blacklist.append(re.compile(chan))

    def _add_channels_from_file(self):
        if self.parsed_args.channel_list:
            with open(self.parsed_args.channel_list, 'r') as f:
                for line in f:
                    for chan in line.split():
                        self._whitelist.append(re.compile(chan))

    def _exclude_channels_from_file(self):
        if self.parsed_args.exclude_list:
            with open(self.parsed_args.exclude_list, 'r') as f:
                for line in f:
                    for chan in line.split():
                        self._blacklist.append(re.compile(chan))

    def filter_channel(self, name):
        if any(expression.match(name) for expression in self._whitelist):
            return False
        elif any(expression.match(name) for expression in self._blacklist):
            return True
        elif not (self._whitelist or 'zmeta' in name):
            return False
        return True


class Message:
    """
    Deals with interpreting message information
    """

    def __init__(self, api, channel, json):
        self.api = api
        self.channel_id = channel.id
        self.channel_name = channel.name
        self._json = json
        self.replies = []
        self.username = ""
        self.url = ""
        self._reaction_count = None
        self._time = None

    @property
    def timestamp(self):
        return self._json["ts"]

    @property
    def from_bot(self):
        if 'subtype' in self._json and self._json['subtype'] == "bot_message":
            return True
        return False

    @property
    def user_id(self):
        return self._json.get('user')

    @property
    def text(self):
        return self._json.get('text')

    @property
    def is_thread(self):
        return self.replies

    @property
    def thread_root(self):
        root = self._json.get("thread_ts")
        if root and root != self.timestamp:
            return root
        return None

    @property
    def reaction_count(self):
        if not self._reaction_count:
            if 'reactions' not in self._json:
                return 0
            self._reaction_count = 0
            for reaction in self._json['reactions']:
                self._reaction_count += int(reaction['count'])
        return self._reaction_count

    @property
    def threaded_reaction_count(self):
        count = 0
        for message in self.replies:
            count += message.reaction_count
        return count

    @property
    def time(self):
        if not self._time:
            time = datetime.datetime.fromtimestamp(float(self.timestamp))
            time = time.replace(second=0, microsecond=0)
            self._time = time.isoformat(sep=" ")
        return self._time

    def __repr__(self):
        return repr(self._json)

    def __str__(self):
        return str(self._json)

    def annotate(self, users):
        self._annotate_user(users)
        self._annotate_link()

    def _annotate_user(self, users):
        user = users.get(self.user_id, User(api=self.api, user_id=self.user_id))
        if user:
            self.username = user.name

    def _annotate_link(self):
        response = self.api.call("chat.getPermalink", channel=self.channel_id, message_ts=self.timestamp)
        self.url = response['permalink']


class User:
    """
    Tracks and aggregates information specific to a user.
    """

    def __init__(self, api, user_id):
        self.api = api
        self.id = user_id
        self._real_name = ""
        self._display_name = ""

    def fetch_name(self):
        if not self._real_name and not self._display_name:
            response = self.api.call("users.info", user=self.id)
            self._real_name = response['user']['profile']['real_name']
            self._display_name = response['user']['profile']['display_name']

    @property
    def name(self):
        if not self._real_name and not self._display_name:
            self.fetch_name()
        if self._display_name:
            return self._display_name
        return self._real_name


class Channel:
    """
    Tracks and aggregates information specific to a channel.
    """

    def __init__(self, api, channel_id, name):
        self.api = api
        self.id = channel_id
        self.name = name
        self.all_messages = {}

    def reset(self):
        self.all_messages = {}

    def fetch_messages(self, start, end):
        more = True
        start_from = start.timestamp()
        end_at = end.timestamp()
        replies = []
        while more:
            response = self.api.call("channels.history", channel=self.id, inclusive=False, oldest=start_from,
                                latest=end_at, count=500)
            more = response['has_more']
            for message in self._extract_messages(response):
                self.all_messages[message.timestamp] = message
                if message.from_bot:
                    continue
                if message.thread_root:
                    replies.append(message)
                end_at = message.timestamp
        for message in replies:
            self._accumulate_thread(message)

    def _extract_messages(self, response):
        messages = []
        message_list = response['messages']
        for json_msg in message_list:
            messages.append(Message(api = self.api, channel=self, json=json_msg))
        return messages

    def _accumulate_thread(self, message):
        root = message.thread_root
        if root not in self.all_messages:
            self.all_messages[root] = self.fetch_message(root)
        self.all_messages[root].replies.append(message)

    def fetch_message(self, timestamp):
        if timestamp in self.all_messages:
            return self.all_messages[timestamp]
        response = self.api.call("channels.history", channel=self.id, inclusive=True, latest=timestamp, count=1)
        return self._extract_messages(response)[0]


class MessageSorter:
    """
    A class to sort lists of messages
    """

    def __init__(self):
        pass

    def sort_messages(self, messages):
        messages.sort(key=lambda message: message.reaction_count)
        messages.reverse()

    def sort_threads(self, messages):
        messages.sort(key=lambda message: message.threaded_reaction_count)
        messages.reverse()


class Filter:
    """
    A class to manage filtering things out as necessary
    """

    def __init__(self, options):
        self._options = options

    def filter_channels(self, channels):
        filtered = []
        for channel in channels:
            if not self._options.filter_channel(channel.name):
                filtered.append(channel)
        return filtered

    def filter_messages(self, all_messages):
        filtered = []
        for message in all_messages:
            if message.reaction_count >= self._options.parsed_args.reactions:
                filtered.append(message)
        return filtered

    def filter_threads(self, all_messages):
        filtered = []
        for message in all_messages:
            if len(message.replies) >= self._options.parsed_args.reply_threshold:
                filtered.append(message)
            elif message.threaded_reaction_count >= self._options.thread_reactions:
                filtered.append(message)
        return filtered


class ChannelFormatter:
    """
    A class to repeatedly format channels
    """

    def __init__(self, separator_char='='):
        self._sep = separator_char
        self._template = "{box}\n{name}\n{box}\n\n"
        pass

    def format(self, channel):
        name = self._sep * 2 + ' ' * 2 + channel.name + ' ' * 2 + self._sep * 2
        box = self._sep * len(name)
        return self._template.format(box=box, name=name)


class MessageFormatter:
    """
    A class to repeatedly format messages
    """

    def __init__(self, wrapper, add_channel_name=True, separator_char='-'):
        self._sep = separator_char * 80
        self._wrapper = wrapper
        self._template = "{sep}\n{url}\n@{name} wrote on {time}\n{react} reactions\n{sep}\n{text}\n"
        if add_channel_name:
            self._template = "{sep}\n{url}\n@{name} wrote in #{channel} on {time}\n{react} reactions\n{sep}\n{text}\n"
        pass

    def format(self, message):
        return self._template.format(sep=self._sep, url=message.url, name=message.username, time=message.time,
                                     text=self._wrapper.fill(message.text), react=message.reaction_count,
                                     channel=message.channel_name)


class ThreadFormatter:
    """
    A class to repeatedly format thread starting messages
    """

    def __init__(self, wrapper, add_channel_name=True, separator_char='-'):
        self._sep = separator_char * 80
        self._wrapper = wrapper
        self._template = \
            "{sep}\n{url}\n@{name} wrote on {time}\n{replies} replies, {react} reactions in thread\n{sep}\n{text}\n"
        if add_channel_name:
            self._template = "{sep}\n{url}\n@{name} wrote in #{channel} on {time}\n{replies} replies, {react} " +\
                             "reactions in thread\n{sep}\n{text}\n"
        pass

    def format(self, message):
        return self._template.format(sep=self._sep, url=message.url, name=message.username, time=message.time,
                                     text=self._wrapper.fill(message.text), replies=len(message.replies),
                                     react=message.threaded_reaction_count, channel=message.channel_name)


class Writer:
    """
    A base class for writing
    """

    def __init__(self, message_filter, sorter):
        self._filter = message_filter
        self._sorter = sorter
        self.total_messages = 0
        self.total_channels = 0
        self.folder_name = Writer._create_folder()
        self._wrapper = textwrap.TextWrapper(width=80, expand_tabs=False, replace_whitespace=False,
                                             drop_whitespace=False)
        self._channel_report_template = \
            "\t{name}: {messages} potential messages, {threads} long threads from {total} total messages"

    @staticmethod
    def _create_folder():
        name = datetime.date.today().isoformat()
        try:
            if not os.path.exists(name):
                os.makedirs(name)
        except OSError:
            print('Error: Creating name. ' + name)
            raise
        return name

    def _filename(self, name):
        return self.folder_name + "/" + name + ".txt"


class ChannelWriter(Writer):
    """
    Writes the message information to files by channel
    """

    def __init__(self, message_filter, sorter):
        super().__init__(message_filter, sorter)
        self.filtered_messages = 0
        self.total_threads = 0
        self._users = {}
        self._channel_formatter = ChannelFormatter()
        self._message_formatter = MessageFormatter(self._wrapper, add_channel_name=False)
        self._thread_formatter = ThreadFormatter(self._wrapper, add_channel_name=False)

    def add_channel(self, channel):
        all_messages = channel.all_messages.values()
        if not all_messages:
            return

        self.total_messages += len(all_messages)

        messages = self._filter.filter_messages(all_messages)
        threads = self._filter.filter_threads(all_messages)
        if not (messages or threads):
            return

        annotate_messages(messages, self._users)
        annotate_messages(threads, self._users)
        print(self._channel_report_template.format(name=channel.name, messages=len(messages), threads=len(threads),
                                                   total=len(channel.all_messages)))
        self.filtered_messages += len(messages)
        self.total_threads += len(threads)
        self.total_channels += 1
        self._write_channel(channel, messages, threads)

    def _write_channel(self, channel, messages, threads):
        with open(self._filename(channel.name), 'w') as f:
            f.write(self._channel_formatter.format(channel))

            self._sorter.sort_messages(messages)
            for message in messages:
                f.write(self._message_formatter.format(message))
                f.write("\n")

            self._sorter.sort_threads(threads)
            f.write("\n")
            f.write("Threaded messages: {}".format(len(threads)))
            f.write("\n")
            for message in threads:
                f.write(self._thread_formatter.format(message))
                f.write("\n")

    def finalize(self):
        if self.total_channels > 1:
            print("\nFound {0} potential messages and {1} long threads across {2} channels and {3} messages".format(
                self.filtered_messages, self.total_threads, self.total_channels, self.total_messages))


class ConsolidatedWriter(Writer):
    """
    Writes the message information to files by messages and threads
    """

    def __init__(self, message_filter, sorter):
        super().__init__(message_filter, sorter)
        self._messages = []
        self._threads = []
        self._message_formatter = MessageFormatter(self._wrapper, add_channel_name=True)
        self._thread_formatter = ThreadFormatter(self._wrapper, add_channel_name=True)

    def add_channel(self, channel):
        all_messages = channel.all_messages.values()
        if not all_messages:
            return

        self.total_messages += len(all_messages)

        messages = self._filter.filter_messages(all_messages)
        threads = self._filter.filter_threads(all_messages)

        print(self._channel_report_template.format(name=channel.name, messages=len(messages), threads=len(threads),
                                                   total=len(channel.all_messages)))
        self._messages.extend(messages)
        self._threads.extend(threads)
        self.total_channels += 1

    def _write_messages(self):
        with open(self._filename("messages"), 'w') as f:
            self._sorter.sort_messages(self._messages)
            for message in self._messages:
                f.write(self._message_formatter.format(message))
                f.write("\n")

    def _write_threads(self):
        with open(self._filename("threads"), 'w') as f:
            self._sorter.sort_threads(self._threads)
            for message in self._threads:
                f.write(self._thread_formatter.format(message))
                f.write("\n")

    def finalize(self):
        users = {}
        annotate_messages(self._messages, users)
        annotate_messages(self._threads, users)

        self._write_messages()
        self._write_threads()

        if self.total_channels > 1:
            print("\nFound {0} potential messages and {1} long threads across {2} channels and {3} messages".format(
                len(self._messages), len(self._threads), writer.total_channels, writer.total_messages))


def annotate_messages(messages, users):
    for message in messages:
        message.annotate(users)


if __name__ == '__main__':
    options = Options()
    options.store_args()

    print("Looking for messages from {0} to {1}".format(options.start_date.isoformat(), options.end_date.isoformat()))

    api = ApiWrapper(options)

    filter = Filter(options)
    channels = filter.filter_channels(api.get_channels())
    print("Found {0} channels".format(len(channels)))
    if not channels:
        sys.exit()

    writer = ConsolidatedWriter(filter, MessageSorter())
    if options.parsed_args.split_by_channels:
        writer = ChannelWriter(filter, MessageSorter())
    for channel in channels:
        channel.fetch_messages(options.start_timestamp, options.end_timestamp)
        writer.add_channel(channel)
        channel.reset()

    writer.finalize()
