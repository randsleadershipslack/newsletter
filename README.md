# newsletter
Utilities to help collate/organize the rands-leadership-slack newsletter

## Authentication
Most utilities need to have API_TOKEN env variable set for a Slack API token, 
which you can get from https://api.slack.com/docs/oauth-test-tokens

## [Digest](WEEKLY_DIGEST_README.md)

This will search slack for channels and then for messages in each 
channel that have reactions or a large number of threaded responses.
It will put these inside a subdirectory named for today's date, with 
a text file for each channel for which messages were found.

### Default Usage

```bash
> env API_TOKEN=<YOUR_SECRET_API_TOKEN> ./weekly_digest.py --exclude-list ./default_exclude.txt
```

## Setup/Install

Install all required python packages:

```bash
> pip install -r requirements.txt
```
