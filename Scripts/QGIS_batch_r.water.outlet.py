#A QGIS script to batch generate watersheds from multi-point feature and a GRASS flow direction raster.
#Tested on QGIS 3.42
#This tool does not snap outlets to stream lines.
#Flow direction raster must be in GRASS format (e.g. generated from r.watershed)
#CRS of the point layer must match that of the raster.

#TODO handle CRS mismatch.
#TODO consider switching this script to use the @alg approach. Much less LoC.
from typing import Any, Optional

from qgis.core import (
    edit,
    QgsField,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsVectorLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorDestination
)
from qgis.processing import run
from os.path import split

class ExampleProcessingAlgorithm(QgsProcessingAlgorithm):

    INPUT_POINTS = "INPUT_POINTS"
    INPUT_FIELD = "INPUT_FIELD"
    INPUT_FDR = "INPUT_FDR"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "BatchRWaterOutlet"

    def displayName(self) -> str:
        return "Batch r.water.outlet"

    def group(self) -> str:
        return "Custom Scripts"

    def groupId(self) -> str:
        return "CustomScripts"

    def shortHelpString(self) -> str:
        return "Delineating multiple points in one vector file using GRASS r.water.outlet tool.<br>This tool takes a point vector files,\
            then uses the coordinates of each point as an input to GRASS r.water.outlet, as such, the Flow DIrection Raster must be in GRASS format.\
                <br>The Field to maintain is an attribute in the input points file that would assigned to the resulting watersheds. Mainly to differentiate\
                    between output watersheds.<br>Note: Input points and raster must be in the same CRS."

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT_POINTS,
                "Input Outlet Points",
                [QgsProcessing.SourceType.TypeVectorPoint],
                optional= False
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.INPUT_FIELD,
                "Field to maintain in output",
                None,
                self.INPUT_POINTS,
                QgsProcessingParameterField.DataType.Any,
                optional = False,
            )
        )

        self.addParameter(
            QgsProcessingParameterRasterLayer(self.INPUT_FDR,
                                              "GRASS Flow Direction Raster",
                                              [],
                                              optional= False)
        )

        self.addParameter(
            QgsProcessingParameterVectorDestination(self.OUTPUT,
                                                    "Output Catchments Polygon",
                                                    optional=False,
                                                    defaultValue='TEMPORARY_OUTPUT')
        )

    def processAlgorithm(self, parameters: dict[str, Any], context: QgsProcessingContext, feedback: QgsProcessingFeedback) -> dict[str, Any]:
        
        points = self.parameterAsSource(parameters, self.INPUT_POINTS, context)
        attribName = self.parameterAsString(parameters, self.INPUT_FIELD, context)
        fdr = self.parameterAsRasterLayer(parameters, self.INPUT_FDR, context)
        outVec = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        
        feedback.pushInfo(f"Selected field {attribName}") #test

        polyList = []
        textSeperator = "".join(["-" for i in range(1, 100)]) #TODO does qgis feedback have a decorator to do this?

        sourceFieldType = QgsField (attribName, points.fields()[1].type())

        for feature in points.getFeatures():
            #delineate the watershed using r.water.outlet
            #feedback.pushInfo(f"attrib = {feature.attribute(attribName)}") #test
            #continue #test


            point = feature.geometry().asPoint()
            coords = f"{point.x()} , {point.y()}"
            feedback.pushInfo(textSeperator)
            feedback.pushInfo(f"Processing point {coords}")
            
            inputSet = {"input": fdr,
                        "coordinates" : coords,
                        "output": 'TEMPORARY_OUTPUT'}
                
            shedRaster = list(run("grass:r.water.outlet", inputSet, feedback = feedback).values())[0]

            #convert the raster to vector using polygonize
            polygonizeInputDict = {"INPUT" : shedRaster,
                               "BAND" : 1,
                               "FIELD" : "value",
                               "EIGHT_CONNECTEDNESS": True,
                               "OUTPUT" : 'TEMPORARY_OUTPUT'}
            
            shedPoly = list(run("gdal:polygonize", polygonizeInputDict, feedback = feedback).values())[0]
            #TODO run the generated polygon through fix geometries.
            
            
            #add the attribute we want to preserve to this polygon
            shedPolyLayer = QgsVectorLayer(shedPoly)
            shedPolyLayer.startEditing()
            attrib = feature.attribute(attribName)
            feedback.pushInfo(f"Appending attribute ( {attribName} = {attrib} ) to created polyon")
            shedPolyLayer.addAttribute(sourceFieldType)
            shedPolyLayer.updateFields()

            for _feature in shedPolyLayer.getFeatures(): #There shouldn't be more than one poly, but I don't really trust r.water.outlet + Polygonize combination...
                shedPolyLayer.changeAttributeValue(_feature[0], _feature.fieldNameIndex(attribName), attrib)

            shedPolyLayer.commitChanges()

            #append polygon to the list of vectors
            polyList.append(shedPoly)

        #merge the individual vectors into one, mult-feature vector layer.
        mergeInputDict = {  "LAYERS" : polyList,
                            "OUTPUT" : outVec}
            
        run("native:mergevectorlayers", mergeInputDict, feedback = feedback)

        return {"output" : outVec}

    def createInstance(self):
        return self.__class__()