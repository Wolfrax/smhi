#!/usr/bin/python
# -*- coding: utf-8 -*-

__author__ = 'mm'

# Mats Melander 2020-08-08
# Script for collecting and visualizing Sweden lightnings data from SMHI

import datetime
import argparse
import requests
from uritemplate import expand
import os
import sys
import json
from json import JSONEncoder
import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import warnings
from flask import Flask, render_template


METOBS_DIR = "metobs_data"
DATA_DIR = "data"
IMG_DIR = "img"
DELTA = 1
FLAG_RESET_AT_NEW_YEAR = True

app = Flask(__name__)


class LightningEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)


class Country:
    def __init__(self, country):
        self.world = gpd.read_file(os.path.join(DATA_DIR, 'ne_50m_admin_0_countries.shp'))
        self.country = self.world[self.world['ADM0_A3'] == country]
        self.min_lon = self.country.total_bounds[0] - DELTA
        self.min_lat = self.country.total_bounds[1] - DELTA
        self.max_lon = self.country.total_bounds[2] + DELTA
        self.max_lat = self.country.total_bounds[3] + DELTA

        self.lon_range = np.arange(self.min_lon, self.max_lon, (self.max_lon - self.min_lon) / 100)
        self.lat_range = np.arange(self.min_lat, self.max_lat, (self.max_lat - self.min_lat) / 100)

        self.fig = plt.figure(figsize=(8, 6))
        self.ax = self.fig.add_subplot(projection=ccrs.AlbersEqualArea(central_latitude=62.3858,
                                                                       central_longitude=16.3220))
        self.ax.set_extent([self.min_lon, self.max_lon, self.min_lat, self.max_lat])

        self.fig_bar = plt.figure(figsize=(4, 3))
        self.ax_bar = self.fig_bar.add_subplot()

    def add_geometries(self):
        self.ax.add_geometries(self.country.geometry, edgecolor='black', facecolor='none', crs=ccrs.PlateCarree())

    def transform_points(self, lon, lat):
        return self.ax.projection.transform_points(ccrs.PlateCarree(), lon, lat)

    def image(self, x, ext):
        im = self.ax.imshow(x, interpolation='bilinear', origin='low', cmap='jet', extent=ext, alpha=0.75)
        self.fig.colorbar(im)

    def bars(self, x):
        nr_of_years = len(x)
        if nr_of_years > 3:
            warnings.warn("Maximum years is 3")
            nr_of_years = 3

        bar_width = round(0.8 / nr_of_years, 1) if nr_of_years > 0 else 0.8

        year = 0
        color = ['b', 'g', 'r']
        month_ticks = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
        h = []
        y = []
        for k in x.keys():
            ind = np.arange(len(x[k]))
            ind = ind + year * bar_width
            h.append(self.ax_bar.bar(ind, list(x[k].values()), bar_width,
                                     tick_label=month_ticks[0:len(x[k])],
                                     align='center',
                                     color=color[year]))
            year += 1
            y.append(k)
            if year == nr_of_years:
                break

        self.ax_bar.autoscale(tight=True)
        self.ax_bar.legend(h, y)

    def save_histogram(self, fn):
        self.fig.savefig(fn, bbox_inches='tight', pad_inches=0.1)

    def save_bars(self, fn):
        self.fig_bar.savefig(fn, bbox_inches='tight', pad_inches=0.1)


class Lightnings:
    def __init__(self):
        self.swe = Country("SWE")
        self.swe.add_geometries()

        dt = datetime.datetime.now() - datetime.timedelta(1)  # Get yesterday date as 'latest'
        self.latest_date = {'year': dt.strftime("%Y"),
                            'month': dt.strftime("%m"),
                            'day': dt.strftime("%d")}

        # File names for resulting plots with year as suffix.
        # Note get-method where file names might get updated
        # to reflect oldest year, ie if we start in 2020 but end in 2019, we create the name "lightnings_map_2019.svg"
        self.fn_map = os.path.join(METOBS_DIR, IMG_DIR, self.latest_date['year'] + "_lightnings_map.svg")
        self.fn_bars = os.path.join(METOBS_DIR, IMG_DIR, self.latest_date['year'] + "_lightnings_bars.svg")
        self.fn = os.path.join(METOBS_DIR, self.latest_date['year'] + "_lightnings.json")
        if os.path.exists(self.fn):
            with open(self.fn) as f:
                self.db = json.load(f)
                self.db['hist'] = np.array(self.db['hist'])
        else:
            self.db = {
                'table': {
                    'Totals': {
                        'Total nr': 0,
                        'Avg nr': 0,
                        'Max nr': 0,
                        'Peak current': 0
                    },
                },
                'days': {'Totals': 0},
                'hist': np.zeros((100, 100)),
                'monthly': {},
                'first_date': datetime.datetime(2999, 12, 31),
                'last_date': datetime.datetime(1900, 1, 1)
            }
        self.x_edges = np.zeros(100)
        self.y_edges = np.zeros(100)

    def get(self, day):
        values = {}
        current_year = self.latest_date['year']
        dt = datetime.datetime.now() - datetime.timedelta(day)
        self.latest_date = {'year': dt.strftime("%Y"),
                            'month': dt.strftime("%m"),
                            'day': dt.strftime("%d")}
        if self.latest_date['year'] != current_year:
            # New year! Change filenames to where figures will be saved.
            if FLAG_RESET_AT_NEW_YEAR:
                # Reset db (except totals) if flag is true at first day of the year
                # Applicable when, for example, we are going from 2020-12-31 to 2021-01-01 and use +1 day increments,
                # ie when "Start date"/"End date" are not set but use default values.
                warnings.warn("Reset self.db due to new year: {}".format(self.latest_date['year']))

                self.db['hist'] = np.zeros((100, 100))
                self.db['monthly'] = {}

            self.fn_map = os.path.join(METOBS_DIR, IMG_DIR, self.latest_date['year'] + "_lightnings_map.svg")
            self.fn_bars = os.path.join(METOBS_DIR, IMG_DIR, self.latest_date['year'] + "_lightnings_bars.svg")
            self.fn = os.path.join(METOBS_DIR, self.latest_date['year'] + "_lightnings.json")

            self.db['days'][self.latest_date['year']] = 0
            self.db['table'][self.latest_date['year']] = {
                'Total nr': 0,
                'Avg nr': 0,
                'Max nr': 0,
                'Peak current': 0
            }

        url = expand('https://opendata-download-lightning.smhi.se/api/version/latest/'
                     'year/{year}/month/{month}/day/{day}/data.json',
                     year=self.latest_date['year'],
                     month=self.latest_date['month'],
                     day=self.latest_date['day'])
        print("Processing {}".format(url))
        try:
            data = requests.get(url).json()
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)

        if dt < self.db['first_date']:
            self.db['first_date'] = dt
        if dt > self.db['last_date']:
            self.db['last_date'] = dt

        self.db['days']['Totals'] += 1
        if self.latest_date['year'] in self.db['days']:
            self.db['days'][self.latest_date['year']] += 1
        else:
            self.db['days'][self.latest_date['year']] = 1

        if data['values']:
            self.db['table']['Totals']['Total nr'] += len(data['values'])
            self.db['table']['Totals']['Avg nr'] = round(self.db['table']['Totals']['Total nr'] /
                                                         self.db['days']['Totals'])
            self.db['table']['Totals']['Max nr'] = max(len(data['values']), self.db['table']['Totals']['Max nr'])

            for v in data['values']:
                self.db['table']['Totals']['Peak current'] = max(abs(v['peakCurrent']),
                                                                 self.db['table']['Totals']['Peak current'])
                v_year = str(v['year'])
                v_month = str("{:02d}".format(v['month']))
                v_day = str("{:02d}".format(v['day']))

                if v_year in self.db['table']:
                    self.db['table'][v_year]['Total nr'] += 1
                    self.db['table'][v_year]['Avg nr'] = round(self.db['table'][v_year]['Total nr'] /
                                                               self.db['days'][v_year])
                    self.db['table'][v_year]['Max nr'] = max(len(data['values']), self.db['table'][v_year]['Max nr'])
                    self.db['table'][v_year]['Peak current'] = max(abs(v['peakCurrent']),
                                                                   self.db['table'][v_year]['Peak current'])
                else:
                    self.db['days'][v_year] = 1
                    self.db['table'][v_year] = {
                        'Total nr': 1,
                        'Avg nr': 1,
                        'Max nr': len(data['values']),
                        'Peak current': abs(v['peakCurrent'])
                    }

                if v_year in values:
                    if v_month in values[v_year]:
                        if v_day in values[v_year][v_month]:
                            values[v_year][v_month][v_day]['lat'] = np.append(values[v_year][v_month][v_day]['lat'],
                                                                              v['lat'])
                            values[v_year][v_month][v_day]['lon'] = np.append(values[v_year][v_month][v_day]['lon'],
                                                                              v['lon'])
                        else:
                            values[v_year][v_month][v_day] = {'lat': np.array(v['lat']),
                                                              'lon': np.array(v['lon'])}
                    else:
                        values[v_year][v_month] = {v_day: {'lat': np.array(v['lat']),
                                                           'lon': np.array(v['lon'])}}

                else:
                    values[v_year] = {v_month: {v_day: {'lat': np.array(v['lat']),
                                                        'lon': np.array(v['lon'])}}}
        else:
            self.db['table']['Totals']['Avg nr'] = round(self.db['table']['Totals']['Total nr'] /
                                                         self.db['days']['Totals'])
            self.db['table'][self.latest_date['year']]['Avg nr'] = \
                round(self.db['table'][self.latest_date['year']]['Total nr'] /
                      self.db['days'][self.latest_date['year']])

        return values

    def monthly(self, values):
        # Generate a dictionary with nr of lightnings per month

        y = self.latest_date['year']
        m = self.latest_date['month']
        d = self.latest_date['day']

        if y in values:
            year = values[y]
            if m in year:
                month = year[m]
                if d in month:
                    # self.db['monthly']['2020']['08'] = 123
                    if y in self.db['monthly']:
                        if m in self.db['monthly'][y]:
                            self.db['monthly'][y][m] += values[y][m][d]['lon'].size
                        else:
                            self.db['monthly'][y][m] = values[y][m][d]['lon'].size
                    else:
                        self.db['monthly'][y] = {'01': 0, '02': 0, '03': 0, '04': 0, '05': 0, '06': 0,
                                                 '07': 0, '08': 0, '09': 0, '10': 0, '11': 0, '12': 0}
                        self.db['monthly'][y][m] = values[y][m][d]['lon'].size

    def histogram(self, values):
        # Generate 2D Histogram with projection for Sweden

        y = self.latest_date['year']
        m = self.latest_date['month']
        d = self.latest_date['day']

        if y in values:
            year = values[y]
            if m in year:
                month = year[m]
                if d in month:
                    # To make the 2d histogram, we need to transform lat/lon points and the min/max lat/lon points
                    # for Sweden. transform_points returns a multidimensional array and we want to use the
                    # first ("[:, 0]") and second ("[:, 1]") columns.
                    # range-parameter ensure that we cover the full bounding box of Sweden.
                    # bins-parameter is the number of bins in longitude and latitude dimensisons, 100 eqach.

                    xy_points = self.swe.transform_points(month[d]['lon'], month[d]['lat'])
                    range_points = self.swe.transform_points(np.array([self.swe.min_lon, self.swe.max_lon]),
                                                             np.array([self.swe.min_lat, self.swe.max_lat]))
                    h, self.x_edges, self.y_edges = np.histogram2d(xy_points[:, 0], xy_points[:, 1],
                                                                   range=(range_points[:, 0], range_points[:, 1]),
                                                                   bins=(len(self.swe.lon_range),
                                                                         len(self.swe.lat_range)))
                    if len(self.db['hist']) > 0:
                        # If we have previous histogram data we accumulate here
                        self.db['hist'] = h + self.db['hist']
                    else:
                        self.db['hist'] = h

    def render_histogram(self):
        hist = self.db['hist']
        h = np.ma.masked_where(hist.T == 0, hist.T)
        self.swe.image(h, (self.x_edges[0], self.x_edges[-1], self.y_edges[0], self.y_edges[-1]))

    def render_monthly(self):
        self.swe.bars(self.db['monthly'])

    def save_json(self):
        with open(self.fn, 'w', encoding='utf-8') as f:
            json.dump(self.db, f, ensure_ascii=False, cls=LightningEncoder)

    def save_histogram(self):
        self.swe.save_histogram(self.fn_map)

    def save_monthly(self):
        self.swe.save_bars(self.fn_bars)


def get_maps():
    file_path = os.path.join(METOBS_DIR, IMG_DIR)
    files = [name for name in os.listdir(file_path) if os.path.isfile(os.path.join(file_path, name))]
    return sorted([os.path.join(IMG_DIR, name) for name in files if name.endswith("_map.svg")])


def get_bars():
    file_path = os.path.join(METOBS_DIR, IMG_DIR)
    files = [name for name in os.listdir(file_path) if os.path.isfile(os.path.join(file_path, name))]
    return sorted([os.path.join(IMG_DIR, name) for name in files if name.endswith("_bars.svg")])


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--start", required=False, default=datetime.datetime.now().strftime('%Y-%m-%d'),
                    help="start date")
    ap.add_argument("-e", "--end", required=False, default=datetime.datetime.now().strftime('%Y-%m-%d'),
                    help="end date")
    args = vars(ap.parse_args())

    try:
        start_date = datetime.datetime.strptime(args['start'], '%Y-%m-%d').date()
        end_date = datetime.datetime.strptime(args['end'], '%Y-%m-%d').date()
    except ValueError:
        raise ValueError("Error: Incorrect format given for dates. They must be given like 'yyyy-mm-dd'.")

    if start_date > datetime.datetime.now().date():
        warnings.warn("Start date > now, reset to now")
        start_date = datetime.datetime.now().date()
    if end_date > datetime.datetime.now().date():
        warnings.warn("End date > now, reset to now")
        end_date = datetime.datetime.now().date()
    if end_date < start_date:
        warnings.warn("End date must be > Start date! Swapping dates.")
        tmp = start_date
        start_date = end_date
        end_date = tmp

    start_day = (datetime.datetime.now() - datetime.datetime(start_date.year, start_date.month, start_date.day)).days
    end_day = (datetime.datetime.now() - datetime.datetime(end_date.year, end_date.month, end_date.day)).days

    # 1. if start_day and end_day is equal (default if args not provided), we will reset 'hist' and 'monthly' to zero
    #    in get-method of lightnings.
    # or
    # 2. if start_day and end_day is not equal, 'hist' and 'monthly' will not be reset.
    #
    # Case 1 above, assumes that this script is executed once per day without args '-s' and '-e', and we will
    # incrementally add the latest available information. Thus, if we have collected information until
    # 2020-12-31 and execute this script to get information for 2021-01-01, we will reset 'hist' and 'monthly', and
    # store histogram and bars plots in a new file for 2021 (not overwriting the 2020 files).
    #
    # Case 2, assume that we have provided args '-s' and '-e' explicitly, for example to 2019-08-01 and 2020-08-01,
    # then we don't want to reset 'hist' and 'monthly' even though we are changing year (plots will be saved in
    # '2019_lightnings_bars.svg' and '2019_lightnings_map.svg').
    #
    FLAG_RESET_AT_NEW_YEAR = (start_day == end_day)

    lightnings = Lightnings()
    for d in range(end_day, start_day + 1):
        values = lightnings.get(d)
        lightnings.histogram(values)
        lightnings.monthly(values)

    lightnings.render_histogram()
    lightnings.render_monthly()

    lightnings.save_histogram()
    lightnings.save_monthly()
    lightnings.save_json()

    map_list = get_maps()
    bar_list = get_bars()
    html_file_name = os.path.join(METOBS_DIR, "lightnings.html")
    with app.app_context():
        html_file = render_template('swe_lightnings.html',
                                    first_date=lightnings.db['first_date'].strftime('%Y-%m-%d'),
                                    last_date=lightnings.db['last_date'].strftime('%Y-%m-%d'),
                                    table=lightnings.db['table'],
                                    maps=map_list,
                                    bars=bar_list)
        with open(html_file_name, encoding='utf-8', mode='w') as outfile:
            outfile.write(html_file)

#    import webbrowser
#    webbrowser.open(html_file_name, new=2)
