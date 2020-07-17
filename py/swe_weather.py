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
import pyproj
import warnings
from flask import Flask, render_template
import platform
import numpy as np
import cartopy.crs as ccrs
import urllib

app = Flask(__name__)

# Turn off annoying warning messages, no relevance for this script
warnings.simplefilter("ignore")

IMG_DIR = "img"
METOBS_DIR = "metobs_data"
DATA_DIR = "data"
FN_AVG_TEMP = "avg_temp.svg"
FN_AIR_PRES = "air_pressure.svg"
FN_RAINFALL = "rainfall.svg"
FN_WIND = "wind.svg"
FN_WIND_STREAM = "wind_stream.svg"
EPSG = 4326  # WGS 84
DPI = 80


if __name__ == "__main__":
    # When running this script from crontab it is necessary to set the working directory to find the correct files
    # when reading/writing as the paths ore relative
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))

    # When running from crontab, pyproj complains on not being able to find the 'PROJ' data directory for unknown
    # configuration reasons (it works when executed form an interactive session).
    # Error message:
    #   File "/home/pi/app/smhi/.venv/lib/python3.7/site-packages/pyproj/datadir.py", line 109, in get_data_dir
    #       "Valid PROJ data directory not found. "
    #   pyproj.exceptions.DataDirError: Valid PROJ data directory not found.Either set the path using the environmental
    #   variable PROJ_LIB or with `pyproj.datadir.set_data_dir`.
    #
    # Below is thus a work around
    #
    if platform.system() == 'Linux':
        pyproj.datadir.set_data_dir('/usr/local/share/proj')

    world = gpd.read_file(os.path.join(DATA_DIR, "ne_10m_admin_1_states_provinces.shp"))
    swe = world[world['admin'] == 'Sweden']  # Filter out Sweden from the world

    try:
        avg_temp = gpd.read_file("https://www.viltstigen.se/metobs/latest/02*")
        avg_temp = avg_temp.to_crs(epsg=EPSG)
    except urllib.error.HTTPError as e:
        print("Error reading average temperature")
        avg_temp = gpd.GeoDataFrame()

    try:
        pressure = gpd.read_file("https://www.viltstigen.se/metobs/latest/09*")
        pressure = pressure.to_crs(epsg=EPSG)
    except urllib.error.HTTPError as e:
        print("Error reading pressure")
        pressure = gpd.GeoDataFrame()

    try:
        rainfall = gpd.read_file("https://www.viltstigen.se/metobs/latest/05*")
        rainfall = rainfall.to_crs(epsg=EPSG)
    except urllib.error.HTTPError as e:
        print("Error reading rainfall")
        rainfall = gpd.GeoDataFrame()

    try:
        wind_directions = gpd.read_file("https://www.viltstigen.se/metobs/latest/03*")  # Probl in EPSG 3006 or 3021
        wind_directions = wind_directions.to_crs(epsg=EPSG)
    except urllib.error.HTTPError as e:
        print("Error reading wind directions")
        wind_directions = gpd.GeoDataFrame()
    try:
        wind_speeds = gpd.read_file("https://www.viltstigen.se/metobs/latest/04*")
        wind_speeds = wind_speeds.to_crs(epsg=EPSG)
    except urllib.error.HTTPError as e:
        print("Error reading wind speeds")
        wind_speeds = gpd.GeoDataFrame()

    if not wind_directions.empty and not wind_speeds.empty:
        wind_stations = gpd.overlay(wind_directions, wind_speeds, how='intersection')
    else:
        wind_stations = gpd.GeoDataFrame()

    try:
        # We want the actual date as header, but data is generated at midnight the day after (read from meta data file)
        # Hence, we need to convert the date to yesterday's date to get it right.
        r = requests.get("https://www.viltstigen.se/smhi_metobs/latest/meta.json").json()
        today = r['generated'].split(" ")[0]
        yesterday = datetime.datetime.strftime(datetime.datetime.strptime(today, "%Y-%m-%d") - datetime.timedelta(days=1),
                                               "%Y-%m-%d")
    except requests.exceptions.RequestException as e:
        print("Error reading meta file")
        yesterday = ""

    proj = gplt.crs.AlbersEqualArea()

    images = []
    if not avg_temp.empty:
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
        plt.savefig(fn_avg_temp, bbox_inches='tight', pad_inches=0.1) #  dpi=DPI,
        images.append(os.path.join(IMG_DIR, FN_AVG_TEMP))

    if not pressure.empty:
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
        plt.savefig(fn_air_pressure, bbox_inches='tight', pad_inches=0.1) #  dpi=DPI,
        images.append(os.path.join(IMG_DIR, FN_AIR_PRES))

    if not rainfall.empty:
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
        plt.savefig(fn_rainfall, bbox_inches='tight', pad_inches=0.1) #  dpi=DPI,
        images.append(os.path.join(IMG_DIR, FN_RAINFALL))

    if not wind_stations.empty:
        X = wind_stations.geometry.x.to_numpy()
        Y = wind_stations.geometry.y.to_numpy()

        # Note, wind directions: Wind from West to East = 270 dgr
        # We need to map vectors to cartesian x - and y-axis using cos and sin
        directions = np.deg2rad(wind_stations['value_1'] - 270)
        U = (wind_stations['value_2'] * np.cos(directions)).to_numpy()
        V = (wind_stations['value_2'] * np.sin(directions)).to_numpy()
        C = wind_stations['value_2']

        fn_wind = os.path.join(METOBS_DIR, IMG_DIR, FN_WIND)
        fig = plt.figure(figsize=(8, 6))  # Default figsize for geoplot, needs to be set explicitly here
        ax = plt.axes(projection=proj)
        ax.set_axis_off()
        swe.plot(edgecolor="Grey", facecolor="whitesmoke", linewidth=0.5, ax=ax)
        qv = ax.quiver(X, Y, U, V, C, transform=ccrs.AlbersEqualArea(), width=0.01)
        fig.colorbar(qv)
        ax.set_title("Wind speed and directions")
        plt.savefig(fn_wind, bbox_inches='tight', pad_inches=0.1) #  dpi=DPI,
        images.append(os.path.join(IMG_DIR, FN_WIND))

        fn_wind_stream = os.path.join(METOBS_DIR, IMG_DIR, FN_WIND_STREAM)
        fig = plt.figure(figsize=(8, 6))  # Default figsize for geoplot, needs to be set explicitly here
        ax = plt.axes(projection=proj)
        ax.set_axis_off()
        swe.plot(edgecolor="Grey", facecolor="whitesmoke", linewidth=0.1, ax=ax)
        magnitude = (U ** 2 + V ** 2) ** 0.5
        strm = ax.streamplot(X, Y, U, V, transform=ccrs.AlbersEqualArea(), color=magnitude)
        ax.set_title("Wind streams")
        fig.colorbar(strm.lines)
        plt.savefig(fn_wind_stream, bbox_inches='tight', pad_inches=0.1) #  dpi=DPI,
        images.append(os.path.join(IMG_DIR, FN_WIND_STREAM))

    html_file_name = os.path.join(METOBS_DIR, "weather.html")
    with app.app_context():
        html_file = render_template('swe_weather.html', head=yesterday, images=images)
        with open(html_file_name, encoding='utf-8', mode='w') as outfile:
            outfile.write(html_file)
