#This script computes the longest flow path given a flow direction map (currently in TauDEM format), outlet points ogr file, and
#polygon ogr file for the subcatchments


from osgeo import gdal, ogr
import numpy, sys, os

sys.setrecursionlimit(50000) #TODO this is a stupid hack to workaround the naivete of the recurssion implementation
#Most likely will cause a stack overflow somewhere. Try bumping the limit up for large watersheds (or downsample them)
#TODO implement file existence checks and handling I/O exceptions

#Inputs
inputRasterPath = "path\\here"
inputOutletsPath = "path\\here"
inputSubcatchmentsPath = "path\\here"

tempDir = os.path.dirname(__file__) + "/tempDir/" #to store clipped rasters. Should be deleted after script finishes executing
#TODO implement exception handling that calls cleanup method in case of some issue. Otherwise this directory (and any clipped\
#rasters) will remain on disk and cause this script to break in subsequent run.

usNeighboursFDR = numpy.array([[8, 7, 6], [1, 0, 5], [2, 3, 4]]) #Value a pixel must have to be considered pouring to the central cell. From left to right, top to bottom.
#TauDEM flow direction convention for FDR: 1 -East, 2 - Northeast, 3 - North, 4 - Northwest, 5 - West, 6 - Southwest, 7 - South, 8 - Southeast.
#TODO add GRASS, ArcHydro/GIS/map, etc's conventions, plus means to pick which one to use.

outputNoDataValue = 0

#cached parameters
sourceY = 0
sourceX = 0
#sourceTransforms = []
clippedRastersRefs = [] #holds a tuple containing file path for each clipped raster, and the geometry used to clip it (as WKT)
outlets = [] #list of outlet georeferenced coordinates
outputRaster = None #ref to gdal raster for output
#outletAssociations = {} #dict(idOfOutletinOutletsList : idOfRasterPathInClippedRastersRefsList)

#defs 
def ComputeExtent(rasterPath) -> list:
    raster = gdal.Open(rasterPath, gdal.GA_ReadOnly)
    transforms = raster.GetGeoTransform() #anchor coord x and y = 0 and 3, pixelSizeX = 1, pixelSizeY = 5
    
    x0 = transforms[0] - transforms[1] / 2.0
    y0 = transforms[3] + abs(transforms[5] / 2.0)
    x1 = x0 + raster.RasterXSize * transforms[1] + transforms[1]
    y1 = y0 - abs(raster.RasterYSize * transforms[5]) - abs(transforms[5])

    extent = [  min(x0, x1),
                min(y0, y1),
                max(x0, x1),
                max(y0, y1)]
    
    return extent

def ProcessInputRaster():
    raster = gdal.Open(inputRasterPath, gdal.GA_ReadOnly)
    
    global sourceX
    global sourceY
    #global sourceTransforms

    sourceX = raster.RasterXSize
    sourceY = raster.RasterYSize
    #sourceTransforms = raster.GetGeoTransform()

    polys = ogr.Open(inputSubcatchmentsPath, 0)
    polyCount = polys.GetLayer().GetFeatureCount()
    print (f"Clipping input raster to {polyCount} subcatchemnts")
    
    #print (polys.GetLayer().GetSpatialRef())
    crs = polys.GetLayer().GetSpatialRef()
    
    os.makedirs(tempDir)

    counter = 0
    for feature in polys.GetLayer():
        outputPath = tempDir + f"clip_{counter}.tif" 
        polyAsWKT = feature.geometry().ExportToWkt()

        gdal.Warp(outputPath, raster, **{
                     "cropToCutline" : True,
                     "cutlineWKT" : polyAsWKT,
                     "cutlineSRS" : crs})

        clippedRastersRefs.append([outputPath, polyAsWKT])
        counter += 1

def LoadOutlets():
    geoPoints = ogr.Open(inputOutletsPath, 0)
    featureCount = geoPoints.GetLayer().GetFeatureCount()
    print (f"Loading an outlets file with {featureCount} features")
    
    for feature in geoPoints.GetLayer():
        geom = feature.geometry()
        geoCoords = [geom.GetX(), geom.GetY()]

        outlets.append(geoCoords)
        print (f"{geoCoords}")

def CreateOutputRaster():
    global outputRaster
    inputRaster = gdal.Open(inputRasterPath, gdal.GA_ReadOnly)

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

    #outputArray = numpy.full(shape=(sourceY, sourceX), fill_value = outputNoDataValue, dtype = numpy.int16, order="C")

    print (f"Created output raster at {outputPath}")

# def Contains(extent, point) -> bool:
#     return extent[0] <= point[0] <= extent[2] and extent[1] <= point[1] <= extent[3]

def GeoCoordToImageSpace(geoCoordPair : list, rasterPath) -> list:
    transforms = gdal.Open(rasterPath, gdal.GA_ReadOnly).GetGeoTransform()
    
    outlet = [  int(-1 * (transforms[3] - geoCoordPair[1]) / transforms[5]) + 1,
                int((geoCoordPair[0] - transforms[0]) / transforms[1]) + 1]
    
    return outlet

def LocalImageSpaceToGlobalImageSpace(pixel : list, localRaster) -> list: #converts coordinate in the clipped raster's coordinate to the large rasters coordinates
    #easiest solution (to think of) is to convert local image to georef, then georef to global
    lTransforms = localRaster.GetGeoTransform() #anchor coord x and y = 0 and 3, pixelSizeX = 1, pixelSizeY = 5
    geoCoords = [pixel[1] * lTransforms[1] + lTransforms[0],
                 lTransforms[3] - abs(pixel[0] * lTransforms[5])]
    gPixel = GeoCoordToImageSpace(geoCoords, inputRasterPath)
    return gPixel

def AssociateOutletWithRaster(outlet): #returns imagespace coord of outlet and the raster it covers (coords relative to this raster), None if no raster covers the point
    for ref in clippedRastersRefs:
        
        ogrPoint = ogr.Geometry(ogr.wkbPoint)
        ogrPoint.AddPoint(outlet[0], outlet[1])
        ogrBoundary = ogr.CreateGeometryFromWkt(ref[1])
        
        if ogrBoundary.Contains(ogrPoint):
            return GeoCoordToImageSpace(outlet, ref[0]), ref[0]

    return None, None

def UpstreamNeighbours(pixel : list, fdr) -> list: #return a list of cells that pour to this point
    #get a view around the pixel
    rawNeighbours = fdr[pixel[0] - 1 : pixel[0] + 2, pixel[1] - 1 : pixel[1] + 2]
    #loop and check each neighbour if its pouring towards the centre, using usNeighboursFDR as a reference.
    usNeighbours = []
    for row in range(0, 3):
        for column in range (0, 3):
            if row == column == 1: #central cell, skip
                continue
            if rawNeighbours[row, column] == usNeighboursFDR[row, column]:
                usNeighbours.append([pixel[0] + row - 1, pixel[1] + column - 1])

    return usNeighbours

#recursive function
#caveats of this approach (other than obvious overflow risk and performance) is that it gives cardinal and ordinal neighbours same weight.
def TraceLFP(outlet : list, fdr) -> list:
    #get surrounding pixels
    usNeighbours = UpstreamNeighbours(outlet, fdr)
    
    if len(usNeighbours) == 0: #this is the heighest point. Ideally at the water divide.
        return [outlet]
    
    longestPath = TraceLFP(usNeighbours[0], fdr)

    for i in range (1, len(usNeighbours)):
        longestPath2 = TraceLFP(usNeighbours[i], fdr)
        if (len(longestPath2) > len (longestPath)):
            longestPath = longestPath2
    
    longestPath.append(outlet)
    return longestPath

def ProcessLFPs():
    #We create one big array for the output
    lfpArray = numpy.full(shape=(sourceY, sourceX), fill_value = outputNoDataValue, dtype = numpy.int16, order="C")
    outletID = 1 #incremented for each outlet
    for rawOutlet in outlets:
        outlet, rasterPath = AssociateOutletWithRaster(rawOutlet)
        if outlet is None:
            print (f"Outlet {rawOutlet} is outside the provided raster or catchments' extents")
            continue
        
        print (f"Tracing lfp for {rawOutlet} --> {outlet} using {rasterPath}")
        raster = gdal.Open(rasterPath, gdal.GA_ReadOnly)
        #fdr is padded to avoid oob reads in the tracing loop without using condition checks
        fdr = numpy.pad(raster.ReadAsArray(), 1, "constant", constant_values = outputNoDataValue)
        lfp = TraceLFP(outlet, fdr)
        print (f"Traced an LFP of length {len(lfp)} pixels")

        for pixel in lfp:
            pixel = [pixel[0] - 1, pixel[1] - 1] #adjust for the padding
            gPixel = LocalImageSpaceToGlobalImageSpace(pixel, raster)
            
            # #test
            # if (gPixel[0] >= 3833 or gPixel[1] >= 3676):
            #     continue
            # #test

            lfpArray[gPixel[0], gPixel[1]] = outletID

        outletID += 1
    
    return lfpArray


def CleanUp():
    for ref in clippedRastersRefs:
        os.remove(ref[0])
    os.removedirs(tempDir)


ProcessInputRaster()
CreateOutputRaster()
LoadOutlets()
result = ProcessLFPs()

outputRaster.GetRasterBand(1).WriteArray(result)
outputRaster = None

CleanUp()
print ("Done!")
