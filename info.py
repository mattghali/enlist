#!/usr/bin/env python
'''
Quick tool to view/clear state of 'enlist'.
With no args, will show current state.
The '--clear' arg clears current megachud. Next run of enlist pulls the next from your list.
'''

from argparse import ArgumentParser
import logging

import enlist
from enlist import State


parser = ArgumentParser(description=__doc__)
parser.add_argument('--clear', action='store_true', default=False,
                    help='clear current megachud')
parser.add_argument('--rebuild-blocks', action='store_true', default=False,
                    help='rebuild internal list of blocked accts')
parser.add_argument('--verbose', action='store_true', default=False,
                    help='enable debugging output')
args = parser.parse_args()

enlist.setup_logging(args)

with enlist.Connection(args) as conn:
    print "current megachud:", conn.state.__dict__.get('megachud.screen_name', None)
    print "blocks:", len(conn.state.blocked)

    if args.clear:
        print 'clearing megachud'
        conn.state.megachud = None
        conn.state.cursor = -1
