# -*- coding: utf-8 -*-
"""Service entry point"""

#from __future__ import absolute_import, division, unicode_literals
from lib.loggers import Logger
if __name__ == '__main__':
    from lib.service import run

    run()
