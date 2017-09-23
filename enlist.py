#!/usr/bin/env python

import argparse, json, logging, os, requests, sys, time
from ConfigParser import SafeConfigParser
import twitter

class Connection(object):
    def __init__(self, args):
        self.args = args
        # read in environment variables for config file and section
        self.vars = (('TWITTER_CONFIG_FILE', 'cfg_path', os.path.join(os.environ['HOME'], '.twitter')),
                    ('TWITTER_CONFIG_PROFILE', 'cfg_section', 'DEFAULT'))

        for (env_name, var_name, default) in self.vars:
            if os.environ.has_key(env_name):
                setattr(self, var_name, os.environ[env_name])
            else:
                setattr(self, var_name, default)

        # Read in values from your dotfile
        parser = SafeConfigParser()
        if parser.read(self.cfg_path):
            for (name, value) in parser.items(self.cfg_section):
                setattr(self, name, value)

        self.api = twitter.Api(sleep_on_rate_limit=True,
                          consumer_key=self.consumer_key,
                          consumer_secret=self.consumer_secret,
                          access_token_key=self.access_token_key,
                          access_token_secret=self.access_token_secret)

        self.api.InitializeRateLimit()


    def addFollowers(self, user, slug, next=-1, count=250):
        if self.api.rate_limit.resources['followers']['/followers/list'].get('remaining', 15) == 0:
            sys.stderr.write('out of rate limit credits, bailing\n')
            print "+++ returning next is %s" % next
            return next

        (next, prev, follow) = self.api.GetFollowersPaged(cursor=next,
                                                        count=count,
                                                        skip_status=True,
                                                        user_id=user.id,
                                                        include_user_entities=False)

        if self.args.verbose: sys.stderr.write("next: %s, requested %s, got %s\n" % (next, count, len(follow)))
        for f in follow:
            self.block(f)
            
        if next:
            self.addFollowers(user, slug, next=next, count=count)

        else:
            if self.args.verbose: sys.stderr.write("finally adding %s\n" % user.screen_name)
            self.block(user)
            return -1


    def getListMembers(self, slug):
        try:
            return self.api.GetListMembers(slug=slug, owner_screen_name=self.screen_name)
        except twitter.error.TwitterError, e:
            sys.stderr.write("error: %s\n" % e)
            return []
        except requests.exceptions.SSLError, e:
            sys.stderr.write("ssl error: %s\n" % e)
            return []


    def block(self, user):
        if user.following:
            sys.stderr.write("tried to block a friend: %s\n" % user.screen_name)
        else:
            try:
                self.api.CreateBlock(user_id=user.id, include_entities=False, skip_status=True)
                if self.args.verbose: sys.stderr.write("blocked: %s\n" % user.screen_name)
            except twitter.error.TwitterError, e:
                sys.stderr.write("exception: %s\n" % e)
            except requests.exceptions.SSLError, e:
                sys.stderr.write("ssl error: %s\n" % e)


    def limits(self):
        l = dict()
        self.api.InitializeRateLimit()
        resources = self.api.rate_limit.resources.copy()
        for res in resources:
            for ep in  resources[res]:
                if resources[res][ep]['remaining'] < resources[res][ep]['limit']:
                    l[ep] = resources[res][ep]
                    l[ep]['reset'] = max(int(l[ep]['reset'] - time.time()), 0)
        return l

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sleep', type=int, default=30, help='interval to poll lists on')
    parser.add_argument('--chuds-list', type=str, default='chuds', help='name of list of users to block')
    parser.add_argument('--megachuds-list', type=str, default='megachuds', help='name of list of users to block, along with followers')
    parser.add_argument('--verbose', action='store_true', default=True, help='enable debugging output')
    args = parser.parse_args()


    conn = Connection(args)

    # initialization
    lists = conn.api.GetLists()
    for i in [ args.chuds_list, args.megachuds_list ]:
        if i not in [ l.slug for l in lists ]:
            conn.api.CreateList(i, mode='private')
            stderr.write("created list: %s\n" % i)

    # main loop
    next = -1
    while True:
        if next == -1:
            megachuds = conn.getListMembers(slug=args.megachuds_list)
            if megachuds:
                megachud = megachuds[0] # pop first from list
            if args.verbose:
                sys.stderr.write("adding megachud %s\n" % megachud.screen_name)
        else:
            if args.verbose:
                sys.stderr.write("continuing megachud %s\n" % megachud.screen_name)

        try:
            print "+++ next was %s" % next
            next = conn.addFollowers(megachud, args.chuds_list, next=next)
            print "+++ got next is %s" % next
        except twitter.error.TwitterError, e:
            # 'not authorized' error listing followers..
            conn.block(megachud)

        chuds = conn.getListMembers(slug=args.chuds_list)
        for chud in chuds:
            conn.block(chud)

        if args.verbose:
            megachuds = conn.getListMembers(slug=args.megachuds_list)
            chuds = conn.getListMembers(slug=args.chuds_list)

            sys.stderr.write('bottom of the loop\n')
            sys.stderr.write("chuds: %s megachuds: %s\n" % (len(chuds), len(megachuds)))
            sys.stderr.write("%s\n\n" % json.dumps(conn.limits(), indent=2))
        time.sleep(args.sleep)
