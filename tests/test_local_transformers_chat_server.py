import unittest
from collections import UserDict
from unittest.mock import patch

import torch
from fastapi.testclient import TestClient
from transformers.cache_utils import DynamicCache
from transformers.utils import import_utils as transformers_import_utils

from scripts.local_transformers_chat_server import (
    _install_transformers_compatibility_shims,
    create_app,
)


class BatchFeatureLike(UserDict):
    pass


class FakeProcessor:
    def apply_chat_template(self, messages, **options):
        return BatchFeatureLike({"input_ids": torch.tensor([[1, 2]])})

    def decode(self, token_ids, **options):
        return "READY"


class FakeModel:
    device = torch.device("cpu")

    def __init__(self):
        self.generation = None

    def generate(self, input_ids, **generation):
        if not torch.is_tensor(input_ids):
            raise TypeError("input_ids must be a tensor")
        self.generation = generation
        return torch.cat((input_ids, torch.tensor([[3]])), dim=1)


class LocalTransformersChatServerTest(unittest.TestCase):
    def test_installs_legacy_torch_fx_probe_for_remote_model_code(self):
        _install_transformers_compatibility_shims()
        self.assertTrue(callable(transformers_import_utils.is_torch_fx_available))
        self.assertFalse(transformers_import_utils.is_torch_fx_available())
        cache = DynamicCache()
        self.assertEqual(cache.seen_tokens, cache.get_seq_length())
        self.assertEqual(cache.seen_tokens, 0)
        self.assertEqual(cache.get_usable_length(16), 0)

    def test_mapping_batch_feature_and_greedy_generation(self):
        processor = FakeProcessor()
        model = FakeModel()
        with patch(
            "scripts.local_transformers_chat_server._load_backend",
            return_value=(processor, model),
        ):
            with TestClient(create_app("fake-model", "image_text", use_cache=False)) as client:
                response = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "fake-model",
                        "messages": [{"role": "user", "content": "ready?"}],
                        "temperature": 0,
                        "max_tokens": 16,
                    },
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["choices"][0]["message"]["content"], "READY")
        self.assertFalse(model.generation["do_sample"])
        self.assertFalse(model.generation["use_cache"])
        self.assertNotIn("temperature", model.generation)


if __name__ == "__main__":
    unittest.main()
