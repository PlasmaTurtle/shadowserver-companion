from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from modules.accretion.components.shadowserver_reports.demo import run_demo


class OfflineDemoTests(unittest.TestCase):
    def test_real_pipeline_without_network_preserves_revisions(self):
        with (
            TemporaryDirectory() as directory,
            patch(
                "socket.create_connection",
                side_effect=AssertionError("Network forbidden in offline demo"),
            ),
        ):
            result = run_demo(directory)
            self.assertEqual(result["mode"], "synthetic_offline_demo")
            self.assertFalse(result["live_api_verified"])
            self.assertEqual(result["first_pull"]["downloaded"], 1)
            self.assertEqual(result["repeat_pull"]["reused"], 1)
            self.assertEqual(result["revised_pull"]["downloaded"], 1)
            one = result["first_pull"]["receipts"][0]
            two = result["revised_pull"]["receipts"][0]
            self.assertNotEqual(one["sha256"], two["sha256"])
            self.assertTrue(Path(one["path"]).exists())
            self.assertTrue(Path(two["path"]).exists())
            self.assertIn(b"2026-11-06 04:00:00", Path(one["path"]).read_bytes())
            exported = Path(directory, "demo-result.json").read_text()
            self.assertNotIn("SYNTHETIC-DEMO-SECRET", exported)
            self.assertNotIn("SYNTHETIC-DEMO-KEY", exported)
            self.assertNotIn("SYNTHETIC-NONFUNCTIONAL", exported)
            self.assertEqual(result["query"]["completeness"], "unknown")


if __name__ == "__main__":
    unittest.main()
