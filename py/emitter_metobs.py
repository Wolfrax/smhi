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
LATEST = "latest_test"


@app.route('/latest/<filename>')
def latest(filename):
    file_path = os.path.join(ROOT, LATEST, escape(filename))
    file_list = sorted(glob.glob(file_path))
    if file_list:
        return os.path.basename(str(file_list[0]))
    else:
        abort(404)
