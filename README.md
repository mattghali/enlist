# enlist
tool to manage twitter blocks via lists


This is a simple script that can quietly run on your computer, or a spare EC2 instance somewhere. It watches lists you maintain in your Twitter account, and blocks users that you add to the lists. Additionally, it can block followers of the users you add too. The entire user interface is two private lists in your Twitter account.

## How it works
Every user added to the `chuds` list gets blocked.

For every user added to the `megachuds` list:
 - All their followers are added to the `chuds` list to be blocked
 - Then they are too!
 
All quietly in the background, while obeying Twitter's API rate limits. 

## Requirements
 - just the `twitter` python library `(pip install twitter)`

## Configuration
You'll need a config file named `.twitter` in your home directory, which looks like this:
```
[DEFAULT]
screen_name: (your screen name)
consumer_key: (your consumer key)
consumer_secret: (your consumer secret)
access_token_key: (your access token key)
access_token_secret: (your access token secret)
```

You can genereate consumer keys and access tokens for your account at https://apps.twitter.com/

## Command line arguments
```
  --sleep SLEEP         interval to poll lists on (default 30)
  --chuds-list CHUDS_LIST
                        name of list of users to block (default 'chuds')
  --megachuds-list MEGACHUDS_LIST
                        name of list of users to block, along with followers (default 'megachuds')
  --verbose             enable debugging output
```

The script will create the lists for you the first time it runs, if they don't exist yet.
