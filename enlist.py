#!/usr/bin/env python

import argparse, os, sys, time
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
        self.me = self.api.GetUser(screen_name=self.screen_name)


    def addFollowers(self, user, slug, next=-1, count=200, bulk=False):
        if self.api.rate_limit.resources['followers']['/followers/list'].get('remaining', 15) == 0:
            if self.args.verbose: sys.stderr.write('out of rate limit credits, bailing')
            return next

        (next, prev, follow) = self.api.GetFollowersPaged(cursor=next,
                                                        count=count,
                                                        skip_status=True,
                                                        user_id=user.id,
                                                        include_user_entities=False)
        if bulk:
            # adds 'count' at once, unless something fails
            users = [ u.id for u in follow ]
            if self.args.verbose: sys.stderr.write("adding %s users\n" % len(users))
            self.addToList(slug, users)

        else:
            # adds one precious chud at a time
            for f in follow:
                if self.args.verbose: sys.stderr.write("adding %s\n" % f.screen_name)
                self.addToList(slug, f.id)
            
        if next:
            self.addFollowers(user, slug, next=next, count=count, bulk=bulk)

        else:
            # finally, block megachud himself (which removes him from megachud list)
            if self.args.verbose: sys.stderr.write("finally adding %s\n" % user.screen_name)
            self.addToList(slug, user)

        return -1


    def addToList(self, slug, user):
        try:
            self.api.CreateListsMember(slug=slug, user_id=user,
                                       owner_screen_name=self.screen_name)
        except twitter.error.TwitterError, e:
            if self.args.verbose: sys.stderr.write("error: %s\n" % e)


    def block(self, user):
        try:
            if user.following:
                if self.args.verbose: sys.stderr.write("tried to block a friend: %s\n" % user.screen_name)
            else:
                if self.args.verbose: sys.stderr.write("blocked: %s\n" % user.screen_name)
                self.api.CreateBlock(user_id=user.id, include_entities=False, skip_status=True)
        except Exception, e:
            if self.args.verbose: sys.stderr.write("exception: %s\n" % e)


    def limits(self):
        resources = self.api.rate_limit.resources
        for res in resources:
            for ep in  resources[res]:
                if resources[res][ep]['remaining'] < resources[res][ep]['limit']:
                         return  "%s: %s" % (ep, resources[res][ep])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sleep', type=int, default=30, help='interval to poll lists on')
    parser.add_argument('--chuds-list', type=str, default='chuds', help='name of list of users to block')
    parser.add_argument('--megachuds-list', type=str, default='megachuds', help='name of list of users to block, along with followers')
    parser.add_argument('--verbose', action='store_true', default=False, help='enable debugging output')
    args = parser.parse_args()

    conn = Connection(args)

    # initialization
    lists = conn.api.GetLists()
    for i in [ args.chuds_list, args.megachuds_list ]:
        if i not in [ l.slug for l in lists ]:
            conn.api.CreateList(i, mode='private')
            if args.verbose: sys.stderr.write("created list: %s\n" % i)

    # main loop
    next = -1
    while True:
        megachuds = conn.api.GetListMembers(slug=args.megachuds_list, owner_screen_name=conn.screen_name)
        for megachud in megachuds:
            if args.verbose:
                if next < 0:
                    sys.stderr.write("adding megachud %s\n" % megachud.screen_name)
                else:
                    sys.stderr.write("continuing megachud %s\n" % megachud.screen_name)
            next = conn.addFollowers(megachud, args.chuds_list, next=next, count=100, bulk=True)

        chuds = conn.api.GetListMembers(slug=args.chuds_list, owner_screen_name=conn.screen_name)
        for chud in chuds:
            conn.block(chud)

        if args.verbose: sys.stderr.write('bottom of the loop\n')
        if args.verbose: sys.stderr.write("%s\n" % conn.limits())
        time.sleep(args.sleep)
