cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(CADS)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/murong-xu/SlicerCADS")
set(EXTENSION_CATEGORY "Segmentation")
set(EXTENSION_CONTRIBUTORS "Murong Xu (University of Zurich)")
set(EXTENSION_DESCRIPTION "CADS is a robust, fully automated framework for segmenting 167 anatomical structures in Computed Tomography (CT), spanning from head to knee regions across diverse anatomical systems.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/murong-xu/SlicerCADS/main/CADS.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/lassoan/SlicerTotalSegmentator/main/Screenshot01.jpg")
set(EXTENSION_DEPENDS "PyTorch")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(CADS)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
