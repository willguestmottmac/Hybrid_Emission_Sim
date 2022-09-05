
'''
FUEL USE
'''


import geopandas as gpd
import snkit
import shapely
import math
from tqdm import tqdm
import xlsxwriter
tqdm.pandas()

import elevation_functions

import matplotlib.pyplot as plt


linz_key = 'fbae4ce80e684f248d7a6dcee97f992d'


#%%
'''
functions
'''
def weight_scaling_factor(truck_kg, load_kg):
    '''
    Fuel Efficiency decreases 0.5% per 1000 pounds
    https://www.internationaltrucks.com/en/blog/fuel-economy-weight
    '''
    # pounds to kgs
    weight_factor = 1000 / 2.205
    # base weight for fuel consumption formula
    baseweight = 60000
    # percent change per 1000 lbs = 0.5%
    percent_change = 0.005
    #scaling factor to account for weight
    scale_factor = ((baseweight - (truck_kg + load_kg)) / weight_factor) * percent_change
    return scale_factor


def Fuel_Use_ICE(alpha, IRI, scale_factor):
    '''   
    Formula for fuel use
    Svenson-The-Influence-of-Road-Characteristics-on-Fuel-Consumption-for-Logging-Trucks.pdf

    Fuel use L/100 km
    alpha is gradient in %
    IRI is continuous in mm/m
    '''
    Fuel_Use = (46.19 + (22.13 * alpha) + (1.47 * alpha * alpha) + (7.7 * IRI)) * (1 - scale_factor)
    return Fuel_Use

def Fuel_Use_Hybrid(alpha, IRI, SF):

    # if outside of the range of model, use the fuel use for an ICE
    if -4.50 <= alpha <= 4.50:
        Percentage_diff = (-0.003*(alpha)**4) + (0.0013*(alpha)**3) + (0.0829*(alpha)**2) - (0.1515*(alpha))
        Calc = (Fuel_Use_ICE(0, IRI, SF)-(Fuel_Use_ICE(0, IRI, SF)*0.88))
        Fuel_Use_HEV = Fuel_Use_ICE(alpha, IRI, SF)-((Calc*Percentage_diff) + Calc)
    else:
        Fuel_Use_HEV = Fuel_Use_ICE(alpha, IRI, SF)
    return Fuel_Use_HEV

def gradient(routes):
    g=[]
    for i,rows in routes.iterrows():
        g.append(100 * (rows['end_elevation'] - rows['start_elevation']) / rows['length_m'])
        
    routes['alpha'] = g
    return routes


'''
def suv_study_scaling(routes):
    suv_L = []

    for i,rows in routes.iterrows():
        angle = rows.alpha
        regular_L = rows['regular_L']
        scaling = (-0.0033 * (angle ** 5)) + (0.0204 * (angle ** 4)) - (0.0117 * (angle ** 3)) - (0.0438 * (angle ** 2)) - (0.1962 * angle) + 1.6679
        suv_L.append(regular_L / scaling)

    routes['suv_L'] = suv_L
    return routes
'''


#%%
'''
READ DATA
'''
#read routes
routes = gpd.read_file('../results/routes_fixed_elevations/AucklandNorthland.gpkg')


    
#clean up route lengths
routes['length_m'] = routes.geometry.length
routes = routes[routes['length_m']>0]

# Clean up angle, slope and elevation change
for i in range(len(routes)):

    routes.loc[i, ('elevation_change_m')] = (routes.loc[i, ('end_elevation')])-(routes.loc[i, ('start_elevation')])
    routes.loc[i, ('slope_m/m')] = (routes.loc[i, ('elevation_change_m')]) / (routes.loc[i, ('length_m')])
    routes.loc[i, ('alpha')] = (math.atan(routes.loc[i, ('slope_m/m')]))*180/math.pi

#%%
'''
CONSTANTS/VARIABLES
'''
# Road Surface Type
IRI_dictionary = {'secondary':4, 
                  'trunk':2, 
                  'motorway':2, 
                  'primary':3,
                 }
# inputs
truck_kg = 23200
load_kg = 60000-truck_kg

# Weight Scaling Factor
scale_factor = weight_scaling_factor(truck_kg, load_kg)

#diesel price
diesel_cost = 1.35


#%%
'''
FUEL USE - REGULAR
'''

#find IRI
routes['IRI'] = routes['generic_road_class'].apply(lambda road_type: IRI_dictionary[road_type])

#find alpha (gradient calculation)
routes = gradient(routes)

#find fuel use
routes['regular_L_per_100km'] = routes.apply(lambda row: Fuel_Use_ICE(row['alpha'], row['IRI'], scale_factor), axis=1)
routes['regular_L_per_m'] = routes['regular_L_per_100km']/100/1000
routes['regular_L'] = routes['regular_L_per_m']*routes['length_m']

# get combined fuel use for each waypoint
route_fuel_use = routes[['origin','destination','regular_L']].groupby(['origin','destination']).sum()


#%%
'''
FUEL USE - HYBRID
'''
routes['hybrid_L_per_100km'] = routes.apply(lambda row: Fuel_Use_Hybrid(row['alpha'], row['IRI'], scale_factor), axis=1)
routes['hybrid_L_per_m'] = routes['hybrid_L_per_100km']/100/1000
routes['hybrid_L'] = routes['hybrid_L_per_m']*routes['length_m']

# get combined fuel use for each waypoint
route_fuel_use_hybrid = routes[['origin','destination','hybrid_L']].groupby(['origin','destination']).sum()
#%%

'''
OTHER METRICS
'''

#fuel cost
routes['regular_$'] = routes['regular_L'] * diesel_cost
routes['hybrid_$'] = routes['hybrid_L'] * diesel_cost


#savings per edge
routes['hybrid_savings_pc'] = 100*(routes['regular_L'] - routes['hybrid_L']) / routes['regular_L']

#export
routes.to_file(driver='GPKG', filename='../results/results_raw.gpkg')



#aggregated results
results_gdf = routes.dissolve(by=['origin', 'destination'], aggfunc='sum').reset_index() 
results_gdf = results_gdf[['origin', 'destination', 'length_m', 'regular_L', 'hybrid_L', 'regular_$', 'hybrid_$', 'geometry']]

#savings
results_gdf['hybrid_savings_pc'] = 100*(results_gdf['regular_L'] - results_gdf['hybrid_L']) / results_gdf['regular_L']

#emissions
results_gdf['CO2_emission_reduction_kg'] = (results_gdf['regular_L'] - results_gdf['hybrid_L'])*2.460

#export
results_gdf.to_file(driver='GPKG', filename='../results/results_dissolved.gpkg')

#%%
'''
PLOT QUICK MAP
'''
world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
nz = world[world['name']=='New Zealand']
nz = nz.to_crs(epsg=2193)

#%%
'''
PLOT DISTANCE VS FUEL USE
'''
routes['OD'] = routes['origin']+'-'+routes['destination']

#routes = routes[routes['origin']=='Lyttleton']

for OD in routes['OD'].unique():
    #filter data
    data = routes[routes['OD']==OD]
    
    #compute cumulative length
    data['length_m_cum'] = data['length_m'].cumsum()
    data['length_km_cum'] = data['length_m_cum']/1000

    #compute cumulative fuel use
    data['regular_L_cum'] = data['regular_L'].cumsum()
    data['hybrid_L_cum'] = data['hybrid_L'].cumsum()
        
    #plotting
    fig, ax1 = plt.subplots(constrained_layout=True)
    
    #elevation vs distance
    ax1.fill_between(data['length_km_cum'], data['end_elevation'], 0, color='k', alpha=0.2, lw=0)
    
    #fuel use vs distance
    ax2 = ax1.twinx()
    ax2.plot(data['length_km_cum'], data['regular_L_cum'], color='k', alpha=0.5, label='Regular')
    ax2.plot(data['length_km_cum'], data['hybrid_L_cum'], color='blue', alpha=0.5, label='Hybrid')
    
    
    ax2.tick_params(axis='y', labelcolor='k')
    
    #properties
    ax1.set_title(OD)
    ax1.set_xlabel("Distance (km)")
    ax1.set_ylabel("Elevation (m)")
    ax2.legend()
    
    ax2.set_ylabel('Cumulative Fuel Use (L)', color='k')  # we already handled the x-label with ax1
    
    plt.savefig('../figures/'+OD+'.png')
    
    



'''
results_df.to_csv('test.csv')

# plot
plt.plot(combined_distance[0:100], combined_fuel_use[0:100])
plt.title('Fuel Use Profile')
plt.ylabel('Fuel Use (L)')
plt.xlabel('Distance (km)')
plt.show()
'''

# workbook = xlsxwriter.Workbook('output.xlsx')
# worksheet = workbook.add_worksheet()

# for row in range(len(routes)):
#     for col in range(len(routes)):
results_gdf.to_excel('output2.xlsx', engine='xlsxwriter')
        #worksheet.write(row + 1, col, round(Collected[col-1],2))
# workbook.close()