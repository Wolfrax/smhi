#!/usr/bin/python

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


class SmhiReader(threading.Thread):
    def __init__(self, smhi_inst, key):
        threading.Thread.__init__(self)
        self.key = key
        self.smhi = smhi_inst
        self.result = []
        self.start()

    def run(self):
        self.result = self.smhi.get(self.key)

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
            elem = {'key': r['key'],
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
                    try:
                        # Note, no key for data, hence always 0
                        lnk = requests.get(lnk["data"][0]["link"][ind4]["href"]).json()
                    except requests.exceptions.RequestException as e:
                        logger.info("{} - {}".format(stn["name"], e))
                    else:
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
                                                          properties={"title": key['title'],
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
        except requests.exceptions.RequestException as e:
            logger.error(e)
            sys.exit(1)

        fc = geojson.FeatureCollection(lst)
        if not fc.is_valid:
            logger.info("Feature Collection not valid: {} - {}".format(key['title'] + " (" + key['summary'] + ")",
                                                                       fc.errors()))
            return None
        else:
            logger.info("Exiting {}, no of stations: {}".format(key['title'], len(lst)))
            return fc


def store(lst):
    """
    Create a file "./data/2019/01/18/avg_temp.geojson"
    """
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))
    now = datetime.datetime.now()
    year = now.strftime("%Y") + "/"
    month = now.strftime("%m") + "/"
    day = now.strftime("%d")
    path = "./data/" + year + month + day
    Path(path).mkdir(parents=True, exist_ok=True)

    for key, val in lst.items():
        res_name = path + "/" + key + ".geojson"
        with open(res_name, 'w') as outfile:
            geojson.dump(lst[key], outfile)
            outfile.close()

    meta_name = path + "/" + "meta.json"
    with open(meta_name, 'w') as outfile:
        json.dump(fp=outfile, obj={"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                   "resources": str(len(lst))})
        outfile.close()


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
        # The sore function uses name as filename, clean name up to make it valid
        name = (k['title'] + "_" + k['summary']).replace(" ", "_").replace(",", "_").replace("/", "_per_")
        name = "".join(i for i in name if i not in "\/:*?<>|")
        result = threads[ind].get_data()
        if result:  # Could be None if there has been an error
            weather_data[name] = threads[ind].get_data()
        ind += 1

    store(weather_data)
    logger.info("Done")
