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

    def test_direct_selection_with_required_references(self):
        self.check_manifest(
            "# source environment\n-c requirements-constraints.txt\n"
            "Requests\n\n./modules/attribution/components/engine\n"
        )

    def test_unknown_and_internal_public_selections_are_rejected(self):
        for dependency in ("unknown", "outreach-attribution"):
            with (
                self.subTest(dependency=dependency),
                self.assertRaisesRegex(ValueError, "differs from Windows lock"),
            ):
                self.check_manifest(
                    "-c requirements-constraints.txt\n"
                    + dependency
                    + "\n./modules/attribution/components/engine"
                )

    def test_constraints_and_local_source_cannot_be_dropped(self):
        for content in (
            "requests\n./modules/attribution/components/engine",
            "-c requirements-constraints.txt\nrequests",
        ):
            with self.subTest(content=content), self.assertRaisesRegex(ValueError, "must retain"):
                self.check_manifest(content)

    def test_noncanonical_requirements_need_explicit_review(self):
        for line in (
            "requests==2.34.2",
            "requests==1.0",
            "requests>=2",
            "--extra-index-url https://example.invalid",
            "-r other.txt",
        ):
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, "Noncanonical"):
                self.check_manifest(
                    "-c requirements-constraints.txt\n./modules/attribution/components/engine\n"
                    + line
                )

    def test_duplicate_selections_and_references_are_rejected(self):
        for line in (
            "requests",
            "-c requirements-constraints.txt",
            "./modules/attribution/components/engine",
        ):
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, "Duplicate"):
                self.check_manifest(
                    "-c requirements-constraints.txt\n./modules/attribution/components/engine\n"
                    "requests\n" + line
                )


if __name__ == "__main__":
    unittest.main()
