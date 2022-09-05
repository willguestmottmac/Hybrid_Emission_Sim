# -*- coding: utf-8 -*-
"""
Created on Thu Dec 17 09:00:41 2020

@author: czor847
"""

#!pip freeze > requirements.txt
#!pip install -r requirements.txt

import networkx as nx
from tqdm import tqdm
tqdm.pandas()

import pandas as pd
import geopandas as gpd

import shapely

import snkit



#%%

def build_initial_network(network):
    
    G = nx.DiGraph()
    
    #weighting dictionary
    weighting_dictionary = {'primary':1.5, #1.5 - but changed to 1.1 for the gisborne-waikato and gisborne-taranaki routes
                            'motorway':1,
                            'secondary':1.5, #1.5 - but changed to 1.1 for the gisborne-waikato and gisborne-taranaki routes
                            'trunk':1
                            }
        
    #add nodes
    for node in tqdm(network.nodes.itertuples(), total=len(network.nodes), desc='add nodes'):

        node_id = int(node.id.split('_')[1])
        
        #add node and selected attributes
        G.add_node(node_id)
        G.nodes[node_id]['location'] = node.location
        G.nodes[node_id]['island'] = node.island
        G.nodes[node_id]['geometry'] = node.geometry
        
    #add edges
    for edge in tqdm(network.edges.itertuples(), total=len(network.edges), desc='add edges'):
        from_id = int(edge.from_id.split('_')[1])
        to_id = int(edge.to_id.split('_')[1])
        
        #forward direction (as line is drawn)
        G.add_edge(from_id, to_id, weight=0)
        G.edges[from_id, to_id]['edge_id']=edge.id        
        G.edges[from_id, to_id]['road_type']=edge.road_type
        G.edges[from_id, to_id]['generic_road_class']=edge.generic_road_class
        G.edges[from_id, to_id]['length_m']=edge.length_m        
        G.edges[from_id, to_id]['geometry']=edge.geometry
        G.edges[from_id, to_id]['road_weighting']=edge.length_m * weighting_dictionary[edge.generic_road_class]
        
        
        #reverse direction (as line is drawn)
        G.add_edge(to_id, from_id, weight=0)
        G.edges[to_id, from_id]['edge_id']=edge.id     
        G.edges[to_id, from_id]['road_type']=edge.road_type
        G.edges[to_id, from_id]['generic_road_class']=edge.generic_road_class
        G.edges[to_id, from_id]['length_m']=edge.length_m        
        G.edges[to_id, from_id]['geometry']=shapely.geometry.LineString(list(edge.geometry.coords)[::-1])       
        G.edges[to_id, from_id]['road_weighting']=edge.length_m * weighting_dictionary[edge.generic_road_class]

    return G

def get_od_lists(network):
    o_geom = dict(zip(network.nodes[network.nodes['node_purpose']=='origin']['id'].tolist(),
                      network.nodes[network.nodes['node_purpose']=='origin']['geometry'].tolist()
                      ))

    d_geom = dict(zip(network.nodes[network.nodes['node_purpose']=='destination']['id'].tolist(),
                      network.nodes[network.nodes['node_purpose']=='destination']['geometry'].tolist()
                      ))

    o_name = dict(zip(network.nodes[network.nodes['node_purpose']=='origin']['id'].tolist(),
                      network.nodes[network.nodes['node_purpose']=='origin']['node_name'].tolist()
                      ))

    d_name = dict(zip(network.nodes[network.nodes['node_purpose']=='destination']['id'].tolist(),
                      network.nodes[network.nodes['node_purpose']=='destination']['node_name'].tolist()
                      ))

    return o_geom, d_geom, o_name, d_name



   
def find_island(geom, nz_islands):
    return snkit.network.nearest(geom, nz_islands)['island']


def create_od_table(network):

    #nz islands    
    nz_islands = gpd.read_file('../data/nz_outline/nz_outline.gpkg')

    #initialise
    od_table = pd.DataFrame(columns=['origin','origin_id', 'origin_name','origin_geom',
                                     'destination','destination_id', 'destination_name','destination_geom',])

    for origin in network.nodes[network.nodes['location']!='road'].itertuples():
        origin_island = origin.island
        for destination in network.nodes[network.nodes['location']!='road'].itertuples():
            destination_island = destination.island
            
            #check origin and destination in the same island
            if  origin_island == destination_island and origin.location != destination.location:
                print(origin.location, destination.location)

                od_table = od_table.append({'origin_id':origin.id,
                                            'origin':int(origin.id.split('_')[1]),
                                            'origin_name':origin.location,
                                            'origin_geom':origin.geometry,
    
                                            'destination_id':destination.id,
                                            'destination':int(destination.id.split('_')[1]),
                                            'destination_name':destination.location,
                                            'destination_geom':destination.geometry,
                                            
                                            }, ignore_index=True)            
    return od_table


def shortest_path_length(G, source, target):
    return nx.shortest_path_length(G, source, target, weight='road_weighting')
    
def shortest_path_nodes(G, source, target):
    return nx.shortest_path(G, source, target, weight='road_weighting')
    
def shortest_path_edges(G, source, target):
    nodes_list = nx.shortest_path(G, source, target, weight='road_weighting')
    return list(zip(nodes_list,nodes_list[1:]))
    
def create_routes(G, network):
    od_table = create_od_table(network)
    od_table['path_length_m'] = od_table.progress_apply(lambda row: shortest_path_length(G, row['origin'], row['destination']), axis=1)
    od_table['path_nodes'] = od_table.progress_apply(lambda row: shortest_path_nodes(G, row['origin'], row['destination']), axis=1)
    od_table['path_edges'] = od_table.progress_apply(lambda row: shortest_path_edges(G, row['origin'], row['destination']), axis=1)
    return od_table
    

#%%

