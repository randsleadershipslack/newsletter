# Digest
You'll need to have API_TOKEN env variable set for a Slack API token, 
which you can get from https://api.slack.com/docs/oauth-test-tokens

## Default Usage

```bash
> env API_TOKEN=<YOUR_SECRET_API_TOKEN> ./weekly_digest.py
```
or
```bash
> env API_TOKEN=<YOUR_SECRET_API_TOKEN> ./weekly_digest.py --exclude-list ./default_exclude.txt
```

This will search slack for channels and then for messages in each 
channel that have reactions.  It will put these inside a subdirectory 
named for today's date, with a text file for each channel for which 
messages were found.

## Options

```bash
> ./weekly_digest.py --help
Create a digest of reacted-to posts from a given week.

optional arguments:
  -h, --help            show this help message and exit
  --week N              Fetch messages from N weeks ago (default: 1)
  --start YYYY-MM-DD    Fetch messages from the given date. Overrides week
                        start.
  --end YYYY-MM-DD      Fetch messages up to the given date. Overrides week
                        end.
  --channel CHANNEL [CHANNEL ...], --channels CHANNEL [CHANNEL ...]
                        Only examine the given channel(s) (regular expressions
                        allowed)
  --channel-list FILE   Only examine the channel(s) given in the file (regular
                        expressions allowed)
  --reactions THRESHOLD
                        The number of reactions necessary for retaining in the
                        digest (default: 3)
  --threads THRESHOLD   The number of replies necessary for retaining a thread
                        in the digest (default: 10)
  --exclude CHANNEL [CHANNEL ...]
                        Specifically exclude the given channel(s) (regular
                        expressions allowed)
  --exclude-list FILE   Specifically exclude the channel(s) given in the file
                        (regular expressions allowed)
```

## Setup/Install

Install all required python packages:

```bash
> pip install -r requirements.txt
```
