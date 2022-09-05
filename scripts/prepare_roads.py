# -*- coding: utf-8 -*-
"""
Created on Wed Dec 16 09:27:29 2020

@author: willguestmottmac
"""


'''

This script will create a topological network of selected NZ roads:
    
    Steps:
        (1) read osm road data
        (2) Filter according to road classes
        (3) Manually add missing roads by ID (where missing from the above classes)
        (4) Merge lines with end node degree = 2
        (5) Create network for export (2x geopackages: 1x nodes, 1x edges) 

'''

#%%#####################################
# PACKAGES
########################################


import geopandas as gpd
import snkit
from tqdm import tqdm
tqdm.pandas()
import pandas as pd
import numpy as np

import geometry_functions

import urllib.request
import ast

import shapely

import functools
import pyproj

from shapely.ops import transform
from shapely.geometry import Point

import warnings

warnings.filterwarnings('ignore')

#%%#####################################
# LOAD DATA
########################################

osm_roads = gpd.read_file('../data/raw_roads/osm_roads.gpkg')


#%%#####################################
# FILTER BY ROAD TYPE
########################################

road_classes_dictionary = { 'motorway':['motorway', 'motorway_link']
                           # ,'trunk':['trunk', 'trunk_link']
                           # ,'primary':['primary', 'primary_link']
                            #,'secondary':['secondary', 'secondary_link']
                            }

roads = osm_roads[osm_roads['infrastructure'].isin(sum(road_classes_dictionary.values(), []))]
roads = roads.rename(columns={'infrastructure':'road_type'})
roads = roads[roads['geometry'].type == 'LineString']
roads['geometry'] = roads.geometry.progress_apply(lambda geom: geometry_functions.remove_third_dimension(geom))

#%%#####################################
# SIMPLIFY THE NETWORK BY MERGING ROADS WITH SAME TYPE (road class) AND DEGREE=2
########################################

#add generic road class column
roads['generic_road_class'] = roads['road_type'].progress_apply(lambda road_type: next((k for k, v in road_classes_dictionary.items() if road_type in v), None))



#split by generic road class
roads_split_by_type = [df for x, df in roads.groupby('generic_road_class', as_index=False)]

#print(roads_split_by_type)

#initialise results
merged_roads = gpd.GeoDataFrame()

for road_df in tqdm(roads_split_by_type, desc='merging roads'):
    print('')
    print('   processing:', road_df.iloc[0]['generic_road_class'])
    network = geometry_functions.create_network(road_df)
    network = geometry_functions.merge_degree2_edges(network)
    merged_roads = gpd.GeoDataFrame( pd.concat( [merged_roads, network.edges], ignore_index=True) )

#merge multilinestring
merged_roads['geometry'] = merged_roads.geometry.progress_apply(lambda geom: snkit.network.merge_multilinestring(geom))

print(merged_roads)
print(type(merged_roads))

'''
#set up as a single network
network = snkit.network.Network(edges=merged_roads)
network = snkit.network.split_multilinestrings(network)
network = snkit.network.add_endpoints(network)
network = snkit.network.add_ids(network)
network = snkit.network.add_topology(network)

#split edges at nodes create single network
network = geometry_functions.split_edges_at_nodes2(network)
network = snkit.network.add_endpoints(network)
network = snkit.network.add_ids(network)
network = snkit.network.add_topology(network)

#save
network = geometry_functions.export_to_gis(network)

'''