#! /usr/bin/env python3

import argparse
# import datetime
from slackclient import SlackClient
import os
# import re
# import sys
# import textwrap

token = "garbage"
try:
    token = os.environ['API_TOKEN']
except:
    pass

slack = SlackClient(token)


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


if __name__ == '__main__':
    options = Options()
    options.store_args()

    print(options.usernames)

