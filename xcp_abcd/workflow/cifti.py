# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
post processing the bold
^^^^^^^^^^^^^^^^^^^^^^^^
.. autofunction:: init_boldpostprocess_wf

"""
import sys
import os
from copy import deepcopy
import nibabel as nb
from nipype import __version__ as nipype_ver
from nipype.pipeline import engine as pe
from nipype.interfaces import utility as niu
from nipype import logging
from ..utils import collect_data
from niworkflows.engine.workflows import LiterateWorkflow as Workflow
from ..interfaces import computeqcplot
from  ..utils import bid_derivative
from ..interfaces import  FunctionalSummary
from  ..workflow import (init_cifti_conts_wf,
    init_post_process_wf,
    init_compute_alff_wf,
    init_surface_reho_wf)

from .outputs import init_writederivatives_wf

LOGGER = logging.getLogger('nipype.workflow')


def init_ciftipostprocess_wf(
    cifti_file,
    lowpass,
    highpass,
    output_dir,
    smoothing,
    head_radius,
    params,
    custom_conf,
    omp_nthreads,
    scrub,
    dummytime,
    fd_thresh,
    num_cifti=1,
    layout=None,
    name='cifti_process_wf'):
    


    

    workflow = Workflow(name=name)
   
    inputnode = pe.Node(niu.IdentityInterface(
        fields=['cifti_file','custom_conf']),
        name='inputnode')
    
    inputnode.inputs.cifti_file = cifti_file
    inputnode.inputs.custom_conf = str(custom_conf)


    outputnode = pe.Node(niu.IdentityInterface(
        fields=['processed_bold', 'smoothed_bold','alff_out','smoothed_alff', 
                'reho_lh','reho_rh','sc207_ts', 'sc207_fc','sc407_ts','sc407_fc',
                'gs360_ts', 'gs360_fc','gd333_ts', 'gd333_fc','qc_file']),
        name='outputnode')

    TR = layout.get_tr(cifti_file)
    


    mem_gbx = _create_mem_gb(cifti_file)

    clean_data_wf = init_post_process_wf(mem_gb=mem_gbx['timeseries'], TR=TR,
                   head_radius=head_radius,lowpass=lowpass,highpass=highpass,
                   smoothing=smoothing,params=params,
                   scrub=scrub,dummytime=dummytime,fd_thresh=fd_thresh,
                   name='clean_data_wf')
    
    cifti_conts_wf = init_cifti_conts_wf(mem_gb=mem_gbx['timeseries'],
                      name='cifti_ts_con_wf')

    alff_compute_wf = init_compute_alff_wf(mem_gb=mem_gbx['timeseries'], TR=TR,
                   lowpass=lowpass,highpass=highpass,smoothing=smoothing,surface=True,
                    name="compute_alff_wf" )

    reho_compute_wf = init_surface_reho_wf(mem_gb=mem_gbx['timeseries'],smoothing=smoothing,
                       name="surface_reho_wf")
    
    write_derivative_wf = init_writederivatives_wf(smoothing=smoothing,bold_file=cifti_file,
                    params=params,scrub=scrub,surface=True,output_dir=output_dir,dummytime=dummytime,
                    lowpass=lowpass,highpass=highpass,TR=TR,omp_nthreads=omp_nthreads,
                    name="write_derivative_wf")

    workflow.connect([
            (inputnode,clean_data_wf,[('cifti_file','inputnode.bold'),]),
            (clean_data_wf, cifti_conts_wf,[('outputnode.processed_bold','inputnode.clean_cifti')]),
            (clean_data_wf, alff_compute_wf,[('outputnode.processed_bold','inputnode.clean_bold')]),
            (clean_data_wf,reho_compute_wf,[('outputnode.processed_bold','inputnode.clean_bold')]),
        
            (clean_data_wf,outputnode,[('outputnode.processed_bold','processed_bold'),
            
                                  ('outputnode.smoothed_bold','smoothed_bold') ]),
                                  
            (alff_compute_wf,outputnode,[('outputnode.alff_out','alff_out')]),
            (reho_compute_wf,outputnode,[('outputnode.lh_reho','reho_lh'),('outputnode.rh_reho','reho_rh')]),

            (cifti_conts_wf,outputnode,[('outputnode.sc207_ts','sc207_ts' ),('outputnode.sc207_fc','sc207_fc'),
                        ('outputnode.sc407_ts','sc407_ts'),('outputnode.sc407_fc','sc407_fc'),
                        ('outputnode.gs360_ts','gs360_ts'),('outputnode.gs360_fc','gs360_fc'),
                        ('outputnode.gd333_ts','gd333_ts'),('outputnode.gd333_fc','gd333_fc')]),
            

      ])
    if custom_conf:
        workflow.connect([
         (inputnode,clean_data_wf,[('custom_conf','inputnode.custom_conf')]),
        ])

    qcreport = pe.Node(computeqcplot(TR=TR,bold_file=cifti_file,dummytime=dummytime,
                       head_radius=head_radius), name="qc_report")
    workflow.connect([
        (clean_data_wf,qcreport,[('outputnode.processed_bold','cleaned_file'),
                            ('outputnode.tmask','tmask')]),
        (qcreport,outputnode,[('qc_file','qc_file')]),
           ])
    
    workflow.connect([
        (clean_data_wf, write_derivative_wf,[('outputnode.processed_bold','inputnode.processed_bold'),
                                   ('outputnode.smoothed_bold','inputnode.smoothed_bold')]),
        (alff_compute_wf,write_derivative_wf,[('outputnode.alff_out','inputnode.alff_out'),
                                      ('outputnode.smoothed_alff','inputnode.smoothed_alff')]),
        (reho_compute_wf,write_derivative_wf,[('outputnode.rh_reho','inputnode.reho_rh'),
                                     ('outputnode.lh_reho','inputnode.reho_lh')]),
        (cifti_conts_wf,write_derivative_wf,[('outputnode.sc207_ts','inputnode.sc207_ts' ),
                                ('outputnode.sc207_fc','inputnode.sc207_fc'),
                                ('outputnode.sc407_ts','inputnode.sc407_ts'),
                                ('outputnode.sc407_fc','inputnode.sc407_fc'),
                                ('outputnode.gs360_ts','inputnode.gs360_ts'),
                                ('outputnode.gs360_fc','inputnode.gs360_fc'),
                                ('outputnode.gd333_ts','inputnode.gd333_ts'),
                                ('outputnode.gd333_fc','inputnode.gd333_fc')]),
        (qcreport,write_derivative_wf,[('qc_file','inputnode.qc_file')]),
        
         ])

    ds_report_preprocessing = pe.Node(
        DerivativesDataSink(base_directory=output_dir, source_file=cifti_file, desc='preprocessing', datatype="figures"),
                  name='ds_report_preprocessing', run_without_submitting=True)
    ds_report_postprocessing = pe.Node(
        DerivativesDataSink(base_directory=output_dir,source_file=cifti_file, desc='postprocessing', datatype="figures"),
                  name='ds_report_postprocessing', run_without_submitting=True)
    
    workflow.connect([
        (qcreport,ds_report_preprocessing,[('raw_qcplot','in_file')]),
        (qcreport,ds_report_postprocessing ,[('clean_qcplot','in_file')]),  
    ])
    
    return workflow



def _create_mem_gb(bold_fname):
    bold_size_gb = os.path.getsize(bold_fname) / (1024**3)
    bold_tlen = nb.load(bold_fname).shape[-1]
    mem_gbz = {
        'derivative': bold_size_gb,
        'resampled': bold_size_gb * 4,
        'timeseries': bold_size_gb * (max(bold_tlen / 100, 1.0) + 4),
    }

    return mem_gbz


class DerivativesDataSink(bid_derivative):
    out_path_base = 'xcp_abcd'