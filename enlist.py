#!/usr/bin/env python

import json, logging, os, requests, time
from argparse import ArgumentParser
from ConfigParser import SafeConfigParser
import twitter

class Connection(object):
    def __init__(self, args):
        self.args = args
        self.megachud = None
        self.cursor = -1

        # Read in environment variables for config file and section
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

        # Create api cxn to twitter
        self.api = twitter.Api(sleep_on_rate_limit=True,
                          consumer_key=self.consumer_key,
                          consumer_secret=self.consumer_secret,
                          access_token_key=self.access_token_key,
                          access_token_secret=self.access_token_secret)

        self.api.InitializeRateLimit()


    def addFollowers(self, user, slug, count=200):
        try:
            (self.cursor, prev, follow) = self.api.GetFollowersPaged(cursor=self.cursor,
                                                                count=count,
                                                                skip_status=True,
                                                                user_id=user.id,
                                                                include_user_entities=False)

            logging.info("cursor: %s, requested %s, got %s" % (self.cursor, count, len(follow)))

            for f in follow:
                self.block(f)
            
            if self.cursor == 0:
                logging.info("finally adding %s" % user.screen_name)
                self.block(user)
                self.megachud = None
                self.cursor = -1

        except twitter.error.TwitterError:
            logging.exception("error listing %s" % user.screen_name)
          # self.block(user)
          # self.megachud = None
          # self.cursor = -1


    def getListMembers(self, slug):
        try:
            return self.api.GetListMembers(slug=slug, owner_screen_name=self.screen_name)
        except twitter.error.TwitterError:
            logging.exception("twitter exception")
            return []
        except requests.exceptions.RequestException:
            logging.exception("requests exception")
            return []


    def block(self, user):
        if user.following:
            logging.warn("tried to block a friend: %s" % user.screen_name)
        else:
            try:
                self.api.CreateBlock(user_id=user.id, include_entities=False, skip_status=True)
                logging.info("blocked: %s" % user.screen_name)
            except twitter.error.TwitterError:
                logging.exception("twitter exception")
            except requests.exceptions.RequestException:
                logging.exception("requests exception")


    def limits(self):
        self.api.InitializeRateLimit()
        resources = self.api.rate_limit.resources.copy()
        l = dict()
        for res in resources:
            for ep in resources[res]:
                if resources[res][ep]['remaining'] < resources[res][ep]['limit']:
                    l[ep] = resources[res][ep]
                    l[ep]['reset'] = max(int(l[ep]['reset'] - time.time()), 0)
        return l


    def check_limit(self, resource='followers', ep='/followers/list'):
        res = self.api.rate_limit.resources.get(resource, {})
        status = res.get(ep, {})
        return status.get('remaining', 15) > 0


    def block_chuds(self):
        chuds = self.getListMembers(slug=args.chuds_list)
        for chud in chuds:
            conn.block(chud)


    def block_megachuds(self):
        if not self.megachud:
            megachuds = conn.getListMembers(slug=args.megachuds_list)
            if megachuds:
                self.megachud = megachuds[0]

        if self.megachud and self.check_limit():
            conn.addFollowers(self.megachud, args.chuds_list)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--sleep', type=int, default=5, help='interval to poll lists on')
    parser.add_argument('--chuds-list', type=str, default='chuds', help='name of list of users to block')
    parser.add_argument('--megachuds-list', type=str, default='megachuds', help='name of list of users to block, along with followers')
    parser.add_argument('--verbose', action='store_true', default=True, help='enable debugging output')
    args = parser.parse_args()

    if args.verbose:
        level = logging.INFO
    else:
        level = logging.WARN
    logging.basicConfig(level=level, format='%(message)s')

    conn = Connection(args)

    lists = conn.api.GetLists()
    for i in [ args.chuds_list, args.megachuds_list ]:
        if i not in [ l.slug for l in lists ]:
            conn.api.CreateList(i, mode='private')
            logging.info("created list: %s" % i)

    # main loop
    while True:
        conn.block_chuds()
        conn.block_megachuds()

        if args.verbose:
            megachuds = conn.getListMembers(slug=args.megachuds_list)
            chuds = conn.getListMembers(slug=args.chuds_list)
            logging.info('bottom of the loop')
            logging.info("chuds: %s megachuds: %s" % (len(chuds), len(megachuds)))
            logging.info("%s\n" % json.dumps(conn.limits(), indent=2))
        time.sleep(args.sleep)
