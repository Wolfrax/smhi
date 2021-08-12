#!/usr/bin/python
#-*- coding: utf-8 -*-

# Test script for generating a root index2.html page
#

__author__ = 'mm'

import os
from pathlib import Path
from flask import Flask, render_template

ROOT = "metobs_data/"
app = Flask(__name__)


def init_row():
    row = {}
    for i in range(1, 13):
        row["{:02d}".format(i)] = {'path': '', 'str': ''}
    return row


if __name__ == "__main__":
    with app.app_context():
        table = {}
        # Look recursively for index.html files from ROOT and downwards
        for path in Path(ROOT).rglob('index.html'):
            # Avoid ROOT/index.html file, only those in sub-directories is valid
            if os.path.join(ROOT, "index.html") != str(path):
                parent_path = str(path.parent)[len(ROOT):]  # Skip ROOT from parent_path

                # First get the components from parent_path; 2020/06/23
                year = parent_path.split("/")[0]                # 2020
                month = parent_path.split("/")[1]               # 06
                day = parent_path.split("/")[2]                 # 23

                # result2 = {'2020': {'23': {'01': {'path': "", 'str': ""},
                #                            '02': {'path': "", 'str': ""},
                #                             ...
                #                            '06': {'path': "2020/06/23", 'str': "23"},
                #                            '07': {'path': "", 'str': ""},
                #                             ...
                #                            '12': {'path': "", 'str: ""}
                #                    }
                #           }
                if year not in table:
                    day_row = init_row()
                    day_row[month] = {'path': str(parent_path), 'str': day}
                    table[year] = {day: day_row}
                else:
                    if day not in table[year]:
                        day_row = init_row()

                    day_row[month] = {'path': str(parent_path), 'str': day}
                    table[year][day] = day_row

        root_index_file = render_template('geojson_root_index.html', files=table)
        with open(os.path.join(ROOT, "index2.html"), encoding='utf-8', mode='w') as outfile:
            outfile.write(root_index_file)

