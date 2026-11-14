"""Parallel CI must cover every discovered test exactly once without splitting modules."""

from collections import Counter
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.pytest_shard import module_plan, pytest_collection_modifyitems


class ShardingTests(unittest.TestCase):
    def test_module_plan_is_order_independent_and_handles_duplicate_test_items(self):
        paths = ["tests/z.py", "tests/a.py", "tests/z.py", "components/test_c.py"]
        self.assertEqual(module_plan(paths, 4), module_plan(reversed(paths), 4))
        self.assertEqual(len(module_plan(paths, 4)), 3)
        with self.assertRaises(ValueError):
            module_plan(paths, 0)

    def test_shards_cover_every_item_once_and_preserve_module_order(self):
        root = Path.cwd()
        original = [
            SimpleNamespace(path=root / f"tests/test_{module}.py", nodeid=f"{module}::{case}")
            for module in ("a", "b", "c", "d", "e", "f", "g")
            for case in range(1 + ord(module) % 5)
        ]
        selected_ids, module_owners, digests = [], {}, set()
        with TemporaryDirectory() as temporary:
            manifest_path = Path(temporary) / "shard-manifest.json"
            for index in range(1, 5):
                deselected = []
                options = {"ci_shard": index, "ci_shards": 4}
                config = SimpleNamespace(
                    rootpath=root,
                    getoption=options.__getitem__,
                    hook=SimpleNamespace(pytest_deselected=lambda items: deselected.extend(items)),
                )
                items = list(original)
                with patch("tools.pytest_shard.Path", return_value=manifest_path):
                    pytest_collection_modifyitems(config, items)
                manifest = json.loads(manifest_path.read_text())
                digests.add(manifest["inventory_sha256"])
                self.assertEqual(manifest["selected_nodeids"], [item.nodeid for item in items])
                self.assertEqual(len(items) + len(deselected), len(original))
                self.assertEqual(items, [item for item in original if item not in deselected])
                for item in items:
                    previous = module_owners.setdefault(item.path, index)
                    self.assertEqual(previous, index)
                    selected_ids.append(item.nodeid)
        self.assertEqual(Counter(selected_ids), Counter(item.nodeid for item in original))
        self.assertEqual(len(digests), 1)


if __name__ == "__main__":
    unittest.main()
