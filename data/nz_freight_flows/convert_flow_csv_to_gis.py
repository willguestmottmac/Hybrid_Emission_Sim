'''
CONVERT THE flows.csv DATA INTO GIS FORMAT
'''


import geopandas as gpd
import shapely

nodes = gpd.read_file('..\\nz_regions\\simplified\\nz_regions_centroids.gpkg')
edges = gpd.read_file('flows.csv')

#ADD GEOMETRY
nodes_geom_dict = dict(zip(nodes.region_nam, nodes.geometry))

for i,rows in edges.iterrows():
    o = nodes_geom_dict[rows.Origin]
    d = nodes_geom_dict[rows.Destination]
    edges.loc[i,'geometry'] = shapely.geometry.LineString([o,d])

#SET CRS
edges.crs = nodes.crs

#ADD DIRECTION OF FLOW
for i,rows in edges.iterrows():
    start_y = rows.geometry.coords[0][1] 
    end_y = rows.geometry.coords[-1][1]
    if start_y > end_y:
        edges.loc[i,'direction'] = 'south'
    else:
        edges.loc[i,'direction'] = 'north'


#ADD MIDPOINT VERTEX
bend_factor = 100000
for i,rows in edges.iterrows():
    geom = rows.geometry
    line_length_m = geom.length
    line_coords = geom.coords[:]
    centroid_coords = geom.centroid.coords[:]
    if  rows.direction == 'north':
        new_x = centroid_coords[0][0] + 10000 * (line_length_m / bend_factor)
        new_y = centroid_coords[0][1] + 10000 * (line_length_m / bend_factor)
    else:
        new_x = centroid_coords[0][0] - 10000 * (line_length_m / bend_factor)
        new_y = centroid_coords[0][1] - 10000 * (line_length_m / bend_factor)        
    centroid_coords = [(new_x,new_y)]  
    line_coords.insert(1,centroid_coords[0])
    linestring = shapely.geometry.LineString(line_coords)
    edges.loc[i,'geometry']=linestring
    
#EXPORT
edges['million tonnes'] = edges['million tonnes'].astype(float)
edges.to_file(driver='GPKG', filename='flows.gpkg')
