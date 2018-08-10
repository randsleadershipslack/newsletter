# newsletter
Utilities to help collate/organize the rands-leadership-slack newsletter

## Digest
You'll need to have API_TOKEN env variable set for a Slack API token, 
which you can get from https://api.slack.com/docs/oauth-test-tokens

### Default Usage

```bash
> env API_TOKEN=<YOUR_SECRET_API_TOKEN> ./weekly_digest.py
```

This will search slack for channels and then for messages in each 
channel that have reactions.  It will put these inside a subdirectory 
named for today's date, with a text file for each channel for which 
messages were found.

### Options

```bash
> ./weekly_digest.py --help

  -h, --help            show this help message and exit

  --week [WEEK]         Fetch messages from n weeks ago (default: 1)

  --start START         Fetch messages from the given date (format YYYY-MM-
                        DD). Overrides week start.

  --end END             Fetch messages up to the given date (format YYYY-MM-
                        DD) Overrides week end.

  --channel[s] CHANNEL [CHANNEL ...]
                        Only examine the given channel(s) (Regular expressions
                        allowed)

  --reactions REACTIONS
                        The number of reactions necessary for retaining in
                        digest (default: 3)

  --exclude EXCLUDE [EXCLUDE ...]
                        Specifically exclude the given channel(s) (Regular
                        expressions allowed)

```

### Setup/Install

Install all required python packages:

```bash
> pip install -r requirements.txt
```
