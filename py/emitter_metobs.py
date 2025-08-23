#!/usr/bin/python
#-*- coding: utf-8 -*-

__author__ = 'mm'

# Mats Melander 2020-06-30
# Script for emitting requests to retrieve meteorological observations as GeoJSON files
#

import os
from flask import Flask, abort
from markupsafe import escape
import glob

app = Flask(__name__)

ROOT = "metobs_data/"
LATEST = "latest"


@app.route('/metobs/<path:subpath>')
def get_file(subpath):
    # There are 2 valid subpaths:
    # 1. "latest/filename"
    # 2. "2020/07/03/filename"

    parts = subpath.split(os.sep)  # No need to escape subpath, this will not be displayed as HTML

    if len(parts) == 2 and parts[0].lower() == LATEST:  # Option 1
        path = os.path.join(ROOT, LATEST)
        #file_path = os.path.join(path, parts[1])
        file_path =  os.path.join(os.path.dirname(os.path.abspath(__file__)), path, parts[1])
    elif len(parts) == 4:  # Option 2
        path = os.path.join(ROOT, parts[0], parts[1], parts[2])
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path, parts[3])
    else:  # Not valid
        path = file_path = ""

    file_list = sorted(glob.glob(file_path)) if file_path else []
    if file_list:
        fn = file_list[0]
        #fn = os.path.join(file_path, os.path.basename(str(file_list[0])))
        if os.path.isdir(fn):
            abort(404)
        else:
            with open(fn) as f:
                res = f.read()
            return res
    else:
        abort(404)


@app.route('/metobs/latest_file/<filename>')
def latest_file(filename):
    file_path = os.path.join(ROOT, LATEST, escape(filename))
    file_list = sorted(glob.glob(file_path))
    if file_list:
        return os.path.basename(str(file_list[0]))
    else:
        abort(404)

if __name__ == "__main__":
    # run with debugging enabled
    app.run(
        host="0.0.0.0",  # accessible from outside (optional, change to "127.0.0.1" if only local)
        port=5000,
        debug=True
    )