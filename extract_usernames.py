#! /usr/bin/env python3

import argparse
# import datetime
from slackclient import SlackClient
import requests
from html.parser import HTMLParser
# import os
import re
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
    Consolidates the argument handling.
    """

    def __init__(self):
        super().__init__(description='Extract a list of user names from a given post.')
        self.parsed_args = None
#         self.start_date = datetime.date.today()
#         self.end_date = datetime.date.today()
#         self.start_timestamp = datetime.datetime.now()
#         self.end_timestamp = datetime.datetime.now()
#         self._whitelist = []
#         self._blacklist = []
#
        self.add_argument("post",
                          help="The post to extract the names from")
#         self.add_argument("--exclude", nargs='+', metavar="CHANNEL",
#                           help="Specifically exclude the given channel(s) (regular expressions allowed)")
#         self.add_argument("--exclude-list", metavar="FILE",
#                           help="Specifically exclude the channel(s) given in the file (regular expressions allowed)")
#
    def store_args(self):
        self.parsed_args = self.parse_args()
#         self._extract_dates()
#         self._compile_lists()
#
#
# class User:
#     """
#     Tracks and aggregates information specific to a user.
#     """
#
#     def __init__(self, user_id):
#         self.id = user_id
#         self.real_name = ""
#         self.display_name = ""
#
#     def fetch_name(self):
#         if not self.real_name and not self.display_name:
#             response = slack.api_call("users.info", user=self.id)
#             if response['ok']:
#                 self.real_name = response['user']['profile']['real_name']
#                 self.display_name = response['user']['profile']['display_name']


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
            self.extracted.append(data)

    def _extract_usernames(self):
        found = []
        matcher = re.compile("(@[a-zA-Z.]+( [A-Z][a-z]+)?)")
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
    for user in parser.usernames:
        print(user)
