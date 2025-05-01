import logging
import os
import glob
import re
import vtk
import qt

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin


class CADS(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CADS"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Murong Xu (University of Zurich)"]
        self.parent.helpText = """
        3D Slicer extension that provides automated whole-body CT segmentation powered by CADS AI model.
        See more information in the <a href="https://github.com/murong-xu/SlicerCADS">extension documentation</a>.
        """
        self.parent.acknowledgementText = """#TODO: use most recent cite
        This extension was developed by Murong Xu (University of Zurich), building upon the foundational framework by Andras Lasso (PerkLab, Queen's University).
        The core segmentation functionality is powered by <a href="https://github.com/murong-xu/CADS">CADS</a>.

        If you use this software in your research, please cite:
        Xu et al., "CADS: Comprehensive Anatomical Dataset and Segmentation for Whole-body CT"
        """
        slicer.app.connect("startupCompleted()",
                           self.configureDefaultTerminology)

    def configureDefaultTerminology(self):
        moduleDir = os.path.dirname(self.parent.path)
        cadsTerminologyFilePath = os.path.join(
            moduleDir, 'Resources', 'SegmentationCategoryTypeModifier-CADS.term.json')
        tlogic = slicer.modules.terminologies.logic()
        self.terminologyName = tlogic.LoadTerminologyFromFile(
            cadsTerminologyFilePath)


class CADSWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/CADS.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CADSLogic()
        self.logic.logCallback = self.addLog

        self.initializeParameterNode()
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene,
                         slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Create button group for radio buttons and connect signals
        self.targetModeGroup = qt.QButtonGroup()
        self.targetModeGroup.addButton(self.ui.allTargetsRadio)
        self.targetModeGroup.addButton(self.ui.subsetTargetsRadio)
        self.targetModeGroup.buttonClicked.connect(self.onTargetModeChanged)

        # Add tasks to taskComboBox
        self.ui.taskComboBox.clear()
        try:
            for task in self.logic.tasks:
                taskTitle = self.logic.tasks[task]['title']
                self.ui.taskComboBox.addItem(str(taskTitle), str(task))
        except Exception as e:
            print(f"Error adding tasks: {str(e)}")

        # Connect all buttons and controls to appropriate slots
        self.ui.inputVolumeSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.taskComboBox.currentIndexChanged.connect(
            self.updateParameterNodeFromGUI)
        self.ui.taskComboBox.currentIndexChanged.connect(
            self.updateTargetsList)
        self.ui.targetsList.itemSelectionChanged.connect(
            self.updateParameterNodeFromGUI)
        self.ui.outputSegmentationSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.useStandardSegmentNamesCheckBox.connect(
            "toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.cpuCheckBox.connect(
            "toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
        self.ui.packageUpgradeButton.connect(
            'clicked(bool)', self.onPackageUpgrade)
        self.ui.packageInfoUpdateButton.connect(
            'clicked(bool)', self.onPackageInfoUpdate)

        # Initial GUI update
        self.updateGUIFromParameterNode()
        self.updateTargetsList()

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
        self.removeObserver(
            self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

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
            firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass(
                "vtkMRMLScalarVolumeNode")
            if firstVolumeNode:
                self._parameterNode.SetNodeReferenceID(
                    "InputVolume", firstVolumeNode.GetID())

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
            self.removeObserver(
                self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(
                self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

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

        # Update task
        currentIndex = self.ui.taskComboBox.currentIndex
        if currentIndex >= 0:
            task = self.ui.taskComboBox.itemData(currentIndex)
            self._parameterNode.SetParameter("Task", str(task))
        
        # Update selected targets
        selectedTargets = self.getSelectedTargets()
        self._parameterNode.SetParameter("Targets", ','.join(selectedTargets))

        self._parameterNode.SetParameter("CPU", "true" if self.ui.cpuCheckBox.checked else "false")
        self._parameterNode.SetParameter("UseStandardSegmentNames", "true" if self.ui.useStandardSegmentNamesCheckBox.checked else "false")
        self._parameterNode.SetNodeReferenceID("OutputSegmentation", self.ui.outputSegmentationSelector.currentNodeID)
        self._parameterNode.SetParameter("TargetMode", "all" if self.ui.allTargetsRadio.isChecked() else "subset")

        self._parameterNode.EndModify(wasModified)

    def updateTargetsList(self):
        """Update available targets based on selected task"""
        if not hasattr(self, 'ui') or not self.ui.targetsList:
            return
                
        self.ui.targetsList.clear()
        
        # Get current task
        currentTask = self.ui.taskComboBox.currentData
        if not currentTask:
            self.ui.targetsList.setEnabled(False)
            return
                
        try:
            from cads.dataset_utils.bodyparts_labelmaps import map_taskid_to_labelmaps
            
            if currentTask == 'all':
                self.ui.targetsList.setEnabled(True)
                all_targets = []
                for subtask in range(551, 560):  # 551-559
                    labelValueToSegmentName = map_taskid_to_labelmaps[subtask]
                    availableTargets = list(labelValueToSegmentName.values())
                    if 'background' in availableTargets:
                        availableTargets.remove('background')
                    for target in availableTargets:
                        all_targets.append(target)
                
                # Convert to SNOMED
                availableTargets_snomed = [
                    self.logic.getSegmentLabelColor(self.logic.cadsLabelTerminology[i]['terminologyStr'])[0] 
                    for i in all_targets
                ]

            else:
                labelValueToSegmentName = map_taskid_to_labelmaps[int(currentTask)]
                availableTargets = list(labelValueToSegmentName.values())
                if 'background' in availableTargets:
                    availableTargets.remove('background')
                availableTargets_snomed = [
                    self.logic.getSegmentLabelColor(self.logic.cadsLabelTerminology[i]['terminologyStr'])[0] 
                    for i in availableTargets
                ]
            
            # Add targets to list widget
            for target in availableTargets_snomed:
                item = qt.QListWidgetItem(str(target))
                self.ui.targetsList.addItem(item)
            
            # Update 'available targetlist' according to radio button
            if self.ui.allTargetsRadio.isChecked():
                # if select 'all': disable the subset selection
                for i in range(self.ui.targetsList.count):
                    self.ui.targetsList.item(i).setSelected(True)
                self.ui.targetsList.setEnabled(False)
            else:
                # if select "Select targets" mode: let user select which ones to show
                self.ui.targetsList.setEnabled(True)

        except ImportError:
            # CADS package not installed (when open this extension for the very 1st time)
            self.ui.targetsList.addItem("CADS package needs to be installed first.")
            self.ui.targetsList.addItem("You can either:")
            self.ui.targetsList.addItem("1. Click 'Force install dependencies' to install packages directly")
            self.ui.targetsList.addItem("2. Upload a CT image and click 'Apply' to install and run")
            self.ui.targetsList.addItem("(Installation may take a few minutes)")
            self.ui.targetsList.setEnabled(False)
            return
        except Exception as e:
            print(f"Error updating targets: {str(e)}")
            import traceback
            traceback.print_exc()
            self.ui.targetsList.setEnabled(False)

    def onTargetModeChanged(self):
        """Handle changes in target selection mode"""
        if self.ui.allTargetsRadio.isChecked():
            # Select all items in the list
            for i in range(self.ui.targetsList.count):
                self.ui.targetsList.item(i).setSelected(True)
            self.ui.targetsList.setEnabled(False)  # Disable manual selection
        else:
            self.ui.targetsList.clearSelection()
            self.ui.targetsList.setEnabled(True)  # Enable manual selection        
        self.updateParameterNodeFromGUI()

    def getSelectedTargets(self):
        """Get list of currently selected targets"""
        selectedTargets = []
        if hasattr(self.ui, 'targetsList'):
            selectedItems = self.ui.targetsList.selectedItems()
            selectedTargets = [item.text() for item in selectedItems]
        return selectedTargets

    
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
        subset = None
        if self._parameterNode:
            targetsStr = self._parameterNode.GetParameter("Targets")
            if targetsStr:
                subset = targetsStr.split(',')

        # Check if input is a sequence/4D data
        inputIsSequenceData = slicer.modules.sequences.logic().GetFirstBrowserNodeForProxyNode(self.ui.inputVolumeSelector.currentNode())
        if inputIsSequenceData:
            slicer.util.messageBox(
                "Input Data Type Error\n\n"
                "CADS model is designed for single-phase 3D CT volumes only.\n"
                "The selected input appears to be a 4D/sequence dataset, which is not supported.\n\n"
                "Please select a standard 3D CT volume to proceed."
            )
            self.ui.inputVolumeSelector.setCurrentNode(None)  # Clear invalid selection
            return False

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
                subset=subset
            )

            # Update UI with first node
            if segmentationNodes and len(segmentationNodes) > 0:
                self.ui.outputSegmentationSelector.setCurrentNode(segmentationNodes[0])

        self.ui.statusLabel.appendPlainText(
            f"\nProcessing finished. Created {len(segmentationNodes)} segmentation nodes."
        )

    def onPackageInfoUpdate(self):
        self.ui.packageInfoTextBrowser.plainText = ''
        with slicer.util.tryWithErrorDisplay("Failed to get CADS package version information", waitCursor=True):
            self.ui.packageInfoTextBrowser.plainText = self.logic.installedCADSPythonPackageInfo().rstrip()

    def onPackageUpgrade(self):
        with slicer.util.tryWithErrorDisplay("Failed to upgrade CADS", waitCursor=True):
            self.logic.setupPythonRequirements(upgrade=True)
        self.onPackageInfoUpdate()
        if not slicer.util.confirmOkCancelDisplay(f"This CADS update requires a 3D Slicer restart.","Press OK to restart."):
            raise ValueError('Restart was cancelled.')
        else:
            slicer.util.restart()

class InstallError(Exception):
    def __init__(self, message, restartRequired=False):
        # Call the base class constructor with the parameters it needs
        super().__init__(message)
        self.message = message
        self.restartRequired = restartRequired
    def __str__(self):
        return self.message

class CADSLogic(ScriptedLoadableModuleLogic):
    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        from collections import OrderedDict

        ScriptedLoadableModuleLogic.__init__(self)

        #TODO: CADS package (script, setup.py, model weights download...) update this in every release (also remember to update version number in setup.py)
        self.cadsPythonPackageDownloadUrl = "https://github.com/murong-xu/CADS/releases/download/v0.0.1/CADS-package.zip" # "https://drive.switch.ch/index.php/s/JQiqMoAZkG1QOsM/download"

        # Custom applications can set custom location for weights.
        # For example, it could be set to `sysconfig.get_path('scripts')` to have an independent copy of
        # the weights for each Slicer installation. However, setting such custom path would result in extra downloads and
        # storage space usage if there were multiple Slicer installations on the same computer.

        self.logCallback = None
        self.clearOutputFolder = True
        self.useStandardSegmentNames = True
        self.pullMaster = False

        # List of property type codes that are specified by in the CADS terminology.
        #
        # # Codes are stored as a list of strings containing coding scheme designator and code value of the property type,
        # separated by "^" character. For example "SCT^123456".
        #
        # If property the code is found in this list then the CADS terminology will be used,
        # otherwise the DICOM terminology will be used. This is necessary because the DICOM terminology
        # does not contain all the necessary items and some items are incomplete (e.g., don't have color or 3D Slicer label).
        #
        self.cadsTerminologyPropertyTypes = []

        # Map from CADS structure name to terminology string.
        # Terminology string uses Slicer terminology entry format - see specification at
        # https://slicer.readthedocs.io/en/latest/developer_guide/modules/segmentations.html#terminologyentry-tag
        self.cadsLabelTerminology = {}

        # Segmentation tasks specified by CADS
        # Ideally, this information should be provided by CADS itself.
        self.tasks = OrderedDict()

        # Define available tasks
        self._defineAvailableTasks()

    def _defineAvailableTasks(self):
        """Define all available segmentation tasks"""
        self.tasks = {
            '551': {'title': 'Core organs', },
            '552': {'title': 'Spine complete', },
            '553': {'title': 'Heart & vessels', },
            '554': {'title': 'Trunk muscles', },
            '555': {'title': 'Ribs complete', },
            '556': {'title': 'RT risk organs', },
            '557': {'title': 'Brain tissues', },
            '558': {'title': 'Head-neck organs', },
            '559': {'title': 'Body regions', },
            'all': {'title': 'All', 'subtasks': ['551', '552', '553', '554', '555', '556', '557', '558', '559']}
        }
        self.loadCADSLabelTerminology()
    
    def loadCADSLabelTerminology(self):
        """Load label terminology from CADS_snomed_mapping.csv file.
        Terminology entries are either in DICOM or CADS "Segmentation category and type".
        """
        moduleDir = os.path.dirname(slicer.util.getModule('CADS').path)
        cadsTerminologyMappingFilePath = os.path.join(moduleDir, 'Resources', 'cads_snomed_mapping.csv')
        cadsTerminologyFilePath = os.path.join(moduleDir, 'Resources', 'SegmentationCategoryTypeModifier-CADS.term.json')

        # load .term.json
        tlogic = slicer.modules.terminologies.logic()
        terminologyName = tlogic.LoadTerminologyFromFile(cadsTerminologyFilePath)

        # Helper function to get code string from CSV file row
        def getCodeString(field, columnNames, row):
            columnValues = []
            for fieldName in ["CodingSchemeDesignator", "CodeValue", "CodeMeaning"]:
                columnIndex = columnNames.index(f"{field}.{fieldName}")
                try:
                    columnValue = row[columnIndex]
                except IndexError:
                    columnValue = ''
                columnValues.append(columnValue)
            return columnValues

        # Load the terminology mappings from CSV
        import csv
        with open(cadsTerminologyMappingFilePath, "r") as f:
            reader = csv.reader(f)
            columnNames = next(reader)
            
            for row in reader:
                try:
                    terminologyEntryStrWithoutCategoryName = (
                        "~"
                        + '^'.join(getCodeString("SegmentedPropertyCategoryCodeSequence", columnNames, row))
                        + '~'
                        + '^'.join(getCodeString("SegmentedPropertyTypeCodeSequence", columnNames, row))
                        + '~'
                        + '^'.join(getCodeString("SegmentedPropertyTypeModifierCodeSequence", columnNames, row))
                        + '~Anatomic codes - DICOM master list'
                        + '~'
                        + '^'.join(getCodeString("AnatomicRegionSequence", columnNames, row))
                        + '~'
                        + '^'.join(getCodeString("AnatomicRegionModifierSequence", columnNames, row))
                        + '|'
                    )

                    # Get Structure name and code values
                    structure_name = row[columnNames.index("Structure")]
                    category_code = row[columnNames.index("SegmentedPropertyCategoryCodeSequence.CodeValue")]
                    type_code = row[columnNames.index("SegmentedPropertyTypeCodeSequence.CodeValue")]
                    
                    category = slicer.vtkSlicerTerminologyCategory()
                    type_object = slicer.vtkSlicerTerminologyType()
                    slicer_label = structure_name  # default: using model's structure_name as slicer display name
                    
                    # retrieve slicer labels 
                    numberOfCategories = tlogic.GetNumberOfCategoriesInTerminology(terminologyName)
                    for i in range(numberOfCategories):
                        tlogic.GetNthCategoryInTerminology(terminologyName, i, category)
                        if category.GetCodeValue() == category_code:
                            numberOfTypes = tlogic.GetNumberOfTypesInTerminologyCategory(terminologyName, category)
                            for j in range(numberOfTypes):
                                tlogic.GetNthTypeInTerminologyCategory(terminologyName, category, j, type_object)
                                if type_object.GetCodeValue() == type_code:
                                    # first, get base label name (e.g. Kidney)
                                    base_label = type_object.GetSlicerLabel() or type_object.GetCodeMeaning()
                                    # then, check if modifier code available (left/right)
                                    modifier_code = row[columnNames.index("SegmentedPropertyTypeModifierCodeSequence.CodeValue")]
                                    if modifier_code:
                                        type_modifier = slicer.vtkSlicerTerminologyType()
                                        numberOfModifiers = tlogic.GetNumberOfTypeModifiersInTerminologyType(
                                            terminologyName, 
                                            category, 
                                            type_object
                                        )
                                        for k in range(numberOfModifiers):
                                            tlogic.GetNthTypeModifierInTerminologyType(
                                                terminologyName,
                                                category,
                                                type_object,
                                                k,
                                                type_modifier
                                            )
                                            if type_modifier.GetCodeValue() == modifier_code:
                                                slicer_label = type_modifier.GetSlicerLabel() or type_modifier.GetCodeMeaning()
                                                break
                                    else:
                                        slicer_label = base_label
                                    break
                    
                    # Store terminology string and mapping information
                    self.cadsLabelTerminology[structure_name] = {
                        'terminologyStr': "Segmentation category and type - CADS" + terminologyEntryStrWithoutCategoryName,
                        'slicerLabel': slicer_label
                    }
                    
                except Exception as e:
                    logging.warning(f"Error processing row in terminology CSV: {str(e)}")

    def getSlicerLabel(self, structure_name):
        """Get Slicer display label for a structure"""
        if structure_name in self.cadsLabelTerminology:
            return self.cadsLabelTerminology[structure_name]['slicerLabel']
        return structure_name

    def getStructureName(self, slicer_label):
        """Get structure name from Slicer display label"""
        for structure_name, info in self.cadsLabelTerminology.items():
            if info['slicerLabel'] == slicer_label:
                return structure_name
        return slicer_label

    def getTerminologyString(self, structure_name):
        """Get terminology string for a structure"""
        if structure_name in self.cadsLabelTerminology:
            return self.cadsLabelTerminology[structure_name]['terminologyStr']
        return None
  
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

    def installedCADSPythonPackageDownloadUrl(self):
        """Get package download URL of the installed CADS Python package"""
        import importlib.metadata
        import json
        try:
            metadataPath = [p for p in importlib.metadata.files('CADS') if 'direct_url.json' in str(p)][0]
            with open(metadataPath.locate()) as json_file:
                data = json.load(json_file)
            return data['url']
        except:
            # Failed to get version information, probably not installed from download URL
            return None

    def installedCADSPythonPackageInfo(self):
        import shutil
        import subprocess
        versionInfo = subprocess.check_output([shutil.which('PythonSlicer'), "-m", "pip", "show", "CADS"]).decode()  # read the version info from setup.py

        # Get download URL, as the version information does not contain the github hash
        # downloadUrl = self.installedCADSPythonPackageDownloadUrl()
        # if downloadUrl:
        #     versionInfo += "Download URL: " + downloadUrl

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

    def pipInstallSelectiveFromURL(self, packageToInstall, installURL, packagesToSkip):
        """Installs a Python package from a local zip file or URL, skipping specified packages.
        Records original source URL in package metadata.
        """
        import os
        import zipfile
        import tempfile
        import urllib.request
        import json
        import shutil
        import importlib.metadata
        import re
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Download or copy zip file
                zip_path = os.path.join(temp_dir, "package.zip")
                if installURL.startswith(('http://', 'https://')):
                    self.log(f'Downloading package from {installURL}...')
                    urllib.request.urlretrieve(installURL, zip_path)
                    source_url = installURL
                else:
                    self.log(f'Copying package from {installURL}...')
                    shutil.copy2(installURL, zip_path)
                    source_url = installURL
                    
                # Extract and find setup files
                self.log('Extracting package...')
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)

                # Look for setup files
                package_dir = None
                for root, _, files in os.walk(temp_dir):
                    if any(f in files for f in ['setup.py', 'pyproject.toml']):
                        package_dir = root
                        break
                    
                if not package_dir:
                    raise ValueError(f"No setup.py or pyproject.toml found in {installURL}")

                # First install the package without dependencies
                self.log(f'Installing {packageToInstall}...')
                slicer.util.pip_install(f"{package_dir} --no-deps")

                # Now create and add direct_url.json to the installed package's dist-info
                try:
                    # Find the package's dist-info directory
                    dist_info_dir = None
                    for path in importlib.metadata.files(packageToInstall):
                        if '.dist-info' in str(path):
                            dist_info_dir = os.path.dirname(path.locate())
                            break
                    
                    if not dist_info_dir:
                        raise RuntimeError(f"Could not find dist-info directory for {packageToInstall}")

                    # Create direct_url.json content
                    direct_url_data = {
                        "url": source_url,  # need to overwrite the tmp dir generated by pip install a local file
                        "dir_info": {
                            "editable": False
                        },
                        "vcs_info": {
                            "vcs": "git",
                            "requested_revision": None,
                            "commit_id": None
                        }
                    }
                    
                    # Save direct_url.json in the dist-info directory
                    direct_url_path = os.path.join(dist_info_dir, "direct_url.json")
                    self.log(f'Creating direct_url.json at: {direct_url_path}')
                    with open(direct_url_path, 'w') as f:
                        json.dump(direct_url_data, f)

                except Exception as e:
                    self.log(f'Warning: Failed to create direct_url.json: {str(e)}')
                    # Continue with installation even if direct_url.json creation fails

                # Process metadata to skip packages
                skippedRequirements = []
                try:
                    metadataPath = [p for p in importlib.metadata.files(packageToInstall) if 'METADATA' in str(p)][0]
                except (IndexError, ImportError) as e:
                    raise RuntimeError(f"Could not find metadata for {packageToInstall}") from e

                # Filter requirements in metadata
                self.log('Processing package dependencies...')
                filteredMetadata = ""
                with open(metadataPath.locate(), "r+", encoding="latin1") as file:
                    for line in file:
                        skipThisPackage = False
                        requirementPrefix = 'Requires-Dist: '
                        
                        if line.startswith(requirementPrefix):
                            # Skip dev dependencies
                            if '; extra == "dev"' in line:
                                continue
                                
                            # Check if package should be skipped
                            for packageToSkip in packagesToSkip:
                                if packageToSkip in line:
                                    skipThisPackage = True
                                    skippedRequirements.append(line.removeprefix(requirementPrefix))
                                    break
                                    
                        if not skipThisPackage:
                            filteredMetadata += line
                            
                    # Update metadata file
                    file.seek(0)
                    file.write(filteredMetadata)
                    file.truncate()

                # Install remaining dependencies
                requirements = importlib.metadata.requires(packageToInstall) or []
                for requirement in requirements:
                    # Skip dev dependencies
                    if '; extra == "dev"' in requirement:
                        continue
                        
                    # Check if package should be skipped
                    skipThisPackage = any(requirement.startswith(pkg) for pkg in packagesToSkip)
                    
                    if not skipThisPackage:
                        # Clean up requirement string
                        if '; extra == ' in requirement:
                            pkg, extra = re.match(r"([\S]+)[\s]*; extra == '([^']+)'", requirement).groups()
                            requirement = f"{pkg}[{extra}]"
                        else:
                            match = re.match("([\S]+)[\s](.+)", requirement)
                            if match:
                                requirement = f"{match.group(1)}{match.group(2)}"
                                
                        self.log(f'Installing dependency: {requirement}')
                        slicer.util.pip_install(requirement)
                    else:
                        self.log(f'Skipping dependency: {requirement}')

                return skippedRequirements

            except urllib.error.URLError as e:
                self.log(f'Error downloading package: {str(e)}')
                raise RuntimeError(f"Failed to download package from {installURL}") from e
            
            except zipfile.BadZipFile as e:
                self.log(f'Error extracting package: {str(e)}')
                raise RuntimeError(f"The file at {installURL} is not a valid zip file") from e
                
            except json.JSONDecodeError as e:
                self.log(f'Error creating direct_url.json: {str(e)}')
                raise RuntimeError("Failed to create package metadata") from e
                
            except OSError as e:
                self.log(f'File system error: {str(e)}')
                raise RuntimeError(f"File system error while installing package: {str(e)}") from e
                
            except Exception as e:
                self.log(f'Unexpected error during installation: {str(e)}')
                raise RuntimeError(f"Failed to install package: {str(e)}") from e
    

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
                    # Skip dev dependencies
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
    
    def _parse_version_from_requirements(self, package_name, requirements):
        """
        Read package version requirement, this function is mainly used to get info from setup.py with conditial dependencies like 'TPTBox==0.2.2;python_version>="3.10"'
        """
        import re
        versions = []
        
        for req in requirements:
            pattern = rf"{package_name}\s*==([\d\.]+)\s*;\s*python_version\s*([<>=]+\s*\"[\d\.]+\")"
            match = re.match(pattern, req.strip())
            if match:
                version = match.group(1)
                condition = match.group(2).strip()
                versions.append((version, condition))
        
        return versions

    def _should_install_version(self, version_info):
        """
        Install correct package version based on Python version
        """
        import sys
        from packaging import version
        
        version_str, condition = version_info
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        
        import re
        match = re.match(r'([<>=]+)\s*"([\d\.]+)"', condition.strip())
        if not match:
            self.log(f"Warning: Invalid version condition format: {condition}")
            return False
            
        operator, version_number = match.groups()        
        comparison = f"version.parse('{python_version}') {operator} version.parse('{version_number}')"
        
        try:
            return eval(comparison)
        except Exception as e:
            self.log(f"Warning: Failed to evaluate version condition: {str(e)}")
            return False

    def setupPythonRequirements(self, upgrade=False):
        import importlib.metadata
        import importlib.util
        import packaging

        # CADS requires this, yet it is not listed among its dependencies
        try:
            import pandas
        except ModuleNotFoundError as e:
            slicer.util.pip_install("pandas")

        # pillow version that is installed in Slicer (10.1.0) is too new,
        # it is incompatible with several CADS dependencies.
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
            'requests',  # CADS would want to force a specific version of requests, which would require a restart of Slicer and it is unnecessary
            'rt_utils',  # Only needed for RTSTRUCT export, which is not needed in Slicer; rt_utils depends on opencv-python which is hard to build
            'TPTBox', # Version corrected below
            'acvl-utils' # Version corrected below (acvl-utils is a slightly different name after pip-install's name standarziation)
            ]

        # acvl_utils workaround - start
        # Recent versions of acvl_utils are broken (https://github.com/MIC-DKFZ/acvl_utils/issues/2).
        # As a workaround, we install an older version manually. This workaround can be removed after acvl_utils is fixed.
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

        # Install CADS with selected dependencies only
        # (it would replace Slicer's "requests")
        needToInstallSegmenter = False  # initial installation flag of CADS
        try:
            import cads
            if not upgrade: # update flag of CADS
                # Check if we need to update CADS Python package version
                downloadUrl = self.installedCADSPythonPackageDownloadUrl()  # 'https://drive.switch.ch/index.php/s/JQiqMoAZkG1QOsM/download'
                if downloadUrl and (downloadUrl != self.cadsPythonPackageDownloadUrl):
                    # CADS have been already installed from GitHub, from a different URL that this module needs
                    if not slicer.util.confirmOkCancelDisplay(
                        f"This module requires CADS Python package update.",
                        detailedText=f"Currently installed: {downloadUrl}\n\nRequired: {self.cadsPythonPackageDownloadUrl}"):
                      raise ValueError('CADS update was cancelled.')
                    upgrade = True
        except ModuleNotFoundError as e:
            needToInstallSegmenter = True
        if needToInstallSegmenter or upgrade:
            self.log(f'CADS Python package is required. Installing it from {self.cadsPythonPackageDownloadUrl}... (it may take several minutes)')

            if upgrade:
                # CADS version information is usually not updated with each git revision, therefore we must uninstall it to force the upgrade
                slicer.util.pip_uninstall("CADS")

            # Update CADS and all its dependencies
            skippedRequirements = self.pipInstallSelectiveFromURL(
                "CADS",
                self.cadsPythonPackageDownloadUrl,
                packagesToSkip + ["nnunetv2"])

            # Install nnunetv2 with selected dependencies only
            # (it would replace Slicer's "SimpleITK")
            try:
                nnunetRequirement = next(requirement for requirement in skippedRequirements if requirement.startswith('nnunetv2'))
            except StopIteration:
                # nnunetv2 requirement was not found in CADS - this must be an error, so let's report it
                raise ValueError("nnunetv2 requirement was not found in CADS")
            # Remove spaces and parentheses from version requirement (convert from "nnunetv2 (==2.1)" to "nnunetv2==2.1")
            nnunetRequirement = re.sub('[ \(\)]', '', nnunetRequirement)
            self.log(f'nnunetv2 Python package is required. Installing {nnunetRequirement} ...')
            self.pipInstallSelective('nnunetv2', nnunetRequirement, packagesToSkip)

            # Install TPTBox separately 
            tptbox_versions = self._parse_version_from_requirements('TPTBox', skippedRequirements)            
            required_version = None
            for version_info in tptbox_versions:
                if self._should_install_version(version_info):
                    required_version = version_info[0]
                    break
            
            if not required_version:
                raise ValueError("No suitable TPTBox version found for current Python version")

            needToInstallTPTBox = True
            try:
                import TPTBox
                if TPTBox.__version__ == required_version:
                    needToInstallTPTBox = False
            except (ImportError, AttributeError):
                pass

            if needToInstallTPTBox:
                self.log(f'Installing TPTBox version {required_version}...')
                slicer.util.pip_install(f"TPTBox=={required_version}")

            # Workaround: fix incompatibility of dynamic_network_architectures==0.4 with totalsegmentator==2.0.5.
            # Revert to the last working version: dynamic_network_architectures==0.2
            from packaging import version
            if version.parse(importlib.metadata.version("dynamic_network_architectures")) == version.parse("0.4"):
                self.log(f'dynamic_network_architectures package version is incompatible. Installing working version...')
                slicer.util.pip_install("dynamic_network_architectures==0.2.0")

            self.log('CADS installation completed successfully.')


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

    def process(self, inputVolume, outputSegmentation, cpu=False, task=None, subset=None):
        """
        Run the processing algorithm.
        Parameters:
            inputVolume: Input volume node
            outputSegmentation: Initial segmentation node
            cpu: Whether to use CPU instead of GPU
            task: Task ID to run
        Returns:
            List of created segmentation nodes
        """
        if not inputVolume:
            raise ValueError("Input volume is invalid")

        if not task:
            raise ValueError("Task ID must be specified")
        if task != 'all':
            try:
                task_id = int(task)
                if str(task_id) not in self.tasks:
                    raise ValueError(f"Invalid task ID: {task}")
            except ValueError:
                raise ValueError(f"Invalid task ID format: {task}. Must be a number or 'all'")
        
        if subset:
            from cads.dataset_utils.bodyparts_labelmaps import map_taskid_to_labelmaps
            try:
                task_id = int(task)
                labelValueToSegmentName = map_taskid_to_labelmaps[task_id]
                invalid_organs = [organ for organ in subset if organ not in labelValueToSegmentName.values()]
                if invalid_organs:
                    raise ValueError(f"Invalid organs in subset: {invalid_organs}")
            except (ValueError, KeyError):
                raise ValueError(f"Cannot validate subset for task: {task}")
            
        import time
        startTime = time.time()
        self.log('Processing started')

        # Create temporary folder - moved here so it can be shared across tasks
        tempFolder = slicer.util.tempDirectory()
        inputFile = os.path.join(tempFolder, "cads-input.nii")
        outputSegmentationFolder = os.path.join(tempFolder, "cads-input")

        # Get Python and CADS paths
        import sysconfig
        import shutil
        pythonSlicerExecutablePath = shutil.which('PythonSlicer')
        if not pythonSlicerExecutablePath:
            raise RuntimeError("Python was not found")
        cadsExecutablePath = os.path.join(sysconfig.get_path('scripts'), 
                                        self.executableName("CADSSlicer"))
        cadsCommand = [pythonSlicerExecutablePath, cadsExecutablePath]

        try:
            # Handle 'all' task specially
            if task == 'all':
                segmentationNodes = self._processAllTasks(
                    inputVolume, outputSegmentation, cpu, subset, 
                    inputFile, outputSegmentationFolder  # Pass the temp folders
                )
                return segmentationNodes

            # Process single task
            segmentationNodes = []
            self.log(f"Writing input file to {inputFile}")
            volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
            volumeStorageNode.SetFileName(inputFile)
            volumeStorageNode.UseCompressionOff()
            volumeStorageNode.WriteData(inputVolume)
            volumeStorageNode.UnRegister(None)

            segmentationNodes = self.processVolume(
                inputFile, inputVolume,
                outputSegmentationFolder, outputSegmentation,
                task, subset, cpu, cadsCommand
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

    def _processAllTasks(self, inputVolume, outputSegmentation, cpu, subset, inputFile, outputSegmentationFolder):
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

        # Get Python and CADS paths
        import sysconfig
        import shutil
        pythonSlicerExecutablePath = shutil.which('PythonSlicer')
        if not pythonSlicerExecutablePath:
            raise RuntimeError("Python was not found")
        cadsExecutablePath = os.path.join(sysconfig.get_path('scripts'), 
                                        self.executableName("CADSSlicer"))
        cadsCommand = [pythonSlicerExecutablePath, cadsExecutablePath]
        
        baseName = outputSegmentation.GetName().replace(" segmentation", "")
        for i, subtask in enumerate(subtasks):
            self.log(f'Processing task {subtask} ({i+1}/{len(subtasks)})')
            taskTitle = self.tasks[subtask]['title']
            taskName = f"{baseName}: {taskTitle}"
            if i == 0:
                currentSegmentation = outputSegmentation
                currentSegmentation.SetName(taskName)
            else:
                currentSegmentation = slicer.mrmlScene.AddNewNodeByClass(
                    'vtkMRMLSegmentationNode',
                    taskName
                )
                
            currentSegmentation.SetAttribute("CADS.TaskID", subtask)
            currentSegmentation.SetAttribute("CADS.TaskTitle", taskTitle)
            
            # Process current task using the same temp folders
            segNodes = self.processVolume(
                inputFile=inputFile,
                inputVolume=inputVolume,
                outputSegmentationFolder=outputSegmentationFolder,
                outputSegmentation=currentSegmentation,
                task=subtask,
                subset=subset,
                cpu=cpu,
                cadsCommand=cadsCommand
            )
            
            if isinstance(segNodes, list):
                allSegmentationNodes.extend(segNodes)
            else:
                allSegmentationNodes.append(segNodes)

        return allSegmentationNodes
    
    def processVolume(self, inputFile, inputVolume, outputSegmentationFolder, outputSegmentation, task, subset, cpu, cadsCommand):
        """Segment a single volume
        """
        # Write input volume to file
        # CADS requires NIFTI
        self.log(f"Writing input file to {inputFile}")
        volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
        volumeStorageNode.SetFileName(inputFile)
        volumeStorageNode.UseCompressionOff()
        volumeStorageNode.WriteData(inputVolume)
        volumeStorageNode.UnRegister(None)

        # Get options
        options = ["-i", inputFile, "-o", outputSegmentationFolder, "-task", str(task), "--preprocessing", "--postprocessing", "-np", str(4), "-ns", str(6)]  #TODO:test
        if cpu:
            options.extend(["--cpu"])

        # Launch CADS

        # When there are many segments then reading each segment from a separate file would be too slow,
        # but we need to do it for some specialized models.
        self.log('Creating segmentations with CADS AI...')
        self.log(f"CADS arguments: {options}")
        # proc = slicer.util.launchConsoleProcess(cadsCommand + options) #TODO:xing
        # self.logProcessOutput(proc)

        # Load result
        self.log('Importing segmentation results...')
        readSegmentationIntoSlicer = self.readSegmentation(
            outputSegmentation,
            outputSegmentationFolder,
            task,
            subset
            )
        
        if not readSegmentationIntoSlicer:
            return []
    
        # Set source volume - required for DICOM Segmentation export
        outputSegmentation.SetNodeReferenceID(outputSegmentation.GetReferenceImageGeometryReferenceRole(), inputVolume.GetID())
        outputSegmentation.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)

        # Place segmentation node in the same place as the input volume
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        inputVolumeShItem = shNode.GetItemByDataNode(inputVolume)
        studyShItem = shNode.GetItemParent(inputVolumeShItem)
        segmentationShItem = shNode.GetItemByDataNode(outputSegmentation)
        shNode.SetItemParent(segmentationShItem, studyShItem)

        return [outputSegmentation]

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
        
    def readSegmentation(self, outputSegmentation, outputSegmentationFolder, task, subset=None):
        # Get label descriptions
        from cads.dataset_utils.bodyparts_labelmaps import map_taskid_to_labelmaps
        labelValueToSegmentName = map_taskid_to_labelmaps[int(task)]

        # Filter by subset if provided
        if subset is not None:
            labelValueToSegmentName = {k: v for k, v in labelValueToSegmentName.items() if self.getSlicerLabel(v) in subset}
            if not labelValueToSegmentName:
                logging.info(f"Task {task}: No selected targets were found in the label map, skipping...")
                return False
        
        maxLabelValue = max(labelValueToSegmentName.keys())
        if min(labelValueToSegmentName.keys()) < 0:
            raise RuntimeError("Label values in class_map must be positive")

        # Get color node with random colors
        randomColorsNode = slicer.mrmlScene.GetNodeByID('vtkMRMLColorTableNodeRandom')
        rgba = [0, 0, 0, 0]

        pattern = os.path.join(outputSegmentationFolder, f'*{task}*.nii.gz')
        matching_files = glob.glob(pattern)
        if len(matching_files) == 0:
            self.log(f"Error: No segmentation file found for task {task} in {outputSegmentationFolder}")
            return False
        elif len(matching_files) > 1:
            self.log(f"Warning: Multiple segmentation files found for task {task}:")
            for f in matching_files:
                self.log(f"  - {os.path.basename(f)}")
            self.log(f"Using the first file: {os.path.basename(matching_files[0])}")
        outputSegmentationFile = matching_files[0]

        # Create color table for this segmentation task (only for selected subset)
        colorTableNode = slicer.vtkMRMLColorTableNode()
        colorTableNode.SetTypeToUser()
        colorTableNode.SetNumberOfColors(maxLabelValue+1)
        colorTableNode.SetName(str(task))
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

        # Remove segments that are not in the subset
        segmentation = outputSegmentation.GetSegmentation()
        segmentIDs = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIDs)
        for i in range(segmentIDs.GetNumberOfValues()):
            segmentID = segmentIDs.GetValue(i)
            if segmentID not in labelValueToSegmentName.values():
                segmentation.RemoveSegment(segmentID)

        slicer.mrmlScene.RemoveNode(colorTableNode)

        # Set terminology and color for remaining segments
        for labelValue in labelValueToSegmentName:
            segmentName = labelValueToSegmentName[labelValue]
            segmentId = segmentName
            self.setTerminology(outputSegmentation, segmentName, segmentId)
        
        return True

    def setTerminology(self, segmentation, segmentName, segmentId):
        segment = segmentation.GetSegmentation().GetSegment(segmentId)  # check whether file contains segmentId
        if not segment:
            # Segment is not present in this segmentation
            return
        if segmentName in self.cadsLabelTerminology:
            terminologyEntryStr = self.cadsLabelTerminology[segmentName]['terminologyStr']
            segment.SetTag(segment.GetTerminologyEntryTagName(), terminologyEntryStr)
            try:
                label, color = self.getSegmentLabelColor(terminologyEntryStr)
                if self.useStandardSegmentNames:
                    segment.SetName(label)
                segment.SetColor(color)
            except RuntimeError as e:
                self.log(str(e))

#
# CADSTest
#
class CADSTest(ScriptedLoadableModuleTest):
    """
    Test cases for CADS module.
    """
    def setUp(self):
        """ 
        Reset the state - clear scene and initialize test data.
        """
        slicer.mrmlScene.Clear()
        self.delayDisplay("Setting up test") 
        self.logic = CADSLogic()
        self.widget = slicer.modules.cads.widgetRepresentation()
        
        import SampleData
        self.inputVolume = SampleData.downloadSample('CTChest')
        self.outputSegmentation = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode')

    def runTest(self):
        """
        Run test suite.
        """
        self.delayDisplay("Starting tests")
        
        self.setUp()
        self.test_Logic()
        
        self.setUp()
        self.test_TerminologyLoading()
        
        self.setUp()
        self.test_SegmentationProcessing()
        
        self.setUp()
        self.test_SubsetProcessing()
        
        self.setUp()
        self.test_ErrorHandling()
        
        self.setUp()
        self.test_FileOperations()

    def test_Logic(self):
        """
        Test basic logic functionality.
        """
        self.delayDisplay("Starting logic test")

        try:
            # test parameterNode init
            parameterNode = self.logic.getParameterNode()
            self.assertIsNotNone(parameterNode)

            # test input arg setting
            defaultParameters = {
                "CPU": "false",
                "UseStandardSegmentNames": "true",
                "Task": "551",  # by default
                "TargetMode": "subset"
            }            
            self.assertIn("551", self.logic.tasks)
            self.assertEqual(self.logic.tasks["551"]["title"], "Core organs")            
            for parameter, defaultValue in defaultParameters.items():
                self.assertEqual(
                    parameterNode.GetParameter(parameter) or "",
                    defaultValue,
                    f"Parameter {parameter} default value incorrect"
                )

            # test task completeness
            self.assertIsNotNone(self.logic.tasks)
            self.assertTrue(len(self.logic.tasks) > 0)            
            for taskId, taskInfo in self.logic.tasks.items():
                if taskId != 'all':
                    self.assertTrue(taskId.isdigit())
                    self.assertIn('title', taskInfo)
                    self.assertIsInstance(taskInfo['title'], str)
            self.delayDisplay('Logic test passed')
            
        except Exception as e:
            self.delayDisplay(f'Test failed: {str(e)}', msec=1000)
            self.fail(f"Logic test failed with error: {str(e)}")

    def test_TerminologyLoading(self):
        """
        Test terminology loading and mapping.
        """
        self.delayDisplay("Starting terminology loading test")

        try:
            # test terminology loading
            self.assertIsNotNone(self.logic.cadsLabelTerminology)
            
            # test mapping
            testCases = [
                ("spleen", "78961009"),
                ("kidney_right", "64033007"),
                ("kidney_left", "64033007"),
            ]
            for structure, expected_code in testCases:
                self.assertIn(structure, self.logic.cadsLabelTerminology)
                term_info = self.logic.cadsLabelTerminology[structure]
                self.assertIn("terminologyStr", term_info)
                self.assertIn("slicerLabel", term_info)
            self.delayDisplay('Terminology loading test passed')
            
        except Exception as e:
            self.delayDisplay(f'Test failed: {str(e)}', msec=1000)
            self.fail(f"Terminology loading test failed with error: {str(e)}")

    def test_SegmentationProcessing(self):
        """
        Test segmentation algorithm processing pipeline.
        """
        import tempfile
        import shutil
        self.delayDisplay("Starting segmentation processing test")

        try:
            tempFolder = tempfile.mkdtemp()
            inputFile = os.path.join(tempFolder, "test_input.nii")
            outputFolder = os.path.join(tempFolder, "test_output")
            os.makedirs(outputFolder, exist_ok=True)

            # write downloaded sample to input file
            volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
            volumeStorageNode.SetFileName(inputFile)
            volumeStorageNode.UseCompressionOff()
            volumeStorageNode.WriteData(self.inputVolume)
            volumeStorageNode.UnRegister(None)

            # test provessVolume()
            result = self.logic.processVolume(
                inputFile=inputFile,
                inputVolume=self.inputVolume,
                outputSegmentationFolder=outputFolder,
                outputSegmentation=self.outputSegmentation,
                task="551",
                subset=None,
                cpu=True,
                cadsCommand=["echo", "test"]
            )
            
            shutil.rmtree(tempFolder)
            
            self.delayDisplay('Segmentation processing test passed')
            
        except Exception as e:
            self.delayDisplay(f'Test failed: {str(e)}', msec=1000)
            self.fail(f"Segmentation processing test failed with error: {str(e)}")

    def test_SubsetProcessing(self):
        """
        Test processing with subset of organs.
        """
        import shutil

        self.delayDisplay("Starting subset processing test")

        try:
            subset = ["lung_upper_lobe_left", "lung_lower_lobe_right", "trachea"]
            
            # test subset is valid
            self.assertTrue(all(organ in self.logic.cadsLabelTerminology for organ in subset))

            # test subset handling
            tempFolder = slicer.util.tempDirectory()
            inputFile = os.path.join(tempFolder, "test_input.nii")
            outputFolder = os.path.join(tempFolder, "test_output")
            os.makedirs(outputFolder, exist_ok=True)

            # write downloaded sample to input file
            volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
            volumeStorageNode.SetFileName(inputFile)
            volumeStorageNode.UseCompressionOff()
            volumeStorageNode.WriteData(self.inputVolume)
            volumeStorageNode.UnRegister(None)

            result = self.logic.processVolume(
                inputFile=inputFile,
                inputVolume=self.inputVolume,
                outputSegmentationFolder=outputFolder,
                outputSegmentation=self.outputSegmentation,
                task="551",
                subset=subset,
                cpu=True,
                cadsCommand=["echo", "test"]
            )

            shutil.rmtree(tempFolder)
            
            self.delayDisplay('Subset processing test passed')
            
        except Exception as e:
            self.delayDisplay(f'Test failed: {str(e)}', msec=1000)
            self.fail(f"Subset processing test failed with error: {str(e)}")

    def test_ErrorHandling(self):
        """
        Test error handling scenarios.
        """
        self.delayDisplay("Starting error handling test")

        try:
            with self.assertRaises(ValueError):
                self.logic.process(None, self.outputSegmentation)

            invalid_tasks = [
                "invalid_task",  # not digit
                "999",          # non-existing task id
                "-1",          # negative
                "0"            # invalid id
            ]
            
            for invalid_task in invalid_tasks:
                try:
                    self.logic.process(
                        self.inputVolume,
                        self.outputSegmentation,
                        task=invalid_task
                    )
                    self.fail(f"Expected ValueError for invalid task: {invalid_task}")
                except ValueError as e:
                    self.assertIn("Invalid task", str(e))

            # test invalid subset
            invalid_subset = ["nonexistent_organ"]
            try:
                self.logic.process(
                    self.inputVolume,
                    self.outputSegmentation,
                    task="551",
                    subset=invalid_subset
                )
                self.fail("Expected ValueError for invalid subset")
            except ValueError as e:
                expected_messages = [
                    "Invalid organs in subset",
                    "Cannot validate subset for task"
                ]
                self.assertTrue(
                    any(msg in str(e) for msg in expected_messages),
                    f"Error message '{str(e)}' does not match any expected message"
                )

            self.delayDisplay('Error handling test passed')
            
        except Exception as e:
            self.delayDisplay(f'Test failed: {str(e)}', msec=1000)
            self.fail(f"Error handling test failed with error: {str(e)}")

    def test_FileOperations(self):
        """
        Test file reading and writing operations.
        """
        import shutil
        import os
        self.delayDisplay("Starting file operations test")

        try:
            tempFolder = slicer.util.tempDirectory()
            
            # test writing an input file
            inputFile = os.path.join(tempFolder, "test_input.nii")
            volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
            volumeStorageNode.SetFileName(inputFile)
            self.assertTrue(volumeStorageNode.WriteData(self.inputVolume))
            
            # test reading a segmentation file
            outputFolder = os.path.join(tempFolder, "test_output")
            os.makedirs(outputFolder, exist_ok=True)
            
            # cleanup
            volumeStorageNode.UnRegister(None)
            shutil.rmtree(tempFolder)

            self.delayDisplay('File operations test passed')
            
        except Exception as e:
            self.delayDisplay(f'Test failed: {str(e)}', msec=1000)
            self.fail(f"File operations test failed with error: {str(e)}")