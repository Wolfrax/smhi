#!/usr/bin/python
#-*- coding: utf-8 -*-

__author__ = 'mm'

# Mats Melander 2020-07-10
# Script for generating maps of Sweden with some weather information
#

import matplotlib.pyplot as plt
import geopandas as gpd
import geoplot as gplt
import requests
import os
import sys
import datetime
# import pyproj
import warnings
from flask import Flask, render_template


app = Flask(__name__)

# Turn off annoying warning messages, no relevance for this script
warnings.simplefilter("ignore")

IMG_DIR = "img"
METOBS_DIR = "metobs_data"
DATA_DIR = "data"
FN_AVG_TEMP = "avg_temp.svg"
FN_AIR_PRES = "air_pressure.svg"
FN_RAINFALL = "rainfall.svg"


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))
    # pyproj.datadir.set_data_dir('/usr/local/share/proj')

    world = gpd.read_file(os.path.join(DATA_DIR, "ne_10m_admin_1_states_provinces.shp"))
    swe = world[world['admin'] == 'Sweden']  # Filter out Sweden from the world

    avg_temp = gpd.read_file("https://www.viltstigen.se/metobs/latest/02*")  # Probl in EPSG 3006 or 3021
    avg_temp = avg_temp.to_crs(epsg=4326)
    pressure = gpd.read_file("https://www.viltstigen.se/metobs/latest/09*")
    pressure = pressure.to_crs(epsg=4326)
    rainfall = gpd.read_file("https://www.viltstigen.se/metobs/latest/05*")
    rainfall = rainfall.to_crs(epsg=4326)

    # We want the actual date as header, but data is generated at midnight the day after (read from meta data file)
    # Hence, we need to convert the date to yesterday's date to get it right.
    r = requests.get("https://www.viltstigen.se/smhi_metobs/latest/meta.json").json()
    today = r['generated'].split(" ")[0]
    yesterday = datetime.datetime.strftime(datetime.datetime.strptime(today, "%Y-%m-%d") - datetime.timedelta(days=1),
                                           "%Y-%m-%d")

    proj = gplt.crs.AlbersEqualArea()

    fn_avg_temp = os.path.join(METOBS_DIR, IMG_DIR, FN_AVG_TEMP)
    ax = gplt.voronoi(avg_temp,
                      cmap='coolwarm',
                      clip=swe,
                      hue="value",
                      legend=True,
                      edgecolor="None",
                      projection=proj)
    gplt.polyplot(swe, edgecolor="Black", zorder=1, linewidth=0.5, projection=proj, ax=ax)
    ax.set_title("Average temperature 1 day")
    plt.savefig(fn_avg_temp, bbox_inches='tight', pad_inches=0.1)

    fn_air_pressure = os.path.join(METOBS_DIR, IMG_DIR, FN_AIR_PRES)
    ax = gplt.voronoi(pressure,
                      cmap='OrRd',
                      clip=swe,
                      hue="value",
                      legend=True,
                      edgecolor="None",
                      projection=proj)
    gplt.polyplot(swe, edgecolor="Black", zorder=1, linewidth=0.5, projection=proj, ax=ax)
    ax.set_title("Air pressure momentary value, last hour")
    plt.savefig(fn_air_pressure, bbox_inches='tight', pad_inches=0.1)

    fn_rainfall = os.path.join(METOBS_DIR, IMG_DIR, FN_RAINFALL)
    ax = gplt.voronoi(rainfall,
                      cmap='Blues',
                      clip=swe,
                      hue="value",
                      legend=True,
                      edgecolor="None",
                      projection=proj)
    gplt.polyplot(swe, edgecolor="Black", zorder=1, linewidth=0.5, projection=proj, ax=ax)
    ax.set_title("Rainfall 1 day")
    plt.savefig(fn_rainfall, bbox_inches='tight', pad_inches=0.1)

    html_file_name = os.path.join(METOBS_DIR, "weather.html")
    with app.app_context():
        html_file = render_template('swe_weather.html', head=yesterday, images=[os.path.join(IMG_DIR, FN_AVG_TEMP),
                                                                                os.path.join(IMG_DIR, FN_AIR_PRES),
                                                                                os.path.join(IMG_DIR, FN_RAINFALL)])
        with open(html_file_name, encoding='utf-8', mode='w') as outfile:
            outfile.write(html_file)
