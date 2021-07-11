import os

import imageio
import nibabel as nib
import numpy as np

from ivadomed.loader import utils as imed_loader_utils


class SegmentationPair(object):
    """This class is used to build segmentation datasets. It represents
    a pair of of two data volumes (the input data and the ground truth data).

    Args:
        input_filenames (list of str): The input filename list (supported by nibabel). For single channel, the list will
            contain 1 input filename.
        gt_filenames (list of str): The ground-truth filenames list.
        metadata (list): Metadata list with each item corresponding to an image (contrast) in input_filenames.
            For single channel, the list will contain metadata related to one image.
        cache (bool): If the data should be cached in memory or not.
        slice_axis (int): Indicates the axis used to extract 2D slices from 3D NifTI files:
            "axial": 2, "sagittal": 0, "coronal": 1. 2D PNG/TIF/JPG files use default "axial": 2.
        prepro_transforms (dict): Output of get_preprocessing_transforms.

    Attributes:
        input_filenames (list): List of input filenames.
        gt_filenames (list): List of ground truth filenames.
        metadata (dict): Dictionary containing metadata of input and gt.
        cache (bool): If the data should be cached in memory or not.
        slice_axis (int): Indicates the axis used to extract 2D slices from 3D NifTI files:
            "axial": 2, "sagittal": 0, "coronal": 1. 2D PNG/TIF/JPG files use default "axial": 2.
        prepro_transforms (dict): Transforms to be applied before training.
        input_handle (list): List of input NifTI data as 'nibabel.nifti1.Nifti1Image' object
        gt_handle (list): List of gt (ground truth) NifTI data as 'nibabel.nifti1.Nifti1Image' object
    """

    def __init__(self, input_filenames, gt_filenames, metadata=None, slice_axis=2, cache=True, prepro_transforms=None,
                 soft_gt=False):

        self.input_filenames = input_filenames
        self.gt_filenames = gt_filenames
        self.metadata = metadata
        self.cache = cache
        self.slice_axis = slice_axis
        self.soft_gt = soft_gt
        self.prepro_transforms = prepro_transforms
        # list of the images
        self.input_handle = []

        # loop over the filenames (list)
        for input_file in self.input_filenames:
            input_img = self.read_file(input_file)
            self.input_handle.append(input_img)
            if len(input_img.shape) > 3:
                raise RuntimeError("4-dimensional volumes not supported.")

        # list of GT for multiclass segmentation
        self.gt_handle = []

        # Labeled data (ie not inference time)
        if self.gt_filenames is not None:
            if not isinstance(self.gt_filenames, list):
                self.gt_filenames = [self.gt_filenames]
            for gt in self.gt_filenames:
                if gt is not None:
                    if isinstance(gt, str):  # this tissue has annotation from only one rater
                        self.gt_handle.append(self.read_file(gt))
                    else:  # this tissue has annotation from several raters
                        self.gt_handle.append([self.read_file(gt_rater) for gt_rater in gt])
                else:
                    self.gt_handle.append(None)

        # Sanity check for dimensions, should be the same
        input_shape, gt_shape = self.get_pair_shapes()

        if self.gt_filenames is not None and self.gt_filenames[0] is not None:
            if not np.allclose(input_shape, gt_shape):
                raise RuntimeError('Input and ground truth with different dimensions.')

        for idx, handle in enumerate(self.input_handle):
            self.input_handle[idx] = nib.as_closest_canonical(handle)

        # Labeled data (ie not inference time)
        if self.gt_filenames is not None:
            for idx, gt in enumerate(self.gt_handle):
                if gt is not None:
                    if not isinstance(gt, list):  # this tissue has annotation from only one rater
                        self.gt_handle[idx] = nib.as_closest_canonical(gt)
                    else:  # this tissue has annotation from several raters
                        self.gt_handle[idx] = [nib.as_closest_canonical(gt_rater) for gt_rater in gt]

        # If binary classification, then extract labels from GT mask

        if self.metadata:
            self.metadata = []
            for data, input_filename in zip(metadata, input_filenames):
                data["input_filenames"] = input_filename
                data["gt_filenames"] = gt_filenames
                self.metadata.append(data)

    def get_pair_shapes(self):
        """Return the tuple (input, ground truth) representing both the input and ground truth shapes."""
        input_shape = []
        for handle in self.input_handle:
            shape = imed_loader_utils.orient_shapes_hwd(handle.header.get_data_shape(), self.slice_axis)
            input_shape.append(tuple(shape))

            if not len(set(input_shape)):
                raise RuntimeError('Inputs have different dimensions.')

        gt_shape = []

        for gt in self.gt_handle:
            if gt is not None:
                if not isinstance(gt, list):  # this tissue has annotation from only one rater
                    gt = [gt]
                for gt_rater in gt:
                    shape = imed_loader_utils.orient_shapes_hwd(gt_rater.header.get_data_shape(), self.slice_axis)
                    gt_shape.append(tuple(shape))

                if not len(set(gt_shape)):
                    raise RuntimeError('Labels have different dimensions.')

        return input_shape[0], gt_shape[0] if len(gt_shape) else None

    def get_pair_data(self):
        """Return the tuple (input, ground truth) with the data content in numpy array."""
        cache_mode = 'fill' if self.cache else 'unchanged'

        input_data = []
        for handle in self.input_handle:
            hwd_oriented = imed_loader_utils.orient_img_hwd(handle.get_fdata(cache_mode, dtype=np.float32), self.slice_axis)
            input_data.append(hwd_oriented)

        gt_data = []
        # Handle unlabeled data
        if self.gt_handle is None:
            gt_data = None
        for gt in self.gt_handle:
            if gt is not None:
                if not isinstance(gt, list):  # this tissue has annotation from only one rater
                    hwd_oriented = imed_loader_utils.orient_img_hwd(gt.get_fdata(cache_mode, dtype=np.float32), self.slice_axis)
                    gt_data.append(hwd_oriented)
                else:  # this tissue has annotation from several raters
                    hwd_oriented_list = [
                        imed_loader_utils.orient_img_hwd(gt_rater.get_fdata(cache_mode, dtype=np.float32),
                                                         self.slice_axis) for gt_rater in gt]
                    gt_data.append([hwd_oriented for hwd_oriented in hwd_oriented_list])
            else:
                gt_data.append(
                    np.zeros(imed_loader_utils.orient_shapes_hwd(self.input_handle[0].shape, self.slice_axis),
                             dtype=np.float32).astype(np.uint8))

        return input_data, gt_data

    def get_pair_metadata(self, slice_index=0, coord=None):
        """Return dictionary containing input and gt metadata.

        Args:
            slice_index (int): Index of 2D slice if 2D model is used, else 0.
            coord (tuple or list): Coordinates of subvolume in volume if 3D model is used, else None.

        Returns:
            dict: Input and gt metadata.
        """
        gt_meta_dict = []
        for idx_class, gt in enumerate(self.gt_handle):
            if gt is not None:
                if not isinstance(gt, list):  # this tissue has annotation from only one rater
                    gt_meta_dict.append(imed_loader_utils.SampleMetadata({
                        "zooms": imed_loader_utils.orient_shapes_hwd(gt.header.get_zooms(), self.slice_axis),
                        "data_shape": imed_loader_utils.orient_shapes_hwd(gt.header.get_data_shape(), self.slice_axis),
                        "gt_filenames": self.metadata[0]["gt_filenames"],
                        "bounding_box": self.metadata[0]["bounding_box"] if 'bounding_box' in self.metadata[
                            0] else None,
                        "data_type": 'gt',
                        "crop_params": {}
                    }))
                else:
                    gt_meta_dict.append([imed_loader_utils.SampleMetadata({
                        "zooms": imed_loader_utils.orient_shapes_hwd(gt_rater.header.get_zooms(), self.slice_axis),
                        "data_shape": imed_loader_utils.orient_shapes_hwd(gt_rater.header.get_data_shape(), self.slice_axis),
                        "gt_filenames": self.metadata[0]["gt_filenames"][idx_class][idx_rater],
                        "bounding_box": self.metadata[0]["bounding_box"] if 'bounding_box' in self.metadata[
                            0] else None,
                        "data_type": 'gt',
                        "crop_params": {}
                    }) for idx_rater, gt_rater in enumerate(gt)])

            else:
                # Temporarily append null metadata to null gt
                gt_meta_dict.append(None)

        # Replace null metadata with metadata from other existing classes of the same subject
        for idx, gt_metadata in enumerate(gt_meta_dict):
            if gt_metadata is None:
                gt_meta_dict[idx] = list(filter(None, gt_meta_dict))[0]

        input_meta_dict = []
        for handle in self.input_handle:
            input_meta_dict.append(imed_loader_utils.SampleMetadata({
                "zooms": imed_loader_utils.orient_shapes_hwd(handle.header.get_zooms(), self.slice_axis),
                "data_shape": imed_loader_utils.orient_shapes_hwd(handle.header.get_data_shape(), self.slice_axis),
                "data_type": 'im',
                "crop_params": {}
            }))

        dreturn = {
            "input_metadata": input_meta_dict,
            "gt_metadata": gt_meta_dict,
        }

        for idx, metadata in enumerate(self.metadata):  # loop across channels
            metadata["slice_index"] = slice_index
            metadata["coord"] = coord
            self.metadata[idx] = metadata
            for metadata_key in metadata.keys():  # loop across input metadata
                dreturn["input_metadata"][idx][metadata_key] = metadata[metadata_key]

        return dreturn

    def get_pair_slice(self, slice_index, gt_type="segmentation"):
        """Return the specified slice from (input, ground truth).

        Args:
            slice_index (int): Slice number.
            gt_type (str): Choice between segmentation or classification, returns mask (array) or label (int) resp.
                for the ground truth.
        """

        metadata = self.get_pair_metadata(slice_index)
        input_dataobj, gt_dataobj = self.get_pair_data()

        if self.slice_axis not in [0, 1, 2]:
            raise RuntimeError("Invalid axis, must be between 0 and 2.")

        input_slices = []
        # Loop over contrasts
        for data_object in input_dataobj:
            input_slices.append(np.asarray(data_object[..., slice_index],
                                           dtype=np.float32))

        # Handle the case for unlabeled data
        if self.gt_handle is None:
            gt_slices = None
        else:
            gt_slices = []
            for gt_obj in gt_dataobj:
                if gt_type == "segmentation":
                    if not isinstance(gt_obj, list):  # annotation from only one rater
                        gt_slices.append(np.asarray(gt_obj[..., slice_index],
                                                    dtype=np.float32))
                    else:  # annotations from several raters
                        gt_slices.append([np.asarray(gt_obj_rater[..., slice_index],
                                                     dtype=np.float32) for gt_obj_rater in gt_obj])
                else:
                    if not isinstance(gt_obj, list):  # annotation from only one rater
                        gt_slices.append(np.asarray(int(np.any(gt_obj[..., slice_index]))))
                    else:  # annotations from several raters
                        gt_slices.append([np.asarray(int(np.any(gt_obj_rater[..., slice_index])))
                                          for gt_obj_rater in gt_obj])
        dreturn = {
            "input": input_slices,
            "gt": gt_slices,
            "input_metadata": metadata["input_metadata"],
            "gt_metadata": metadata["gt_metadata"],
        }

        return dreturn

    def read_file(self, filename):
        """Read file according to file extension and returns 'nibabel.nifti1.Nifti1Image' object.

        Args:
            filename (str): Subject filename.

        Returns:
            'nibabel.nifti1.Nifti1Image' object
        """
        extension = imed_loader_utils.get_file_extension(filename)
        # TODO: remove "ome" from condition when implementing OMETIFF support (#739)
        if (not extension) or ("ome" in extension):
            raise RuntimeError("The input file extension '{}' of '{}' is not supported. ivadomed supports the following "
                               "file extensions: '.nii', '.nii.gz', '.png', '.tif', '.tiff', '.jpg' and '.jpeg'."
                               .format(extension, os.path.basename(filename)))

        if "nii" in extension:
            # For '.nii' and '.nii.gz' extentions
            img = nib.load(filename)
        else:
            img = self.convert_file_to_nifti(filename, extension)
        return img

    def convert_file_to_nifti(self, filename, extension):
        """
        Convert a non-NifTI image into a 'nibabel.nifti1.Nifti1Image' object and save to a file.
        This method is especially relevant for making microscopy data compatible with NifTI-only
        pipelines.

        The implementation of this method is dependent on the development of the corresponding
        microscopy BEP (github.com/ivadomed/ivadomed/issues/301, bids.neuroimaging.io/bep031):
        * "pixdim" (zooms) for Nifti1Image object is extracted as follows:
            * For train, test and segment commands, PixelSize is taken from the metadata in BIDS JSON sidecar file.
            * For inference with the segment_volume function, PixelSize must be provided in the 'options' argument.
        * PixelSize definition in example dataset is a scalar in micrometers (BIDS BEP031 v0.0.2)
        * PixelSize definition changed for list of 2-numbers [X, Y] or 3-numbers [X, Y, Z] in micrometers
          for 2D and 3D respectively (BIDS BEP031 v0.0.3)
        * Both PixelSize definitions are supported in this function.

        TODO: (#739) implement OMETIFF behavior (if "ome" in extension)

        Args:
            filename (str): Subject filename.
            extension (str): File extension.

        Returns:
            'nibabel.nifti1.Nifti1Image' object
        """
        # For '.png', '.tif', '.tiff', '.jpg' and 'jpeg' extentions
        # Read image as grayscale in numpy array (behavior TBD in ivadomed for RGB or RBGA)
        if "tif" in extension:
            img = np.expand_dims(imageio.imread(filename, format='tiff-pil', as_gray=True), axis=-1)
        else:
            img = np.expand_dims(imageio.imread(filename, as_gray=True), axis=-1)

        # Convert numpy array to Nifti1Image object with 4x4 identity affine matrix
        img = nib.Nifti1Image(img, affine=np.eye(4))

        # Get pixel size in um from json metadata and convert to mm
        array_length = [2, 3]        # Accepted array length for 'PixelSize' metadata
        conversion_factor = 0.001    # Conversion factor from um to mm
        if 'PixelSize' in self.metadata[0]:
            ps_in_um = self.metadata[0]['PixelSize']
            if isinstance(ps_in_um, list) and (len(ps_in_um) in array_length):
                ps_in_um = np.asarray(ps_in_um)
            elif isinstance(ps_in_um, float):
                ps_in_um = np.asarray([ps_in_um, ps_in_um])
            else:
                raise RuntimeError("'PixelSize' metadata type is not supported. Format must be 2D [X, Y] array,"
                                   " 3D [X, Y, Z] array or float.")
            # Note: pixdim[1,2,3] must be non-zero in Nifti objects even if there is only one slice.
            # When ps_in_um[2] (pixdim[3]) is not present or 0, we assign the same PixelSize as ps_in_um[0] (pixdim[1])
            ps_in_um = np.resize(ps_in_um, 3)
            if ps_in_um[2] == 0:
                ps_in_um[2] = ps_in_um[0]
            ps_in_mm = tuple(ps_in_um * conversion_factor)
        else:
            raise RuntimeError("'PixelSize' is missing from metadata")

        # Set "pixdim" (zooms) in Nifti1Image object header
        img.header.set_zooms((ps_in_mm))

        # If it doesn't already exist, save NifTI file in path_data alongside PNG/TIF/JPG file
        fname_out = imed_loader_utils.update_filename_to_nifti(filename)
        if not os.path.exists(fname_out):
            nib.save(img, fname_out)

        return img