from ivadomed import adaptative as adaptative
from medicaltorch.filters import SliceFilter
import os

GPU_NUMBER = 5
BATCH_SIZE = 8
DROPOUT = 0.4
DEPTH = 3
BN = 0.1
N_EPOCHS = 10
INIT_LR = 0.01
FILM_LAYERS = [0, 0, 0, 0, 0, 1, 1, 1]
PATH_BIDS = 'testing_data'


def test_hdf5():
    print('[INFO]: Starting test ... ')
    train_lst = ['sub-test001']

    hdf5_file = adaptative.Bids_to_hdf5(PATH_BIDS,
                                        subject_lst=train_lst,
                                        hdf5_name='testing_data/mytestfile.hdf5',
                                        target_suffix="_lesion-manual",
                                        roi_suffix="_seg-manual",
                                        contrast_lst=['T1w', 'T2w', 'T2star'],
                                        metadata_choice="contrast",
                                        contrast_balance={},
                                        slice_axis=2,
                                        slice_filter_fn=SliceFilter(filter_empty_input=True, filter_empty_mask=True))

    # Checking architecture
    def print_attrs(name, obj):
        print("Name of the object: {}".format(name))
        print("Type: {}".format(type(name)))
        print("Including the following attributes:")
        for key, val in obj.attrs.items():
            print("    %s: %s" % (key, val))

    hdf5_file.hdf5_file.visititems(print_attrs)
    print('[INFO]: Test passed successfully. ')


test_hdf5()
