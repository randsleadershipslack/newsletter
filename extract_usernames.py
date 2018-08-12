#! /usr/bin/env python3

import argparse
from html.parser import HTMLParser
import os
import re
import requests
from slackclient import SlackClient

token = "garbage"
try:
    token = os.environ['API_TOKEN']
except:
    pass

slack = SlackClient(token)


class Options(argparse.ArgumentParser):
    """
    Consolidates the argument handling.
    """

    def __init__(self):
        super().__init__(description='Extract a list of user names from a given post.')
        self.parsed_args = None
        self._blacklist = []

        self.add_argument("post",
                          help="The post to extract the names from")
        self.add_argument("--exclude", nargs='+', metavar="USER",
                          help="Specifically exclude the given user(s)")
        self.add_argument("--exclude-list", metavar="FILE",
                          help="Specifically exclude the user(s) given in the file (one per line)")
#
    def store_args(self):
        self.parsed_args = self.parse_args()
        self._compile_blacklist()

    def _compile_blacklist(self):
        self._add_command_line_exclusions()
        self._exclude_channels_from_file()

    def _add_command_line_exclusions(self):
        if self.parsed_args.exclude:
            for user in self.parsed_args.exclude:
                self._blacklist.append(user)

    def _exclude_channels_from_file(self):
        if self.parsed_args.exclude_list:
            with open(self.parsed_args.exclude_list, 'r') as f:
                for line in f:
                    self._blacklist.append(line.rstrip('\n') )

    def filter_users(self, users):
        filtered = []
        for user in users:
            if user not in self._blacklist:
                filtered.append(user)

        return filtered


class MyParser(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.extract = False
        self.extracted = []
        self.usernames = []

        self.feed(text)
        self._extract_usernames()

    def handle_starttag(self, tag, attrs):
        if tag == "ts-rocket":
            self.extract = True

    def handle_endtag(self, tag):
        if tag == "ts-rocket":
            self.extract = False

    def handle_data(self, data):
        if self.extract:
            if not "edited by" in data:
                self.extracted.append(data)


    def _extract_usernames(self):
        found = []
        matcher = re.compile("(@[a-zA-Z][a-zA-Z.][a-zA-Z]+( [A-Z][a-z]+)?)")
        for line in self.extracted:
            found.extend(re.findall(matcher, line))
        unique = set()
        for full, last in found:
            unique.add(full)

        self.usernames = sorted(unique, key=lambda s: s.casefold())


if __name__ == '__main__':
    options = Options()
    options.store_args()

    post = requests.get(options.parsed_args.post)

    parser = MyParser(post.text)
    for user in options.filter_users(parser.usernames):
        print(user)
