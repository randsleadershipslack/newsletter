#! /usr/bin/env python3

import argparse
from slackclient import SlackClient
import os

token = "garbage"
try:
    token = os.environ['API_TOKEN']
except:
    pass

slack = SlackClient(token)

default_message = """:robot_face:I am a bot. Beep-boop:robot_face:"""


class Options(argparse.ArgumentParser):
    """
    Consolidates our argument handling.
    """

    def __init__(self):
        super().__init__(description='Notify a set of users about their potential inclusion in a newsletter.')
        self.parsed_args = None
        self.usernames = []

        self.add_argument("--users", "--user", nargs='+', metavar="USER",
                          help="Notify the given user(s)")
        self.add_argument("--user_list", metavar="FILE",
                          help="Notify the user(s) given in the file (one per line)")
        self.add_argument("--message", metavar="FILE",
                          help="Use the given file's contents as the message to send")
        self.add_argument("--dry", action="store_true",
                          help="Print the message and users, but don't actually send the messages")

    def store_args(self):
        self.parsed_args = self.parse_args()
        self._compile_lists()
        if not self.usernames:
            self.error("At least one user or file of users is required.")
        self._normalize_usernames()

    def _compile_lists(self):
        self._add_command_line_users()
        self._add_users_from_file()

    def _add_command_line_users(self):
        if self.parsed_args.users:
            self.usernames.extend(self.parsed_args.users)

    def _add_users_from_file(self):
        if self.parsed_args.user_list:
            with open(self.parsed_args.user_list, 'r') as f:
                for line in f:
                    self.usernames.append(line.rstrip('\n') )

    def _normalize_usernames(self):
        normalized = set()
        for user in self.usernames:
            if user[0] == '@':
                normalized.add(user)
            else:
                normalized.add('@' + user)
        self.usernames = sorted(normalized, key=lambda s: s.casefold())


class OriginatingUser:
    """
    Information about the originating user.
    """

    def __init__(self):
        response = slack.api_call("users.profile.get")
        if not response['ok']:
            print(response['headers'])
            raise RuntimeError
        profile = response['profile']
        self.username = "@" + profile['display_name_normalized']
        self.firstname = self.username
        if profile['first_name']:
            self.firstname = profile['first_name']


class Message:
    """
    Handle formatting the message to be sent and sending it as appropriate
    """

    def __init__(self):
        pass

    def send(self, from_user, users, dry=False):
        if dry:
            print("-" * 80)
            print(default_message)
            print("-" * 80)
            print("")

        for user in users:
            print("Notifying {}".format(user))
            if not dry:
                slack.api_call("chat.postMessage", channel=user, text=default_message, as_user=from_user)


if __name__ == '__main__':
    options = Options()
    options.store_args()

    from_user = OriginatingUser()

    #TODO: temp
    options.usernames = ["@slackbot"]

    message = Message()
    message.send(from_user, options.usernames, dry=options.parsed_args.dry)
