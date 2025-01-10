#This script is made to extract time series for a single point from multiple, multiband precipitation rasters on disk (but can be used 
#for any similar dataset). 
#This implementation assumes daily data is stored in the bands of each raster in a "day of the year" fashion. i.e. the first band
#is DoY = 1 -> January 1st, second band is DoY = 2 -> January 2nd, and so on.
#The rasters must be extracted and named systematically. The name must contain the year.
#Adjust the ExtractDateStringFromName(filename : str) for each dataset naming scheme.
#Note: while some dataset (e.g. GPCC daily) is distributed as NCDF, this code was note tested for this format. You may need to convert
#them to multiband geotiffs using QGIS.

#TODO add sampling methods other than NN.

import glob, os
from osgeo import gdal
from datetime import datetime, timedelta

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

#Adjust this function depending on the format of the file name
#This implementation assumes the files to take the name "year.tif", e.g. "2000.tif"
def ExtractDateStringFromName(fileName : str) -> str:
    splitString = fileName.split(".")
    return splitString[0]


#Processing
#Practically a nearest neighbour sampler
def SamplePoint(point, rasterPath) -> dict: #{"yyyy-mm-dd" : value}
    raster = gdal.Open(rasterPath, gdal.GA_ReadOnly)
    bandsCount = raster.RasterCount
    transformations = raster.GetGeoTransform() #anchor coord x and y = 0 and 3, pixelSizeX = 1, pixelSizeY = 5

    #get image space coordinate of point
    x = int((point[0] - transformations[0]) / transformations[1])
    y = int(-1 * (transformations[3] - point[1]) / transformations[5])

    yearStart = datetime(int(ExtractDateStringFromName(fileName = os.path.split(rasterPath)[1])), 1, 1)

    yearTS = {}
    for doy in range (1, bandsCount+1):
        value = round(raster.GetRasterBand(doy).ReadAsArray()[y][x], precision)
        date = (yearStart + timedelta(days = (doy - 1))).strftime("%Y-%m-%d")
        yearTS[date] = value

    #return round(raster.GetRasterBand(1).ReadAsArray()[y][x], precision)
    return yearTS

#Create a dictionary of rasters to sample
rasters = []

for file in glob.glob(rastersPath + searchGlob):
    rasters.append(file)

print (f"Found {len(rasters)} rasters")

#Loop over dictionary and sample the time series
timeSeries = {}

for raster in rasters:
    rasterPath = raster
    timeSeries = {**timeSeries, **SamplePoint(pointToSample, rasterPath)}

timeSeries = dict(sorted(timeSeries.items()))

#Write timeseries to disk
with open(outputPath, "w") as output:
    output.write("Date,Value\n")
    for key in timeSeries:
        output.write(f"{key},{str(timeSeries[key])}\n") #str(timeseries[key]) to force output of rounded precision above, else it would output entire float64(?) decimals.
