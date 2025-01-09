#This script computes the longest flow path given a flow direction map (currently in TauDEM format) and outlet points ogr file
#This script doesn't cater for successive subcatchments (i.e. those downstream of others), and the lfp would simply match the 
#delineated streamline for D/S subs. See the Discrete version of this script for that case.

from osgeo import gdal, ogr
import numpy, sys, os

sys.setrecursionlimit(50000) #TODO this is a stupid hack to workaround the naivete of the recurssion implementation
#Most likely will cause a stack overflow somewhere. Try bumping the limit up for large watersheds (or downsample them)
#TODO implement file existence checks and handling I/O exceptions

#Inputs
#FDR raster
inputRasterPath = "path\\here"
#Outlets OGR file
inputOutletsPath = "path\\here"

#Value a pixel must have to be considered pouring to the central cell. From left to right, top to bottom.
usNeighboursFDR = numpy.array([[8, 7, 6], [1, 0, 5], [2, 3, 4]]) 
#TauDEM flow direction convention for FDR: 1 -East, 2 - Northeast, 3 - North, 4 - Northwest, 5 - West, 6 - Southwest, 7 - South, 8 - Southeast.
#TODO add GRASS, ArcHydro/GIS/map, etc's conventions, plus means to pick which one to use.

#cached parameters
raster = None #ref to the gdal dataset containing the raster
fdr = None #numpy array containing the raster's values
inputRasterExtents = [] #minX, minY, maxX, maxY. Note: extents include pixel widths/height at the edge.
inputRasterTransforms = [] #for use in transforming world space coords to image space coords

#defs 
def LoadInputRaster():
    global raster
    global fdr
    global inputRasterExtents
    global inputRasterTransforms 

    raster = gdal.Open(inputRasterPath, gdal.GA_ReadOnly)

    fdr = raster.ReadAsArray()
    #pad the input raster's data array with NoData to avoid adding boundary check for the edges. Note that now coordinates are shifted by (1,1)
    fdr = numpy.pad(fdr, 1, "constant", constant_values = raster.GetRasterBand(1).GetNoDataValue())
    
    #cache some parameters used continusly bellow
    inputRasterTransforms = raster.GetGeoTransform() #anchor coord x and y = 0 and 3, pixelSizeX = 1, pixelSizeY = 5
    
    x0 = inputRasterTransforms[0] - inputRasterTransforms[1] / 2.0
    y0 = inputRasterTransforms[3] + abs(inputRasterTransforms[5] / 2.0)
    x1 = x0 + raster.RasterXSize * inputRasterTransforms[1] + inputRasterTransforms[1]
    y1 = y0 - abs(raster.RasterYSize * inputRasterTransforms[5]) - abs(inputRasterTransforms[5])

    inputRasterExtents = [min(x0, x1),
                          min(y0, y1),
                          max(x0, x1),
                          max(y0, y1)]

    print (f"Loaded input raster extent: {inputRasterExtents}")

def IsWithinBounds(geoPoint : list) -> bool:
    return inputRasterExtents[0] <= geoPoint[0] <= inputRasterExtents[2] and inputRasterExtents[1] <= geoPoint[1] <= inputRasterExtents[3]

def GeoCoordToImageSpace(geoCoordPair : list) -> list:
    if not IsWithinBounds(geoCoordPair):
        return None
    
    outlet = [  int(-1 * (inputRasterTransforms[3] - geoCoordPair[1]) / inputRasterTransforms[5]) + 1,
                int((geoCoordPair[0] - inputRasterTransforms[0]) / inputRasterTransforms[1]) + 1]
    
    return outlet

def LoadOutletsAsImageSpacePoints() -> list:
    geoPoints = ogr.Open(inputOutletsPath, 0)
    featureCount = geoPoints.GetLayer().GetFeatureCount()
    print (f"Loading an outlets file with {featureCount} features")
    points = []
    
    for feature in geoPoints.GetLayer():
        geom = feature.geometry()
        geoCoords = [geom.GetX(), geom.GetY()]
        imageCoords = GeoCoordToImageSpace(geoCoords)

        if imageCoords is None:
            print (f"Warning! Coordinates {geoCoords} are outside the input raster's extents")
            continue

        points.append(imageCoords)
        print (f"{geoCoords} ----> {imageCoords}")

    return points

# #test
# LoadInputRaster()
# print (LoadOutletsAsImageSpacePoints())

# exit()
# #end test

def UpstreamNeighbours(pixel : list) -> list: #return a list of cells that pour to this point
    #get a view around the pixel
    rawNeighbours = fdr[pixel[0] - 1 : pixel[0] + 2, pixel[1] - 1 : pixel[1] + 2]
    #print (f"find neighbours for pixel {pixel}") #test
    #loop and check each neighbour if its pouring towards the centre, using usNeighboursFDR as a reference.
    usNeighbours = []
    for row in range(0, 3):
        for column in range (0, 3):
            if row == column == 1: #central cell, skip
                continue
            #print (f"neighbour {row},{column}, fdr = {rawNeighbours[row, column]}, us ref: {usNeighboursFDR[row, column]}") #test
            # if  pixel == [364, 22]: #test
            #     print (f"neighbour {row},{column}, fdr = {rawNeighbours[row, column]}, us ref: {usNeighboursFDR[row, column]}") #test
            if rawNeighbours[row, column] == usNeighboursFDR[row, column]:
                usNeighbours.append([pixel[0] + row - 1, pixel[1] + column - 1])

    return usNeighbours

# print (UpstreamNeighbours(outlet)) #test
# exit() #test

#recursive function
#caveats of this approach (other than obvious overflow risk and performance) is that it gives cardinal and ordinal neighbours same weight.
def TraceLFP(outlet : list) -> list:
    #get surrounding pixels
    usNeighbours = UpstreamNeighbours(outlet)
    
    if len(usNeighbours) == 0: #this is the heighest point. Ideally at the water divide.
        return [outlet]
    
    longestPath = TraceLFP(usNeighbours[0])

    for i in range (1, len(usNeighbours)):
        longestPath2 = TraceLFP(usNeighbours[i])
        if (len(longestPath2) > len (longestPath)):
            longestPath = longestPath2
    
    longestPath.append(outlet)
    return longestPath

def CreateOutputRasterAndArray(inputRaster, outputNoDataValue = 0):
    outputPath = baseOutputPath = os.path.dirname(inputRasterPath) + "/lfp.tif" 
    counter = 1
    while os.path.exists(outputPath):
        outputPath = baseOutputPath[:-4] + str(counter) + ".tif"
        counter += 1

    sourceX = inputRaster.RasterXSize
    sourceY = inputRaster.RasterYSize

    outputRaster = gdal.GetDriverByName("GTiff").Create(outputPath, xsize = sourceX, ysize = sourceY, bands = 1, eType = gdal.GDT_Int16)

    outputRaster.SetProjection(inputRaster.GetProjection())
    outputRaster.SetGeoTransform(inputRaster.GetGeoTransform())
    outputRaster.GetRasterBand(1).SetNoDataValue(outputNoDataValue)

    outputArray = numpy.full(shape=(sourceY, sourceX), fill_value = outputNoDataValue, dtype = numpy.int16, order="C")

    print (f"Created output raster at {outputPath}")
    return outputRaster, outputArray


#Processing steps
LoadInputRaster()
points = LoadOutletsAsImageSpacePoints()

#exit() #test
#create lfp raster based on the computed lfp
output, lfpArray = CreateOutputRasterAndArray(raster) #TODO rewrite this function. Creating output raster should happen after the loop bellow (but we need array before)

counter = 1
for point in points:
    lfp = TraceLFP(point)

    for pixel in lfp:
        #remember to adjust indexing to the padding we did above
        lfpArray[pixel[0] - 1, pixel[1] - 1] = counter
    
    counter += 1

#write to disk
output.GetRasterBand(1).WriteArray(lfpArray)
output = None

print ("Done!")