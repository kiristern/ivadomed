# Deals with postprocessing on generated segmentation.

import functools
import numpy as np
import nibabel as nib
from scipy.ndimage.measurements import label
from scipy.ndimage.morphology import binary_fill_holes


def nifti_capable(wrapped):
    @functools.wraps(wrapped)
    def wrapper(data, *args, **kwargs):
        if isinstance(data, nib.Nifti1Image):
            return nib.Nifti1Image(wrapper(np.copy(np.asanyarray(data.dataobj)), *args, **kwargs), data.affine)
        return wrapped(data, *args, **kwargs)
    return wrapper


@nifti_capable
def threshold_predictions(predictions, thr=0.5):
    """
    Threshold a soft (ie not binary) array of predictions given a threshold value, and returns
    a binary array.

    Args:
        predictions (array or nibabel object): Image to binarize.
        thr (float): Threshold value: voxels with a value < to thr are assigned 0 as value, 1
            otherwise.
    Returns:
        array: Array or nibabel (same object as the input) containing only zeros or ones. Output type is int.
    """
    thresholded_preds = np.copy(predictions)[:]
    low_values_indices = thresholded_preds < thr
    thresholded_preds[low_values_indices] = 0
    low_values_indices = thresholded_preds >= thr
    thresholded_preds[low_values_indices] = 1
    return thresholded_preds.astype(np.int)


@nifti_capable
def keep_largest_object(predictions):
    """
    Keep the largest connected object from the input array (2D or 3D).
    Note: If the input is not binary, the function calls the thresholding with low value (here 10e-3),
        applies morphomath operation, and then uses the mask_prediction function to apply the operation
        on the soft pred based on the binary output of the morphomath process.

    Args:
        predictions (array or nibabel object): Input segmentation.
            Image could be 2D or 3D, soft or binary.
    Returns:
        Array or nibabel (same object as the input).
    """
    predictions_proc = np.copy(predictions)
    # If input is not binary, then make it binary by thresholding it
    if not np.array_equal(predictions, predictions.astype(bool)):
        predictions_proc = threshold_predictions(predictions_proc, thr=1e-3)
    # Find number of closed objects using skimage "label"
    labeled_obj, num_obj = label(np.copy(predictions_proc))
    # If more than one object is found, keep the largest one
    if num_obj > 1:
        # Keep the largest object
        predictions_proc[np.where(labeled_obj != (np.bincount(labeled_obj.flat)[1:].argmax() + 1))] = 0
    # If input is not binary, then call mask_prediction to apply the operation to the soft input
    if not np.array_equal(predictions, predictions.astype(bool)):
        predictions_proc = mask_predictions(predictions, predictions_proc)
    return predictions_proc


@nifti_capable
def keep_largest_object_per_slice(predictions, axis=2):
    """
    Keep the largest connected object for each 2D slice, along a specified axis.
    Note: If the input is not binary, the function calls the thresholding with low value (here 10e-3),
        applies morphomath operation, and then uses the mask_prediction function to apply the operation
        on the soft pred based on the binary output of the morphomath process.

    Args:
        predictions (array or nibabel object): Input segmentation. Image could be 2D or 3D,
            soft or binary.
        axis (int): 2D slices are extracted along this axis.
    Returns:
        Array or nibabel (same object as the input).
    """
    # Split the 3D input array as a list of slice along axis
    list_preds_in = np.split(predictions, predictions.shape[axis], axis=axis)
    # Init list of processed slices
    list_preds_out = []
    # Loop across the slices along the given axis
    for idx in range(len(list_preds_in)):
        slice_processed = keep_largest_object(np.squeeze(list_preds_in[idx], axis=axis))
        list_preds_out.append(slice_processed)
    return np.stack(list_preds_out, axis=axis)


@nifti_capable
def fill_holes(predictions, structure=(3, 3, 3)):
    """
    Fill holes in the predictions using a given structuring element.
    Note: If the input is not binary, the function calls the thresholding with low value (here 10e-3),
        applies morphomath operation, and then uses the mask_prediction function to apply the operation
        on the soft pred based on the binary output of the morphomath process.

    Args:
        predictions (array or nibabel object): Input segmentation. Image could be 2D or 3D,
            soft or binary.
        structure (tuple of integers): Structuring element, number of ints equals
            number of dimensions in the input array.
    Returns:
        Array or nibabel (same object as the input). Output type is int.
    """
    predictions_proc = np.copy(predictions)
    # If input is not binary, then make it binary by thresholding it
    if not np.array_equal(predictions, predictions.astype(bool)):
        predictions_proc = threshold_predictions(predictions_proc, thr=1e-3)
    assert len(structure) == len(predictions.shape)
    predictions_proc = binary_fill_holes(np.copy(predictions_proc),
                                     structure=np.ones(structure)).astype(np.int)
    # If input is not binary, then call mask_prediction to apply the operation to the soft input
    if not np.array_equal(predictions, predictions.astype(bool)):
        predictions_proc = mask_predictions(predictions, predictions_proc)
    return predictions_proc


@nifti_capable
def mask_predictions(predictions, mask_binary):
    """
    Mask predictions using a binary mask: sets everything outside the mask to zero.

    Args:
        predictions (array or nibabel object): Input binary segmentation. Image could be 2D or 3D.
        mask_binary (array): array with the same shape as predictions, containing only zeros or ones.
    Returns:
        Array or nibabel (same object as the input).
    """
    assert predictions.shape == mask_binary.shape
    assert np.array_equal(mask_binary, mask_binary.astype(bool))
    return predictions * mask_binary
