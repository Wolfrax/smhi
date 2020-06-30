#!/usr/bin/python
#-*- coding: utf-8 -*-

__author__ = 'mm'

# Call as
# $ python generate_index_html.py data/2020/06/23/ 2020-06-23

import os
import sys
from flask import Flask, render_template

app = Flask(__name__)


def get_files(file_path):
    files = [name for name in os.listdir(file_path) if os.path.isfile(os.path.join(file_path, name))]
    return sorted([name for name in files if name.endswith(".geojson")])


if __name__ == "__main__":
    with app.app_context():
        os.chdir(os.path.abspath(sys.argv[1]))
        path = os.getcwd()
        index_file = render_template('geojson_index.html', title=sys.argv[2], files=get_files(path))
        with open("index.html", encoding='utf-8', mode='w') as outfile:
            outfile.write(index_file)
