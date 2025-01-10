#This script is made to extract time series for a single point from multiple precipitation rasters on disk (but can be used for any
#similar dataset). This specific script is meant for datasets with daily temporal resolution split into one raster for each day.
#The rasters must be extracted and named systematically. The name must contain the year, month and date (directly or indirectly)
#Adjust the ExtractDateStringFromName(filename : str) for each dataset naming scheme.
#Adjust the searchGlob variable 

#TODO add sampling methods other than NN.

import glob, os
from osgeo import gdal

#Inputs
pointToSample = [-1.234, 5.678] #x, y coordiantes. Must match rasters' CRS

rastersPath = "/path/to/rasters/root/dir/"

#The string searchGlob is appended to rastersPath to create the search glob wildcard.
#If for example your rasters all all in the root of rasterPath directory, then "*.tif" is enough to include all tifs in it.
#If the rasters are split between multiple subdirectories, then "*/*.tif" may be used to traverse these subdirs.
#See Python Glob function for more details.
searchGlob = "*.tif" 


outputPath = os.path.dirname(__file__) + "/output.csv"
precision = 2 #max number of decimal digits to be written in the output

#Adjust this function depending on the format of the file name.
#This function is supposed to return a string "year-month-date", e.g. "2000-08-16"
def ExtractDateStringFromName(fileName : str) -> str:
    #This implementation is for CHIPRS daily datasets with filenames like "chirps-v2.0.2001.09.03.tif"
    # splitString = fileName.split(".")
    # return "-".join([splitString[2], splitString[3], splitString[4]])
    
    #This implementation is for ARC v2 filename like: "africa_arc.19830115.tif"
    splitString = fileName.split(".")[1]
    return f"{splitString[:4]}-{splitString[4:6]}-{splitString[6:8]}"


#Processing
#Practically a nearest neighbour sampler
def SamplePoint(point, rasterPath) -> float:
    raster = gdal.Open(rasterPath, gdal.GA_ReadOnly)
    transformations = raster.GetGeoTransform() #anchor coord x and y = 0 and 3, pixelSizeX = 1, pixelSizeY = 5

    #get image space coordinate of point
    x = int((point[0] - transformations[0]) / transformations[1])
    y = int(-1 * (transformations[3] - point[1]) / transformations[5])

    return round(raster.GetRasterBand(1).ReadAsArray()[y][x], precision)

#Create a dictionary of rasters to sample
rasters = {}

for file in glob.glob(rastersPath + searchGlob):
    fileName = os.path.split(file)[1]
    rasters[ExtractDateStringFromName(fileName)] = file

print (f"Found {len(rasters)} rasters")

#sort the list based on the date (key) to make the output easier to use (Doesn't work on older python versions, I think)
rasters = dict(sorted(rasters.items()))

#Loop over dictionary and sample the time series
timeSeries = {}

for key in rasters:
    rasterPath = rasters[key]
    timeSeries[key] = SamplePoint(pointToSample, rasterPath)

#Write timeseries to disk
with open(outputPath, "w") as output:
    output.write("Date,Value\n")
    for key in timeSeries:
        output.write(f"{key},{str(timeSeries[key])}\n") #str(timeseries[key]) to force output of rounded precision above, else it would output entire float64(?) decimals.
