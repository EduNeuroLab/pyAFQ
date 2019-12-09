import os.path as op

import pytest

import numpy as np
import numpy.testing as npt

import nibabel as nib
import dipy.data as dpd
import dipy.data.fetcher as fetcher
import dipy.tracking.streamline as dts
import dipy.tracking.utils as dtu
from dipy.stats.analysis import afq_profile

import AFQ.data as afd
import AFQ.tractography as aft
import AFQ.registration as reg
import AFQ.segmentation as seg
import AFQ.dti as dti
from AFQ.utils.volume import patch_up_roi


def test_segment():
    dpd.fetch_stanford_hardi()
    hardi_dir = op.join(fetcher.dipy_home, "stanford_hardi")
    hardi_fdata = op.join(hardi_dir, "HARDI150.nii.gz")
    hardi_img = nib.load(hardi_fdata)
    hardi_fbval = op.join(hardi_dir, "HARDI150.bval")
    hardi_fbvec = op.join(hardi_dir, "HARDI150.bvec")
    file_dict = afd.read_stanford_hardi_tractography()
    mapping = file_dict['mapping.nii.gz']
    streamlines = file_dict['tractography_subsampled.trk']
    streamlines = streamlines[streamlines._lengths > 10]

    templates = afd.read_templates()
    bundles = {'CST_L': {'ROIs': [templates['CST_roi1_L'],
                                  templates['CST_roi2_L']],
                         'rules': [True, True],
                         'prob_map': templates['CST_L_prob_map'],
                         'cross_midline': None},
               'CST_R': {'ROIs': [templates['CST_roi1_R'],
                                  templates['CST_roi1_R']],
                         'rules': [True, True],
                         'prob_map': templates['CST_R_prob_map'],
                         'cross_midline': None}}

    dpd.fetch_stanford_hardi()
    hardi_dir = op.join(fetcher.dipy_home, "stanford_hardi")
    hardi_fdata = op.join(hardi_dir, "HARDI150.nii.gz")
    hardi_img = nib.load(hardi_fdata)
    hardi_fbval = op.join(hardi_dir, "HARDI150.bval")
    hardi_fbvec = op.join(hardi_dir, "HARDI150.bvec")
    file_dict = afd.read_stanford_hardi_tractography()
    mapping = file_dict['mapping.nii.gz']
    MNI_T2_img = dpd.read_mni_template()
    mapping = reg.read_mapping(mapping, hardi_img, MNI_T2_img)
    dti_params = dti.fit_dti(hardi_fdata, hardi_fbval, hardi_fbvec,
                             out_dir='.')

    FA_img = nib.load(dti_params['FA'])
    FA_data = FA_img.get_fdata()
    seed_roi = np.zeros(hardi_img.shape[:-1])
    for bundle in bundles:
        for roi in bundles[bundle]['ROIs']:
            warped_roi = patch_up_roi(
                (mapping.transform_inverse(
                    roi.get_data().astype(np.float32),
                 interpolation='linear')) > 0)

            # Add voxels that aren't there yet:
            seed_roi = np.logical_or(seed_roi, warped_roi)
    seed_roi[FA_data < 0.6] = 0
    streamlines = aft.track(dti_params['params'], seed_mask=seed_roi,
                            stop_mask=FA_data, stop_threshold=0.1)

    streamlines = dts.Streamlines(
        dtu.transform_tracking_output(streamlines,
                                      np.linalg.inv(hardi_img.affine)))

    segmentation = seg.Segmentation()
    segmentation.segment(bundles,
                         streamlines,
                         hardi_fdata,
                         hardi_fbval,
                         hardi_fbvec,
                         mapping=mapping)
    fiber_groups = segmentation.fiber_groups
    for bundle in bundles:
        fiber_groups[bundle] = dts.Streamlines(
            dtu.transform_tracking_output(fiber_groups[bundle],
                                          np.linalg.inv(hardi_img.affine)))
    # We asked for 2 fiber groups:
    npt.assert_equal(len(fiber_groups), 2)
    # Here's one of them:
    CST_R_sl = fiber_groups['CST_R']
    # Let's make sure there are streamlines in there:
    npt.assert_(len(CST_R_sl) > 0)
    # Calculate the tract profile for a volume of all-ones:
    tract_profile = afq_profile(
        np.ones(nib.load(hardi_fdata).shape[:3]),
        CST_R_sl, np.eye(4))
    npt.assert_almost_equal(tract_profile, np.ones(100))

    clean_sl = seg.clean_bundle(CST_R_sl)
    npt.assert_equal(len(clean_sl), len(CST_R_sl))

    # Setting distance_threshold to a small number will exclude some
    # streamlines:
    clean_sl = seg.clean_bundle(CST_R_sl, distance_threshold=2)
    npt.assert_equal(len(clean_sl), 3)
    # Same with length:
    clean_sl = seg.clean_bundle(CST_R_sl, length_threshold=1)
    npt.assert_equal(len(clean_sl), 9)
    clean_sl = seg.clean_bundle(CST_R_sl, distance_threshold=2,
                                length_threshold=1)
    npt.assert_equal(len(clean_sl), 9)


    # What if you don't have probability maps?
    bundles = {'CST_L': {'ROIs': [templates['CST_roi1_L'],
                                  templates['CST_roi2_L']],
                         'rules': [True, True],
                         'cross_midline': False},
               'CST_R': {'ROIs': [templates['CST_roi1_R'],
                                  templates['CST_roi1_R']],
                         'rules': [True, True],
                         'cross_midline': False}}

    segmentation.segment(bundles,
                         streamlines,
                         hardi_fdata,
                         hardi_fbval,
                         hardi_fbvec,
                         mapping=mapping)
    fiber_groups = segmentation.fiber_groups

    # This condition should still hold
    npt.assert_equal(len(fiber_groups), 2)
    npt.assert_(len(fiber_groups['CST_R']) > 0)

    # Test with the return_idx kwarg set to True:
    segmentation = seg.Segmentation(return_idx=True)
    segmentation.segment(bundles,
                         streamlines,
                         hardi_fdata,
                         hardi_fbval,
                         hardi_fbvec,
                         mapping=mapping)
    fiber_groups = segmentation.fiber_groups

    npt.assert_equal(len(fiber_groups), 2)
    npt.assert_(len(fiber_groups['CST_R']['sl']) > 0)
    npt.assert_(len(fiber_groups['CST_R']['idx']) > 0)


    # get bundles for reco method
    bundles = afd.read_hcp_atlas_16_bundles()
    bundle_names = ['whole_brain', 'CST_R', 'CST_L']
    for key in list(bundles):
        if key not in bundle_names:
            bundles.pop(key, None)

    # Try recobundles method
    segmentation = seg.Segmentation(algo='Reco',
                                    progressive=False,
                                    greater_than=10,
                                    rm_small_clusters=1,
                                    rng=np.random.RandomState(seed=8))
    fiber_groups = segmentation.segment(bundles, streamlines)

    for bundle in ['CST_R', 'CST_L']:
        fiber_groups[bundle] = dts.Streamlines(
            dtu.transform_tracking_output(fiber_groups[bundle],
                                          np.linalg.inv(hardi_img.affine)))

    # The same conditions should hold for recobundles
    # We asked for 2 fiber groups:
    npt.assert_equal(len(fiber_groups), 2)
    # Here's one of them:
    CST_R_sl = fiber_groups['CST_R']
    # Let's make sure there are streamlines in there:
    npt.assert_(len(CST_R_sl) > 0)
    # Calculate the tract profile for a volume of all-ones:
    tract_profile = afq_profile(
        np.ones(nib.load(hardi_fdata).shape[:3]),
        CST_R_sl, np.eye(4))
    npt.assert_almost_equal(tract_profile, np.ones(100))

    # Test with the return_idx kwarg set to True:
    segmentation = seg.Segmentation(algo='Reco',
                                    progressive=False,
                                    greater_than=10,
                                    rm_small_clusters=1,
                                    rng=np.random.RandomState(seed=8),
                                    return_idx=True)

    fiber_groups = segmentation.segment(bundles, streamlines)
    fiber_groups = segmentation.fiber_groups

    npt.assert_equal(len(fiber_groups), 2)
    npt.assert_(len(fiber_groups['CST_R']['sl']) > 0)
    npt.assert_(len(fiber_groups['CST_R']['idx']) > 0)

def test_clean_by_endpoints():
    sl = [np.array([[1, 1, 1],
                    [2, 1, 1],
                    [3, 1, 1],
                    [4, 1, 1]]),
          np.array([[1, 1, 2],
                    [2, 1, 2],
                    [3, 1, 2],
                    [4, 1, 2]]),
          np.array([[1, 1, 1],
                    [2, 1, 1],
                    [3, 1, 1]]),
          np.array([[1, 1, 1],
                    [2, 1, 1]])]

    atlas = np.zeros((20, 20, 20))

    # Targets:
    atlas[1, 1, 1] = 1
    atlas[1, 1, 2] = 2
    atlas[4, 1, 1] = 3
    atlas[4, 1, 2] = 4

    clean_sl = seg.clean_by_endpoints(sl, [1, 2], [3, 4], atlas=atlas)
    npt.assert_equal(list(clean_sl), sl[:2])

    # If tol=1, the third streamline also gets included
    clean_sl = seg.clean_by_endpoints(sl, [1, 2], [3, 4], tol=1, atlas=atlas)
    npt.assert_equal(list(clean_sl), sl[:3])

    # Provide the Nx3 array of indices instead.
    idx_start = np.array(np.where(atlas==1)).T
    idx_end = np.array(np.where(atlas==3)).T

    clean_sl = seg.clean_by_endpoints(sl, idx_start, idx_end, atlas=atlas)
    npt.assert_equal(list(clean_sl), np.array([sl[0]]))

    # Sometimes no requirement for one side:
    clean_sl = seg.clean_by_endpoints(sl, [1], None, atlas=atlas)
    npt.assert_equal(list(clean_sl), [sl[0], sl[2], sl[3]])

