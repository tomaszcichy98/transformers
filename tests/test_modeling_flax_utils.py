# Copyright 2020 The HuggingFace Team. All rights reserved.
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

import tempfile
import unittest

import numpy as np
from huggingface_hub import HfFolder, delete_repo, snapshot_download
from requests.exceptions import HTTPError

from transformers import BertConfig, BertModel, is_flax_available
from transformers.testing_utils import TOKEN, USER, is_staging_test, require_flax, require_safetensors, require_torch
from transformers.utils import FLAX_WEIGHTS_NAME, SAFE_WEIGHTS_NAME


if is_flax_available():
    import os

    from flax.core.frozen_dict import unfreeze
    from flax.traverse_util import flatten_dict

    from transformers import FlaxBertModel

    os.environ["XLA_PYTHON_CLIENT_MEM_FRACTION"] = "0.12"  # assumed parallelism: 8


@require_flax
@is_staging_test
class FlaxModelPushToHubTester(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._token = TOKEN
        HfFolder.save_token(TOKEN)

    @classmethod
    def tearDownClass(cls):
        try:
            delete_repo(token=cls._token, repo_id="test-model-flax")
        except HTTPError:
            pass

        try:
            delete_repo(token=cls._token, repo_id="valid_org/test-model-flax-org")
        except HTTPError:
            pass

    def test_push_to_hub(self):
        config = BertConfig(
            vocab_size=99, hidden_size=32, num_hidden_layers=5, num_attention_heads=4, intermediate_size=37
        )
        model = FlaxBertModel(config)
        model.push_to_hub("test-model-flax", token=self._token)

        new_model = FlaxBertModel.from_pretrained(f"{USER}/test-model-flax")

        base_params = flatten_dict(unfreeze(model.params))
        new_params = flatten_dict(unfreeze(new_model.params))

        for key in base_params.keys():
            max_diff = (base_params[key] - new_params[key]).sum().item()
            self.assertLessEqual(max_diff, 1e-3, msg=f"{key} not identical")

        # Reset repo
        delete_repo(token=self._token, repo_id="test-model-flax")

        # Push to hub via save_pretrained
        with tempfile.TemporaryDirectory() as tmp_dir:
            model.save_pretrained(tmp_dir, repo_id="test-model-flax", push_to_hub=True, token=self._token)

        new_model = FlaxBertModel.from_pretrained(f"{USER}/test-model-flax")

        base_params = flatten_dict(unfreeze(model.params))
        new_params = flatten_dict(unfreeze(new_model.params))

        for key in base_params.keys():
            max_diff = (base_params[key] - new_params[key]).sum().item()
            self.assertLessEqual(max_diff, 1e-3, msg=f"{key} not identical")

    def test_push_to_hub_in_organization(self):
        config = BertConfig(
            vocab_size=99, hidden_size=32, num_hidden_layers=5, num_attention_heads=4, intermediate_size=37
        )
        model = FlaxBertModel(config)
        model.push_to_hub("valid_org/test-model-flax-org", token=self._token)

        new_model = FlaxBertModel.from_pretrained("valid_org/test-model-flax-org")

        base_params = flatten_dict(unfreeze(model.params))
        new_params = flatten_dict(unfreeze(new_model.params))

        for key in base_params.keys():
            max_diff = (base_params[key] - new_params[key]).sum().item()
            self.assertLessEqual(max_diff, 1e-3, msg=f"{key} not identical")

        # Reset repo
        delete_repo(token=self._token, repo_id="valid_org/test-model-flax-org")

        # Push to hub via save_pretrained
        with tempfile.TemporaryDirectory() as tmp_dir:
            model.save_pretrained(
                tmp_dir, repo_id="valid_org/test-model-flax-org", push_to_hub=True, token=self._token
            )

        new_model = FlaxBertModel.from_pretrained("valid_org/test-model-flax-org")

        base_params = flatten_dict(unfreeze(model.params))
        new_params = flatten_dict(unfreeze(new_model.params))

        for key in base_params.keys():
            max_diff = (base_params[key] - new_params[key]).sum().item()
            self.assertLessEqual(max_diff, 1e-3, msg=f"{key} not identical")


def check_models_equal(model1, model2):
    models_are_equal = True
    flat_params_1 = flatten_dict(model1.params)
    flat_params_2 = flatten_dict(model2.params)
    for key in flat_params_1.keys():
        if np.sum(np.abs(flat_params_1[key] - flat_params_2[key])) > 1e-4:
            models_are_equal = False

    return models_are_equal


@require_flax
class FlaxModelUtilsTest(unittest.TestCase):
    def test_model_from_pretrained_subfolder(self):
        config = BertConfig.from_pretrained("hf-internal-testing/tiny-bert-flax-only")
        model = FlaxBertModel(config)

        subfolder = "bert"
        with tempfile.TemporaryDirectory() as tmp_dir:
            model.save_pretrained(os.path.join(tmp_dir, subfolder))

            with self.assertRaises(OSError):
                _ = FlaxBertModel.from_pretrained(tmp_dir)

            model_loaded = FlaxBertModel.from_pretrained(tmp_dir, subfolder=subfolder)

        self.assertTrue(check_models_equal(model, model_loaded))

    def test_model_from_pretrained_subfolder_sharded(self):
        config = BertConfig.from_pretrained("hf-internal-testing/tiny-bert-flax-only")
        model = FlaxBertModel(config)

        subfolder = "bert"
        with tempfile.TemporaryDirectory() as tmp_dir:
            model.save_pretrained(os.path.join(tmp_dir, subfolder), max_shard_size="10KB")

            with self.assertRaises(OSError):
                _ = FlaxBertModel.from_pretrained(tmp_dir)

            model_loaded = FlaxBertModel.from_pretrained(tmp_dir, subfolder=subfolder)

        self.assertTrue(check_models_equal(model, model_loaded))

    def test_model_from_pretrained_hub_subfolder(self):
        subfolder = "bert"
        model_id = "hf-internal-testing/tiny-random-bert-subfolder"

        with self.assertRaises(OSError):
            _ = FlaxBertModel.from_pretrained(model_id)

        model = FlaxBertModel.from_pretrained(model_id, subfolder=subfolder)

        self.assertIsNotNone(model)

    def test_model_from_pretrained_hub_subfolder_sharded(self):
        subfolder = "bert"
        model_id = "hf-internal-testing/tiny-random-bert-sharded-subfolder"
        with self.assertRaises(OSError):
            _ = FlaxBertModel.from_pretrained(model_id)

        model = FlaxBertModel.from_pretrained(model_id, subfolder=subfolder)

        self.assertIsNotNone(model)

    @require_safetensors
    def test_safetensors_save_and_load(self):
        model = FlaxBertModel.from_pretrained("hf-internal-testing/tiny-bert-flax-only")
        with tempfile.TemporaryDirectory() as tmp_dir:
            model.save_pretrained(tmp_dir, safe_serialization=True)

            # No msgpack file, only a model.safetensors
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, SAFE_WEIGHTS_NAME)))
            self.assertFalse(os.path.isfile(os.path.join(tmp_dir, FLAX_WEIGHTS_NAME)))

            new_model = FlaxBertModel.from_pretrained(tmp_dir)

        self.assertTrue(check_models_equal(model, new_model))

    @require_flax
    @require_torch
    def test_safetensors_save_and_load_pt_to_flax(self):
        model = FlaxBertModel.from_pretrained("hf-internal-testing/tiny-random-bert", from_pt=True)
        pt_model = BertModel.from_pretrained("hf-internal-testing/tiny-random-bert")
        with tempfile.TemporaryDirectory() as tmp_dir:
            pt_model.save_pretrained(tmp_dir)

            # Check we have a model.safetensors file
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, SAFE_WEIGHTS_NAME)))

            new_model = FlaxBertModel.from_pretrained(tmp_dir)

        # Check models are equal
        self.assertTrue(check_models_equal(model, new_model))

    @require_safetensors
    def test_safetensors_load_from_hub(self):
        flax_model = FlaxBertModel.from_pretrained("hf-internal-testing/tiny-bert-flax-only")

        # Can load from the Flax-formatted checkpoint
        safetensors_model = FlaxBertModel.from_pretrained("hf-internal-testing/tiny-bert-flax-safetensors-only")
        self.assertTrue(check_models_equal(flax_model, safetensors_model))

    @require_torch
    @require_safetensors
    def test_safetensors_load_from_hub_flax_and_pt(self):
        flax_model = FlaxBertModel.from_pretrained("hf-internal-testing/tiny-bert-flax-only")

        # Can load from the PyTorch-formatted checkpoint
        safetensors_model = FlaxBertModel.from_pretrained("hf-internal-testing/tiny-bert-pt-only", from_pt=True)
        self.assertTrue(check_models_equal(flax_model, safetensors_model))

    @require_safetensors
    def test_safetensors_flax_from_flax(self):
        model = FlaxBertModel.from_pretrained("hf-internal-testing/tiny-bert-flax-only")

        with tempfile.TemporaryDirectory() as tmp_dir:
            model.save_pretrained(tmp_dir, safe_serialization=True)
            new_model = FlaxBertModel.from_pretrained(tmp_dir)

        self.assertTrue(check_models_equal(model, new_model))

    @require_safetensors
    @require_torch
    def test_safetensors_flax_from_torch(self):
        hub_model = FlaxBertModel.from_pretrained("hf-internal-testing/tiny-bert-flax-only")
        model = BertModel.from_pretrained("hf-internal-testing/tiny-bert-pt-only")

        with tempfile.TemporaryDirectory() as tmp_dir:
            model.save_pretrained(tmp_dir, safe_serialization=True)
            new_model = FlaxBertModel.from_pretrained(tmp_dir)

        self.assertTrue(check_models_equal(hub_model, new_model))

    @require_safetensors
    def test_safetensors_flax_from_sharded_msgpack_with_sharded_safetensors_local(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = snapshot_download(
                "hf-internal-testing/tiny-bert-flax-safetensors-msgpack-sharded", cache_dir=tmp_dir
            )

            # This should not raise even if there are two types of sharded weights
            FlaxBertModel.from_pretrained(path)

    @require_safetensors
    def test_safetensors_flax_from_sharded_msgpack_with_sharded_safetensors_hub(self):
        # This should not raise even if there are two types of sharded weights
        # This should discard the safetensors weights in favor of the msgpack sharded weights
        FlaxBertModel.from_pretrained("hf-internal-testing/tiny-bert-flax-safetensors-msgpack-sharded")
