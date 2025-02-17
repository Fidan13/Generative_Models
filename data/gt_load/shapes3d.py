# coding=utf-8
# Copyright 2018 The DisentanglementLib Authors.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shapes3D data set."""

import os
from data.gt_load import gt_data, util
import numpy as np
import dask.array as da
from six.moves import range
import tensorflow as tf
import h5py

# dataset_path = "..//gt_datasets"
#
# SHAPES3D_PATH = os.path.join(
#     dataset_path, "3dshapes",
#     "look-at-object-room_floor-hueXwall-hueXobj-"
#     "hueXobj-sizeXobj-shapeXview-azi.npz"
# )
#

class Shapes3D(gt_data.GroundTruthData):
    """Shapes3D dataset.

    The data set was originally introduced in "Disentangling by Factorising".

    The ground-truth factors of variation are:
    0 - floor color (10 different values)
    1 - wall color (10 different values)
    2 - object color (10 different values)
    3 - object size (8 different values)
    4 - object type (4 different values)
    5 - azimuth (15 different values)
    """

    def __init__(self, data_path):
        # load dataset
        dataset = h5py.File(data_path, 'r')
        n_samples = int(1e4)
        #with h5py.File(data_path, 'r') as dataset:
        n_total = dataset['images'][()].shape[0]
        images = dataset['images'][()][:n_samples]
        labels = dataset['labels'][()][:n_samples]

        self.images = (
            images.reshape([n_samples, 64, 64, 3]).astype(np.float32) / 255.)
        features = labels.reshape([n_samples, 6])
        self.factor_sizes = [10, 10, 10, 8, 4, 15]

        self.latents_factor_indices = list(range(6))
        self.num_total_factors = features.shape[1]
        self.state_space = util.SplitDiscreteStateSpace(self.factor_sizes,
                                                        self.latents_factor_indices)
        self.factor_bases = np.prod(self.factor_sizes) / np.cumprod(
            self.factor_sizes)
        self.factor_bases *= (n_samples / n_total)
        self.factor_bases = np.clip(self.factor_bases, 0, n_samples)

    @property
    def num_factors(self):
        return self.state_space.num_latents_factors

    @property
    def factors_num_values(self):
        return self.factor_sizes

    @property
    def observation_shape(self):
        return [64, 64, 3]

    def sample_factors(self, num, random_state):
        """Sample a batch of factors Y."""
        return self.state_space.sample_latents_factors(num, random_state)

    def sample_observations_from_factors(self, factors, random_state):
        all_factors = self.state_space.sample_all_factors(factors, random_state)

        indices = np.array(np.dot(all_factors, self.factor_bases), dtype=np.int64)
        return self.images[indices]
