#!/usr/bin/python
#-*- coding: utf-8 -*-

__author__ = 'mm'

# Mats Melander 2020-07-10
# Script for generating maps of Sweden with some weather information
#

import matplotlib.pyplot as plt
import geopandas as gpd
import numpy as np
import os
import sys
import cartopy.crs as ccrs
from scipy.interpolate import griddata
from flask import Flask, render_template
import requests
import datetime


DELTA = 1
DATA_DIR = "data"
IMG_DIR = "img"
METOBS_DIR = "metobs_data"

app = Flask(__name__)


def add_windstreams(fig, ax, plot_type):
    wind_directions = gpd.read_file("https://www.viltstigen.se/metobs/latest/03*")  # Probl in EPSG 3006 or 3021
    wind_speeds = gpd.read_file("https://www.viltstigen.se/metobs/latest/04*")
    wind_stations = gpd.overlay(wind_directions, wind_speeds, how='intersection')

    x = wind_stations.geometry.x.to_numpy()
    y = wind_stations.geometry.y.to_numpy()

    # Note, wind directions: Wind from West to East = 270 dgr
    # We need to map vectors to cartesian x - and y-axis using cos and sin
    directions = np.deg2rad(wind_stations['value_1'] - 270)
    u = (wind_stations['value_2'] * np.cos(directions)).to_numpy()
    v = (wind_stations['value_2'] * np.sin(directions)).to_numpy()

    magnitude = (u ** 2 + v ** 2) ** 0.5
    if plot_type == 'Stream':
        img = ax.streamplot(x, y, u, v, transform=ccrs.PlateCarree(), color=magnitude)
    else:
        img = ax.quiver(x, y, u, v, magnitude, transform=ccrs.PlateCarree())

    fig.colorbar(img.lines if plot_type == 'Stream' else img)


def imshow(fig, ax, data, bounds, col_map, add_contour=True, add_colorbar=True):
    x = data.geometry.x.to_numpy()  # X coordinate/latitude for station
    y = data.geometry.y.to_numpy()

    grid_x = np.arange(bounds[0]-DELTA, bounds[2]+DELTA, 0.1)
    grid_y = np.arange(bounds[1]-DELTA, bounds[3]+DELTA, 0.1)
    xi, yi = np.meshgrid(grid_x, grid_y)

    z = data['value'].to_numpy()
    zi = griddata((x, y), z, (xi, yi), method='linear')

    im = ax.imshow(zi, cmap=col_map, extent=[bounds[0]-DELTA, bounds[2]+DELTA, bounds[1]-DELTA, bounds[3]+DELTA],
                   interpolation='None', origin='lower', transform=ccrs.PlateCarree(), zorder=1)
    if add_contour:
        cnt = ax.contour(xi, yi, zi, 5, linewidths=0.25, colors='black', transform=ccrs.PlateCarree(), zorder=2)
        ax.clabel(cnt, colors='black', inline=True, fontsize=10, fmt="%i")
    if add_colorbar:
        fig.colorbar(im)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))

    world = gpd.read_file(os.path.join(DATA_DIR, "ne_50m_admin_0_countries.shp"))
    swe = world[world['ADM0_A3'] == 'SWE']  # Filter out Sweden from the world

    try:
        # We want the actual date as header, but data is generated at midnight the day after (read from meta data file)
        # Hence, we need to convert the date to yesterday's date to get it right.
        r = requests.get("https://www.viltstigen.se/smhi_metobs/latest/meta.json").json()
        today = r['generated'].split(" ")[0]
        yesterday = datetime.datetime.strftime(datetime.datetime.strptime(today, "%Y-%m-%d") -
                                               datetime.timedelta(days=1), "%Y-%m-%d")
    except requests.exceptions.RequestException as e:
        print("Error reading meta file")
        yesterday = ""

    images = []

    for obs in ['Temp', 'Rain', 'Pressure', 'Wind', 'Quiver']:
        fig = plt.figure(figsize=(8, 6))
        ax = plt.axes(projection=ccrs.AlbersEqualArea(central_latitude=62.3858, central_longitude=16.3220))
        ax.set_extent([swe.total_bounds[0] - DELTA, swe.total_bounds[2] + DELTA,
                       swe.total_bounds[1] - DELTA, swe.total_bounds[3] + DELTA])
        ax.add_geometries(swe.geometry, edgecolor='black', facecolor='none', crs=ccrs.PlateCarree(), zorder=3)

        if obs == 'Temp':
            obs_data = gpd.read_file("https://www.viltstigen.se/metobs/latest/02*")
            cmap = 'coolwarm'
            title = 'Average temperature 1 day'
            fname = 'temp.svg'
            fn = os.path.join(METOBS_DIR, IMG_DIR, fname)
        elif obs == 'Rain':
            obs_data = gpd.read_file("https://www.viltstigen.se/metobs/latest/05*")
            cmap = 'Blues'
            title = 'Rainfall 1 day'
            fname = 'rain.svg'
            fn = os.path.join(METOBS_DIR, IMG_DIR, fname)
        elif obs == 'Pressure':
            obs_data = gpd.read_file("https://www.viltstigen.se/metobs/latest/09*")
            cmap = 'coolwarm'
            title = 'Air pressure, momentary value last hour'
            fname = 'pressure.svg'
            fn = os.path.join(METOBS_DIR, IMG_DIR, fname)
        elif obs == 'Wind' or 'Quiver':
            obs_data = gpd.read_file("https://www.viltstigen.se/metobs/latest/09*")
            cmap = 'coolwarm'
            title = 'Wind streams and air pressure' if obs == 'Wind' else "Wind direction and strengths"
            fname = 'winds.svg' if obs == 'Wind' else "wind_quiver.svg"
            fn = os.path.join(METOBS_DIR, IMG_DIR, fname)
        else:
            obs_data = cmap = fn = fname = title = None

        if obs == 'Wind':
            imshow(fig, ax, obs_data, swe.total_bounds, cmap, add_contour=False, add_colorbar=False)
            add_windstreams(fig, ax, plot_type='Stream')
        elif obs == 'Quiver':
            add_windstreams(fig, ax, plot_type='Quiver')
        else:
            imshow(fig, ax, obs_data, swe.total_bounds, cmap)

        images.append(os.path.join(IMG_DIR, fname))
        ax.set_title(title)
        plt.savefig(fn, bbox_inches='tight', pad_inches=0.1)

    html_file_name = os.path.join(METOBS_DIR, "weather.html")
    with app.app_context():
        html_file = render_template('swe_weather.html', head=yesterday, images=images)
        with open(html_file_name, encoding='utf-8', mode='w') as outfile:
            outfile.write(html_file)
