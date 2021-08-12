#!/usr/bin/python
#-*- coding: utf-8 -*-

import json
import sys


def dump(fn):
    with open(fn, mode='r') as handle:
        parsed = json.load(handle)
    print(json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False))

if __name__ == "__main__":
    print("Filename needed") if len(sys.argv) < 2 else dump(sys.argv[1])
