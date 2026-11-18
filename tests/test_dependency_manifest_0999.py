"""Prevent source setup from drifting outside the verified distribution lock."""

import importlib.util
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dependency_manifest_gate", ROOT / "tools/check_dependencies.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SourceManifestTests(unittest.TestCase):
    def check_manifest(self, text):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "requirements.txt").write_text(text, encoding="utf-8")
            gate.verify_source_requirements(root, {"requests": {"version": "2.34.2"}})

    def test_matching_direct_pin_with_required_references(self):
        self.check_manifest(
            "# source environment\n-c requirements-constraints.txt\n"
            "Requests==2.34.2\n\n./components/attribution\n"
        )

    def test_conflicting_unknown_and_internal_public_pins_are_rejected(self):
        for dependency in ("requests==1.0", "unknown==1.0", "outreach-attribution==0.2.6"):
            with (
                self.subTest(dependency=dependency),
                self.assertRaisesRegex(ValueError, "differs from Windows lock"),
            ):
                self.check_manifest(
                    "-c requirements-constraints.txt\n" + dependency + "\n./components/attribution"
                )

    def test_constraints_and_local_source_cannot_be_dropped(self):
        for content in (
            "requests==2.34.2\n./components/attribution",
            "-c requirements-constraints.txt\nrequests==2.34.2",
        ):
            with self.subTest(content=content), self.assertRaisesRegex(ValueError, "must retain"):
                self.check_manifest(content)

    def test_noncanonical_requirements_need_explicit_review(self):
        for line in ("requests>=2", "--extra-index-url https://example.invalid", "-r other.txt"):
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, "Noncanonical"):
                self.check_manifest(
                    "-c requirements-constraints.txt\n./components/attribution\n" + line
                )

    def test_duplicate_pins_and_references_are_rejected(self):
        for line in (
            "requests==2.34.2",
            "-c requirements-constraints.txt",
            "./components/attribution",
        ):
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, "Duplicate"):
                self.check_manifest(
                    "-c requirements-constraints.txt\n./components/attribution\n"
                    "requests==2.34.2\n" + line
                )


if __name__ == "__main__":
    unittest.main()
