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
        self.add_argument("--threads", type=int, default=10, metavar="THRESHOLD",
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

    def __init__(self, json):
        self.json = json

    @property
    def timestamp(self):
        return self.json["ts"]

    def from_bot(self):
        if 'subtype' in self.json and self.json['subtype'] == "bot_message":
            return True
        return False

    def __repr__(self):
        return self.json


class MessageInfo:
    """
    Tracks information about a particular message
    """

    def __init__(self, channel_id, user_id, reactions, text, ts):
        self.channel_id = channel_id
        self.user = user_id
        self.reactions = reactions
        self.text = text
        self.ts = ts
        time = datetime.datetime.fromtimestamp(float(ts))
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

    @staticmethod
    def num_reactions(message):
        if 'reactions' not in message:
            return 0
        reaction_count = 0
        for reaction in message['reactions']:
            reaction_count += int(reaction['count'])
        return reaction_count


class Channel:
    """
    Tracks and aggregates information specific to a channel.
    """

    def __init__(self, channel_id, name):
        self.id = channel_id
        self.name = name
        self.messages = []

    def fetch_messages(self, start, end, required_reactions, users):
        if required_reactions < 1:
            raise ValueError

        self.messages = []
        self.threads = {}
        more = True
        start_from = start.timestamp()
        end_at = end.timestamp()
        while more:
            response = slack.api_call("channels.history", channel=self.id, inclusive=False, oldest=start_from,
                                      latest=end_at, count=500)
            if response['ok']:
                more = response['has_more']
                message_list = response['messages']
                for message in message_list:
                    msg = Message(message)
                    if msg.from_bot():
                        continue
                    try:
                        if Channel._has_enough_reactions(msg, required_reactions):
                            self._remember_message(msg)
                            Channel._remember_user(msg, users)
                        self._accumulate_thread(msg)
                        end_at = msg.timestamp
                    except:
                        print(msg)
                        raise
            else:
                print(response['headers'])
                raise RuntimeError

    @staticmethod
    def _has_enough_reactions(msg, required_reactions):
        return MessageInfo.num_reactions(msg.json) >= required_reactions

    def _remember_message(self, msg):
        self.messages.append(MessageInfo(channel_id=self.id, user_id=msg.json['user'],
                                         reactions=MessageInfo.num_reactions(msg.json), text=msg.json['text'],
                                         ts=msg.timestamp))

    def _accumulate_thread(self, msg):
        root = msg.json.get("thread_ts")
        if root and root != msg.timestamp:
            self.threads[root] = self.threads.get(root, 0) + 1

    @staticmethod
    def _remember_user(msg, users):
        user = users.get(msg.json['user'], None)
        if not user:
            user = User(msg.json['user'])
            users[user.id] = user

    def annotate_messages(self, users):
        for message in self.messages:
            message.annotate_user(users[message.user])
            message.annotate_link()

    def filter_threads(self, required_responses):
        filtered = {}
        for root, count in self.threads.items():
            if count >= required_responses:
                message = MessageInfo(channel_id=self.id, user_id=None, reactions=None, text=None, ts=root)
                filtered[message] = count
        self.threads = filtered

    def annotate_threads(self):
        for root in self.threads.keys():
            root.annotate_link()


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

    def _formatted_thread(self, thread_root, count):
        separator = "-" * 80
        return "{0}\n{1} replies: {2}\n".format(separator, count, thread_root.url)

    def write_channel(self, channel):
        with open(self._filename(channel), 'w') as f:
            f.write(Writer._formatted_header(channel))
            for message in channel.messages:
                f.write(self._formatted_message(message))
                f.write("\n")

            f.write("\n")
            f.write("Threaded messages: {}".format(len(channel.threads)))
            f.write("\n")
            for thread_root, count in channel.threads.items():
                f.write(self._formatted_thread(thread_root, count))
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
        channel.filter_threads(options.parsed_args.threads)

        if not (channel.messages or channel.threads):
            continue

        for (user_id, user) in users.items():
            user.fetch_name()

        channel.messages.reverse()
        channel.annotate_messages(users)
        channel.annotate_threads()

        writer.write_channel(channel)
        total_messages += len(channel.messages)
        total_threads += len(channel.threads)
        total_channels += 1
        print("\t{0}: {1} potential messages, {2} long threads".format(channel.name, len(channel.messages),
                                                                       len(channel.threads)))

    if len(channels) > 1:
        print("\nFound {0} potential messages and {1} long threads across {2} channels".format(
            total_messages, total_threads, total_channels))
