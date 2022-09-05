


# -*- coding: utf-8 -*-
"""
Created on Wed Dec 16 09:27:29 2020

@author: czor847
"""



'''

This script will calculate the stuff between origin and destination pairs :
    
    Steps:
        (1) Add O-D pairs to the network and update node id/topology
        (2) Save as a working network
        (3) Setup as networkx
        (4) Find shortest path OD routes
        (5) Split shortest path into segments (i.e. 100 m) 
        (6) Find elevations for start and end points

'''

#%%#####################################
# PACKAGES
########################################

import geopandas as gpd
from tqdm import tqdm
tqdm.pandas()
import pandas as pd
pd.options.mode.chained_assignment = None  # default='warn'

import shapely
from shapely.ops import transform
from shapely.geometry import Point

import snkit
import networkx

import numpy as np
import math
import os

import urllib.request
import ast
import functools
import pyproj

import geometry_functions
import network_analysis_functions
import elevation_functions

import sys
sys.setrecursionlimit(10000)

#%%#####################################
# IMPORT DATA
########################################

road_nodes = gpd.read_file('../data/road_network/nodes.gpkg')
road_edges = gpd.read_file('../data/road_network/edges.gpkg')
od_data = gpd.read_file('../data/od_data/od_points.gpkg')

#%%#####################################
# ADD origins AND desitnations TO NETWORK
########################################

#merge the OD data to a new network
network = snkit.network.Network(nodes=gpd.GeoDataFrame( pd.concat( [road_nodes, od_data], ignore_index=True) ),
                                edges=road_edges,
                                )

#create links from OD nodes to nearest edge
network = geometry_functions.link_isolated_nodes_to_nearest_edge(network)

#split road edges at new nodes connecting the OD points to the road network
network = geometry_functions.split_edges_at_new_od_nodes(network, tolerance=1e-9)
 
#fill in the missing info - assume new links are 'secondary' roads
network.nodes['node_purpose'] = network.nodes['node_purpose'].fillna('road_network')
network.nodes['node_type'] = network.nodes['node_type'].fillna('road_network')
network.edges['road_type'] = network.edges['road_type'].fillna('OD_connector')
network.edges.loc[network.edges['road_type'] == 'OD_connector', 'generic_road_class'] = 'secondary'

#complete topology: add ids
network = snkit.network.add_ids(network)

'''
USE THE NORMAL NODE INTEGER FORMAT - NETWORK X USES NODE IDS
#complete topology: overwrite id if it has a proper name <---- some reasons was fucking out sometimes when using .loc (just using a loop for now)
for i,rows in tqdm(network.nodes.iterrows(),total=len(network.nodes)):
    if  isinstance(rows['node_name'], str):
        network.nodes.loc[i,'id']=rows['node_name']
'''     
#complete topology: add topology
network = snkit.network.add_topology(network)    

#Add Edge Lengths
network.edges['length_m'] = network.edges.geometry.length
        

#%%#####################################
# save working network
########################################
n=network.nodes
e=network.edges

network = geometry_functions.set_nztm_crs(network)
network.nodes.to_file(filename='../data/WORKING_NODES.gpkg', driver='GPKG')
network.edges.to_file(filename='../data/WORKING_EDGES.gpkg', driver='GPKG')

#%%#####################################
# networkx - setup
########################################

#load GIS data
network = snkit.network.Network(nodes=gpd.read_file('../data/WORKING_NODES.gpkg'), edges=gpd.read_file('../data/WORKING_EDGES.gpkg'))

#create graph
G = network_analysis_functions.build_initial_network(network)

#create od_table
od_table = network_analysis_functions.create_routes(G, network)

#For given OD pairing, find all the route segments and ensure the geometry is facing the correct orientation
route_segments = gpd.GeoDataFrame(columns=['origin_name', 'destination_name'], crs=network.edges.crs)

all_routes = gpd.GeoDataFrame()

for i,rows in tqdm(od_table.iterrows(), total=len(od_table), desc='Origin-Destination'):
    origin_name = rows.o_name
    destination_name = rows.d_name
    print('')
    print(origin_name , 'to', destination_name)
    
    '''
    if  i==4:
        df = od_table[od_table.index == i]
        aaaaaaaaaaaaaaaaaaa
    '''
            
    #append just those edges in the correct direction
    for (from_id, to_id) in rows.path_edges:
        
        #check the forward and reverse facing edges for from/to ID pairings - will be blank (len=0) if no edge is found
        forward_edge = network.edges[(network.edges['from_id']=='node_'+str(from_id)) & (network.edges['to_id']=='node_'+str(to_id))]
        reverse_edge = network.edges[(network.edges['from_id']=='node_'+str(to_id)) & (network.edges['to_id']=='node_'+str(from_id))]
        
        #add forward edge
        if  len(forward_edge) == 1:
            route_segments = gpd.GeoDataFrame(pd.concat( [route_segments, forward_edge], ignore_index=True))
            
        #add if reverse edge
        if  len(reverse_edge) == 1:
            #reverse geometry
            reverse_edge['geometry']=reverse_edge['geometry'].apply(lambda geom: shapely.geometry.LineString(list(geom.coords)[::-1]))
            #append
            route_segments = gpd.GeoDataFrame(pd.concat( [route_segments, reverse_edge], ignore_index=True))
            
    #fill in the origin and destination names
    route_segments['origin_name']=route_segments['origin_name'].fillna(origin_name)
    route_segments['destination_name']=route_segments['destination_name'].fillna(destination_name)
    #route_segments.to_file(filename='../TEMP.gpkg', driver='GPKG')
    
    #simplify geometries
    route_segments['geometry']=route_segments.geometry.apply(lambda geom: snkit.network.set_precision(geom, 0))
    route_segments['order']=route_segments.index
    route_segments['order']+=1

    #merge into a single line string #DROPPED TO SPEED THINGS UP
    '''single_route = geometry_functions.merge_to_single_line_string(route_segments)
    single_route.to_file(driver='GPKG', filename='../TEMP.gpkg')   
    '''
    
    #split route into X m segements
    distance = 1000

    split_edges = gpd.GeoDataFrame()
    for i,rows in tqdm(route_segments.iterrows(), total=len(route_segments), desc='splitting'):
        segment = route_segments[route_segments.index==i]
        split_partial_route = geometry_functions.create_split_edges_dataframe(segment, distance)
        split_edges = gpd.GeoDataFrame( pd.concat( [split_edges, split_partial_route], ignore_index=True) )
    
    split_edges['order']=split_edges.index
    split_edges['order']+=1
    #split_edges.to_file(driver='GPKG', filename='../TEMP.gpkg')   

    all_routes = gpd.GeoDataFrame( pd.concat( [all_routes, split_edges], ignore_index=True) )
    all_routes.to_file(driver='GPKG', filename='../results/all_routes.gpkg')   


#%%
#simplify geometries
all_routes['geometry']=all_routes.geometry.apply(lambda geom: snkit.network.set_precision(geom, 0))

#elevation at start/end edges
linz_key = 'fbae4ce80e684f248d7a6dcee97f992d'

#only find elevations for unique points
all_start_points = [line.coords[0] for line in split_edges.geometry]
all_end_points = [line.coords[-1] for line in split_edges.geometry]
unique_points = list(set(all_start_points+all_end_points))
elevation_dictionary = {}

for coords in tqdm(unique_points, total=len(unique_points), desc='finding elevations'):
    elevation = elevation_functions.find_elevation_of_point(shapely.geometry.Point(coords), linz_key)
    elevation_dictionary[coords] = elevation
        
split_edges['start_elevation'] = split_edges.geometry.apply(lambda geom: elevation_dictionary[geom.coords[0]])
split_edges['end_elevation'] = split_edges.geometry.apply(lambda geom: elevation_dictionary[geom.coords[-1]])
