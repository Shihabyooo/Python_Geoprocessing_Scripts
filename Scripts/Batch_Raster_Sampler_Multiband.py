#This script is made to extract time series for a single point from multiple, multiband precipitation rasters on disk (but can be used 
#for any similar dataset). 
#This implementation assumes daily data is stored in the bands of each raster in a "day of the year" fashion. i.e. the first band
#is DoY = 1 -> January 1st, second band is DoY = 2 -> January 2nd, and so on.
#The rasters must be extracted and named systematically. The name must contain the year.
#Adjust the ExtractDateStringFromName(filename : str) for each dataset naming scheme.
#Note: while some dataset (e.g. GPCC daily) is distributed as NCDF, this code was note tested for this format. You may need to convert
#them to multiband geotiffs using QGIS.

#TODO add sampling methods other than NN.

from glob import glob
from os import path
from osgeo import gdal
from datetime import datetime, timedelta

#Inputs
#pointsToSample is a dict with key = point name (to be used in output, must be unique), and value = coordinates of the point. must be in same CRS as rasters
#TODO add option to import points from vectors files (gpkg, shp, etc)
pointsToSample = {"point_1_eg" : [0.5, 1.5],
                  "point_2_eg" : [1.0, 1.5],
                  "point_3_eg" : [-0.5, 1.0]}



rastersPath = "/path/to/raster"
#The string searchGlob is appended to rastersPath to create the search glob wildcard.
#If for example your rasters all all in the root of rasterPath directory, then "/*.tif" is enough to include all tifs in it.
#If the rasters are split between multiple subdirectories, then "*/*.tif" may be used to traverse these subdirs.
#See Python Glob function for more details.
searchGlob = "/*.tif" 

outputPath = path.dirname(__file__) + "/outputFile.csv"
precision = 2 #max number of decimal digits to be written in the output

#Adjust this function depending on the format of the file name
#This implementation assumes the files to take the name "year.tif", e.g. "2000.tif"
def ExtractDateStringFromName(fileName : str) -> str: 
    splitString = fileName.split(".")
    return splitString[0]

#Processing
#Practically a nearest neighbour sampler
def SamplePoints(points : dict, rasterPath : str) -> dict:
    raster = gdal.Open(rasterPath, gdal.GA_ReadOnly)
    bandsCount = raster.RasterCount
    transformations = raster.GetGeoTransform() #anchor coord x and y = 0 and 3, pixelSizeX = 1, pixelSizeY = 5
    
    pixels = {}
    for pointID in points.keys():
        geoRefCoords = points[pointID]
        x = int((geoRefCoords[0] - transformations[0]) / transformations[1])
        y = int(-1 * (transformations[3] - geoRefCoords[1]) / transformations[5])
        pixels[pointID] = [y, x]
    
    yearStart = datetime(int(ExtractDateStringFromName(fileName = path.split(rasterPath)[1])), 1, 1)
    
    yearTS = {} #dict of dicts, date then pointID
    for doy in range (1, bandsCount+1):
        rasterArray = raster.GetRasterBand(doy).ReadAsArray()
        date = (yearStart + timedelta(days = (doy - 1))).strftime("%Y-%m-%d")
        yearTS[date] = {}
        for pointID in pixels.keys():
            pixel = pixels[pointID]
            value = round(rasterArray[pixel[0]][pixel[1]], precision)
            yearTS[date][pointID] = value
    
    return yearTS
    

#Create a dictionary of rasters to sample
rasters = []

for file in glob(rastersPath + searchGlob):
    rasters.append(file)

print (f"Found {len(rasters)} rasters")

#Loop over dictionary and sample the time series
timeSeries = {} #dict of dicts, date then pointID

for raster in rasters:
    print (f"Sampling raster {raster}")
    timeSeries = {**timeSeries, **SamplePoints(pointsToSample, raster)}

print (f"Sorting time series")
timeSeries = dict(sorted(timeSeries.items()))

#Write timeseries to disk
print (f"Writing results to {outputPath}")
with open(outputPath, "w") as output:
    header = "Date"
    pointIDs = pointsToSample.keys()
    print (f"point IDs : {pointIDs}")
    for pointID in  pointsToSample:
        header += f",{pointID}"
    header += "\n" #add breakline
    output.write(header)

    for date in timeSeries.keys():
        line = date
        for pointID in pointIDs:
            line += "," + str(timeSeries[date][pointID]) #str(timeseries[key]) to force output of rounded precision above, else it would output entire float64(?) decimals.
        line += "\n"

        output.write(line)
