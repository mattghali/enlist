import logging
logging.basicConfig(level=logging.DEBUG)

class error(object):
    def TwitterError(self, e):
        pass

class TLimits(object):
    def __init__(self, limit):
        self.limit = limit
        self.resources = dict()
        self.resources['followers'] = dict()
        self.resources['followers']['/followers/list'] = dict()
        self.resources['followers']['/followers/list']['remaining'] = self.limit
        self.resources['followers']['/followers/list']['limit'] = self.limit
        self.resources['followers']['/followers/list']['reset'] = 0

    def decrement(self):
        self.resources['followers']['/followers/list']['remaining'] -= 1

    def reset(self):
        self.resources['followers']['/followers/list']['remaining'] = self.limit

    def get(self):
        return self.resources['followers']['/followers/list']['remaining']


class TList(object):
    def __init__(self, name, length):
        self.slug = name
        self.length = length
        self.users = [ TUser('User', i) for i in range(self.length) ]


class TUser(object):
    def __init__(self, type, id):
        self.id = id
        self.following = False
        self.screen_name = type + '_' + str(id)



class Api(object):
    def __init__(self, **kwargs):
        logging.debug('Api object created')
        self.rate_limit = TLimits(3)
        self.lists = [ TList('chuds', 0), TList('megachuds', 5) ]
        self.follow_pagesize = 3

    def InitializeRateLimit(self):
        logging.debug("%s called" % 'InitializeRateLimit')
        if self.rate_limit.get() == 0: self.rate_limit.reset()

    def CreateList(self, name, mode='p'):
        logging.warn("tried to create list: %s" % name)

    def GetLists(self):
        logging.debug("%s called" % 'GetLists')
        return self.lists

    def GetListMembers(self, **kwargs):
        logging.debug("%s called" % 'GetListMembers')
        slug = kwargs['slug']
        for l in self.lists:
            if l.slug == slug: return l.users

    def GetFollowersPaged(self, **kwargs):
        logging.debug("%s called" % 'GetFollowersPaged')
        self.rate_limit.decrement()
        cursor = kwargs.get('cursor')
        user_id = kwargs.get('user_id')
        logging.debug("cursor called: %s" % cursor)
        if cursor < 0: cursor == 0
        limit = cursor + self.follow_pagesize
        followers = list()
        while cursor < limit:
            followers.append(TUser('Follower', cursor))
            cursor += 1
        logging.debug("cursor returned: %s" % cursor)
        if cursor > 10: cursor = 0
        return (cursor, 0, followers)

    def CreateBlock(self, **kwargs):
        user_id = kwargs.get('user_id')

