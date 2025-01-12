import logging
import os
import re
import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin


class OMASeg(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "OMASeg"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Murong"]
        self.parent.helpText = """
        3D Slicer extension for automated whole-body CT segmentation using "OMASeg" AI model.
        See more information in the <a href="https://github.com/murong-xu/SlicerOMASeg">extension documentation</a>.
        """
        self.parent.acknowledgementText = """  #TODO: cite
        This file was originally developed by Andras Lasso (PerkLab, Queen's University).
        The module uses <a href="https://github.com/murong-xu/OMASeg">OMASeg</a>.
        If you use the OMASeg from this software in your research, please cite:
        OMASeg: Open Model for Anatomy Segmentation in Computer Tomography
        """
        slicer.app.connect("startupCompleted()", self.configureDefaultTerminology)

    def configureDefaultTerminology(self):
        moduleDir = os.path.dirname(self.parent.path)
        omaSegTerminologyFilePath = os.path.join(moduleDir, 'Resources', 'SegmentationCategoryTypeModifier-OMASeg.term.json')
        tlogic = slicer.modules.terminologies.logic()
        self.terminologyName = tlogic.LoadTerminologyFromFile(omaSegTerminologyFilePath)


class OMASegWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/OMASeg.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = OMASegLogic()
        self.logic.logCallback = self.addLog

        for task in self.logic.tasks:
            taskTitle = self.logic.tasks[task]['title']
            if self.logic.isLicenseRequiredForTask(task):
                taskTitle += " [license required]"
            self.ui.taskComboBox.addItem(taskTitle, task)

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.cpuCheckBox.connect('toggled(bool)', self.updateParameterNodeFromGUI)
        self.ui.useStandardSegmentNamesCheckBox.connect('toggled(bool)', self.updateParameterNodeFromGUI)


        self.ui.taskComboBox.currentTextChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.outputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.outputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.ui.segmentationShow3DButton.setSegmentationNode)

        # Buttons
        self.ui.packageInfoUpdateButton.connect('clicked(bool)', self.onPackageInfoUpdate)
        self.ui.packageUpgradeButton.connect('clicked(bool)', self.onPackageUpgrade)
        self.ui.setLicenseButton.connect('clicked(bool)', self.onSetLicense)
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def enter(self):
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
        self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
          self.initializeParameterNode()

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        if not self._parameterNode.GetNodeReference("InputVolume"):
            firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if firstVolumeNode:
                self._parameterNode.SetNodeReferenceID("InputVolume", firstVolumeNode.GetID())

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)

        # Unobserve previously selected parameter node and add an observer to the newly selected.
        # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
        # those are reflected immediately in the GUI.
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        # Update node selectors and sliders
        self.ui.inputVolumeSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputVolume"))
        task = self._parameterNode.GetParameter("Task")
        self.ui.taskComboBox.setCurrentIndex(self.ui.taskComboBox.findData(task))
        self.ui.cpuCheckBox.checked = self._parameterNode.GetParameter("CPU") == "true"
        self.ui.useStandardSegmentNamesCheckBox.checked = self._parameterNode.GetParameter("UseStandardSegmentNames") == "true"
        self.ui.outputSegmentationSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputSegmentation"))

        # Update buttons states and tooltips
        inputVolume = self._parameterNode.GetNodeReference("InputVolume")
        if inputVolume:
            self.ui.applyButton.toolTip = "Start segmentation"
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = "Select input volume"
            self.ui.applyButton.enabled = False

        if inputVolume:
            self.ui.outputSegmentationSelector.baseName = inputVolume.GetName() + " segmentation"

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

        self._parameterNode.SetNodeReferenceID("InputVolume", self.ui.inputVolumeSelector.currentNodeID)
        self._parameterNode.SetParameter("Task", self.ui.taskComboBox.currentData)
        self._parameterNode.SetParameter("CPU", "true" if self.ui.cpuCheckBox.checked else "false")
        self._parameterNode.SetParameter("UseStandardSegmentNames", "true" if self.ui.useStandardSegmentNamesCheckBox.checked else "false")
        self._parameterNode.SetNodeReferenceID("OutputSegmentation", self.ui.outputSegmentationSelector.currentNodeID)

        self._parameterNode.EndModify(wasModified)

    def addLog(self, text):
        """Append text to log window
        """
        self.ui.statusLabel.appendPlainText(text)
        slicer.app.processEvents()  # force update

    def onApplyButton(self):
        """
        Run processing when user clicks "Apply" button.
        """
        self.ui.statusLabel.plainText = ''

        import qt

        sequenceBrowserNode = slicer.modules.sequences.logic().GetFirstBrowserNodeForProxyNode(self.ui.inputVolumeSelector.currentNode())
        if sequenceBrowserNode:  #TODO: handle sequence input
            if not slicer.util.confirmYesNoDisplay("The input volume you provided are part of a sequence. Do you want to segment all frames of that sequence?"):
                sequenceBrowserNode = None

        try:
            slicer.app.setOverrideCursor(qt.Qt.WaitCursor)
            self.logic.setupPythonRequirements()
            slicer.app.restoreOverrideCursor()
        except Exception as e:
            slicer.app.restoreOverrideCursor()
            import traceback
            traceback.print_exc()
            self.ui.statusLabel.appendPlainText(f"Failed to install Python dependencies:\n{e}\n")
            restartRequired = False
            if isinstance(e, InstallError):
                restartRequired = e.restartRequired
            if restartRequired:
                self.ui.statusLabel.appendPlainText("\nApplication restart required.")
                if slicer.util.confirmOkCancelDisplay(
                    "Application is required to complete installation of required Python packages.\nPress OK to restart.",
                    "Confirm application restart",
                    detailedText=str(e)
                    ):
                    slicer.util.restart()
                else:
                    return
            else:
                slicer.util.errorDisplay(f"Failed to install required packages.\n\n{e}")
                return

        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):
            # Create initial segmentation node if needed
            if not self.ui.outputSegmentationSelector.currentNode():
                self.ui.outputSegmentationSelector.addNode()

            self.logic.useStandardSegmentNames = self.ui.useStandardSegmentNamesCheckBox.checked

            # Process and get all created nodes
            segmentationNodes = self.logic.process(
                self.ui.inputVolumeSelector.currentNode(),
                self.ui.outputSegmentationSelector.currentNode(),
                self.ui.cpuCheckBox.checked,
                self.ui.taskComboBox.currentData,
                interactive=True,
                sequenceBrowserNode=sequenceBrowserNode
            )

            # Update UI with first node
            if segmentationNodes and len(segmentationNodes) > 0:
                self.ui.outputSegmentationSelector.setCurrentNode(segmentationNodes[0])

        self.ui.statusLabel.appendPlainText(
            f"\nProcessing finished. Created {len(segmentationNodes)} segmentation nodes."
        )

    def onPackageInfoUpdate(self):
        self.ui.packageInfoTextBrowser.plainText = ''
        with slicer.util.tryWithErrorDisplay("Failed to get OMASeg package version information", waitCursor=True):
            self.ui.packageInfoTextBrowser.plainText = self.logic.installedOMASegPythonPackageInfo().rstrip()  #TODO:

    def onPackageUpgrade(self):  #TODO: handle on-demand package update+check
        with slicer.util.tryWithErrorDisplay("Failed to upgrade OMASeg", waitCursor=True):
            self.logic.setupPythonRequirements(upgrade=True)
        self.onPackageInfoUpdate()
        if not slicer.util.confirmOkCancelDisplay(f"This OMASeg update requires a 3D Slicer restart.","Press OK to restart."):
            raise ValueError('Restart was cancelled.')
        else:
            slicer.util.restart()

    def onSetLicense(self):  #TODO: do we need to set up license?
        import qt
        licenseText = qt.QInputDialog.getText(slicer.util.mainWindow(), "Set OMASeg license key", "License key:")

        success = False
        with slicer.util.tryWithErrorDisplay("Failed to set OMASeg license.", waitCursor=True):
            if not licenseText:
                raise ValueError("License is not specified.")
            self.logic.setupPythonRequirements()
            self.logic.setLicense(licenseText)
            success = True

        if success:
            slicer.util.infoDisplay("License key is set. You can now use OMASeg tasks that require a license.")


class InstallError(Exception):
    def __init__(self, message, restartRequired=False):
        # Call the base class constructor with the parameters it needs
        super().__init__(message)
        self.message = message
        self.restartRequired = restartRequired
    def __str__(self):
        return self.message

class OMASegLogic(ScriptedLoadableModuleLogic):
    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        from collections import OrderedDict

        ScriptedLoadableModuleLogic.__init__(self)
        self.omaSegPythonPackageDownloadUrl = "https://github.com/murong-xu/OMASeg/releases/download/dev/OMASeg_SSH.zip"  #TODO:

        # Custom applications can set custom location for weights.
        # For example, it could be set to `sysconfig.get_path('scripts')` to have an independent copy of
        # the weights for each Slicer installation. However, setting such custom path would result in extra downloads and
        # storage space usage if there were multiple Slicer installations on the same computer.
        self.omaSegWeightsPath = None  #TODO: what to do with the weight path

        self.logCallback = None
        self.clearOutputFolder = True
        self.useStandardSegmentNames = True
        self.pullMaster = False

        # List of property type codes that are specified by in the OMASeg terminology.
        #
        # # Codes are stored as a list of strings containing coding scheme designator and code value of the property type,
        # separated by "^" character. For example "SCT^123456".
        #
        # If property the code is found in this list then the OMASeg terminology will be used,
        # otherwise the DICOM terminology will be used. This is necessary because the DICOM terminology
        # does not contain all the necessary items and some items are incomplete (e.g., don't have color or 3D Slicer label).
        #
        self.omaSegTerminologyPropertyTypes = []

        # Map from OMASeg structure name to terminology string.
        # Terminology string uses Slicer terminology entry format - see specification at
        # https://slicer.readthedocs.io/en/latest/developer_guide/modules/segmentations.html#terminologyentry-tag
        self.omaSegLabelTerminology = {}

        # Segmentation tasks specified by OMASeg
        # Ideally, this information should be provided by OMASeg itself.
        self.tasks = OrderedDict()

        # Define available tasks
        self._defineAvailableTasks()

    def _defineAvailableTasks(self):
        """Define all available segmentation tasks"""
        # Individual tasks
        individual_tasks = ['551', '552', '553', '554', '555', '556', '557', '558', '559']
        
        for task_id in individual_tasks:
            self.tasks[task_id] = {
                'title': task_id,
                'supportsMultiLabel': True
            }
            
        # Special 'all' task that runs all individual tasks
        self.tasks['all'] = {
            'title': 'all',
            'supportsMultiLabel': True,
            'subtasks': individual_tasks
        }

        self.loadOMASegLabelTerminology()

    def loadOMASegLabelTerminology(self):
        """Load label terminology from OMASeg_snomed_mapping.csv file.
        Terminology entries are either in DICOM or OMASeg "Segmentation category and type".
        """

        moduleDir = os.path.dirname(slicer.util.getModule('OMASeg').path)
        omaSegTerminologyMappingFilePath = os.path.join(moduleDir, 'Resources', 'omaseg_snomed_mapping.csv')

        terminologiesLogic = slicer.util.getModuleLogic('Terminologies')
        omaSegTerminologyName = "Segmentation category and type - OMASeg"

        anatomicalStructureCategory = slicer.vtkSlicerTerminologyCategory()
        numberOfCategories = terminologiesLogic.GetNumberOfCategoriesInTerminology(omaSegTerminologyName)
        for i in range(numberOfCategories):
            terminologiesLogic.GetNthCategoryInTerminology(omaSegTerminologyName, i, anatomicalStructureCategory)
            if anatomicalStructureCategory.GetCodingSchemeDesignator() == 'SCT' and anatomicalStructureCategory.GetCodeValue() == '123037004':
                # Found the (123037004, SCT, "Anatomical Structure") category within DICOM master list
                break

        alteredStructureCategory = slicer.vtkSlicerTerminologyCategory()
        for i in range(numberOfCategories):
            terminologiesLogic.GetNthCategoryInTerminology(omaSegTerminologyName, i, alteredStructureCategory)
            if alteredStructureCategory.GetCodingSchemeDesignator() == 'SCT' and alteredStructureCategory.GetCodeValue() == '49755003':
                # Found the (49755003, SCT, "Morphologically Altered Structure") category within DICOM master list
                break

        # Retrieve all property type codes from the OMASeg terminology
        self.omaSegTerminologyPropertyTypes = []
        terminologyType = slicer.vtkSlicerTerminologyType()
        numberOfTypes = terminologiesLogic.GetNumberOfTypesInTerminologyCategory(omaSegTerminologyName, anatomicalStructureCategory)
        for i in range(numberOfTypes):
            if terminologiesLogic.GetNthTypeInTerminologyCategory(omaSegTerminologyName, anatomicalStructureCategory, i, terminologyType):
                self.omaSegTerminologyPropertyTypes.append(terminologyType.GetCodingSchemeDesignator() + "^" + terminologyType.GetCodeValue())
        numberOfTypes = terminologiesLogic.GetNumberOfTypesInTerminologyCategory(omaSegTerminologyName, alteredStructureCategory)
        for i in range(numberOfTypes):
            if terminologiesLogic.GetNthTypeInTerminologyCategory(omaSegTerminologyName, alteredStructureCategory, i, terminologyType):
                self.omaSegTerminologyPropertyTypes.append(terminologyType.GetCodingSchemeDesignator() + "^" + terminologyType.GetCodeValue())

        # Helper function to get code string from CSV file row
        def getCodeString(field, columnNames, row):
            columnValues = []
            for fieldName in ["CodingSchemeDesignator", "CodeValue", "CodeMeaning"]:
                columnIndex = columnNames.index(f"{field}.{fieldName}")
                try:
                    columnValue = row[columnIndex]
                except IndexError:
                    # Probably the line in the CSV file was not terminated by multiple commas (,)
                    columnValue = ''
                columnValues.append(columnValue)
            return columnValues

        import csv
        with open(omaSegTerminologyMappingFilePath, "r") as f:
            reader = csv.reader(f)
            columnNames = next(reader)
            data = {}
            # Loop through the rows of the csv file
            for row in reader:

                # Determine segmentation category (DICOM or OMASeg)
                terminologyEntryStrWithoutCategoryName = (
                    "~"
                    # Property category: "SCT^123037004^Anatomical Structure" or "SCT^49755003^Morphologically Altered Structure"
                    + '^'.join(getCodeString("SegmentedPropertyCategoryCodeSequence", columnNames, row))
                    + '~'
                    # Property type: "SCT^23451007^Adrenal gland", "SCT^367643001^Cyst", ...
                    + '^'.join(getCodeString("SegmentedPropertyTypeCodeSequence", columnNames, row))
                    + '~'
                    # Property type modifier: "SCT^7771000^Left", ...
                    + '^'.join(getCodeString("SegmentedPropertyTypeModifierCodeSequence", columnNames, row))
                    + '~Anatomic codes - DICOM master list'
                    + '~'
                    # Anatomic region (set if category is not anatomical structure): "SCT^64033007^Kidney", ...
                    + '^'.join(getCodeString("AnatomicRegionSequence", columnNames, row))
                    + '~'
                    # Anatomic region modifier: "SCT^7771000^Left", ...
                    + '^'.join(getCodeString("AnatomicRegionModifierSequence", columnNames, row))
                    + '|')
                terminologyEntry = slicer.vtkSlicerTerminologyEntry()
                terminologyPropertyTypeStr = (  # Example: SCT^23451007
                    row[columnNames.index("SegmentedPropertyTypeCodeSequence.CodingSchemeDesignator")]
                    + "^" + row[columnNames.index("SegmentedPropertyTypeCodeSequence.CodeValue")])
                if terminologyPropertyTypeStr in self.omaSegTerminologyPropertyTypes:
                    terminologyEntryStr = "Segmentation category and type - OMASeg" + terminologyEntryStrWithoutCategoryName
                else:
                    terminologyEntryStr = "Segmentation category and type - DICOM master list" + terminologyEntryStrWithoutCategoryName

                # Store the terminology string for this structure
                omaSegStructureName = row[columnNames.index("Structure")]  # OMASeg structure name, such as "adrenal_gland_left"
                self.omaSegLabelTerminology[omaSegStructureName] = terminologyEntryStr


    def isMultiLabelSupportedForTask(self, task):
        return (task in self.tasks) and ('supportsMultiLabel' in self.tasks[task]) and self.tasks[task]['supportsMultiLabel']

    def isPreSegmentationRequiredForTask(self, task):
        return (task in self.tasks) and ('requiresPreSegmentation' in self.tasks[task]) and self.tasks[task]['requiresPreSegmentation']

    def isLicenseRequiredForTask(self, task):  # TODO: license in our model?
        return (task in self.tasks) and ('requiresLicense' in self.tasks[task]) and self.tasks[task]['requiresLicense']

    def getSegmentLabelColor(self, terminologyEntryStr):
        """Get segment label and color from terminology"""

        def labelColorFromTypeObject(typeObject):
            """typeObject is a terminology type or type modifier"""
            label = typeObject.GetSlicerLabel() if typeObject.GetSlicerLabel() else typeObject.GetCodeMeaning()
            rgb = typeObject.GetRecommendedDisplayRGBValue()
            return label, (rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)

        tlogic = slicer.modules.terminologies.logic()

        terminologyEntry = slicer.vtkSlicerTerminologyEntry()
        if not tlogic.DeserializeTerminologyEntry(terminologyEntryStr, terminologyEntry):
            raise RuntimeError(f"Failed to deserialize terminology string: {terminologyEntryStr}")

        numberOfTypes = tlogic.GetNumberOfTypesInTerminologyCategory(terminologyEntry.GetTerminologyContextName(), terminologyEntry.GetCategoryObject())
        foundTerminologyEntry = slicer.vtkSlicerTerminologyEntry()
        for typeIndex in range(numberOfTypes):
            tlogic.GetNthTypeInTerminologyCategory(terminologyEntry.GetTerminologyContextName(), terminologyEntry.GetCategoryObject(), typeIndex, foundTerminologyEntry.GetTypeObject())
            if terminologyEntry.GetTypeObject().GetCodingSchemeDesignator() != foundTerminologyEntry.GetTypeObject().GetCodingSchemeDesignator():
                continue
            if terminologyEntry.GetTypeObject().GetCodeValue() != foundTerminologyEntry.GetTypeObject().GetCodeValue():
                continue
            if terminologyEntry.GetTypeModifierObject() and terminologyEntry.GetTypeModifierObject().GetCodeValue():
                # Type has a modifier, get the color from there
                numberOfModifiers = tlogic.GetNumberOfTypeModifiersInTerminologyType(terminologyEntry.GetTerminologyContextName(), terminologyEntry.GetCategoryObject(), terminologyEntry.GetTypeObject())
                foundMatchingModifier = False
                for modifierIndex in range(numberOfModifiers):
                    tlogic.GetNthTypeModifierInTerminologyType(terminologyEntry.GetTerminologyContextName(), terminologyEntry.GetCategoryObject(), terminologyEntry.GetTypeObject(),
                        modifierIndex, foundTerminologyEntry.GetTypeModifierObject())
                    if terminologyEntry.GetTypeModifierObject().GetCodingSchemeDesignator() != foundTerminologyEntry.GetTypeModifierObject().GetCodingSchemeDesignator():
                        continue
                    if terminologyEntry.GetTypeModifierObject().GetCodeValue() != foundTerminologyEntry.GetTypeModifierObject().GetCodeValue():
                        continue
                    return labelColorFromTypeObject(foundTerminologyEntry.GetTypeModifierObject())
                continue
            return labelColorFromTypeObject(foundTerminologyEntry.GetTypeObject())

        raise RuntimeError(f"Color was not found for terminology {terminologyEntryStr}")

    def log(self, text):
        logging.info(text)
        if self.logCallback:
            self.logCallback(text)

    def installedOMASegPythonPackageDownloadUrl(self):  #TODO: how to retrieve correct URL?
        """Get package download URL of the installed OMASeg Python package"""
        import importlib.metadata
        import json
        try:
            metadataPath = [p for p in importlib.metadata.files('OMASeg') if 'direct_url.json' in str(p)][0]
            with open(metadataPath.locate()) as json_file:
                data = json.load(json_file)
            return data['url']
        except:
            # Failed to get version information, probably not installed from download URL
            return None

    def installedOMASegPythonPackageInfo(self):
        import shutil
        import subprocess
        versionInfo = subprocess.check_output([shutil.which('PythonSlicer'), "-m", "pip", "show", "OMASeg"]).decode()

        # Get download URL, as the version information does not contain the github hash
        downloadUrl = self.installedOMASegPythonPackageDownloadUrl()
        if downloadUrl:
            versionInfo += "Download URL: " + downloadUrl

        return versionInfo

    def simpleITKPythonPackageVersion(self):
        """Utility function to get version of currently installed SimpleITK.
        Currently not used, but it can be useful for diagnostic purposes.
        """

        import shutil
        import subprocess
        versionInfo = subprocess.check_output([shutil.which('PythonSlicer'), "-m", "pip", "show", "SimpleITK"]).decode()

        # versionInfo looks something like this:
        #
        #   Name: SimpleITK
        #   Version: 2.2.0rc2.dev368
        #   Summary: SimpleITK is a simplified interface to the Insight Toolkit (ITK) for image registration and segmentation
        #   ...
        #

        # Get version string (second half of the second line):
        version = versionInfo.split('\n')[1].split(' ')[1].strip()
        return version

    def pipInstallSelectiveFromLocal(self, packageToInstall, installURL, packagesToSkip):  #TODO: 优化针对OMASeg install zip file的安装
        """Installs a Python package, skipping a list of packages.
        Return the list of skipped requirements (package name with version requirement).
        """
        # TODO: 
        import os
        import zipfile
        import tempfile
        import urllib.request

        temp_dir = tempfile.mkdtemp()        
        # Check if installURL is a URL or local path
        if installURL.startswith(('http://', 'https://')):
            # Download the zip file if it's a URL
            zip_path = os.path.join(temp_dir, "package.zip")
            urllib.request.urlretrieve(installURL, zip_path)
        else:
            # Use the local path directly
            zip_path = installURL

        # check zip file structure
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
            
            # look for setup.py/pyproject.toml
            setup_files = []
            for root, dirs, files in os.walk(temp_dir):
                if 'setup.py' in files or 'pyproject.toml' in files:
                    package_dir = root
                    setup_files.extend([os.path.join(root, f) for f in files 
                                    if f in ['setup.py', 'pyproject.toml']])
                    break
            
            if not setup_files:
                raise ValueError(f"No setup.py or pyproject.toml found in {installURL}")
            
            slicer.util.pip_install(f"{package_dir} --no-deps")
        # slicer.util.pip_install(f"{installCommand} --no-deps")
        skippedRequirements = []  # list of all missed packages and their version

        # Get path to site-packages\nnunetv2-5.1.dist-info\METADATA
        import importlib.metadata
        metadataPath = [p for p in importlib.metadata.files(packageToInstall) if 'METADATA' in str(p)][0]
        metadataPath.locate()

        # Remove line: `Requires-Dist: SimpleITK (==2.0.2)`
        # User Latin-1 encoding to read the file, as it may contain non-ASCII characters and not necessarily in UTF-8 encoding.
        filteredMetadata = ""
        with open(metadataPath.locate(), "r+", encoding="latin1") as file:
            for line in file:
                skipThisPackage = False
                requirementPrefix = 'Requires-Dist: '
                if line.startswith(requirementPrefix):
                    for packageToSkip in packagesToSkip:
                        if packageToSkip in line:
                            skipThisPackage = True
                            break
                if skipThisPackage:
                    # skip SimpleITK requirement
                    skippedRequirements.append(line.removeprefix(requirementPrefix))
                    continue
                filteredMetadata += line
            # Update file content with filtered result
            file.seek(0)
            file.write(filteredMetadata)
            file.truncate()

        # Install all dependencies but the ones listed in packagesToSkip
        import importlib.metadata
        requirements = importlib.metadata.requires(packageToInstall)
        for requirement in requirements:
            skipThisPackage = False
            for packageToSkip in packagesToSkip:
                if requirement.startswith(packageToSkip):
                    # Do not install
                    skipThisPackage = True
                    break

            match = False
            if not match:
                # ruff ; extra == 'dev' -> rewrite to: ruff[extra]
                match = re.match(r"([\S]+)[\s]*; extra == '([^']+)'", requirement)
                if match:
                    requirement = f"{match.group(1)}[{match.group(2)}]"
            if not match:
                # nibabel >=2.3.0 -> rewrite to: nibabel>=2.3.0
                match = re.match("([\S]+)[\s](.+)", requirement)
                if match:
                    requirement = f"{match.group(1)}{match.group(2)}"

            if skipThisPackage:
                self.log(f'- Skip {requirement}')
            else:
                self.log(f'- Installing {requirement}...')
                slicer.util.pip_install(requirement)

        return skippedRequirements
    
    def pipInstallSelective(self, packageToInstall, installCommand, packagesToSkip):
        """Installs a Python package, skipping a list of packages.
        Return the list of skipped requirements (package name with version requirement).
        """
        slicer.util.pip_install(f"{installCommand} --no-deps")
        skippedRequirements = []  # list of all missed packages and their version

        # Get path to site-packages\nnunetv2-2.2.dist-info\METADATA
        import importlib.metadata
        metadataPath = [p for p in importlib.metadata.files(packageToInstall) if 'METADATA' in str(p)][0]
        metadataPath.locate()

        # Remove line: `Requires-Dist: SimpleITK (==2.0.2)`
        # User Latin-1 encoding to read the file, as it may contain non-ASCII characters and not necessarily in UTF-8 encoding.
        filteredMetadata = ""
        with open(metadataPath.locate(), "r+", encoding="latin1") as file:
            for line in file:
                skipThisPackage = False
                requirementPrefix = 'Requires-Dist: '
                if line.startswith(requirementPrefix):
                    # Skip dev dependencies  TODO:
                    if '; extra == "dev"' in line:
                        continue
                    for packageToSkip in packagesToSkip:
                        if packageToSkip in line:
                            skipThisPackage = True
                            break
                if skipThisPackage:
                    # skip SimpleITK requirement
                    skippedRequirements.append(line.removeprefix(requirementPrefix))
                    continue
                filteredMetadata += line
            # Update file content with filtered result
            file.seek(0)
            file.write(filteredMetadata)
            file.truncate()

        # Install all dependencies but the ones listed in packagesToSkip
        import importlib.metadata
        requirements = importlib.metadata.requires(packageToInstall)
        for requirement in requirements:
            # Skip dev dependencies  TODO:
            if '; extra == "dev"' in requirement:
                continue
            skipThisPackage = False
            for packageToSkip in packagesToSkip:
                if requirement.startswith(packageToSkip):
                    # Do not install
                    skipThisPackage = True
                    break

            match = False
            if not match:
                # ruff ; extra == 'dev' -> rewrite to: ruff[extra]
                match = re.match(r"([\S]+)[\s]*; extra == '([^']+)'", requirement)
                if match:
                    requirement = f"{match.group(1)}[{match.group(2)}]"
            if not match:
                # nibabel >=2.3.0 -> rewrite to: nibabel>=2.3.0
                match = re.match("([\S]+)[\s](.+)", requirement)
                if match:
                    requirement = f"{match.group(1)}{match.group(2)}"

            if skipThisPackage:
                self.log(f'- Skip {requirement}')
            else:
                self.log(f'- Installing {requirement}...')
                slicer.util.pip_install(requirement)

        return skippedRequirements

    def setupPythonRequirements(self, upgrade=False):
        import importlib.metadata
        import importlib.util
        import packaging

        # OMASeg requires this, yet it is not listed among its dependencies
        try:
            import pandas
        except ModuleNotFoundError as e:
            slicer.util.pip_install("pandas")

        # pillow version that is installed in Slicer (10.1.0) is too new,
        # it is incompatible with several OMASeg dependencies.
        # Attempt to uninstall and install an older version before any of the packages import  it.
        needToInstallPillow = True
        try:
            if packaging.version.parse(importlib.metadata.version("pillow")) < packaging.version.parse("10.1"):
                # A suitable pillow version is already installed
                needToInstallPillow = False
        except Exception as e:
            pass
        if needToInstallPillow:
            slicer.util.pip_install("pillow<10.1")

        # These packages come preinstalled with Slicer and should remain unchanged
        packagesToSkip = [
            'SimpleITK',  # Slicer's SimpleITK uses a special IO class, which should not be replaced
            'torch',  # needs special installation using SlicerPyTorch
            'requests',  # OMASeg would want to force a specific version of requests, which would require a restart of Slicer and it is unnecessary
            'rt_utils',  # Only needed for RTSTRUCT export, which is not needed in Slicer; rt_utils depends on opencv-python which is hard to build
            ]

        # acvl_utils workaround - start
        # Recent versions of acvl_utils are broken (https://github.com/MIC-DKFZ/acvl_utils/issues/2).
        # As a workaround, we install an older version manually. This workaround can be removed after acvl_utils is fixed.
        packagesToSkip.append("acvl_utils")
        needToInstallAcvlUtils = True
        try:
            if packaging.version.parse(importlib.metadata.version("acvl_utils")) == packaging.version.parse("0.2"):
                # A suitable version is already installed
                needToInstallAcvlUtils = False
        except Exception as e:
            pass
        if needToInstallAcvlUtils:
            slicer.util.pip_install("acvl_utils==0.2")
        # acvl_utils workaround - end

        # Install PyTorch
        try:
          import PyTorchUtils
        except ModuleNotFoundError as e:
          raise InstallError("This module requires PyTorch extension. Install it from the Extensions Manager.")

        minimumTorchVersion = "1.12"
        torchLogic = PyTorchUtils.PyTorchUtilsLogic()
        if not torchLogic.torchInstalled():
            self.log('PyTorch Python package is required. Installing... (it may take several minutes)')
            torch = torchLogic.installTorch(askConfirmation=True, torchVersionRequirement = f">={minimumTorchVersion}")
            if torch is None:
                raise InstallError("This module requires PyTorch extension. Install it from the Extensions Manager.")
        else:
            # torch is installed, check version
            from packaging import version
            if version.parse(torchLogic.torch.__version__) < version.parse(minimumTorchVersion):
                raise InstallError(f'PyTorch version {torchLogic.torch.__version__} is not compatible with this module.'
                                 + f' Minimum required version is {minimumTorchVersion}. You can use "PyTorch Util" module to install PyTorch'
                                 + f' with version requirement set to: >={minimumTorchVersion}')

        # Install OMASeg with selected dependencies only
        # (it would replace Slicer's "requests")
        needToInstallSegmenter = False
        try:
            import omaseg
            if not upgrade:
                # Check if we need to update OMASeg Python package version
                downloadUrl = self.installedOMASegPythonPackageDownloadUrl()
                if downloadUrl and (downloadUrl != self.omaSegPythonPackageDownloadUrl):
                    # OMASeg have been already installed from GitHub, from a different URL that this module needs
                    if not slicer.util.confirmOkCancelDisplay(
                        f"This module requires OMASeg Python package update.",
                        detailedText=f"Currently installed: {downloadUrl}\n\nRequired: {self.omaSegPythonPackageDownloadUrl}"):  # TODO: 
                      raise ValueError('OMASeg update was cancelled.')
                    upgrade = True
        except ModuleNotFoundError as e:
            needToInstallSegmenter = True
        upgrade = True
        if needToInstallSegmenter or upgrade:  # TODO:
            self.log(f'OMASeg Python package is required. Installing it from {self.omaSegPythonPackageDownloadUrl}... (it may take several minutes)')

            if upgrade:
                # OMASeg version information is usually not updated with each git revision, therefore we must uninstall it to force the upgrade
                slicer.util.pip_uninstall("OMASeg")

            # Update OMASeg and all its dependencies
            skippedRequirements = self.pipInstallSelectiveFromLocal(  #TODO:
                "OMASeg",
                self.omaSegPythonPackageDownloadUrl,
                packagesToSkip + ["nnunetv2"])

            # Install nnunetv2 with selected dependencies only
            # (it would replace Slicer's "SimpleITK")
            try:
                nnunetRequirement = next(requirement for requirement in skippedRequirements if requirement.startswith('nnunetv2'))
            except StopIteration:
                # nnunetv2 requirement was not found in OMASeg - this must be an error, so let's report it
                raise ValueError("nnunetv2 requirement was not found in OMASeg")
            # Remove spaces and parentheses from version requirement (convert from "nnunetv2 (==2.1)" to "nnunetv2==2.1")
            nnunetRequirement = re.sub('[ \(\)]', '', nnunetRequirement)
            self.log(f'nnunetv2 Python package is required. Installing {nnunetRequirement} ...')
            self.pipInstallSelective('nnunetv2', nnunetRequirement, packagesToSkip)

            # Workaround: fix incompatibility of dynamic_network_architectures==0.4 with totalsegmentator==2.0.5.
            # Revert to the last working version: dynamic_network_architectures==0.2
            from packaging import version
            if version.parse(importlib.metadata.version("dynamic_network_architectures")) == version.parse("0.4"):
                self.log(f'dynamic_network_architectures package version is incompatible. Installing working version...')
                slicer.util.pip_install("dynamic_network_architectures==0.2.0")

            self.log('OMASeg installation completed successfully.')


    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("Task"):
            parameterNode.SetParameter("Task", "551")
        if not parameterNode.GetParameter("UseStandardSegmentNames"):
            parameterNode.SetParameter("UseStandardSegmentNames", "true")

    def logProcessOutput(self, proc, returnOutput=False):
        # Wait for the process to end and forward output to the log
        output = ""
        from subprocess import CalledProcessError
        while True:
            try:
                line = proc.stdout.readline()
                if not line:
                    break
                if returnOutput:
                    output += line
                self.log(line.rstrip())
            except UnicodeDecodeError as e:
                # Code page conversion happens because `universal_newlines=True` sets process output to text mode,
                # and it fails because probably system locale is not UTF8. We just ignore the error and discard the string,
                # as we only guarantee correct behavior if an UTF8 locale is used.
                pass

        proc.wait()
        retcode = proc.returncode
        if retcode != 0:
            raise CalledProcessError(retcode, proc.args, output=proc.stdout, stderr=proc.stderr)
        return output if returnOutput else None


    def check_zip_extension(self, file_path):
        _, ext = os.path.splitext(file_path)

        if ext.lower() != '.zip':
            raise ValueError(f"The selected file '{file_path}' is not a .zip file!")

    @staticmethod
    def executableName(name):
        return name + ".exe" if os.name == "nt" else name

    def setLicense(self, licenseStr):

        """
        Import weights.
        Weights are provided in ZIP format.
        This function can be used without GUI widget.
        """

        # Get totalseg_import_weights command
        # totalseg_import_weights (.py file, without extension) is installed in Python Scripts folder

        if not licenseStr:
            raise ValueError(f"The license string is empty.")

        self.log('Setting license...')

        # Get Python executable path
        import shutil
        pythonSlicerExecutablePath = shutil.which('PythonSlicer')
        if not pythonSlicerExecutablePath:
            raise RuntimeError("Python was not found")

        # Get arguments
        import sysconfig
        omaSegLicenseToolExecutablePath = os.path.join(sysconfig.get_path('scripts'), OMASegLogic.executableName("totalseg_set_license"))
        cmd = [pythonSlicerExecutablePath, omaSegLicenseToolExecutablePath, "-l", licenseStr]

        # Launch command
        logging.debug(f"Launch OMASeg license tool: {cmd}")
        proc = slicer.util.launchConsoleProcess(cmd)
        licenseToolOutput = self.logProcessOutput(proc, returnOutput=True)
        if "ERROR: Invalid license number" in licenseToolOutput:
            raise ValueError('Invalid license number. Please check your license number or contact support.')

        self.log('License has been successfully set.')

        if slicer.util.confirmOkCancelDisplay(f"This license update requires a 3D Slicer restart.","Press OK to restart."):
            slicer.util.restart()
        else:
            raise ValueError('Restart was cancelled.')


    def process(self, inputVolume, outputSegmentation, cpu=False, task=None, subset=None, interactive=False, sequenceBrowserNode=None):
        """
        Run the processing algorithm.
        Parameters:
            inputVolume: Input volume node
            outputSegmentation: Initial segmentation node
            cpu: Whether to use CPU instead of GPU
            task: Task ID to run
            subset: Subset of structures to segment
            interactive: Whether running in interactive mode
            sequenceBrowserNode: Optional sequence browser node for sequence processing
        Returns:
            List of created segmentation nodes
        """
        if not inputVolume:
            raise ValueError("Input volume is invalid")

        if task == None and not subset:
            task = "all"

        import time
        startTime = time.time()
        self.log('Processing started')

        if self.omaSegWeightsPath:
            os.environ["OMASEG_WEIGHTS_PATH"] = self.omaSegWeightsPath  #TODO: how to integrate weights importing

        # Create temporary folder - moved here so it can be shared across tasks
        tempFolder = slicer.util.tempDirectory()
        inputFile = os.path.join(tempFolder, "omaseg-input.nii")
        outputSegmentationFolder = os.path.join(tempFolder, "segmentation")

        # Get Python and OMASeg paths
        import sysconfig
        import shutil
        pythonSlicerExecutablePath = shutil.which('PythonSlicer')
        if not pythonSlicerExecutablePath:
            raise RuntimeError("Python was not found")
        omaSegExecutablePath = os.path.join(sysconfig.get_path('scripts'), 
                                        self.executableName("OMASegDummy"))
        omaSegCommand = [pythonSlicerExecutablePath, omaSegExecutablePath]

        try:
            # Handle 'all' task specially
            if task == 'all':
                segmentationNodes = self._processAllTasks(
                    inputVolume, outputSegmentation, cpu, 
                    interactive, sequenceBrowserNode,
                    inputFile, outputSegmentationFolder  # Pass the temp folders
                )
                return segmentationNodes

            # Process single task
            inputVolumeSequence = None
            if sequenceBrowserNode:
                inputVolumeSequence = sequenceBrowserNode.GetSequenceNode(inputVolume)

            segmentationNodes = []

            if inputVolumeSequence is not None:
                # Handle sequence data TODO:
                segmentationSequence = sequenceBrowserNode.GetSequenceNode(outputSegmentation)
                if not segmentationSequence:
                    segmentationSequence = slicer.mrmlScene.AddNewNodeByClass(
                        "vtkMRMLSequenceNode", 
                        outputSegmentation.GetName()
                    )
                    sequenceBrowserNode.AddProxyNode(outputSegmentation, segmentationSequence, False)

                selectedItemNumber = sequenceBrowserNode.GetSelectedItemNumber()
                sequenceBrowserNode.PlaybackActiveOff()
                sequenceBrowserNode.SelectFirstItem()
                sequenceBrowserNode.SetRecording(segmentationSequence, True)
                sequenceBrowserNode.SetSaveChanges(segmentationSequence, True)

                numberOfItems = sequenceBrowserNode.GetNumberOfItems()
                for i in range(numberOfItems):
                    self.log(f"Segmenting item {i+1}/{numberOfItems} of sequence")
                    currentNodes = self.processVolume(
                        inputFile, inputVolume,
                        outputSegmentationFolder, outputSegmentation,
                        task, subset, cpu, omaSegCommand
                    )
                    if currentNodes:
                        segmentationNodes.extend(currentNodes)
                    sequenceBrowserNode.SelectNextItem()
                
                sequenceBrowserNode.SetSelectedItemNumber(selectedItemNumber)
            
            else:
                # Process single volume
                self.log(f"Writing input file to {inputFile}")
                volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
                volumeStorageNode.SetFileName(inputFile)
                volumeStorageNode.UseCompressionOff()
                volumeStorageNode.WriteData(inputVolume)
                volumeStorageNode.UnRegister(None)

                segmentationNodes = self.processVolume(
                    inputFile, inputVolume,
                    outputSegmentationFolder, outputSegmentation,
                    task, subset, cpu, omaSegCommand
                )

            stopTime = time.time()
            self.log(f"Processing completed in {stopTime-startTime:.2f} seconds")

            return segmentationNodes

        except Exception as e:
            self.log(f"Error during processing: {str(e)}")
            raise

        finally:
            # Cleanup temp folder after all processing is complete
            if self.clearOutputFolder:
                self.log("Cleaning up temporary folder...")
                if os.path.isdir(tempFolder):
                    shutil.rmtree(tempFolder)
            else:
                self.log(f"Not cleaning up temporary folder: {tempFolder}")

    def _processAllTasks(self, inputVolume, outputSegmentation, cpu, interactive, 
                    sequenceBrowserNode, inputFile, outputSegmentationFolder):
        """
        Process all tasks sequentially using the same temporary folders
        Returns list of all created segmentation nodes
        """
        allSegmentationNodes = []
        subtasks = self.tasks['all']['subtasks']
        
        # Write input volume to file once for all tasks
        self.log(f"Writing input file to {inputFile}")
        volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
        volumeStorageNode.SetFileName(inputFile)
        volumeStorageNode.UseCompressionOff()
        volumeStorageNode.WriteData(inputVolume)
        volumeStorageNode.UnRegister(None)

        # Get Python and OMASeg paths
        import sysconfig
        import shutil
        pythonSlicerExecutablePath = shutil.which('PythonSlicer')
        if not pythonSlicerExecutablePath:
            raise RuntimeError("Python was not found")
        omaSegExecutablePath = os.path.join(sysconfig.get_path('scripts'), 
                                        self.executableName("OMASegDummy"))
        omaSegCommand = [pythonSlicerExecutablePath, omaSegExecutablePath]
        
        originalName = outputSegmentation.GetName()
        for i, subtask in enumerate(subtasks):
            self.log(f'Processing task {subtask} ({i+1}/{len(subtasks)})')
            
            # Create new segmentation node for each task except first
            if i == 0:
                currentSegmentation = outputSegmentation
                currentSegmentation.SetName(f"{originalName}_{subtask}")
            else:
                currentSegmentation = slicer.mrmlScene.AddNewNodeByClass(
                    'vtkMRMLSegmentationNode',
                    f"{originalName}_{subtask}"
                )
            
            # Process current task using the same temp folders
            segNodes = self.processVolume(
                inputFile=inputFile,
                inputVolume=inputVolume,
                outputSegmentationFolder=outputSegmentationFolder,
                outputSegmentation=currentSegmentation,
                task=subtask,
                subset=None,
                cpu=cpu,
                omaSegCommand=omaSegCommand
            )
            
            if isinstance(segNodes, list):
                allSegmentationNodes.extend(segNodes)
            else:
                allSegmentationNodes.append(segNodes)

        return allSegmentationNodes
    
    def processVolume(self, inputFile, inputVolume, outputSegmentationFolder, outputSegmentation, task, subset, cpu, omaSegCommand):
        """Segment a single volume
        """

        # Write input volume to file
        # OMASeg requires NIFTI
        self.log(f"Writing input file to {inputFile}")
        volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
        volumeStorageNode.SetFileName(inputFile)
        volumeStorageNode.UseCompressionOff()
        volumeStorageNode.WriteData(inputVolume)
        volumeStorageNode.UnRegister(None)

        # Get options
        # model_folder = '/Users/murong/Desktop/tum/models'
        model_folder = '/home/jixing/Desktop/USZ/models'  #TODO: load from model folder
        if cpu:     
            options = ["-i", inputFile, "-o", outputSegmentationFolder, "--cpu", "-task", task, '-model', model_folder]
        else:
            options = ["-i", inputFile, "-o", outputSegmentationFolder, "-task", task, '-model', model_folder]

        # Launch OMASeg in fast mode to get initial segmentation, if needed

        #options.extend(["--nr_thr_saving", "1"])
        #options.append("--force_split")

        if self.isPreSegmentationRequiredForTask(task):  #TODO: check what TotalSeg did here
            preOptions = options
            self.log('Creating segmentations with OMASeg AI (pre-run)...')
            self.log(f"OMASeg arguments: {preOptions}")
            proc = slicer.util.launchConsoleProcess(omaSegCommand + preOptions)
            self.logProcessOutput(proc)

        # Launch OMASeg

        # When there are many segments then reading each segment from a separate file would be too slow,
        # but we need to do it for some specialized models.
        multilabel = self.isMultiLabelSupportedForTask(task)

        # if multilabel: TODO: 改善上面的argument input
        #     options.append("--ml")
        # if task:
        #     options.extend(["--task", task])
        # if fast:
        #     options.append("--fast")
        # if cpu:
        #     options.extend(["--device", "cpu"])
        # if subset:
        #     options.append("--roi_subset")
        #     # append each item of the subset
        #     for item in subset:
        #         try:
        #             if self.omaSegLabelTerminology[item]:
        #                 options.append(item)
        #         except:
        #             # Failed to get terminology info, item probably misspelled
        #             raise ValueError("'" + item + "' is not a valid OMASeg label terminology.")
        self.log('Creating segmentations with OMASeg AI...')
        self.log(f"OMASeg arguments: {options}")
        # proc = slicer.util.launchConsoleProcess(omaSegCommand + options)
        # self.logProcessOutput(proc)

        # Load result  TODO: 两种load
        self.log('Importing segmentation results...')
        if multilabel: 
            self.readSegmentation(
                outputSegmentation, 
                outputSegmentationFolder, 
                task
            )
        else:
            segmentationNodes = self.readSegmentationFolder(
                outputSegmentation,
                outputSegmentationFolder,
                task,
                subset
            )
            # # Set properties for all nodes
            # for segNode in segmentationNodes:
            #     self._setSegmentationNodeProperties(segNode, inputVolume)
            # return segmentationNodes
    
        # Set source volume - required for DICOM Segmentation export
        outputSegmentation.SetNodeReferenceID(outputSegmentation.GetReferenceImageGeometryReferenceRole(), inputVolume.GetID())
        outputSegmentation.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)

        # Place segmentation node in the same place as the input volume
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        inputVolumeShItem = shNode.GetItemByDataNode(inputVolume)
        studyShItem = shNode.GetItemParent(inputVolumeShItem)
        segmentationShItem = shNode.GetItemByDataNode(outputSegmentation)
        shNode.SetItemParent(segmentationShItem, studyShItem)

    def _setSegmentationNodeProperties(self, segmentationNode, inputVolume):
        """Helper method to set common properties for segmentation nodes"""
        # Set source volume reference
        segmentationNode.SetNodeReferenceID(
            segmentationNode.GetReferenceImageGeometryReferenceRole(),
            inputVolume.GetID()
        )
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)

        # Set scene placement
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        inputVolumeShItem = shNode.GetItemByDataNode(inputVolume)
        studyShItem = shNode.GetItemParent(inputVolumeShItem)
        segmentationShItem = shNode.GetItemByDataNode(segmentationNode)
        shNode.SetItemParent(segmentationShItem, studyShItem)
        
    def readSegmentationFolder(self, outputSegmentation, output_segmentation_dir, task, subset=None):
        """
        The method is very slow, but this is the only option for some specialized tasks.
        """

        import os

        outputSegmentation.GetSegmentation().RemoveAllSegments()

        # Get color node with random colors
        randomColorsNode = slicer.mrmlScene.GetNodeByID('vtkMRMLColorTableNodeRandom')
        rgba = [0, 0, 0, 0]
        # Get label descriptions

        # Get label descriptions if task is provided
        from totalsegmentator.map_to_binary import class_map  #TODO:
        labelValueToSegmentName = class_map[int(task)] if task else {}

        def import_labelmap_to_segmentation(labelmapVolumeNode, segmentName, segmentId):
            updatedSegmentIds = vtk.vtkStringArray()
            updatedSegmentIds.InsertNextValue(segmentId)
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmapVolumeNode, outputSegmentation, updatedSegmentIds)
            self.setTerminology(outputSegmentation, segmentName, segmentId)
            slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

        # Read each candidate file
        for labelValue, segmentName in labelValueToSegmentName.items():
            self.log(f"Importing candidate {segmentName}")
            labelVolumePath = os.path.join(output_segmentation_dir, f"{segmentName}.nii.gz")
            if not os.path.exists(labelVolumePath):
                self.log(f"Path {segmentName} not exists.")
                continue
            labelmapVolumeNode = slicer.util.loadLabelVolume(labelVolumePath, {"name": segmentName})
            randomColorsNode.GetColor(labelValue, rgba)
            segmentId = outputSegmentation.GetSegmentation().AddEmptySegment(segmentName, segmentName, rgba[0:3])
            import_labelmap_to_segmentation(labelmapVolumeNode, segmentName, segmentId)

        # Read each subset file if subset is provided
        if subset is not None and task is None:
            for segmentName in subset:
                self.log(f"Importing subset {segmentName}")
                labelVolumePath = os.path.join(output_segmentation_dir, f"{segmentName}.nii.gz")
                if os.path.exists(labelVolumePath):
                    labelmapVolumeNode = slicer.util.loadLabelVolume(labelVolumePath, {"name": segmentName})
                    segmentId = outputSegmentation.GetSegmentation().AddEmptySegment(segmentName, segmentName)
                    import_labelmap_to_segmentation(labelmapVolumeNode, segmentName, segmentId)
                else:
                    self.log(f"{segmentName} not found.")

        return [outputSegmentation]  # Return as list for consistency

    def readSegmentation(self, outputSegmentation, outputSegmentationFolder, task):
        # Get label descriptions
        from omaseg.dataset_utils.bodyparts_labelmaps import map_taskid_to_labelmaps
        labelValueToSegmentName = map_taskid_to_labelmaps[int(task)]
        maxLabelValue = max(labelValueToSegmentName.keys())
        if min(labelValueToSegmentName.keys()) < 0:
            raise RuntimeError("Label values in class_map must be positive")

        # Get color node with random colors
        randomColorsNode = slicer.mrmlScene.GetNodeByID('vtkMRMLColorTableNodeRandom')
        rgba = [0, 0, 0, 0]

        outputSegmentationFile = os.path.join(outputSegmentationFolder, 'segmentation_task_'+task+'.nii.gz')

        # Create color table for this segmentation task
        colorTableNode = slicer.vtkMRMLColorTableNode()
        colorTableNode.SetTypeToUser()
        colorTableNode.SetNumberOfColors(maxLabelValue+1)
        colorTableNode.SetName(str(task))  # TODO:
        for labelValue in labelValueToSegmentName:
            randomColorsNode.GetColor(labelValue,rgba)
            colorTableNode.SetColor(labelValue, rgba[0], rgba[1], rgba[2], rgba[3])
            colorTableNode.SetColorName(labelValue, labelValueToSegmentName[labelValue])
        slicer.mrmlScene.AddNode(colorTableNode)

        # Load the segmentation
        outputSegmentation.SetLabelmapConversionColorTableNodeID(colorTableNode.GetID())
        outputSegmentation.AddDefaultStorageNode()
        storageNode = outputSegmentation.GetStorageNode()
        storageNode.SetFileName(outputSegmentationFile)
        storageNode.ReadData(outputSegmentation)

        slicer.mrmlScene.RemoveNode(colorTableNode)

        # Set terminology and color
        for labelValue in labelValueToSegmentName:
            segmentName = labelValueToSegmentName[labelValue]
            segmentId = segmentName
            self.setTerminology(outputSegmentation, segmentName, segmentId)

    def setTerminology(self, segmentation, segmentName, segmentId):
        segment = segmentation.GetSegmentation().GetSegment(segmentId)  # check whether file contains segmentId
        if not segment:
            # Segment is not present in this segmentation
            return
        if segmentName in self.omaSegLabelTerminology:
            terminologyEntryStr = self.omaSegLabelTerminology[segmentName]
            segment.SetTag(segment.GetTerminologyEntryTagName(), terminologyEntryStr)
            try:
                label, color = self.getSegmentLabelColor(terminologyEntryStr)
                if self.useStandardSegmentNames:
                    segment.SetName(label)
                segment.SetColor(color)
            except RuntimeError as e:
                self.log(str(e))

#
# OMASegTest
#

class OMASegTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_OMASeg1()
        self.setUp()
        self.test_OMASegSubset()

    def test_OMASeg1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData
        inputVolume = SampleData.downloadSample('CTACardio')
        self.delayDisplay('Loaded test data set')

        outputSegmentation = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode')

        # Test the module logic

        # Logic testing is disabled by default to not overload automatic build machines (pytorch is a huge package and computation
        # on CPU takes 5-10 minutes). Set testLogic to True to enable testing.
        testLogic = False

        if testLogic:
            logic = OMASegLogic()
            logic.logCallback = self._mylog

            self.delayDisplay('Set up required Python packages')
            logic.setupPythonRequirements()

            self.delayDisplay('Compute output')
            logic.process(inputVolume, outputSegmentation)

        else:
            logging.warning("test_OMASeg1 logic testing was skipped")

        self.delayDisplay('Test passed')

    def _mylog(self,text):
        print(text)

    def test_OMASegSubset(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData
        inputVolume = SampleData.downloadSample('CTACardio')
        self.delayDisplay('Loaded test data set')

        outputSegmentation = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode')

        # Test the module logic

        # Logic testing is disabled by default to not overload automatic build machines (pytorch is a huge package and computation
        # on CPU takes 5-10 minutes). Set testLogic to True to enable testing.
        testLogic = False

        if testLogic:
            logic = OMASegLogic()
            logic.logCallback = self._mylog

            self.delayDisplay('Set up required Python packages')
            logic.setupPythonRequirements()

            self.delayDisplay('Compute output')
            _subset = ["lung_upper_lobe_left","lung_lower_lobe_right","trachea"]
            logic.process(inputVolume, outputSegmentation, subset = _subset)

        else:
            logging.warning("test_OMASeg1 logic testing was skipped")

        self.delayDisplay('Test passed')
