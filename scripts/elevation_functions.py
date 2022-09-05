'''
FIND ELEVATION FOR A GIVEN GEOMETRY
'''

import pyproj
import functools

import urllib
import ast

import shapely

from tqdm import tqdm
tqdm.pandas()

import snkit


#%%

def convert_from_nztm_to_wsg(geom):
    wgs84 = pyproj.Proj(init='epsg:4326')
    nztm = pyproj.Proj(init='epsg:2193')
    project = functools.partial(pyproj.transform, nztm, wgs84)

    wgs84_pt = shapely.ops.transform(project, geom)
    x = wgs84_pt.coords[0][0]
    y = wgs84_pt.coords[0][1]
    return x, y


def vector_query(linz_key, layer_id, x, y):
    max_results = 99
    radius = 1
    url_search='https://data.linz.govt.nz/services/query/v1/vector.json?key='+str(linz_key)+'&layer='+str(layer_id)+'&x='+str(x)+'&y='+str(y)+'&max_results='+str(max_results)+'&radius='+str(radius)+'&geometry=true&with_field_names=true'
    scraped_data = urllib.request.urlopen(url_search).read()
    scraped_data = scraped_data.decode("UTF-8")
    try:
        scraped_data = ast.literal_eval(scraped_data)
    except:
        #try replace 'null'
        scraped_data = scraped_data.replace('null', '0')
        scraped_data = ast.literal_eval(scraped_data)
    scraped_data = scraped_data['vectorQuery']['layers'][str(layer_id)]
    return scraped_data


def raster_query(linz_key, layer_id, x, y):
    url_search='https://data.linz.govt.nz/services/query/v1/raster.json?key='+str(linz_key)+'&layer='+str(layer_id)+'&x='+str(x)+'&y='+str(y)
    scraped_data = urllib.request.urlopen(url_search).read()
    scraped_data = scraped_data.decode("UTF-8")
    scraped_data = ast.literal_eval(scraped_data)
    return scraped_data



def extract_elevation(scraped_data, layer_id):
    value = scraped_data['rasterQuery']['layers'][str(layer_id)]['bands'][0]['value']
    return value




'''
geom = G.nodes[source]['geometry']
koordiantes_key = 'ee758f9af4224aeeac9ee80cc5621880'
linz_key = 'fbae4ce80e684f248d7a6dcee97f992d'
e = find_elevation(geom, linz_key)
'''

def find_elevation_of_point(geom, linz_key):
    #convert todecimal degrees 4326
    x,y = convert_from_nztm_to_wsg(geom)
    #check linz lidar coverage map
    layer_id = 104252
    scraped_data = vector_query(linz_key, layer_id, x, y)
    
    #try DSM
    try:
        elevation = get_elevation_from_lidar(scraped_data, x, y, 'dsm_id', linz_key)
        if  elevation == None:
            pass
        else:  
            return elevation
    except:
        pass
    
    #try DEM
    try:
        elevation = get_elevation_from_lidar(scraped_data, x, y, 'dem_id', linz_key)
        if  elevation == None:
            pass
        else:  
            return elevation
    except:
        pass
    
    #try national DEM
    try:
        elevation = try_nz_dem(linz_key, x, y)
        if  elevation == None:
            pass
        else:  
            return elevation
    except:        
        pass
    
    #if nothing works
    '''TRY THE SURVEY SCHOOL DATA (15m RESOLUTIONS)'''
    koordinates_key = 'ee758f9af4224aeeac9ee80cc5621880'
    for survey_school_layer_id in tqdm([3732,3754,3734, 3736,3755,3749,3737,3759,3758, 3747,3738, 3744,3750,3741,3751,3743,3742,3740,3756,3746,3748,3731,3735,3733,3752,3753,3757,3739,3745,3730,3729,3728], desc='testing survey school data'):
        
        url_search='https://koordinates.com/services/query/v1/raster.json?key='+str(koordinates_key)+'&layer='+str(survey_school_layer_id)+'&x='+str(x)+'&y='+str(y)
        
        scraped_data = urllib.request.urlopen(url_search).read()
        scraped_data = scraped_data.decode("UTF-8")
        scraped_data = scraped_data.replace('[null]','["missing"]')
        scraped_data = ast.literal_eval(scraped_data)
    
        
        try:
            elevation = extract_elevation(scraped_data, survey_school_layer_id)
            return elevation
        except:
            pass
    
    return -999

def get_elevation_from_lidar(scraped_data, x, y, elevation_model, linz_key):
    #initialise elevation
    elevation = None
    #cycle through the layers to find the first elevation
    for features in scraped_data['features']:
        if elevation is None:
            try:
                properties = features['properties']
                layer_id = properties[elevation_model]
                #try query dsm
                elevation_data = raster_query(linz_key, layer_id, x, y)
                elevation = extract_elevation(elevation_data, layer_id)
            except:
                pass
    return elevation

def try_nz_dem(linz_key, x, y):
    #last resort, use NZ 8m DEM
    layer_id = 51768
    elevation_data = raster_query(linz_key, layer_id, x, y)
    elevation = extract_elevation(elevation_data, layer_id)
    return elevation




'''
CLEAN UP MISSING ELEVATIONS
'''  
def clean_up_missing_elevations(routes):
    #set up all known elevations - use staring points of each line   
    points = routes.copy()
    points.geometry=points.geometry.apply(lambda line: shapely.geometry.Point(line.coords[0]))
    points = points[['start_elevation', 'geometry']]
    points = points[points.start_elevation != -999]

    for i,rows in tqdm(routes.iterrows(), total=len(routes), desc='find missing elevation'):
        start = rows.start_elevation
        end = rows.end_elevation
        if   start != -999 and end != -999:
             pass
        elif start == -999 and end != -999:
             routes.loc[i,'start_elevation'] = end
        elif start != -999 and end == -999:
             routes.loc[i,'end_elevation'] =  start
        elif start == -999 and end == -999:
             #find nearest point to start
             st = shapely.geometry.Point(rows.geometry.coords[0])
             st_elevation = snkit.network.nearest(st, points)['start_elevation']
             routes.loc[i,'start_elevation'] = st_elevation

             en = shapely.geometry.Point(rows.geometry.coords[-1])
             en_elevation = snkit.network.nearest(en, points)['start_elevation']
             routes.loc[i,'end_elevation'] = en_elevation

    return routes
             
