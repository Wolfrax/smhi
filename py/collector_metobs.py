#!/usr/bin/python
#-*- coding: utf-8 -*-

__author__ = 'mm'

# Mats Melander 2020-06-21
# Script for collecting meteorological observations from SMHI open data and store it in GeoJSON format
#

import sys
import requests
import logging
from logging.handlers import RotatingFileHandler
import threading
import os
import datetime
import time
import geojson
from pathlib import Path
import json
from flask import Flask, render_template


app = Flask(__name__)


class SmhiReader(threading.Thread):
    def __init__(self, smhi_inst, key):
        threading.Thread.__init__(self)
        self.key = key
        self.smhi = smhi_inst
        self.result = {}
        self.start()

    def run(self):
        self.result = {'fc': self.smhi.get(self.key), 'resource': self.key}

    def get_data(self):
        return self.result


class Smhi:
    def __init__(self):
        self.url = "http://opendata-download-metobs.smhi.se/api.json"  # Root for SMHI REST API

        try:
            api = requests.get(self.url).json()

            # The "next("... construct is used several times below to keep the code short
            # It is equivalent to:
            # for (index, d) in enumerate(lst["version"]):
            #    if d["key"] == "latest":
            #        i = index

            # ind1 points to the latest version of SMHI api, ind2 to the json-type of the latset api
            ind1 = next(i for (i, d) in enumerate(api["version"]) if d["key"] == "latest")
            ind2 = next(i for (i, d) in enumerate(api["version"][ind1]["link"]) if d["type"] == "application/json")
            self.resources = requests.get(api["version"][ind1]["link"][ind2]["href"]).json()
        except requests.exceptions.RequestException as e:
            logger.error(e)
            sys.exit(1)

        self.keys = []
        for r in self.resources['resource']:
            elem = {'key': "{:02d}".format(int(r['key'])),  # include leading '0' ("1" -> "01")
                    'title': r['title'],
                    'summary': r['summary'],
                    'link': r['link'][0]['href']}
            self.keys.append(elem)

    @staticmethod
    def get(key):
        logger.info("Starting {}".format(key['title'] + " (" + key['summary'] + ")"))
        try:
            # Try to get the indicated resource from the SMHI latest api (setup at initialization)
            stations = requests.get(key['link']).json()
            lst = []
            for i, stn in enumerate(stations["station"]):
                ind1 = next(i for (i, d) in enumerate(stn["link"]) if d["type"] == "application/json")
                lnk = requests.get(stn["link"][ind1]["href"]).json()
                ind2 = next((i for (i, d) in enumerate(lnk["period"]) if d["key"] == "latest-day"), None)
                if ind2 is not None:
                    lnk = lnk["period"][ind2]
                    ind3 = next(i for (i, d) in enumerate(lnk["link"]) if d["type"] == "application/json")
                    lnk = requests.get(lnk["link"][ind3]["href"]).json()
                    ind4 = next(i for (i, d) in enumerate(lnk["link"]) if d["type"] == "application/json")
                    # Note, no key for data, hence always 0
                    lnk = requests.get(lnk["data"][0]["link"][ind4]["href"]).json()
                    if lnk["value"] is not None and stn['active'] is True:
                        try:
                            # NB if we take the last element we get the latest value,
                            # the first element (0) is the oldest, the last is the youngest (in case we have a list)
                            val = float(lnk["value"][-1]["value"])
                        except ValueError:
                            # There is a value that cannot be converted to float (e.g. "regn", store it as text
                            val = lnk["value"][-1]["value"]

                        # avoid duplicates
                        if (stn["longitude"], stn["latitude"]) not in list(geojson.utils.coords(lst)):
                            point = geojson.Point((stn["longitude"], stn["latitude"]))
                            s, ms = divmod(stn["updated"], 1000)
                            ts = '{}.{:03d}'.format(time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(s)), ms)
                            feature = geojson.Feature(geometry=point,
                                                      properties={"key": key["key"],
                                                                  "title": key['title'],
                                                                  "summary": key["summary"],
                                                                  "updated": stn["updated"],
                                                                  "timestamp": ts,
                                                                  "height": stn["height"],
                                                                  "value": val},
                                                      id=stn["name"])
                            if not feature.is_valid:
                                logger.info("Feature not valid: {} - {}".format(stn["name"], feature.errors()))
                            else:
                                lst.append(feature)
                        else:
                            logger.info("{}: found point long: {}, lat: {}".format(key['title'],
                                                                                   stn["longitude"],
                                                                                   stn["latitude"]))
            fc = geojson.FeatureCollection(lst)
            if not fc.is_valid:
                logger.info("Feature Collection not valid: {} - {}".format(key['title'] + " (" + key['summary'] + ")",
                                                                           fc.errors()))
                return None
            else:
                logger.info("Exiting {}, no of stations: {}".format(key['title'], len(lst)))
                return fc

        except (requests.exceptions.RequestException, json.decoder.JSONDecodeError) as e:
            logger.error(e)
            sys.exit(1)


ROOT = "metobs_data/"
INDEX_HTML = "index.html"


def init_row():
    row = {}
    for i in range(1, 13):
        row["{:02d}".format(i)] = {'path': '', 'str': ''}
    return row


def store(lst):
    """
    Create a file "ROOT/2020/06/21/XXX.geojson" and a meta-data file "ROOT/2020/06/21/meta.json"
    meta.json includes a summary and a translation from "3" (key) to "title" and "summary"
    Then create an index.html file, with a list of all geojson-files created
    Also create a top-level index.html to navigate in the directory structure
    Finally create a symbolic link 'latest', pointing at the new directory
    """
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))
    now = datetime.datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")
    path = os.path.join(ROOT, year, month, day)
    Path(path).mkdir(parents=True, exist_ok=True)

    nr_res = 0  # Keep track of number of resource files generated, written into the meta-data file
    key_translations = {}  # Keep a dictionary of 'key': 'title': 'ABC', 'summary' 'DEF'
    for k, v in lst.items():
        nr_res += 1
        key_translations[k] = {'resource': v['resource']}
        title = v['resource']['title'].replace(" ", "_").replace(",", "").replace("/", "_per_")
        summary = v['resource']['summary'].replace(" ", "_").replace(",", "").replace("/", "_per_")
        res_name = os.path.join(path, k + "_" + title + "__" + summary + ".geojson")
        with open(res_name, encoding='utf-8', mode='w') as outfile:
            geojson.dump(fp=outfile, obj=v['fc'], ensure_ascii=False)
            outfile.close()

    meta_name = os.path.join(path, "meta.json")
    with open(meta_name, encoding='utf-8', mode='w') as outfile:
        json.dump(fp=outfile,
                  obj={"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "resources": str(nr_res),
                       "translations": key_translations},
                  ensure_ascii=False)
        outfile.close()

    # Now generate index.html in each directory, this is a HTML list of geojson-files generated
    index_name = os.path.join(path, INDEX_HTML)
    with app.app_context():
        files = [name for name in os.listdir(path) if os.path.isfile(os.path.join(path, name))]
        geojson_files = sorted([name for name in files if name.endswith(".geojson")])
        index_file = render_template('geojson_index.html',
                                     title=path[len(ROOT):].replace("/", "-"),
                                     files=geojson_files)
        with open(index_name, encoding='utf-8', mode='w') as outfile:
            outfile.write(index_file)

        table = {}
        # Look recursively for index.html files from ROOT and downwards
        for path in Path(ROOT).rglob(INDEX_HTML):
            # Avoid ROOT/index.html file, only those in sub-directories is valid
            if os.path.join(ROOT, INDEX_HTML) != str(path):
                parent_path = str(path.parent)[len(ROOT):]  # Skip ROOT from parent_path

                # First get the components from parent_path; 2020/06/23
                table_year = parent_path.split(os.path.sep)[0]   # 2020
                table_month = parent_path.split(os.path.sep)[1]  # 06
                table_day = parent_path.split(os.path.sep)[2]    # 23

                # result2 = {'2020': {'23': {'01': {'path': "", 'str': ""},
                #                            '02': {'path': "", 'str': ""},
                #                             ...
                #                            '06': {'path': "2020/06/23", 'str': "23"},
                #                            '07': {'path': "", 'str': ""},
                #                             ...
                #                            '12': {'path': "", 'str: ""}
                #                    }
                #           }
                if table_year not in table:
                    day_row = init_row()
                    day_row[table_month] = {'path': str(parent_path), 'str': table_day}
                    table[table_year] = {table_day: day_row}
                else:
                    if table_day not in table[table_year]:
                        # day_row = init_row()
                        table[table_year][table_day] = init_row()

                    table[table_year][table_day][table_month] = {'path': str(parent_path), 'str': table_day}
                    # day_row[table_month] = {'path': str(parent_path), 'str': table_day}
                    # table[table_year][table_day] = day_row

        root_index_file = render_template('geojson_root_index.html', files=table)
        with open(os.path.join(ROOT, INDEX_HTML), encoding='utf-8', mode='w') as outfile:
            outfile.write(root_index_file)

        # Create a symbolic link to the latest generated directory in the ROOT directory
        latest_path = os.path.join(year, month, day)
        try:
            os.symlink(latest_path, os.path.join(ROOT, 'latest'))
        except FileExistsError:
            os.remove(os.path.join(ROOT, 'latest'))
            os.symlink(latest_path, os.path.join(ROOT, 'latest'))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('requests').setLevel(logging.WARNING)  # Turn off annoying logging info messages
    logging.getLogger("urllib3").setLevel(logging.WARNING)   # Turn off annoying logging info messages
    logger = logging.getLogger('collector')

    fh = RotatingFileHandler('collector.log', mode='a', maxBytes=100 * 1024 * 1024, backupCount=2)
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info("Start")
    smhi = Smhi()  # One instance, will populate "keys" at initialization

    threads = []
    for k in smhi.keys:
        threads.append(SmhiReader(smhi, k))  # Will start a thread for this key (resource)

    for t in threads:
        t.join()  # Wait for all reading threads to terminate

    weather_data = {}
    ind = 0
    for k in smhi.keys:
        result = threads[ind].get_data()
        if result:  # Could be None if there has been an error
            weather_data[k['key']] = threads[ind].get_data()
        ind += 1

    store(weather_data)
    logger.info("Done")
