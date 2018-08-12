# Usernames

## Default Usage

```bash
> env API_TOKEN=<YOUR_SECRET_API_TOKEN> ./weekly_digest.py --exclude-list ./default_exclude.txt
```

This will download a given post (via it's _publicly available_ url)
and scan it for usernames mentioned in the post, printing a sorted
list of those usernames.

You may also want to exclude your own username.

## Options

```bash
> ./extract_usernames.py --help
Extract a list of user names from a given post.

positional arguments:
  post                  The post to extract the names from

optional arguments:
  -h, --help            show this help message and exit
  --exclude USER [USER ...]
                        Specifically exclude the given user(s)
  --exclude-list FILE   Specifically exclude the user(s) given in the file
                        (one per line)
```

## Setup/Install

Install all required python packages:

```bash
> pip install -r requirements.txt
```
