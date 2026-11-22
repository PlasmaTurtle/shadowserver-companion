import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.accretion.components.shadowserver_reports.errors import StorageError
from modules.accretion.components.shadowserver_reports.schema import SchemaStore


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
            # Snapshot paths are resolved; resolve the root too, since Windows
            # temporary directories may use an 8.3 alias for the same location.
            root = Path(directory).resolve()
            for report_type in (
                "../../type",
                r"..\..\type",
                r"C:\outside\type",
                r"\\server\share\type",
            ):
                with self.subTest(report_type=report_type):
                    snap = SchemaStore(directory).capture(report_type, {"ip": "string"})
                    relative = Path(snap.path).relative_to(root)
                    self.assertEqual(len(relative.parts), 2)
                    self.assertRegex(relative.parts[0], r"^[0-9a-f]{64}$")
                    self.assertEqual(relative.name, snap.sha256 + ".json")


if __name__ == "__main__":
    unittest.main()
