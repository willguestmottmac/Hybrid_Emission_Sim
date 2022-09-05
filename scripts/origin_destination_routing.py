'''
TO DO
- rerun everything  @100m
-  check for steep slopes - i.e. napier port, lyttleton tunnel etc. and update
- fuel use calculation parameters need fixing
'''





'''
STEP 1 - READ O-D PAIRING

STEP 2 - CREATE NETWORK AND FIND SHORTEST PATH (WEIGHTED ACCORIDNG TO ROAD TYPE)

STEP 3 - SPLIT ROUTE INTO X METER SEGMENTS

STEP 4 - FIND ELEVATIONS ALONG ROUTE

STEP 5 - SAVE DATA FOR FUEL CONSUMPTION CALCULATIONS

'''

#%%#####################################
# PACKAGES
########################################
#!pip freeze > requirements.txt
#!pip install -r requirements.txt

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

import pickle

#%%#####################################
# IMPORT RAW DATA
########################################

road_nodes = gpd.read_file('../data/road_network/nodes.gpkg')
road_edges = gpd.read_file('../data/road_network/edges.gpkg')
od_data = gpd.read_file('../data/od_data/od_points.gpkg')

results = gpd.read_file('../results/raw_route_results.gpkg')

elevation_dictionary = pickle.load(open('../results/elevation_dictionary.pkl', 'rb'))
    
#%%#####################################
# CREATE A NETWORK
########################################

#merge the OD data to the road network
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

#complete network topology
network = snkit.network.add_ids(network)
network = snkit.network.add_topology(network)    
network.edges['length_m'] = network.edges.geometry.length

#save as a working connected network
network = geometry_functions.set_nztm_crs(network)
network.nodes.to_file(filename='../data/WORKING_NODES.gpkg', driver='GPKG')
network.edges.to_file(filename='../data/WORKING_EDGES.gpkg', driver='GPKG')

#%%#####################################
# COMPUTE SHORTEST PATHS
########################################

#load GIS data
network = snkit.network.Network(nodes=gpd.read_file('../data/WORKING_NODES.gpkg'), edges=gpd.read_file('../data/WORKING_EDGES.gpkg'))

#create graph
G = network_analysis_functions.build_initial_network(network)

#create od_table of shortest paths - no interisland connectivity
od_table = network_analysis_functions.create_routes(G, network)


#%%#####################################
# SELECT THE ORIGINS OR DESTINATIONS TO WORK ON
########################################

origins = ['Lyttleton']#['Port of Napier']#['Marsden Point']##['Centreport Wellington', 'Port Chalmers']#['Port of Auckland'] # Lyttleton
destinations = []
distance = 1000
linz_key = 'fbae4ce80e684f248d7a6dcee97f992d'


#select just those OD pairs that are related to the origins or destinations above
od_pairs_selected = od_table[od_table['o_name'].isin(origins) | od_table['d_name'].isin(destinations)]

for i,rows in tqdm(od_pairs_selected.iterrows(), total=len(od_pairs_selected), desc='od pair'):
    #pull out useful data
    origin = rows.o_name
    destination = rows.d_name
    edges_along_route = rows.path_edges
    
    print('')
    print(origin,' -> ', destination)
    
    #initialise results
    route_segments = gpd.GeoDataFrame()
    route_segments_split = gpd.GeoDataFrame()
    
    #pull out the network edges along the shortest path routes
    for (from_id, to_id) in edges_along_route:

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
        
    #fill in missing data        
    route_segments['length_m'] = route_segments.geometry.length  
    
    #split into X metre segments   
    for i,rows in tqdm(route_segments.iterrows(), total=len(route_segments), desc='splitting'):
        split_edges = geometry_functions.break_line_max_length(rows.geometry, distance)
        
        for edge in split_edges:
            route_segments_split = route_segments_split.append({
                        'origin':origin,
                        'destination':destination,
                        'generic_road_class':rows['generic_road_class'],
                        'geometry':edge,
                        },ignore_index=True)
    
    #clean up
    route_segments_split['length_m'] = route_segments_split.geometry.length
    route_segments_split['geometry']=route_segments_split.geometry.apply(lambda geom: snkit.network.set_precision(geom, 0))
    route_segments_split['order']=route_segments_split.index+1
    
    #only find elevations for unique points
    all_start_points = [line.coords[0] for line in route_segments_split.geometry]
    all_end_points = [line.coords[-1] for line in route_segments_split.geometry]
    unique_points = list(set(all_start_points+all_end_points))
    
    for coords in tqdm(unique_points, total=len(unique_points), desc='finding elevations'):
        #check if elevation is already known
        if  coords in elevation_dictionary.keys():
            pass
        else:
            #store in elevation dictionary
            elevation_dictionary[coords] = elevation_functions.find_elevation_of_point(shapely.geometry.Point(coords), linz_key)

    #apply elevations
    route_segments_split['start_elevation'] = route_segments_split.geometry.apply(lambda geom: elevation_dictionary[geom.coords[0]])
    route_segments_split['end_elevation'] = route_segments_split.geometry.apply(lambda geom: elevation_dictionary[geom.coords[-1]])
    
    #save data
    results = gpd.GeoDataFrame( pd.concat( [results, route_segments_split], ignore_index=True) )
    results.crs = {'init': 'epsg:2193'}
    results['length_m'] = results.geometry.length
    results.to_file(driver='GPKG', filename='../results/raw_route_results.gpkg')   
    
    #save elevation dictionary
    pickle.dump(elevation_dictionary, open('../results/elevation_dictionary.pkl', 'wb'), protocol=pickle.HIGHEST_PROTOCOL)
    
    
#%%

 

