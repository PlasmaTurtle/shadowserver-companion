import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from workbench.shadowserver_reports.errors import StorageError
from workbench.shadowserver_reports.schema import SchemaStore


class SchemaTests(unittest.TestCase):
    def test_changes_preserve_original_and_unknown_field_types(self):
        with TemporaryDirectory() as directory:
            store = SchemaStore(directory)
            first = store.capture("scan_http_vulnerable", {"ip": "string", "old": {"future": True}})
            second = store.capture("scan_http_vulnerable", {"ip": "array", "new": "string"})
            self.assertEqual(second.previous_sha256, first.sha256)
            self.assertEqual(second.added_fields, ("new",))
            self.assertEqual(second.removed_fields, ("old",))
            self.assertEqual(second.changed_fields, ("ip",))
            self.assertEqual(json.loads(Path(first.path).read_text())["old"], {"future": True})
            third = store.capture("scan_http_vulnerable", {"new": "string", "ip": "array"})
            self.assertEqual(second.sha256, third.sha256)
            self.assertEqual(third.added_fields, ())
            self.assertEqual(third.changed_fields, ())

    def test_corrupt_schema_cache_is_not_silently_trusted(self):
        with TemporaryDirectory() as directory:
            store = SchemaStore(directory)
            first = store.capture("type", {"ip": "string"})
            Path(first.path).write_text("{}")
            with self.assertRaises(StorageError):
                store.capture("type", {"ip": "string"})

    def test_report_type_never_becomes_local_path(self):
        with TemporaryDirectory() as directory:
            snap = SchemaStore(directory).capture("../../type", {"ip": "string"})
            self.assertTrue(Path(snap.path).is_relative_to(Path(directory)))


if __name__ == "__main__":
    unittest.main()
