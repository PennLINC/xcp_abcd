# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
post processing the bold
^^^^^^^^^^^^^^^^^^^^^^^^
.. autofunction:: init_boldpostprocess_wf

"""
import sys
import os
import numpy as np
from copy import deepcopy
from xcp_abcd.workflow import cifti
import nibabel as nb
from nipype import __version__ as nipype_ver
from nipype.pipeline import engine as pe
from nipype.interfaces import utility as niu
from nipype import logging
from ..utils import collect_data
import sklearn
from ..interfaces import computeqcplot
from niworkflows.engine.workflows import LiterateWorkflow as Workflow
from  ..utils import bid_derivative
from ..interfaces import  FunctionalSummary
from templateflow.api import get as get_template
from niworkflows.interfaces.fixes import FixHeaderApplyTransforms as ApplyTransforms
from nipype.interfaces.afni import Despike
from ..interfaces import (ConfoundMatrix,FilteringData,regress)
from ..interfaces import interpolate
from  ..workflow import init_censoring_wf,init_resd_smoohthing
#from postprocessing import stringforparams
from ..workflow import get_transformfile

from  ..workflow import (init_fcon_ts_wf,
    init_compute_alff_wf,
    init_3d_reho_wf)
from .outputs import init_writederivatives_wf
from xcp_abcd import workflow

LOGGER = logging.getLogger('nipype.workflow')



def init_boldpostprocess_wf(
     lower_bpf,
     upper_bpf,
     contigvol,
     bpf_order,
     motion_filter_order,
     motion_filter_type,
     band_stop_min,
     band_stop_max,
     smoothing,
     bold_file,
     head_radius,
     params,
     custom_conf,
     omp_nthreads,
     dummytime,
     output_dir,
     fd_thresh,
     num_bold,
     mni_to_t1w,
     despike,
     brain_template='MNI152NLin2009cAsym',
     layout=None,
     name='bold_postprocess_wf',
      ):

    """
    This workflow organizes bold processing workflow.
    Workflow Graph
        .. workflow::
            :graph2use: orig
            :simple_form: yes
            from xcp_abcd.workflow.bold import init_boldpostprocess_wf
            wf = init_boldpostprocess_wf(
                bold_file,
                lower_bpf,
                upper_bpf,
                contigvol,
                bpf_order,
                motion_filter_order,
                motion_filter_type,
                band_stop_min,
                band_stop_max,
                smoothing,
                head_radius,
                params,
                custom_conf,
                omp_nthreads,
                dummytime,
                output_dir,
                fd_thresh,
                num_bold,
                template='MNI152NLin2009cAsym',
                layout=None,
                name='bold_postprocess_wf',
             )
    Parameters
    ----------
    bold_file: str
        bold file for post processing
    lower_bpf : float
        Lower band pass filter
    upper_bpf : float
        Upper band pass filter
    layout : BIDSLayout object
        BIDS dataset layout
    contigvol: int
        number of contigious volumes
    despike: bool
        afni depsike
    motion_filter_order: int
        respiratory motion filter order
    motion_filter_type: str
        respiratory motion filter type: lp or notch
    band_stop_min: float
        respiratory minimum frequency in breathe per minutes(bpm)
    band_stop_max,: float
        respiratory maximum frequency in breathe per minutes(bpm)
    layout : BIDSLayout object
        BIDS dataset layout
    omp_nthreads : int
        Maximum number of threads an individual process may use
    output_dir : str
        Directory in which to save xcp_abcd output
    fd_thresh
        Criterion for flagging framewise displacement outliers
    head_radius : float
        radius of the head for FD computation
    params: str
        nuissance regressors to be selected from fmriprep regressors
    smoothing: float
        smooth the derivatives output with kernel size (fwhm)
    custom_conf: str
        path to cusrtom nuissance regressors
    dummytime: float
        the first vols in seconds to be removed before postprocessing

    Inputs
    ------
    bold_file
        BOLD series NIfTI file
    mni_to_t1w
        MNI to T1W ants Transformation file/h5
    ref_file
        Bold reference file from fmriprep
    bold_mask
        bold_mask from fmriprep
    cutstom_conf
        custom regressors

    Outputs
    -------
    processed_bold
        clean bold after regression and filtering
    smoothed_bold
        smoothed clean bold
    alff_out
        alff niifti
    smoothed_alff
        smoothed alff
    reho_out
        reho output computed by afni.3dreho
    sc217_ts
        schaefer 200 timeseries
    sc217_fc
        schaefer 200 func matrices
    sc417_ts
        schaefer 400 timeseries
    sc417_fc
        schaefer 400 func matrices
    gs360_ts
        glasser 360 timeseries
    gs360_fc
        glasser 360  func matrices
    gd333_ts
        gordon 333 timeseries
    gd333_fc
        gordon 333 func matrices
    qc_file
        quality control files
    """


    TR = layout.get_tr(bold_file)
    file_base = os.path.basename(str(bold_file))
    workflow = Workflow(name=name)

    workflow.__desc__ = """
For each of the {num_bold} BOLD runs found per subject (across all
tasks and sessions), the following postprocessing was performed:
""".format(num_bold=num_bold)

    if dummytime > 0:
        nvolx = str(np.floor(dummytime / TR))
        workflow.__desc__ = workflow.__desc__ + """ \
Before nuissance regression and filtering of the data, the first {nvol} were discarded,
.Furthermore, any volumes with framewise-displacement greater than 
{fd_thresh} [@satterthwaite2;@power_fd_dvars;@satterthwaite_2013] were  flagged as outliers
 and excluded from nuissance regression.
""".format(nvol=nvolx,fd_thresh=fd_thresh)

    else:
        workflow.__desc__ = workflow.__desc__ + """ \
Before nuissance regression and filtering any volumes with framewise-displacement greater than 
{fd_thresh} [@satterthwaite2;@power_fd_dvars;@satterthwaite_2013] were  flagged as outlier
 and excluded from further analyses.
""".format(fd_thresh=fd_thresh)

    workflow.__desc__ = workflow.__desc__ +  """ \
The following nuissance regressors {regressors} [@mitigating_2018;@benchmarkp;@satterthwaite_2013] were selected 
from nuissance confound matrices of fMRIPrep output.  These nuissance regressors were regressed out 
from the bold data with *LinearRegression* as implemented in Scikit-Learn {sclver} [@scikit-learn].
The residual were then  band pass filtered within the frequency band {highpass}-{lowpass} Hz. 
 """.format(regressors=stringforparams(params=params),sclver=sklearn.__version__,
             lowpass=upper_bpf,highpass=lower_bpf)


    # get reference and mask
    mask_file,ref_file = _get_ref_mask(fname=bold_file)

    inputnode = pe.Node(niu.IdentityInterface(
        fields=['bold_file','ref_file','bold_mask','cutstom_conf','mni_to_t1w']),
        name='inputnode')

    inputnode.inputs.bold_file = str(bold_file)
    inputnode.inputs.ref_file = str(ref_file)
    inputnode.inputs.bold_mask = str(mask_file)
    inputnode.inputs.custom_conf = str(custom_conf)


    outputnode = pe.Node(niu.IdentityInterface(
        fields=['processed_bold', 'smoothed_bold','alff_out','smoothed_alff',
                'reho_out','sc217_ts', 'sc217_fc','sc417_ts','sc417_fc','ts50_ts','ts50_fc',
                'gs360_ts', 'gs360_fc','gd333_ts', 'gd333_fc','qc_file','fd']),
        name='outputnode')

    mem_gbx = _create_mem_gb(bold_file)


    fcon_ts_wf = init_fcon_ts_wf(mem_gb=mem_gbx['resampled'],mni_to_t1w=mni_to_t1w,
                 t1w_to_native=_t12native(bold_file),bold_file=bold_file,
                 brain_template=brain_template,name="fcons_ts_wf")

    alff_compute_wf = init_compute_alff_wf(mem_gb=mem_gbx['resampled'], TR=TR,
                   lowpass=upper_bpf,highpass=lower_bpf,smoothing=smoothing, cifti=False,
                    name="compute_alff_wf" )

    reho_compute_wf = init_3d_reho_wf(mem_gb=mem_gbx['resampled'],smoothing=smoothing,
                       name="afni_reho_wf")

    write_derivative_wf = init_writederivatives_wf(smoothing=smoothing,bold_file=bold_file,
                    params=params,cifti=None,output_dir=output_dir,dummytime=dummytime,
                    lowpass=upper_bpf,highpass=lower_bpf,TR=TR,omp_nthreads=omp_nthreads,
                    name="write_derivative_wf")

    confoundmat_wf = pe.Node(ConfoundMatrix(head_radius=head_radius, params=params,
                filtertype=motion_filter_type,cutoff=band_stop_max,
                low_freq=band_stop_max,high_freq=band_stop_min,TR=TR,
                filterorder=motion_filter_order),
                  name="ConfoundMatrix_wf", mem_gb=mem_gbx['resampled'])

    censorscrub_wf = init_censoring_wf(mem_gb=mem_gbx['resampled'],TR=TR,head_radius=head_radius,
                contigvol=contigvol,dummytime=dummytime,fd_thresh=fd_thresh,name='censoring')
    
    resdsmoothing_wf = init_resd_smoohthing(mem_gb=mem_gbx['resampled'],smoothing=smoothing,cifti=False,
                name="resd_smoothing_wf")
    
    filtering_wf  = pe.Node(FilteringData(tr=TR,lowpass=upper_bpf,highpass=lower_bpf,
                filter_order=bpf_order),
                    name="filtering_wf", mem_gb=mem_gbx['resampled'])

    regression_wf = pe.Node(regress(tr=TR),
               name="regression_wf",mem_gb = mem_gbx['resampled'])

    interpolate_wf = pe.Node(interpolate(TR=TR),
                  name="interpolation_wf",mem_gb = mem_gbx['resampled'])

    

    # get transform file for resampling and fcon
      
    
    
    transformfile = get_transformfile(bold_file=bold_file,
            mni_to_t1w=mni_to_t1w,t1w_to_native=mni_to_t1w)
    t1w_mask = get_maskfiles(mni_to_t1w=mni_to_t1w)

    bold2MNI_trans, bold2T1w_trans = get_transformfilex(bold_file=bold_file,
            mni_to_t1w=mni_to_t1w,t1w_to_native=mni_to_t1w) 

    
    resample_parc = pe.Node(ApplyTransforms(
        dimension=3,
        input_image=str(get_template(
            'MNI152NLin2009cAsym', resolution=1, desc='carpet',
            suffix='dseg', extension=['.nii', '.nii.gz'])),
        interpolation='MultiLabel',transforms=transformfile),
        name='resample_parc')
    
    resample_bold2T1w = pe.Node(ApplyTransforms(
        dimension=3,
         input_image=bold_file,reference_image=t1w_mask,
         interpolation='NearestNeighbor',transforms=bold2T1w_trans),
         name='bold2t1_trans')
    
    resample_bold2MNI = pe.Node(ApplyTransforms(
        dimension=3,
         input_image=bold_file,reference_image=str(get_template(
            'MNI152NLin2009cAsym', resolution=2, desc='brain',
            suffix='mask', extension=['.nii', '.nii.gz'])),
         interpolation='NearestNeighbor',transforms=bold2MNI_trans),
         name='bold2t1_trans')

    qcreport = pe.Node(computeqcplot(TR=TR,bold_file=bold_file,dummytime=dummytime,t1w_mask=t1w_mask,
                       template_mask = str(get_template('MNI152NLin2009cAsym', resolution=2, desc='brain',
                        suffix='mask', extension=['.nii', '.nii.gz'])),
                       head_radius=head_radius), name="qc_report",mem_gb = mem_gbx['resampled'])
    

    workflow.connect([
             # connect bold confound matrix to extract confound matrix 
            (inputnode, confoundmat_wf, [('bold_file', 'in_file'),]),
         ])
    
    # if there is despiking
    if despike:
        despike_wf = pe.Node(Despike(outputtype='NIFTI_GZ',args='-NEW'),name="despike_wf",mem_gb=mem_gbx['resampled'])

        workflow.connect([
            (inputnode,despike_wf,[('bold_file','in_file')]),
            (despike_wf,censorscrub_wf,[('out_file','inputnode.bold')])
            ])
    else:
        workflow.connect([
            (inputnode,censorscrub_wf,[('bold_file','inputnode.bold')]),
            ])
     
    # add neccessary input for censoring if there is one
    workflow.connect([
	     (inputnode,censorscrub_wf,[('bold_file','inputnode.bold_file'),
	        ('bold_mask','inputnode.bold_mask'),('custom_conf','inputnode.custom_conf')]),
	     (confoundmat_wf,censorscrub_wf,[('confound_file','inputnode.confound_file')])
     ])

    # regression workflow 
    workflow.connect([
	      (inputnode,regression_wf,[('bold_mask','mask')]),
	      (censorscrub_wf,regression_wf,[('outputnode.bold_censored','in_file'),
	             ('outputnode.fmriprepconf_censored','confounds'), 
		      ('outputnode.customconf_censored','custom_conf')])
        ])
    # interpolation workflow
    workflow.connect([
	      (inputnode,interpolate_wf,[('bold_file','bold_file'),('bold_mask','mask_file')]),
	      (censorscrub_wf,interpolate_wf,[('outputnode.tmask','tmask')]),
	      (regression_wf,interpolate_wf,[('res_file','in_file')]),     
	])
    # add filtering workflow 
    workflow.connect([
             (inputnode,filtering_wf,[('bold_mask','mask')]),
	     (interpolate_wf,filtering_wf,[('bold_interpolated','in_file')]),

    ])
    
    # residual smoothing 
    workflow.connect([
	   (filtering_wf,resdsmoothing_wf,[('filt_file','inputnode.bold_file')]) 
    ])

    #functional connect workflow
    workflow.connect([
         (inputnode,fcon_ts_wf,[('ref_file','inputnode.ref_file'),]),
         (filtering_wf,fcon_ts_wf,[('filt_file','inputnode.clean_bold'),]),
      ])
   # reho and alff
    workflow.connect([ 
	 (inputnode,alff_compute_wf,[('bold_mask','inputnode.bold_mask')]),
	 (inputnode,reho_compute_wf,[('bold_mask','inputnode.bold_mask')]),
	 (filtering_wf, alff_compute_wf,[('filt_file','inputnode.clean_bold')]),
	 (filtering_wf, reho_compute_wf,[('filt_file','inputnode.clean_bold')]),
      ])

   # qc report
    workflow.connect([
        (inputnode,qcreport,[('bold_mask','mask_file')]),
        (filtering_wf,qcreport,[('filt_file','cleaned_file')]),
        (censorscrub_wf,qcreport,[('outputnode.tmask','tmask')]),
        (inputnode,resample_parc,[('ref_file','reference_image')]),
        (resample_parc,qcreport,[('output_image','seg_file')]),
        (resample_bold2T1w,qcreport,[('output_image','bold2T1w_mask')]),
        (resample_bold2MNI,qcreport,[('output_image','bold2temp_mask')])
        (qcreport,outputnode,[('qc_file','qc_file')]),
           ])

    

   # write  to the outputnode, may be use in future
    workflow.connect([
	(filtering_wf,outputnode,[('filt_file','processed_bold')]),
	(censorscrub_wf,outputnode,[('outputnode.fd','fd')]),
	(resdsmoothing_wf,outputnode,[('outputnode.smoothed_bold','smoothed_bold')]),
	(alff_compute_wf,outputnode,[('outputnode.alff_out','alff_out'),
                                      ('outputnode.smoothed_alff','smoothed_alff')]),
        (reho_compute_wf,outputnode,[('outputnode.reho_out','reho_out')]),
	    (fcon_ts_wf,outputnode,[('outputnode.sc217_ts','sc217_ts' ),('outputnode.sc217_fc','sc217_fc'),
                        ('outputnode.sc417_ts','sc417_ts'),('outputnode.sc417_fc','sc417_fc'),
                        ('outputnode.gs360_ts','gs360_ts'),('outputnode.gs360_fc','gs360_fc'),
                        ('outputnode.gd333_ts','gd333_ts'),('outputnode.gd333_fc','gd333_fc'),
                        ('outputnode.ts50_ts','ts50_ts'),('outputnode.ts50_fc','ts50_fc')]),

       ])
   
    # write derivatives 
    workflow.connect([
          (filtering_wf,write_derivative_wf,[('filt_file','inputnode.processed_bold')]),
	  (resdsmoothing_wf,write_derivative_wf,[('outputnode.smoothed_bold','inputnode.smoothed_bold')]),
          (censorscrub_wf,write_derivative_wf,[('outputnode.fd','inputnode.fd')]),
          (alff_compute_wf,write_derivative_wf,[('outputnode.alff_out','inputnode.alff_out'),
                                   ('outputnode.smoothed_alff','inputnode.smoothed_alff')]),
          (reho_compute_wf,write_derivative_wf,[('outputnode.reho_out','inputnode.reho_out')]),
          (fcon_ts_wf,write_derivative_wf,[('outputnode.sc217_ts','inputnode.sc217_ts' ),
                                ('outputnode.sc217_fc','inputnode.sc217_fc'),
                                ('outputnode.sc417_ts','inputnode.sc417_ts'),
                                ('outputnode.sc417_fc','inputnode.sc417_fc'),
                                ('outputnode.gs360_ts','inputnode.gs360_ts'),
                                ('outputnode.gs360_fc','inputnode.gs360_fc'),
                                ('outputnode.gd333_ts','inputnode.gd333_ts'),
                                ('outputnode.gd333_fc','inputnode.gd333_fc'),
                                ('outputnode.ts50_ts','inputnode.ts50_ts'),
                                ('outputnode.ts50_fc','inputnode.ts50_fc')]),
         (qcreport,write_derivative_wf,[('qc_file','inputnode.qc_file')]),



         ])
    functional_qc = pe.Node(FunctionalSummary(bold_file=bold_file,tr=TR),
                name='qcsummary', run_without_submitting=True)

    ds_report_qualitycontrol = pe.Node(
        DerivativesDataSink(base_directory=output_dir, desc='qualitycontrol',source_file=bold_file, datatype="figures"),
                  name='ds_report_qualitycontrol', run_without_submitting=True)

    ds_report_preprocessing = pe.Node(
        DerivativesDataSink(base_directory=output_dir, desc='preprocessing',source_file=bold_file, datatype="figures"),
                  name='ds_report_preprocessing', run_without_submitting=True)
    ds_report_postprocessing = pe.Node(
        DerivativesDataSink(base_directory=output_dir,source_file=bold_file, desc='postprocessing', datatype="figures"),
                  name='ds_report_postprocessing', run_without_submitting=True)

    ds_report_connectivity = pe.Node(
        DerivativesDataSink(base_directory=output_dir,source_file=bold_file, desc='connectvityplot', datatype="figures"),
                  name='ds_report_connectivity', run_without_submitting=True)

    ds_report_rehoplot = pe.Node(
        DerivativesDataSink(base_directory=output_dir,source_file=bold_file, desc='rehoplot', datatype="figures"),
                  name='ds_report_rehoplot', run_without_submitting=True)

    ds_report_afniplot = pe.Node(
        DerivativesDataSink(base_directory=output_dir,source_file=bold_file, desc='afniplot', datatype="figures"),
                  name='ds_report_afniplot', run_without_submitting=True)

    workflow.connect([
        (qcreport,ds_report_preprocessing,[('raw_qcplot','in_file')]),
        (qcreport,ds_report_postprocessing ,[('clean_qcplot','in_file')]),
        (qcreport,functional_qc,[('qc_file','qc_file')]),
        (functional_qc,ds_report_qualitycontrol,[('out_report','in_file')]),
        (fcon_ts_wf,ds_report_connectivity,[('outputnode.connectplot','in_file')]),
        (reho_compute_wf,ds_report_rehoplot,[('outputnode.rehohtml','in_file')]),
        (alff_compute_wf,ds_report_afniplot ,[('outputnode.alffhtml','in_file')]),
    ])

    return workflow





def _create_mem_gb(bold_fname):
    bold_size_gb = os.path.getsize(bold_fname) / (1024**3)
    bold_tlen = nb.load(bold_fname).shape[-1]
    mem_gbz = {
        'derivative': bold_size_gb,
        'resampled': bold_size_gb * 4,
        'timeseries': bold_size_gb * (max(bold_tlen/100, 1.0) + 4),
    }

    return mem_gbz

def _get_ref_mask(fname):
    directx = os.path.dirname(fname)
    filename = filename=os.path.basename(fname)
    filex = filename.split('preproc_bold.nii.gz')[0] + 'brain_mask.nii.gz'
    filez = filename.split('_desc-preproc_bold.nii.gz')[0] +'_boldref.nii.gz'
    mask = directx + '/' + filex
    ref = directx + '/' + filez
    return mask, ref

def _t12native(fname):
    directx = os.path.dirname(fname)
    filename = os.path.basename(fname)
    fileup = filename.split('desc-preproc_bold.nii.gz')[0].split('space-')[0]

    t12ref = directx + '/' + fileup + 'from-T1w_to-scanner_mode-image_xfm.txt'

    return t12ref


class DerivativesDataSink(bid_derivative):
    out_path_base = 'xcp_abcd'
 
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



def get_maskfiles(mni_to_t1w):
    t1mask = mni_to_t1w.split('from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')[0]+'desc-brain_mask.nii.gz'
    return t1mask