
'''
common geometric functions
'''

from shapely.geometry import *
import snkit
import pandas as pd
import geopandas as gpd
import snkit
from tqdm import tqdm
tqdm.pandas()
import pandas as pd
import numpy as np
import shapely



def create_network(edges):
    network = snkit.network.Network(edges=edges)
    network = snkit.network.add_endpoints(network)
    network = snkit.network.round_geometries(network, precision=3)
    network = snkit.network.add_ids(network)
    network = snkit.network.add_topology(network)
    return network


def set_nztm_crs(network):
    network.nodes.crs = {'init': 'epsg:2193'}
    network.edges.crs = {'init': 'epsg:2193'}
    return network
    
def export_to_gis(network):
    network = set_nztm_crs(network)
    network.nodes.to_file(driver='GPKG', filename='../data/road_network/nodes.gpkg')
    network.edges.to_file(driver='GPKG', filename='../data/road_network/edges.gpkg')
    return network

def explode_fast(gdf):
    gs = gdf.explode()
    gdf2 = gs.reset_index().rename(columns={0: 'geometry'})
    gdf_out = gdf2.merge(gdf.drop('geometry', axis=1), left_on='level_0', right_index=True)
    gdf_out = gdf_out.set_index(['level_0', 'level_1']).set_geometry('geometry')
    gdf_out.crs = gdf.crs
    return gdf_out

def clean_up_exploded_route(gdf):
    gdf = gdf.reset_index(drop=True)
    gdf=gdf[['origin_name_x', 'destination_name_x', 'geometry']]
    gdf=gdf.rename(columns={'origin_name_x':'origin_name', 
                            'destination_name_x':'destination_name'
                            })
    return gdf



def split_edges_at_nodes2(network, tolerance=1e-9):
    split_edges = []
    for edge in tqdm(network.edges.itertuples(index=False), desc="split", total=len(network.edges)):
        hits = snkit.network.nodes_intersecting(edge.geometry, network.nodes, tolerance)
        split_points = MultiPoint([hit.geometry for hit in hits.itertuples()])
        # potentially split to multiple edges
        edges = snkit.network.split_edge_at_points(edge, split_points, tolerance)
        split_edges.append(edges)
    # combine dfs
    edges = pd.concat(split_edges, axis=0)
    # reset index and drop
    edges = edges.reset_index().drop('index', axis=1)
    # return new network with split edges
    return snkit.network.Network(nodes=network.nodes, edges=edges)


def remove_third_dimension(geom):
    if geom.is_empty:
        return geom
    if isinstance(geom, Polygon):
        exterior = geom.exterior
        new_exterior = remove_third_dimension(exterior)

        interiors = geom.interiors
        new_interiors = []
        for int in interiors:
            new_interiors.append(remove_third_dimension(int))

        return Polygon(new_exterior, new_interiors)

    elif isinstance(geom, LinearRing):
        return LinearRing([xy[0:2] for xy in list(geom.coords)])

    elif isinstance(geom, LineString):
        return LineString([xy[0:2] for xy in list(geom.coords)])

    elif isinstance(geom, Point):
        return Point([xy[0:2] for xy in list(geom.coords)])

    elif isinstance(geom, MultiPoint):
        points = list(geom.geoms)
        new_points = []
        for point in points:
            new_points.append(remove_third_dimension(point))

        return MultiPoint(new_points)

    elif isinstance(geom, MultiLineString):
        lines = list(geom.geoms)
        new_lines = []
        for line in lines:
            new_lines.append(remove_third_dimension(line))

        return MultiLineString(new_lines)

    elif isinstance(geom, MultiPolygon):
        pols = list(geom.geoms)

        new_pols = []
        for pol in pols:
            new_pols.append(remove_third_dimension(pol))

        return MultiPolygon(new_pols)

    elif isinstance(geom, GeometryCollection):
        geoms = list(geom.geoms)

        new_geoms = []
        for geom in geoms:
            new_geoms.append(remove_third_dimension(geom))

        return GeometryCollection(new_geoms)

    else:
        raise RuntimeError("Currently this type of geometry is not supported: {}".format(type(geom)))


def merge_to_single_line_string(route_segments):
    network = create_network(route_segments)
    network.edges['road_type']=network.edges['origin_name']+'_'+network.edges['destination_name']
    
    n=network.nodes
    e= network.edges
    
    network = merge_degree2_edges(network)
    e= network.edges
    e.geometry = e.geometry.apply(snkit.network.merge_multilinestring)
    e=explode_fast(e)
    e=clean_up_exploded_route(e)
    return e


def merge_degree2_edges(network):

    if 'degree' not in network.nodes.columns:
        network.nodes['degree'] = network.nodes.id.apply(lambda x:
                                                 snkit.network.node_connectivity_degree(x,network))

    degree2 = list(network.nodes.id.loc[network.nodes.degree == 2])
    d2_set = set(degree2)
    node_paths = []
    edge_paths = []

    while d2_set:
        popped_node = d2_set.pop()
        node_path = [popped_node]
        candidates = set([popped_node])
        while candidates:
            popped_cand = candidates.pop()
            matches = list(np.unique(network.edges[['from_id','to_id']].loc[(
                    (network.edges.from_id.isin([popped_cand])) |
                    (network.edges.to_id.isin([popped_cand])))].values))
            matches.remove(popped_cand)
            for match in matches:
                if match in node_path:
                    continue

                if match in degree2:
                    candidates.add(match)
                    node_path.append(match)
                    d2_set.remove(match)
                else:
                    node_path.append(match)
        if len(node_path) > 2:
            node_paths.append(node_path)
            edge_paths.append(network.edges.loc[(
                    (network.edges.from_id.isin(node_path)) &
                    (network.edges.to_id.isin(node_path)))])

    concat_edge_paths = []
    unique_edge_ids = set()
    for edge_path in edge_paths:
        unique_edge_ids.update(list(edge_path.id))
        concat_edge_paths.append(edge_path.dissolve(by=['road_type'], aggfunc='first'))

    edges_new = network.edges.copy()
    edges_new = edges_new.loc[~(edges_new.id.isin(list(unique_edge_ids)))]
    edges_new.geometry = edges_new.geometry.apply(snkit.network.merge_multilinestring)
    network.edges = pd.concat([edges_new,pd.concat(concat_edge_paths).reset_index()],sort=False)

    nodes_new = network.nodes.copy()
    network.nodes = nodes_new.loc[~(nodes_new.id.isin(list(degree2)))]

    return snkit.network.Network(
        nodes=network.nodes,
        edges=network.edges
    )
    
    


def link_isolated_nodes_to_nearest_edge(network, condition=None):

    new_node_geoms = []
    new_edge_geoms = []
    for node in tqdm(network.nodes.itertuples(index=False), desc="link", total=len(network.nodes)):
        # find if already has a node id (string)
        if  isinstance(node.id, str): #math.isnan(node.id):
            continue
        # for each node, find edges within
        edge = snkit.network.nearest_edge(node.geometry, network.edges)
        if condition is not None and not condition(node, edge):
            continue
        # add nodes at points-nearest
        point = snkit.network.nearest_point_on_line(node.geometry, edge.geometry)
        if point != node.geometry:
            new_node_geoms.append(point)
            # add edges linking
            line = shapely.geometry.LineString([node.geometry, point])
            new_edge_geoms.append(line)

    new_nodes = snkit.network.matching_gdf_from_geoms(network.nodes, new_node_geoms)
    all_nodes = snkit.network.concat_dedup([network.nodes, new_nodes])

    new_edges = snkit.network.matching_gdf_from_geoms(network.edges, new_edge_geoms)
    all_edges = snkit.network.concat_dedup([network.edges, new_edges])

    # split edges as necessary after new node creation
    unsplit = snkit.network.Network(
        nodes=all_nodes,
        edges=all_edges
    )
    return unsplit


def split_edges_at_new_od_nodes(network, tolerance=1e-9):
    """Split network edges where they intersect one of the new OD node geometries
    """
    #reduce the search node dataframe down
    new_nodes_gdf = network.nodes[pd.isnull(network.nodes['id'])]
    
    split_edges = []
    for edge in tqdm(network.edges.itertuples(index=False), desc="split", total=len(network.edges)):
        hits = snkit.network.nodes_intersecting(edge.geometry, new_nodes_gdf, tolerance)
        split_points = shapely.geometry.MultiPoint([hit.geometry for hit in hits.itertuples()])

        # potentially split to multiple edges
        edges = snkit.network.split_edge_at_points(edge, split_points, tolerance)
        split_edges.append(edges)

    # combine dfs
    edges = pd.concat(split_edges, axis=0)
    # reset index and drop
    edges = edges.reset_index().drop('index', axis=1)
    # return new network with split edges
    return snkit.network.Network(
        nodes=network.nodes,
        edges=edges
    )
    
    

 
def create_split_edges_dataframe(single_route, distance):
    origin_name = single_route.iloc[0]['origin_name']
    destination_name = single_route.iloc[0]['destination_name']
    edge_geometries = break_line_max_length(single_route.iloc[0].geometry, distance)

    split_edges = gpd.GeoDataFrame()
    
    for geom in edge_geometries:
        split_edges=split_edges.append({'origin_name':origin_name,
                                       'destination_name':destination_name,
                                       'geometry':geom}, 
                                       ignore_index=True)
        
    split_edges['length_m']=split_edges.geometry.length    
    #split_edges.to_file(driver='GPKG', filename='../TEMP.gpkg')   
    return split_edges    
    


def break_line_max_length(line, dist):
    if line.length <= dist:
        return [line]
    else: 
        segments = cut(line, dist)
        return [segments[0]] + break_line_max_length(segments[1], dist)


def cut(line, distance):
    if distance <= 0.0 or distance >= line.length:
        return [line]
    coords = list(line.coords)
    for i, p in enumerate(coords):
        pd = line.project(shapely.geometry.Point(p)) 
        if pd == distance:
            return [
                shapely.geometry.LineString(coords[:i+1]),
                shapely.geometry.LineString(coords[i:])]
        if pd > distance:
            cp = line.interpolate(distance)
            return [
                shapely.geometry.LineString(coords[:i] + [(cp.x, cp.y)]),
                shapely.geometry.LineString([(cp.x, cp.y)] + coords[i:])]
            
            