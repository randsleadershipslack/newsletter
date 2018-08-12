# Notification
You'll need to have API_TOKEN env variable set for a Slack API token, 
which you can get from https://api.slack.com/docs/oauth-test-tokens

## Default Usage

This tool is a bit more complicated, and I recommend a dry run at least
once prior to using it live.

The simplest way to use this is to put the users in a file, one per 
line, and pass that file to the script along with the URL and deadline
for responses.  The default shown below is also marked to do a dry run
(not actually notify anyone).

```bash
> env API_TOKEN=<YOUR_SECRET_API_TOKEN> ./notification.py --url https://slack-files.com/T04T4TH8W-FC8263BF1-c513d92bbb --deadline "Monday 9 AM Pacific" --user_list ./users.txt --dry
```

This will format a message as if from a robot, letting them know about 
potential newsletter inclusion and how to allow (or reject) the
inclusion.

## Example Message
> :robot_face:I am a bot, posting on behalf of Caleb. Beep-boop:robot_face:

> We’re presently preparing to publish a newsletter for this slack, and
some of the content you authored or participated or were named in has
been selected for potential inclusion.  While all the content is
public in channel history, we’re attempting to make the collation
process opt-in.

> The current draft is at https://slack-files.com/T04T4TH8W-FC8263BF1-c513d92bbb

> We would like you to agree to the inclusion of your content.  Ideally,
you’d provide blanket inclusion approval, but if you’d like to have
finer control, or even blanket exclusion, that’s perfectly acceptable
as well.

> **If you don’t specifically approve your mentions/content by Monday 9 AM Pacific, we will exclude it**.

> Caleb will see your response to this message, which can be as
short as “Ok” (just this newsletter), “Ok - always”, “No”, and
“No - always” (or :thumbsup:/:thumbsdown:).

> If you have questions, please either reply here, or in #rands-newsletter if
they’re more general.

> Thanks for being an active part of the community, and we look forward
to hearing from you soon.

> :robot_face:Beep-boop. Bot out:robot_face:


## Options

```bash
> ./notification.py --help
Notify a set of users about their potential inclusion in a newsletter.

optional arguments:
  -h, --help            show this help message and exit
  --users USER [USER ...], --user USER [USER ...]
                        Notify the given user(s). Must provide users either on
                        the command line or via file
  --user_list FILE      Notify the user(s) given in the file (one per line).
                        Must provide users either on the command line or via
                        file
  --url URL             Use the given *public* url in the message. Must
                        include either url/deadline OR a message file
  --deadline DATE       Use the given deadline for responses in the message
                        (pass in quotes, as in 'Monday 9 AM Pacific'). Must
                        include either url/deadline OR a message file
  --message FILE        Use the given file's contents as the message to send.
                        Must include either url/deadline OR a message file
  --dry                 Print the message and users, but don't actually send
                        the messages

```

## Setup/Install

Install all required python packages:

```bash
> pip install -r requirements.txt
```