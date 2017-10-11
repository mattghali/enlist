#!/usr/bin/env python

import json, logging, os, requests, time
from argparse import ArgumentParser
from ConfigParser import SafeConfigParser
import cPickle as pickle
import twitter

class State(object):
    def __init__(self):
        self.megachud = None
        self.cursor = -1
        self.blocked = []

class Connection(object):
    def __init__(self, args):
        self.args = args

        # Read in environment variables for config file and section
        self.vars = (('TWITTER_CONFIG_FILE', 'cfg_path', os.path.join(os.environ['HOME'], '.twitter')),
                    ('TWITTER_CONFIG_PROFILE', 'cfg_section', 'DEFAULT'),
                    ('ENLIST_STATEFILE', 'statefile', os.path.join(os.environ['HOME'], '.enlist')))

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

    def __enter__(self):
        if os.path.exists(self.statefile):
            logging.info("reading statefile %s" % self.statefile)
            self.state = pickle.load(open(self.statefile, 'rb'))
        else:
            self.state = State()

        # Create api cxn to twitter
        self.api = twitter.Api(sleep_on_rate_limit=True,
                          consumer_key=self.consumer_key,
                          consumer_secret=self.consumer_secret,
                          access_token_key=self.access_token_key,
                          access_token_secret=self.access_token_secret)

        self.api.InitializeRateLimit()

        if not self.state.blocked:
            logging.warn("building list of blocked accounts. this takes a while but only happens once")
            self.state.blocked = self.api.GetBlocksIDs()
            logging.warn("done!")

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            logging.info("writing statefile %s" % self.statefile)
            pickle.dump(self.state, open(self.statefile, 'wb'))
        except:
            logging.exception("can't write statefile!")


    def addFollowers(self, user, count=200):
        try:
            (self.state.cursor, prev, follow) = self.api.GetFollowersPaged(cursor=self.state.cursor,
                                                                count=count,
                                                                skip_status=True,
                                                                user_id=user.id,
                                                                include_user_entities=False)

            logging.info("cursor: %s, requested %s, got %s" % (self.state.cursor, count, len(follow)))

            for f in follow:
                self.block(f)
            
            if self.state.cursor == 0:
                logging.info("finally adding %s" % user.screen_name)
                self.block(user)
                self.state.megachud = None
                self.state.cursor = -1

        except twitter.error.TwitterError:
            logging.exception("error listing %s" % user.screen_name)


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
        elif user.id in self.state.blocked:
            logging.info("user already blocked: %s" % user.screen_name)
        else:
            try:
                self.api.CreateBlock(user_id=user.id, include_entities=False, skip_status=True)
                self.state.blocked.append(user.id)
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
            self.block(chud)


    def block_megachuds(self):
        if not self.state.megachud:
            megachuds = self.getListMembers(slug=args.megachuds_list)
            if megachuds:
                self.state.megachud = megachuds[0]

        if self.state.megachud and self.check_limit():
            self.addFollowers(self.state.megachud)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--sleep', type=int, default=30, help='interval to poll lists on')
    parser.add_argument('--chuds-list', type=str, default='chuds', help='name of list of users to block')
    parser.add_argument('--megachuds-list', type=str, default='megachuds', help='name of list of users to block, along with followers')
    parser.add_argument('--verbose', action='store_true', default=False, help='enable debugging output')
    args = parser.parse_args()

    if args.verbose:
        level = logging.INFO
    else:
        level = logging.WARN
    logging.basicConfig(level=level, format='%(message)s')

    with Connection(args) as conn:
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
                logging.info("chuds: %s megachuds: %s" % (len(chuds), len(megachuds)))
                logging.info("%s\n" % json.dumps(conn.limits(), indent=2))

            if not conn.state.megachud: time.sleep(args.sleep)
