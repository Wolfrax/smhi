#!/usr/bin/python
#-*- coding: utf-8 -*-

__author__ = 'mm'

# Mats Melander 2020-07-10
# Script for generating maps of Sweden with some weather information
#

import matplotlib.pyplot as plt
import matplotlib.streamplot as splt
import geopandas as gpd
import numpy as np
import os
import sys
import cartopy.crs as ccrs
from scipy.interpolate import griddata
from flask import Flask, render_template
import requests
import datetime
from uritemplate import expand


DELTA = 1
DATA_DIR = "data"
IMG_DIR = "img"
METOBS_DIR = "metobs_data"

app = Flask(__name__)


class Map:
    def __init__(self):
        self.world = gpd.read_file(os.path.join(DATA_DIR, "ne_50m_admin_0_countries.shp"))
        self.country = None
        self.min_x = None
        self.min_y = None
        self.max_x = None
        self.max_y = None

        # We want the actual date as header, but data is generated at midnight the day after (read from meta data file)
        # Hence, we need to convert the date to yesterday's date to get it right.
        r = requests.get("https://www.viltstigen.se/smhi_metobs/latest/meta.json").json()
        today = r['generated'].split(" ")[0]
        yesterday = datetime.datetime.strftime(datetime.datetime.strptime(today, "%Y-%m-%d") -
                                               datetime.timedelta(days=1), "%Y-%m-%d")
        self.title = yesterday

        self.fig = plt.figure(figsize=(8, 6))
        self.ax = plt.axes(projection=ccrs.AlbersEqualArea(central_latitude=62.3858, central_longitude=16.3220))

        self.zorder = 0

    def new_geometry(self, tag):
        country = self.world[self.world['ADM0_A3'] == tag]
        self.min_x = country.total_bounds[0] - DELTA
        self.min_y = country.total_bounds[1] - DELTA
        self.max_x = country.total_bounds[2] + DELTA
        self.max_y = country.total_bounds[3] + DELTA
        self.ax.set_extent([self.min_x, self.max_x, self.min_y, self.max_y])
        return country

    def add_geometry(self, g):
        self.ax.add_geometries(g.geometry,
                               edgecolor='black',
                               facecolor='none',
                               crs=ccrs.PlateCarree(),
                               zorder=self.zorder)
        self.zorder += 1

    def gen_grid(self, data):
        grid_x = np.arange(self.min_x, self.max_x, 0.1)
        grid_y = np.arange(self.min_y, self.max_y, 0.1)

        x, y = np.meshgrid(grid_x, grid_y)
        z = griddata((data.geometry.x.to_numpy(), data.geometry.y.to_numpy()),
                     data['value'].to_numpy(),
                     (x, y),
                     method='linear')
        return {'x': x, 'y': y, 'z': z}

    def add_image(self, gr, col_map):
        pl = self.ax.imshow(gr['z'],
                            cmap=col_map,
                            extent=[self.min_x, self.max_x, self.min_y, self.max_y],
                            interpolation='None',
                            origin='lower',
                            transform=ccrs.PlateCarree(),
                            zorder=self.zorder)
        self.zorder += 1
        return pl

    def add_contour(self, gr):
        cnt = self.ax.contour(gr['x'], gr['y'], gr['z'], 5,
                              linewidths=0.25, colors='black', transform=ccrs.PlateCarree(), zorder=self.zorder)
        self.ax.clabel(cnt, colors='black', inline=True, fontsize=10, fmt="%i")
        self.zorder += 1

    def add_colorbar(self, image):
        self.fig.colorbar(image.lines if isinstance(image, splt.StreamplotSet) else image)

    def add_title(self, title_str):
        self.ax.set_title(title_str)

    def add_vectorfield(self, df, streampl):
        x = df.geometry.x.to_numpy()
        y = df.geometry.y.to_numpy()

        # Note, wind directions: Wind from West to East = 270 dgr
        # We need to map vectors to cartesian x - and y-axis using cos and sin
        directions = np.deg2rad(df['value_1'] - 270)
        u = (df['value_2'] * np.cos(directions)).to_numpy()
        v = (df['value_2'] * np.sin(directions)).to_numpy()

        magnitude = (u ** 2 + v ** 2) ** 0.5
        if streampl:
            pl = self.ax.streamplot(x, y, u, v, transform=ccrs.PlateCarree(), color=magnitude, zorder=self.zorder)
        else:
            pl = self.ax.quiver(x, y, u, v, magnitude, transform=ccrs.PlateCarree(), zorder=self.zorder)
        self.zorder += 1
        return pl

    def add_scatter(self, data):
        self.ax.scatter(data['lon'], data['lat'], c=data['peakCurrent'], marker='x',
                        transform=ccrs.PlateCarree(), zorder=self.zorder)
        self.zorder += 1


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))

    images = []
    obs_data = cmap = fname = fn = title = wind_stations = lightnings = None

    for img in ['Temp', 'Rain', 'Pressure', 'Wind', 'Quiver']:
        mp = Map()

        if img == 'Temp':
            obs_data = gpd.read_file("https://www.viltstigen.se/metobs/latest/02*")
            cmap = 'coolwarm'
            title = 'Average temperature 1 day'
            fname = 'temp.svg'
            fn = os.path.join(METOBS_DIR, IMG_DIR, fname)
        elif img == 'Rain':
            obs_data = gpd.read_file("https://www.viltstigen.se/metobs/latest/05*")
            cmap = 'Blues'
            title = 'Rainfall and lightning 1 day'
            fname = 'rain.svg'
            fn = os.path.join(METOBS_DIR, IMG_DIR, fname)

            dt = datetime.datetime.now() - datetime.timedelta(1)  # Get yesterday date
            lightning_data = requests.get(
                expand('https://opendata-download-lightning.smhi.se/api/version/latest/'
                       'year/{year}/month/{month}/day/{day}/data.json',
                       year=dt.strftime("%Y"),
                       month=dt.strftime("%m"),
                       day=dt.strftime("%d"))).json()

            lightnings = {'lat': [], 'lon': [], 'peakCurrent': []}
            for l in lightning_data['values']:
                lightnings['lat'].append(l['lat'])
                lightnings['lon'].append(l['lon'])
                lightnings['peakCurrent'].append(l['peakCurrent'])
        elif img == 'Pressure':
            obs_data = gpd.read_file("https://www.viltstigen.se/metobs/latest/09*")
            cmap = 'coolwarm'
            title = 'Air pressure, momentary value last hour'
            fname = 'pressure.svg'
            fn = os.path.join(METOBS_DIR, IMG_DIR, fname)
        elif img == 'Wind' or 'Quiver':
            obs_data = gpd.read_file("https://www.viltstigen.se/metobs/latest/09*")
            wind_directions = gpd.read_file("https://www.viltstigen.se/metobs/latest/03*")
            wind_speeds = gpd.read_file("https://www.viltstigen.se/metobs/latest/04*")
            wind_stations = gpd.overlay(wind_directions, wind_speeds, how='intersection')
            cmap = 'coolwarm'
            title = 'Wind streams and air pressure' if img == 'Wind' else "Wind direction and strengths"
            fname = 'winds.svg' if img == 'Wind' else "wind_quiver.svg"
            fn = os.path.join(METOBS_DIR, IMG_DIR, fname)

        geom = mp.new_geometry('SWE')

        if img in ['Temp', 'Rain', 'Pressure']:
            grid = mp.gen_grid(obs_data)
            im = mp.add_image(grid, cmap)
            mp.add_contour(grid)
            mp.add_colorbar(im)
            if img == 'Rain' and lightnings:
                mp.add_scatter(lightnings)
        elif img in ['Wind', 'Quiver']:
            if img == 'Wind':
                grid = mp.gen_grid(obs_data)
                mp.add_image(grid, cmap)
            mappable = mp.add_vectorfield(wind_stations, streampl=(img == 'Wind'))
            mp.add_colorbar(mappable)

        mp.add_title(title)
        mp.add_geometry(geom)

        images.append(os.path.join(IMG_DIR, fname))
        plt.savefig(fn, bbox_inches='tight', pad_inches=0.1)

    html_file_name = os.path.join(METOBS_DIR, "weather.html")
    with app.app_context():
        html_file = render_template('swe_weather.html', head=mp.title, images=images)
        with open(html_file_name, encoding='utf-8', mode='w') as outfile:
            outfile.write(html_file)
