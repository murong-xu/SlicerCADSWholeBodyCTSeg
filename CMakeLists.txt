cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(CADSWholeBodyCTSeg)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/murong-xu/SlicerCADSWholeBodyCTSeg")
set(EXTENSION_CATEGORY "Segmentation")
set(EXTENSION_CONTRIBUTORS "Murong Xu (University of Zurich)")
set(EXTENSION_DESCRIPTION "CADS is a fully automated framework for segmenting 167 anatomical structures in Computed Tomography (CT), spanning from head to knee regions across diverse anatomical systems.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/murong-xu/SlicerCADSWholeBodyCTSeg/main/CADS.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/murong-xu/SlicerCADSWholeBodyCTSeg/main/Screenshot_01.png")
set(EXTENSION_DEPENDS "PyTorch NNUNet")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(CADSWholeBodyCTSeg)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
