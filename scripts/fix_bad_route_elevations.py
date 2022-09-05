# -*- coding: utf-8 -*-
"""
Created on Tue Feb  9 12:31:19 2021

@author: czor847

PATH == G:\My Drive\Will\Python Project\hybrid_freight\scripts

"""


import pandas as pd
import geopandas as gpd
import shapely
import math 
import numpy as np

#%%

#read input data
route_data = gpd.read_file('../results/Road_Edges_100m_Intervals.gpkg')

#clean up
route_data['elevation_change_m'] = route_data['end_elevation']-route_data['start_elevation']
route_data.crs = {'init':'epsg:2193'}


#%%
##### TEMP --- JUST LOOK AT HB/NORTHLAND
#####od_route = route_data[route_data['od']=='HBNorthland']


#%%

def update_the_od_data(od_route, ignore_orders):
    #drop out the lines that have been merged already (the list called 'ignore_orders')     
    od_route = od_route[~od_route['order'].isin(ignore_orders)]
    od_route['order'] = np.arange(1, len(od_route) + 1)  
    
    od_route['check']=0
    od_route.loc[od_route['alpha']>20,'check']=999
    od_route.loc[od_route['alpha']<-20,'check']=999
    remaining_errors = len(od_route[od_route['check']==999])
    print(len(od_route[od_route['check']==999]))
    print('there are errors = ', remaining_errors)
    return od_route, remaining_errors





for unique_od in route_data['od'].unique():
    print('starting>',unique_od)

    #filter to the route data
    od_route = route_data[route_data['od']==unique_od]
    #reindex just in case
    od_route['order'] = np.arange(1, len(od_route) + 1)  
    
    #initialise
    prev_remaining_errors = np.inf
    od_route, remaining_errors = update_the_od_data(od_route, ignore_orders=[])

    
    while   remaining_errors < prev_remaining_errors:
       
            prev_remaining_errors = remaining_errors
            ignore_orders = []
            
            for i,rows in od_route.iterrows():
                
                #if it's >20 degrees or <-20 degrees, also check if it's not the first or last 
                if  abs(rows.alpha) > 20 and rows.order not in [od_route.order.min(), od_route.order.max()]:
                                
                    #bad segement details
                    bad_segment_order = rows.order #order=1 if it's the first edge (start of route)
                    bad_segment_geometry = rows.geometry
                
                    #find the details of the previous edge
                    previous_order = bad_segment_order - 1
                    previous_alpha = od_route[od_route['order']==previous_order].iloc[0]['alpha']
                    previous_start_elevation = od_route[od_route['order']==previous_order].iloc[0]['start_elevation']
                    previous_geometry = od_route[od_route['order']==previous_order].iloc[0]['geometry']
                
                    #find the details of the next edge
                    next_order = bad_segment_order + 1
                    next_alpha = od_route[od_route['order']==next_order].iloc[0]['alpha'] 
                    next_end_elevation = od_route[od_route['order']==next_order].iloc[0]['end_elevation'] 
                    next_geometry = od_route[od_route['order']==next_order].iloc[0]['geometry']
                
                    #if the previous edge or next edge is also too steep, then pass
                    if   abs(previous_alpha) > 20 or abs(next_alpha) > 20:
                         pass
                    
                    elif previous_order in ignore_orders:
                         pass
                    
                    else:
                        #NEW GEOMETRY
                        #new joined geometry = previous_geom + bad_segement_geom + next_geometry
                        multi_line = shapely.geometry.MultiLineString([previous_geometry, bad_segment_geometry, next_geometry])
                        new_geometry = shapely.ops.linemerge(multi_line)
                        new_length_m = new_geometry.length
                        
                        #new start/end elevations
                        new_start_elevtaion = previous_start_elevation
                        new_end_elevation = next_end_elevation
                        new_elevation_change_m = new_end_elevation - new_start_elevtaion
                        
                        #new slope (rise/run) and alpha
                        new_slope = (new_elevation_change_m)/new_length_m
                        new_alpha = math.atan(new_elevation_change_m/new_length_m)
                        
                        #overwrite
                        od_route.loc[i,'length_m'] = new_length_m
                        od_route.loc[i,'start_elevation'] = new_start_elevtaion
                        od_route.loc[i,'end_elevation'] = new_end_elevation
                        od_route.loc[i,'slope_m/m'] = new_slope
                        od_route.loc[i,'alpha'] = new_alpha
                        od_route.loc[i,'elevation_change_m'] = new_elevation_change_m
                        
                        #we want to drop the previous and next lines because theyve been merged into one, add to a 'ignore list' for now to drop later.
                        ignore_orders = ignore_orders + [previous_order, next_order]
                        
            #check how many errors still need sorting out    
            od_route, remaining_errors = update_the_od_data(od_route, ignore_orders)
  

    print('>>>> EXPORTING', unique_od)
    od_route = od_route.drop(columns=['keep'])
    od_route.to_file(driver='GPKG', filename='../results/routes_fixed_elevations/'+unique_od+'.gpkg')
    
    
    

#%%
'''
convert elevation dictionary to points
'''
elev_dict = pd.read_pickle('../results/elevation_dictionary.pkl')
df = pd.DataFrame(elev_dict.items())
df = df.rename(columns={0:'geometry', 
                        1:'elevation_m'})
df['geometry'] = df.geometry.apply(lambda geom: shapely.geometry.Point([geom[0],geom[1]]))
gdf = gpd.GeoDataFrame(df, geometry='geometry', crs={'init':'epsg:2193'})
gdf['elevation_m'] = gdf.elevation_m.apply(lambda e: round(e,1))
gdf.to_file(driver='GPKG', filename='../results/elevation_dictionary.gpkg')