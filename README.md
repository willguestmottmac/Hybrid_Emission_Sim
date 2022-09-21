# Hybrid_Emission_Sim

## What does this simulation model?
This simulation makes a comparison of heavy duty freight trucks CO2 emissions over the trucking routes of New Zealand for both conventaional diesel ICE trucks and diesel-hybrid trucks. 

## Set up
This tool has been developed in a conda environment. The conda environement has been exported **hybrid_truc_sim.yml** (also no build option exported to **hybrid_truc_sim_no_build.yml**).

To build this environment: 

*conda env create --name {envname} --file=environments.yml*

## Method
A simulation environment was created to replicate the New Zealand heavy trucking supply chain using Python. This environment consists of modelled elevation profiles between pre-defined origin and destination. These origin and designation points were determined as locations where transported goods would either be picked up or dropped off. They were the major ports in New Zealand and distribution centres in the main centres of New Zealand. 

![nz_routes](https://user-images.githubusercontent.com/84685671/191444804-120a51ee-687e-4c96-9422-95047e883569.jpg)

From a known route with a start point set of coordinates and an endpoint set of coordinates, a shortest path algorithm was used to determine the fastest route between the two points. The origin to destination route was spliced up into segment waypoints to calculate the elevation at each waypoint. The distance between the spliced values was approximately 100m but was measured to the nearest vertices of the road. The average gradient between each waypoint can be calculated via trigonometry. From this, an elevation model was made of the route.

![svenson](https://user-images.githubusercontent.com/84685671/191446780-306c0e29-2c04-4b8f-9a0c-2c4ba6b06738.jpg)


From the Svenson Model, the fuel consumption for a truck over a given route was calculated based on an elevation profile and data relating to the IRI along the route. A modification was made to make a scaling factor that enables the weight of the truck plus load to be taken into account, using a 60-tonne truck as a reference. The weight factor is important as fuel efficiency decreases 0.5% per 1000 lbs of weight.
The fuel consumptions in L/100km for a diesel ICE truck and a diesel-hybrid truck were allotted iteratively to each iterative set of waypoints. Since the distance was known between each set of waypoints, the total fuel consumption in L can be calculated. The result was a total L fuel consumption for a given route was calculated from the sum of all the waypoint fuel consumptions.

Using a nominal diesel price of NZD $1.35 (October 2020) a fuel saving dollar value was attributed to each route per trip. 
In addition to this cost per trip, a yearly saving figure can be attached to the routes by utilising the freight volumes per year from the National Demand Freight Study. The total volume of freight between origin and destination per year can be divided by the weight of a nominal truck weight (10 tonne tractor + 30 tonne trailer load) to calculate the total number of trips done per year.

Yearly CO2 emission reductions were also calculated by multiplying the emission reduction per route by the number of routes completed per year.

## Outputs

An example of a North Island trucking route and fuel consumption:
![Auckland-BOP](https://user-images.githubusercontent.com/84685671/191445922-730ac41b-a426-4d58-b1a7-e15ee0686371.png)

An example of a South Island trucking route and fuel consumption:
![Picton-Canterbury](https://user-images.githubusercontent.com/84685671/191445986-c7b7e11e-23a7-43de-b0cb-adb27336434f.png)

Calculated freight routes and volumes:
![freight volumes](https://user-images.githubusercontent.com/84685671/191446199-f05cef97-3c6a-4070-a311-21b1b5ffcc79.jpg)

Yearly savings calculated:
![savings](https://user-images.githubusercontent.com/84685671/191447050-2dcba339-bbe1-4301-9c8e-97539dfa0a2c.jpg)

