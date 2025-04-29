cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(CADS)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/murong-xu/SlicerCADS")
set(EXTENSION_CATEGORY "Segmentation")
set(EXTENSION_CONTRIBUTORS "Murong Xu")
set(EXTENSION_DESCRIPTION "Fully automatic whole-body CT segmentation of 167 structures, using CADS AI model.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/lassoan/SlicerTotalSegmentator/main/TotalSegmentator.png")
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
