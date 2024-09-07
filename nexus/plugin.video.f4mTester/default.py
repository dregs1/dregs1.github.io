
# -*- coding: utf-8 -*-
from lib.helper import *
from lib.addon import run
from sys import argv

if __name__ == '__main__':
    try:
        params = dict(parse_qsl(argv[2].replace('?', '')))
    except:
        params = {}
        
    run(params)




