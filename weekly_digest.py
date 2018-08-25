#! /usr/bin/env python3

import argparse
import datetime
from slackclient import SlackClient
import os
import re
import sys
import textwrap

token = "garbage"
try:
    token = os.environ['API_TOKEN']
except:
    pass

slack = SlackClient(token)


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
                          help="The number of replies necessary for retaining a thread in the digest (default: %(default)s)")
        self.add_argument("--exclude", nargs='+', metavar="CHANNEL",
                          help="Specifically exclude the given channel(s) (regular expressions allowed)")
        self.add_argument("--exclude-list", metavar="FILE",
                          help="Specifically exclude the channel(s) given in the file (regular expressions allowed)")

    def store_args(self):
        self.parsed_args = self.parse_args()
        self._extract_dates()
        self._compile_lists()

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
            for channel in self.parsed_args.channel:
                self._whitelist.append(re.compile(channel))

    def _add_command_line_exclusions(self):
        if self.parsed_args.exclude:
            for channel in self.parsed_args.exclude:
                self._blacklist.append(re.compile(channel))

    def _add_channels_from_file(self):
        if self.parsed_args.channel_list:
            with open(self.parsed_args.channel_list, 'r') as f:
                for line in f:
                    for channel in line.split():
                        self._whitelist.append(re.compile(channel))

    def _exclude_channels_from_file(self):
        if self.parsed_args.exclude_list:
            with open(self.parsed_args.exclude_list, 'r') as f:
                for line in f:
                    for channel in line.split():
                        self._blacklist.append(re.compile(channel))

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

    def __init__(self, channel_id, json):
        self.channel_id = channel_id
        self._json = json
        self.replies = []

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
        return self._json['user']

    @property
    def text(self):
        return self._json['text']

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
        if 'reactions' not in self._json:
            return 0
        reaction_count = 0
        for reaction in self._json['reactions']:
            reaction_count += int(reaction['count'])
        return reaction_count

    def __repr__(self):
        return repr(self._json)

    def __str__(self):
        return str(self._json)


class MessageInfo:
    """
    Tracks information about a particular message
    """

    def __init__(self, channel_id, ts=None, message=None):
        self.channel_id = channel_id
        if not (ts or message):
            raise RuntimeError("Must provide either a timestamp or a message")
        self.ts = ts
        self.message = message
        if message:
            self.channel_id = message.channel_id
            self.user = message.user_id
            self.reactions = message.reaction_count
            self.text = message.text
            self.ts = message.timestamp

        time = datetime.datetime.fromtimestamp(float(self.ts))
        time = time.replace(second=0, microsecond=0)
        self.time = time.isoformat(sep=" ")
        self.user_showname = ""
        self.url = ""

    def annotate_user(self, user):
        if user:
            if user.display_name:
                self.user_showname = user.display_name
            else:
                self.user_showname = user.real_name

    def annotate_link(self):
        response = slack.api_call("chat.getPermalink", channel=self.channel_id, message_ts=self.ts)
        if response['ok']:
            self.url = response['permalink']


class Channel:
    """
    Tracks and aggregates information specific to a channel.
    """

    def __init__(self, channel_id, name):
        self.id = channel_id
        self.name = name
        self.messages = []
        self.all_messages = {}

    def reset(self):
        self.messages = []
        self.all_messages = {}

    def fetch_messages(self, start, end, required_reactions, users):
        if required_reactions < 1:
            raise ValueError

        more = True
        start_from = start.timestamp()
        end_at = end.timestamp()
        replies = []
        while more:
            response = slack.api_call("channels.history", channel=self.id, inclusive=False, oldest=start_from,
                                      latest=end_at, count=500)
            if response['ok']:
                more = response['has_more']
                message_list = response['messages']
                for json_msg in message_list:
                    message = Message(channel_id=self.id, json=json_msg)
                    self.all_messages[message.timestamp] = message
                    if message.from_bot:
                        continue
                    try:
                        if Channel._has_enough_reactions(message, required_reactions):
                            self._remember_message(message)
                            Channel._remember_user(message, users)
                        if message.thread_root:
                            replies.append(message)
                        end_at = message.timestamp
                    except:
                        print(message)
                        raise
            else:
                print(response['headers'])
                raise RuntimeError
        for message in replies:
            self._accumulate_thread(message)

    @staticmethod
    def _has_enough_reactions(message, required_reactions):
        return message.reaction_count >= required_reactions

    def _remember_message(self, message):
        self.messages.append(MessageInfo(channel_id=message.channel_id, message=message))

    def _accumulate_thread(self, message):
        default_root = Message(channel_id=message.channel_id, json="")
        self.all_messages.get(message.thread_root, default_root).replies.append(message)

    @staticmethod
    def _remember_user(message, users):
        user = users.get(message.user_id, None)
        if not user:
            user = User(message.user_id)
            users[user.id] = user

    def annotate_messages(self, users):
        for message in self.messages:
            message.annotate_user(users[message.user])
            message.annotate_link()

    def filter_threads(self, required_responses):
        filtered = {}
        for root, message in self.all_messages.items():
            if len(message.replies) >= required_responses:
                info = MessageInfo(channel_id=self.id, message=message)
                filtered[message.timestamp] = info
        return filtered

    def annotate_threads(self, threads):
        for message in threads.values():
            message.annotate_link()


class User:
    """
    Tracks and aggregates information specific to a user.
    """

    def __init__(self, user_id):
        self.id = user_id
        self.real_name = ""
        self.display_name = ""

    def fetch_name(self):
        if not self.real_name and not self.display_name:
            response = slack.api_call("users.info", user=self.id)
            if response['ok']:
                self.real_name = response['user']['profile']['real_name']
                self.display_name = response['user']['profile']['display_name']


def get_channels(options):
    response = slack.api_call("channels.list", exclude_archived=1, exclude_members=1)
    channels = []
    if response["ok"]:
        for channel in response["channels"]:
            name = channel['name']
            channel_id = channel['id']
            if not options.filter_channel(name):
                channels.append(Channel(channel_id=channel_id, name=name))
    return channels


class Writer:
    """
    Writes the message information to file
    """

    def __init__(self):
        self.folder_name = Writer._create_folder()
        self.wrapper = textwrap.TextWrapper(width=80, expand_tabs=False, replace_whitespace=False,
                                            drop_whitespace=False)
        pass

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

    def _filename(self, channel):
        return self.folder_name + "/" + channel.name + ".txt"

    @staticmethod
    def _formatted_header(channel):
        name = "==  {0}  ==".format(channel.name)
        box = "{0}".format("=" * len(name))
        return "{0}\n{1}\n{0}\n\n".format(box, name)

    def _formatted_message(self, message):
        separator = "-" * 80
        return "{0}\n{1}\n@{2} wrote on {3}\n{5} reactions\n{0}\n{4}\n".format(
            separator, message.url, message.user_showname, message.time, self.wrapper.fill(message.text),
            message.reactions)

    def _formatted_thread_message(self, message_info):
        separator = "-" * 80
        return "{0}\n{1}\n@{2} wrote on {3}\n{5} replies\n{0}\n{4}\n".format(
            separator, message_info.url, message_info.user_showname, message_info.time,
            self.wrapper.fill(message_info.text), len(message_info.message.replies))

    def write_channel(self, channel, threads):
        with open(self._filename(channel), 'w') as f:
            f.write(Writer._formatted_header(channel))
            for message in channel.messages:
                f.write(self._formatted_message(message))
                f.write("\n")

            f.write("\n")
            f.write("Threaded messages: {}".format(len(threads)))
            f.write("\n")
            for message in threads.values():
                f.write(self._formatted_thread_message(message))
                f.write("\n")


if __name__ == '__main__':
    options = Options()
    options.store_args()

    print("Looking for messages from {0} to {1}".format(options.start_date.isoformat(), options.end_date.isoformat()))

    users = {}
    channels = get_channels(options)
    print("Found {0} channels".format(len(channels)))
    if not channels:
        sys.exit()

    writer = Writer()
    total_messages = 0
    total_threads = 0
    total_channels = 0
    for channel in channels:
        channel.fetch_messages(options.start_timestamp, options.end_timestamp, options.parsed_args.reactions, users)
        threads = channel.filter_threads(options.parsed_args.reply_threshold)

        if not (channel.messages or threads):
            continue

        for (user_id, user) in users.items():
            user.fetch_name()

        channel.messages.reverse()
        channel.annotate_messages(users)
        channel.annotate_threads(threads)

        writer.write_channel(channel, threads)
        total_messages += len(channel.messages)
        total_threads += len(threads)
        total_channels += 1
        print("\t{0}: {1} potential messages, {2} long threads from {3} total messages".format(channel.name,
                                                                                               len(channel.messages),
                                                                                               len(threads),
                                                                                               len(channel.all_messages)))

    if len(channels) > 1:
        print("\nFound {0} potential messages and {1} long threads across {2} channels".format(
            total_messages, total_threads, total_channels))
