#A sample code to compute the convergence index (CI) from a provided aspect raster
#For references on CI, see
    #https://doi.org/10.5194/hess-14-1527-2010
    #https://doi.org/10.1016/j.geomorph.2020.107123

from osgeo import gdal
import numpy, math, os, sys

#Input path to the aspect image
inputPath = "/path/to/aspec/raster.tif"

#the window size of the CI computations. Program will take a square of width = 2 * window + 1
window = 1   

if not os.path.exists(inputPath):
    print(f"file \"{inputPath}\" does not exist")
    sys.exit() #stops the execution of this code.

#create output file path based on input
outputPath = inputPath[0:-4] + "_ConvergenceIndex.tif" 

#open the source aspect image
raster = gdal.Open(inputPath, gdal.GA_ReadOnly)

#get some details we need for output creation and computations
sourceX = raster.RasterXSize
sourceY = raster.RasterYSize
sourceBands = raster.RasterCount
sourceType = raster.GetRasterBand(1).DataType
sourceNoDataVal = raster.GetRasterBand(1).GetNoDataValue()
sourceProjection = raster.GetProjection()
sourceGeoTransform = raster.GetGeoTransform()

#"aspect" here is going to be a numpy array with the raster's values.
aspect = raster.ReadAsArray()

print (f"rows x column: {sourceY} x {sourceX}, bands: {sourceBands}, noData: {sourceNoDataVal}")

#create an output file, set its parameter to match the input
output = gdal.GetDriverByName("GTiff").Create(outputPath, xsize = sourceX, ysize = sourceY, bands = sourceBands, eType = sourceType)

output.SetProjection(sourceProjection)
output.SetGeoTransform(sourceGeoTransform)
output.GetRasterBand(1).SetNoDataValue(sourceNoDataVal)

#create a memory array to store our computations, will have a default NoData value.
dataset = numpy.full(shape=(sourceY, sourceX), fill_value= sourceNoDataVal, dtype = numpy.float32, order="C")

#Create an array to store the direction from each grid  cell to the center as an azimuth angle
centerDir = numpy.zeros((2 * window + 1, 2 * window + 1), dtype = numpy.float32)
#compute the direction-to-center array. Basic mathematics/trigonometry. 
for row in range (0, window * 2 + 1):
    for column in range (0, window * 2 + 1):
        distY = row - window
        distX = window - column
        toCenterAzimuth = math.degrees(math.atan2(distX, distY)) #atan2(opposite, adjacent), returns radians, so convert to degrees
        
        #we need the azimuth (angle from the north), the atan2() returns negatives for angles in 2nd and 3rd quadrants, we fix that first
        if (toCenterAzimuth < 0):
            toCenterAzimuth += 360
        centerDir[row, column] = toCenterAzimuth

print (centerDir)

#Now we compute the convergence index
for row in range(window, sourceY - window):
    for column in range (window, sourceX - window):
        if aspect[row, column] != sourceNoDataVal:
            #Get a slice (a "view") of the original aspect array covering only the window we are working inside
            subArray = aspect[row - window : row + window + 1, column - window : column + window + 1]
            
            #counter is the number of samples we are going to average.
            #To account for cells with possible NoData, we first need to count valid cells (minus central ones)
            # (subArrau != sourceNoDataValue) returns a boolean array with 1 for cells with data, and 0 for NoData. count_nonzero counts the former.
            counter = numpy.count_nonzero(subArray != sourceNoDataVal) - 1

            #We create a copy of the view in which we replace the NoData values with zero. Because typical values like -9999 would break the
            #summing component of the averaging process.
            sanitizedSubArray = subArray
            sanitizedSubArray[sanitizedSubArray == sourceNoDataVal] = 0.0 # This part basically tells Numpy to replace cells with values = NoData with 0.

            #Returning the delta between angles is a little bit tricker than just subtracting them (because of their cyclical nature)
            #delta_t = 180 - ||t1 - t2| - 180|
            absDiff = 180.0 - numpy.abs(numpy.abs(sanitizedSubArray - centerDir)  - 180.0)

            ci = absDiff.sum()
            
            #Old, "naive" implementation. Could be useful for demoing how things work without numpy abstraction (minus its optimisations)
            #ci = 0.0
            #counter = 0
            # for subRow in range (0, 2 * window + 1):
            #     for subColumn in range (0, 2 * window + 1):
            #         #Skip central cell and cells with noData
            #         if (subRow == window and subColumn == window) or (subArray[subRow, subColumn] == sourceNoDataVal):
            #             continue
            #         ci += 180.0 - abs(abs(subArray[subRow, subColumn] - centerDir[subRow, subColumn]) - 180.0)
            #         counter += 1

            #Some cells may have all NoData neighbours (e.g. cells near the edge), we disregard those (since they are already set as NoData. See "dataset" definition above)
            if counter > 0:
                dataset[row, column] = (ci / counter) - 90.0

output.GetRasterBand(1).WriteArray(dataset) #write the computations above to the output raster (good place to remind of the difference between memory and file)
output = None #to flush to disk, GDAL python api requies closing the file (e.g. by dereferencing) (also good place to explain about memory flushing)

print ("Done!")