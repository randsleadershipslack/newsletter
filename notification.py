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

    def store_args(self):
        self.parsed_args = self.parse_args()
        self._compile_lists()
        if not self.usernames:
            self.error("At least one user or user-file is required.")

    def _compile_lists(self):
        self._add_command_line_users()

    def _add_command_line_users(self):
        if self.parsed_args.users:
            self.usernames.extend(self.parsed_args.users)


if __name__ == '__main__':
    options = Options()
    options.store_args()

    print(options.usernames)

