#! /usr/bin/env python3

import argparse
import datetime
from slackclient import SlackClient
import os
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
        self.whitelist = None
        self.blacklist = None

        self.add_argument("--week", type=int, default=1, const=1, nargs='?',
                          help="Fetch messages from n weeks ago (default: %(default)s)")
        self.add_argument("--start", type=valid_date,
                          help="Fetch messages from the given date (format YYYY-MM-DD).  Overrides week start.")
        self.add_argument("--end", type=valid_date,
                          help="Fetch messages up to the given date (format YYYY-MM-DD)  Overrides week end.")
        self.add_argument("--channel", "--channels", nargs='+',
                          help="Only examine the given channel(s)")
        self.add_argument("--reactions", type=int, default=3,
                          help="The number of reactions necessary for retaining in digest (default: %(default)s)")
        self.add_argument("--exclude", nargs='+',
                          help="Specifically exclude the given channel(s)")

    def store_args(self):
        self.parsed_args = self.parse_args()
        self.extract_dates()
        self.whitelist=options.parsed_args.channel
        self.blacklist=options.parsed_args.exclude

    @staticmethod
    def find_week(week):
        ago = datetime.date.today() - datetime.timedelta(week * 7)
        if ago.weekday() == 6:
            start_date = ago
        else:
            start_date = ago - datetime.timedelta(7 - ((6 - ago.weekday()) % 7))
        end_date = start_date + datetime.timedelta(7)
        return start_date, end_date

    def extract_dates(self):
        # Work in dates to force the beginning of the day
        if self.parsed_args.week:
            self.start_date, self.end_date = self.find_week(self.parsed_args.week)

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

    def filter_channel(self, name):
        if self.whitelist and name in self.whitelist:
            return False
        elif self.blacklist and name in self.blacklist:
            return True
        elif not (self.whitelist or 'zmeta' in name):
            return False
        return True


class Message:
    """
    Tracks information about a particular message
    """

    def __init__(self, channel_id, user_id, text, ts):
        self.channel_id = channel_id
        self.user = user_id
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
                    if self.has_enough_reactions(message, required_reactions):
                        self.remember_message(message)
                        self.remember_user(message, users)
                    end_at = message["ts"]
            else:
                print(response['headers'])
                raise RuntimeError

    @staticmethod
    def has_enough_reactions(message, required_reactions):
        if 'reactions' not in message:
            return False
        reaction_count = 0
        for reaction in message['reactions']:
            reaction_count += int(reaction['count'])
        return reaction_count >= required_reactions

    def remember_message(self, message):
        self.messages.append(Message(self.id, message['user'], message['text'], message['ts']))

    @staticmethod
    def remember_user(message, users):
        user = users.get(message['user'], None)
        if not user:
            user = User(message['user'])
            users[user.id] = user

    def annotate_messages(self, users):
        for message in self.messages:
            message.annotate_user(users[message.user])
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
        self.folder_name = self.create_folder()
        self.wrapper = textwrap.TextWrapper(width=80, expand_tabs=False, replace_whitespace=False,
                                            drop_whitespace=False)
        pass

    @staticmethod
    def create_folder():
        name = datetime.date.today().isoformat()
        try:
            if not os.path.exists(name):
                os.makedirs(name)
        except OSError:
            print('Error: Creating name. ' + name)
            raise
        return name

    def filename(self, channel):
        return self.folder_name + "/" + channel.name + ".txt"

    @staticmethod
    def formatted_header(channel):
        name = "==  {0}  ==".format(channel.name)
        box = "{0}".format("=" * len(name))
        return "{0}\n{1}\n{0}\n\n".format(box, name)

    def formatted_message(self, message):
        separator = "-" * 80
        return "{0}\n{1}\n@{2} wrote on {3}\n{0}\n{4}\n".format(
            separator, message.url, message.user_showname, message.time, self.wrapper.fill(message.text))

    def write_channel(self, channel):
        with open(self.filename(channel), 'w') as f:
            f.write(self.formatted_header(channel))
            for message in channel.messages:
                f.write(self.formatted_message(message))
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
    total_channels = 0
    for channel in channels:
        channel.fetch_messages(options.start_timestamp, options.end_timestamp, options.parsed_args.reactions, users)

        for (user_id, user) in users.items():
            user.fetch_name()

        if not channel.messages:
            continue

        channel.messages.reverse()
        channel.annotate_messages(users)

        writer.write_channel(channel)
        total_messages += len(channel.messages)
        total_channels += 1
        print("\t{1}: {0} potential messages".format(len(channel.messages), channel.name))

    if len(channels) > 1:
        print("\nFound {0} potential messages across {1} channels".format(total_messages, total_channels))
