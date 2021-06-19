import os 
from templateflow.api import get as get_template
import numpy as np

def get_transformfilex(bold_file,mni_to_t1w,t1w_to_native):

    file_base = os.path.basename(str(bold_file))
   
    MNI6 = str(get_template(template='MNI152NLin2009cAsym',mode='image',suffix='xfm')[0])
     
    if 'MNI152NLin2009cAsym' in file_base:
        transformfileMNI = 'identity'
        transformfileT1W  = str(mni_to_t1w)

    elif 'MNI152NLin6Asym' in file_base:
        transformfileMNI = MNI6
        transformfileT1W = [str(MNI6),str(mni_to_t1w)]

    elif 'PNC' in file_base:
        mnisf = mni_to_t1w.split('from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')[0]
        pnc_to_t1w  = mnisf + 'from-PNC_to-T1w_mode-image_xfm.h5'
        t1w_to_mni  = mnisf + 'from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5'
        transformfileMNI =[str(pnc_to_t1w),str(t1w_to_mni)]
        transformfileT1W = str(pnc_to_t1w)

    elif 'NKI' in file_base:
        mnisf = mni_to_t1w.split('from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')[0]
        nki_to_t1w  = mnisf + 'from-NKI_to-T1w_mode-image_xfm.h5'
        t1w_to_mni  = mnisf + 'from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5'
        transformfileMNI =[str(nki_to_t1w),str(t1w_to_mni)]
        transformfileT1W = str(nki_to_t1w)

    elif 'OASIS' in file_base:
        mnisf = mni_to_t1w.split('from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')[0]
        oasis_to_t1w  = mnisf + 'from-OASIS_to-T1w_mode-image_xfm.h5'
        t1w_to_mni  = mnisf + 'from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5'
        transformfileMNI =[str(oasis_to_t1w),str(t1w_to_mni)]
        transformfileT1W = str(oasis_to_t1w)

    elif 'T1w' in file_base:
        mnisf = mni_to_t1w.split('from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')[0]
        oasis_to_t1w  = mnisf + 'from-OASIS_to-T1w_mode-image_xfm.h5'
        t1w_to_mni  = mnisf + 'from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5'
        transformfileMNI = str(t1w_to_mni)
        transformfileT1W = 'identity'
    else:
        t1wf = t1w_to_native.split('from-T1w_to-scanner_mode-image_xfm.txt')[0]
        native_to_t1w =t1wf + 'from-T1w_to-scanner_mode-image_xfm.txt'
        mnisf = mni_to_t1w.split('from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')[0]
        t1w_to_mni  = mnisf + 'from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5'
        transformfileMNI = [str(t1w_to_mni),str(native_to_t1w)]
        transformfileT1W =  str(native_to_t1w)
  
    return transformfileMNI, transformfileT1W



def get_maskfiles(bold_file,mni_to_t1w):
    boldmask = bold_file.split('desc-preproc_bold.nii.gz')[0]+ 'desc-brain_mask.nii.gz'
    t1mask = mni_to_t1w.split('from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')[0]+'desc-brain_mask.nii.gz'
    return boldmask,t1mask


def get_transformfile(bold_file,mni_to_t1w,t1w_to_native):

    file_base = os.path.basename(str(bold_file))
   
    MNI6 = str(get_template(template='MNI152NLin2009cAsym',mode='image',suffix='xfm')[0])
     
    if 'MNI152NLin6Asym' in file_base:
        transformfile = 'identity'
    elif 'MNI152NLin2009cAsym' in file_base:
        transformfile = str(MNI6)
    elif 'PNC' in file_base:
        mnisf = mni_to_t1w.split('from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')[0]
        t1w_to_pnc = mnisf + 'from-T1w_to-PNC_mode-image_xfm.h5'
        transformfile = [str(MNI6),str(mni_to_t1w),str(t1w_to_pnc)]
    elif 'NKI' in file_base:
        mnisf = mni_to_t1w.split('from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')[0]
        t1w_to_nki = mnisf + 'from-T1w_to-NKI_mode-image_xfm.h5'
        transformfile = [str(MNI6),str(mni_to_t1w),str(t1w_to_nki)] 
    elif 'OASIS' in file_base:
        mnisf = mni_to_t1w.split('from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')[0]
        t1w_to_oasis = mnisf + 'from-T1w_to-OASIS_mode-image_xfm.h5'
        transformfile = [str(MNI6),str(mni_to_t1w),str(t1w_to_oasis)] 
    elif 'T1w' in file_base:
        transformfile = str(mni_to_t1w)
    else:
        transformfile = [str(mni_to_t1w), str(t1w_to_native)]

    return transformfile

def fwhm2sigma(fwhm):
    return fwhm / np.sqrt(8 * np.log(2))

def stringforparams(params):
    if params == '24P':
        bsignal = "including six motion parameters with their temporal derivatives, \
            quadratic expansion of both six motion paramters and their derivatives  \
            to make a total of 24 nuissance regressors "
    if params == '27P':
        bsignal = "including six motion parameters with their temporal derivatives, \
            quadratic expansion of both six motion paramters and their derivatives, global signal,  \
            white and CSF signal to make a total 27 nuissance regressors"
    if params == '36P':
        bsignal= "including six motion parameters, white ,CSF and global signals,  with their temporal derivatives, \
            quadratic expansion of these nuissance regressors and their derivatives  \
            to make a total 36 nuissance regressors"
    return bsignal