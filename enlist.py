#!/usr/bin/env python

import json, logging, logging.handlers, os, requests, sys, time
from argparse import ArgumentParser
from ConfigParser import SafeConfigParser
import twitter


class Connection(object):
    def __init__(self, args):
        self.args = args

        # Read in environment variables for config file and section
        self.vars = (('TWITTER_CONFIG_FILE',
                      'cfg_path', os.path.join(os.environ['HOME'], '.twitter')),
                    ('TWITTER_CONFIG_PROFILE', 'cfg_section', 'DEFAULT'),
                    ('ENLIST_STATEFILE',
                     'statefile', os.path.join(os.environ['HOME'], '.enlist.json')))

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
            logging.warn("reading statefile %s" % self.statefile)
            try:
                self.state = json.load(open(self.statefile, 'r'))
            except:
                logging.exception("can't read statefile!")
                self.state = self.initState()

            if self.state.get('exc_type', None):
                logging.error("recovered from an %s exception: %s"
                                % (self.state.get('exc_type'), self.state.get('exc_value')))
                self.state['exc_type'], self.state['exc_value'] = (None, None)
        else:
            self.state = self.initState()

        # Create api cxn to twitter
        self.api = twitter.Api(sleep_on_rate_limit=True,
                               consumer_key=self.consumer_key,
                               consumer_secret=self.consumer_secret,
                               access_token_key=self.access_token_key,
                               access_token_secret=self.access_token_secret)

        self.api.InitializeRateLimit()

        if not self.state.get('blocked') or self.args.rebuild_blocks and not self.args.skip_blocks:
            logging.warn("building list of blocked accounts.")
            logging.warn("this takes a while but only happens once")
            self.getBlocks()
            logging.warn("done!")

        lists = self.api.GetLists()
        for name in [ self.args.chuds_list, self.args.megachuds_list ]:
            if name not in [ l.slug for l in lists ]:
                self.api.CreateList(name, mode='private')
                logging.warn("created list: %s" % name)

        self.poll_lists()
        return self


    def __exit__(self, exc_type, exc_value, traceback):
        self.state['exc_type'] = exc_type
        self.state['exc_value'] = exc_value
        logging.warn("writing statefile %s" % self.statefile)
        try:
            json.dump(self.state, open(self.statefile, 'w'))
        except:
            logging.exception("can't write statefile!")


    def initState(self):
        state = dict()
        state['megachud'] = None
        state['already_blocked'] = 0
        state['cursor'] = -1
        state['blocked'] = []
        state['exc_type'], state['exc_value'] = (None, None)

        return state


    def getBlocks(self):
        next_cursor = -1
        while next_cursor != 0:
            try:
                (next_cursor, prev_cursor, blocks) = self.api.GetBlocksIDsPaged(cursor=next_cursor)
            except:
                logging.exception("error reading blocks")
            logging.warn("cursor: %s got %s blocks - %s total" % (next_cursor, len(blocks), len(self.state['blocked'])))

            for b in blocks:
                if b not in self.state.get('blocked'):
                    self.state['blocked'].append(b)
                else:
                    logging.debug("already seen: id %s" % b)


    def addFollowers(self, user, count=200):
        try:
            (self.state['cursor'], prev,
             follow) = self.api.GetFollowersPaged(cursor=self.state.get('cursor'),
                                                  count=count,
                                                  skip_status=True,
                                                  user_id=user.id,
                                                  include_user_entities=False)

        except twitter.error.TwitterError:
            follow = list()
            self.state['cursor'] = 0
            logging.exception("error listing %s" % user.screen_name)

        logging.warn("cursor: %s, requested %s, got %s"
                        % (self.state.get('cursor'), count, len(follow)))

        for u in follow:
            self.block(u)

        if self.state.get('cursor') == 0:
            logging.warn("finally blocking megachud %s" % user.screen_name)
            self.del_megachud(user)
            self.block(user, force=True)
            self.state['megachud'] = None
            self.state['already_blocked'] = 0
            self.state['cursor'] = -1


    def getListMembers(self, slug):
        try:
            return self.api.GetListMembers(slug=slug,
                                           owner_screen_name=self.screen_name)
        except twitter.error.TwitterError:
            logging.exception("twitter exception")
            return []
        except requests.exceptions.RequestException:
            logging.exception("requests exception")
            return []


    def block(self, user, force=False):
        self.state['already_blocked'] += 1
        if user.following:
            logging.warn("tried to block a friend: %s" % user.screen_name)
        elif user.id in self.state.get('blocked') and not force:
            logging.info("already blocked: %s" % user.screen_name)
        elif self.check_megachud(user):
            logging.warn("user is future megachud: %s" % user.screen_name)
        else:
            try:
                self.api.CreateBlock(user_id=user.id,
                                     include_entities=False, skip_status=True)
                self.state['blocked'].append(user.id)
                logging.info("user blocked: %s" % user.screen_name)
            except twitter.error.TwitterError:
                logging.exception("twitter exception")
            except requests.exceptions.RequestException:
                logging.exception("requests exception")


    def get_limit(self, resource='followers', ep='/followers/list'):
        res = self.api.rate_limit.resources.get(resource, {})
        status = res.get(ep, {})
        if not status: logging.error("oops, got empty limit status")
        status.setdefault('reset', int(time.time() + 900))
        status.setdefault('limit', 15)
        status.setdefault('remaining', 15)
        return status


    def wait_limit(self, resource='followers', ep='/followers/list'):
        status = self.get_limit(resource=resource, ep=ep)

        if status.get('remaining', 15) > 0:
            runtime_left = status.get('reset') - int(time.time())
            delay = runtime_left / status.get('remaining')
        else:
            logging.error("OOPS: 0 remaining!")
            delay = status.get('reset') - int(time.time())

        logging.warn("sleeping for %s seconds" % delay)
        self.watch_sleep(delay)
        return True


    def watch_sleep(self, t):
        t = int(t)
        if self.args.verbose: sys.stderr.write('waiting..')
        while t > 0:
            if self.args.verbose:
                if t % 10 == 0: sys.stderr.write("%s" % t)
                if t % 2 == 0: sys.stderr.write('.')
            time.sleep(1)
            t -= 1
        if self.args.verbose: sys.stderr.write('0\n')


    def block_chuds(self):
        for chud in self.chuds:
            self.block(chud)


    def block_megachuds(self):
        if self.state.get('megachud') and self.wait_limit():
            user_id = self.state.get('megachud')
            user = self.api.GetUser(user_id=user_id)
            self.addFollowers(user)


    def poll_lists(self):
        self.megachuds = self.getListMembers(slug=self.args.megachuds_list)
        self.chuds = self.getListMembers(slug=self.args.chuds_list)
        if not self.state.get('megachud'):
            if self.megachuds:
                self.state['megachud'] = self.megachuds.pop().id

        logging.warn("chuds: %s megachuds: %s total blocks: %s"
                        % (len(self.chuds),
                           len(self.megachuds),
                           len(self.state.get('blocked'))))


    def check_megachud(self, user):
        return user.id in [ u.id for u in self.megachuds ]


    def del_megachud(self, user):
        for u in self.megachuds:
            if user.id == u.id: self.megachuds.remove(u)


def setup_logging(args):
    if args.verbose:
        level = logging.INFO
    else:
        level = logging.WARN
    logging.basicConfig(level=level, format='%(message)s')
    logger = logging.getLogger()
    logger.addHandler(logging.handlers.SysLogHandler(facility=logging.handlers.SysLogHandler.LOG_LOCAL3))



if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--sleep', type=int, default=30,
                        help='interval to poll lists on')
    parser.add_argument('--chuds-list', type=str, default='chuds',
                        help='name of list of users to block')
    parser.add_argument('--megachuds-list', type=str, default='megachuds',
                        help='name of list of users to block, with followers')
    parser.add_argument('--rebuild-blocks', action='store_true', default=False,
                        help='rebuild internal list of blocked accts')
    parser.add_argument('--skip-blocks', action='store_true', default=False,
                        help='skip building internal list of blocked accts')
    parser.add_argument('--verbose', action='store_true', default=False,
                        help='enable debugging output')
    args = parser.parse_args()

    setup_logging(args)

    with Connection(args) as conn:
        while True:
            conn.block_chuds()
            conn.block_megachuds()
            conn.poll_lists()

            if conn.state.get('megachud'):
                megachud = conn.api.GetUser(user_id=conn.state.get('megachud'))
                logging.warn("continuing on %s (%s/%s)..."
                                % (megachud.screen_name,
                                   conn.state.get('already_blocked'),
                                   megachud.followers_count))
            else:
                logging.warn("no megachuds in list. sleeping for %s seconds"
                                % args.sleep)
                conn.watch_sleep(args.sleep)
