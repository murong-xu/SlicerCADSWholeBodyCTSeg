# CADS 3D Slicer Plugin
This repository provides the 3D Slicer extension of the [CADS-model](https://github.com/murong-xu/CADS), enabling one-click, fully automated segmentation of 167 anatomical structures in whole-body CT directly inside 3D Slicer.

<img src="Screenshot_01.png" alt="overview" width="95%">

[CADS-model](https://github.com/murong-xu/CADS) is part of the broader CADS project, which also includes the [CADS-dataset](https://huggingface.co/datasets/mrmrx/CADS-dataset), a comprehensive collection of more than 22,000 CT scans with annotations for 167 anatomical structures.

👉 This repository focuses only on the plugin for [CADS-model](https://github.com/murong-xu/CADS), providing an easy-to-use interface for clinical and research workflows.

## Useful Links
- [📄 CADS Paper Preprint](https://arxiv.org/abs/2507.22953)
- [🤗 CADS-dataset](https://huggingface.co/datasets/mrmrx/CADS-dataset)
- [📦 CADS-model Weights](https://github.com/murong-xu/CADS/releases/tag/cads-model_v1.0.0)
- [🔧 CADS-model Codebase](https://github.com/murong-xu/CADS)
- [🛠 CADS-model 3D Slicer Plugin](https://github.com/murong-xu/SlicerCADSWholeBodyCTSeg)

If you use this software and find this work useful, please cite:

```bibtex
@article{xu2025cads,
  title={CADS: A Comprehensive Anatomical Dataset and Segmentation for Whole-Body Anatomy in Computed Tomography},
  author={Xu, Murong and Amiranashvili, Tamaz and Navarro, Fernando and Fritsak, Maksym and Hamamci, Ibrahim Ethem and Shit, Suprosanna and Wittmann, Bastian and Er, Sezgin and Christ, Sebastian M. and de la Rosa, Ezequiel and Deseoe, Julian and Graf, Robert and Möller, Hendrik and Sekuboyina, Anjany and Peeken, Jan C. and Becker, Sven and Baldini, Giulia and Haubold, Johannes and Nensa, Felix and Hosch, René and Mirajkar, Nikhil and Khalid, Saad and Zachow, Stefan and Weber, Marc-André and Langs, Georg and Wasserthal, Jakob and Ozdemir, Mehmet Kemal and Fedorov, Andrey and Kikinis, Ron and Tanadini-Lang, Stephanie and Kirschke, Jan S. and Combs, Stephanie E. and Menze, Bjoern},
  journal={arXiv preprint arXiv:2507.22953},
  year={2025}
}
```

## Installation
1. **Install 3D Slicer**  
   Download and install the latest version of [3D Slicer](https://download.slicer.org/).  
   Compatibility note (verified on September 12, 2025): Our extension has been tested with preview release **5.9.0**.

2. **Install PyTorch**  
   Slicer makes it easy to set up the correct PyTorch version:  
   - Open `Extension Manager` in Slicer → search for `PyTorch` → click `Install`.  
     (Slicer will ask you to restart after installation.)  
   - After restarting, go to the `PyTorch Utils` module.  
     In the `Torch version requirement` box, type `<2.6`, then click `Install PyTorch`. A PyTorch version (>= 2.0.0 and <2.6.0) compatible with your machine should be installed.

3. **Install nnUNet**  
   Slicer makes it easy to set up the correct nnUNet:  
   - Open `Extension Manager` in Slicer → search for `NNUNet` → click `Install`.  
     (Slicer will ask you to restart after installation.)  
   - After restarting, go to the `nnUNet` module.  
     In the `To install` box, type `==2.5.1`, then click `Install`.  
       A nnUNet version (==2.5.1) should be installed.

4. **Install CADSWholeBodyCTSeg Extension**  
   - ~~Open `Extension Manager` → search for `CADSWholeBodyCTSeg` → click `Install`.
     (Again, restart Slicer after installation.)~~
   - ~~Once restarted, open the `CADSWholeBodyCTSeg` module in Slicer and you should see the user interface ready to use.~~

   🚧 **In progress**: Installing CADSWholeBodyCTSeg directly through the 3D Slicer Extension Manager is in progress and will be available soon!  

   In the meantime, please use the manual installation described below:

   - Clone this repository to your machine: 
      - `git clone git@github.com:murong-xu/SlicerCADSWholeBodyCTSeg.git`
      - Or simply download it from https://github.com/murong-xu/SlicerCADSWholeBodyCTSeg
   - Tell Slicer where to find it:
      - Open 3D Slicer
      - Go to `Edit`(the very top-left corner) → `Application Settings` → `Modules`.
      - Under `Additional module paths`, click the `arrow` on the right, then hit `Add`.
      - Navigate to the **SlicerCADSWholeBodyCTSeg** folder you just downloaded, open it, and select the **CADSWholeBodyCTSeg** subfolder.
      - Press OK and restart Slicer.
   - Once restarted, open the `CADSWholeBodyCTSeg` module in Slicer and you should see the user interface ready to use.

## Quick Start
1. **Open the CADSWholeBodyCTSeg extension** in 3D Slicer.  
2. **Load your CT image file.**  
3. **Set the input parameters:**  
   - `Input volume`: The CT image you want to segment.  
   - `Segmentation task`: Choose a specific task from the dropdown menu (the targets for each task will be displayed in the UI), or select **All** to run every task in sequence.  
   - `Target mode`: 
     - `All targets`: Generate a complete segmentation for the chosen task.  
     - `Select targets`: Pick only the structures you want from the list below.  
   - `Advanced options`: 
     - `Use standard segment names` (default: *Yes*): Displays segmentation results using SNOMED-CT terminology.  
     - `Force to use CPU` (default: *No*): Runs inference on CPU if you don’t have a GPU. (Note: CPU is slower and will take longer.)  
     - `CADSWholeBodyCTSeg Python package`:  
       - `Force install dependencies`: Re-installs the CADSWholeBodyCTSeg package.  
       - `Get package information`: Shows the current CADSWholeBodyCTSeg package version.  
4. **Run**: Click `Apply`, the CADS-model will begin segmenting your CT scan.  
5. **View the results:**  
   - Once finished, the results will appear automatically. You can then go to the `Data` tab to view the list of structures.
   - You can view the segmentations in the three orthogonal 2D views, or drag them into the 3D viewer.  
   - Hovering over a structure name will show detailed structure information in SNOMED-CT terminology.  

<img src="Screenshot_02.png" alt="overview" width="95%">

## Target Structures in Each Task
Each task represents a specific anatomical group.

**Task - Core organs**:
Spleen, Kidney R/L, Gallbladder, Liver, Stomach, Aorta, Inferior vena cava, Portal and splenic veins, Pancreas, Adrenal glands R/L, Upper/Lower lobes of left lung, Upper/Middle/Lower lobes of right lung.

**Task - Spine complete**:
Vertebrae C1-C7, T1-T12, L1-L5.

**Task - Heart & vessels**:
Esophagus, Trachea, Myocardium, Heart atrium R/L, Heart ventricle R/L, Pulmonary artery, Brain, Common iliac artery R/L, Common iliac vein R/L, Small intestine, Duodenum, Colon, Urinary bladder, Face.

**Task - Trunk muscles**:
Humerus R/L, Scapula R/L, Clavicle R/L, Femur R/L, Hip R/L, Sacrum, Gluteus maximus/medius/minimus muscles R/L, Deep muscle of back R/L, Iliopsoas muscle R/L.

**Task - Ribs complete**:
Ribs 1-12 R/L.

**Task - RT risk organs**:
Spinal canal, Larynx, Heart, Colostomy bag, Sigmoid colon, Rectum, Prostate, Seminal vesicle, Mammary gland R/L, Sternum, Psoas major muscle R/L, Rectus abdominis muscle R/L.

**Task - Brain tissues**:
White matter, Gray matter, Cerebrospinal fluid, Scalp, Eyeballs, Compact bone, Spongy bone, Blood, Muscle of head.

**Task - Head-neck organs**:
Carotid artery R/L, Arytenoid cartilage, Mandible, Brainstem, Buccal mucosa, Oral cavity, Cochlear R/L, Cricopharyngeus, Cervical esophagus, Anterior/Posterior eyeball segment R/L, Lacrimal gland R/L, Submandibular gland R/L, Thyroid, Glottis, Supraglottis, Both lips, Optic chiasm, Optic nerve R/L, Parotid gland R/L, Pituitary gland.

**Task - Body regions**:
Subcutaneous tissue, Muscle, Abdominal cavity, Thoracic cavity, Bones, Gland structure, Pericardium, Prosthetic breast implant, Mediastinum, Spinal cord.

## License

- **Codebase** (the `cads` package and all source code in this repository) is licensed under the [Apache License 2.0](LICENSE).  
- **Model weights** released in the [Releases](https://github.com/murong-xu/CADS/releases) section are licensed under [CC BY 4.0](MODEL_LICENSE).  

## Troubleshooting
**CUDA Memory Error (torch.OutOfMemoryError)** 

Even though the model is designed to automatically manage available GPU/CPU resources during prediction, you may still run into out-of-memory errors. This usually happens if:
1. Your GPU has very limited VRAM (e.g., around 4 GB), or
2. The input CT image is large.

In these cases, I recommend switching to `Force to use CPU` mode. It will be slower than GPU (CPU-only needs around 10+ minutes for a chest+abdomen CT), but it will run more reliably and avoid memory issues.


## Contact
If you encounter any issues or have suggestions, please open an issue in this GitHub repository.  

We truly appreciate your feedback and ideas, it helps us make the project better!  