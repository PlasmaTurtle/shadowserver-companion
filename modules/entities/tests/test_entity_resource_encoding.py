"""Bundled location data remains usable without Python's global UTF-8 mode."""

import json
import os
from pathlib import Path
import subprocess
import sys


def test_bundled_places_preserve_names_under_locale_text_defaults():
    root = Path(__file__).resolve().parents[3]
    program = r"""
import json
import sys
from modules.entities.components.entity_validation import locations, validate_profile

assert sys.flags.utf8_mode == 0
city = "Ca\u00f1on City"
rows = locations("CO", "Ca\u00f1on")
profile = validate_profile({"city": city, "state": "CO"})
assert rows == [{"city": city, "state": "CO"}]
assert profile["city"] == city and profile["state"] == "CO"
print(json.dumps(rows))
"""
    run = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8=0",
            "-X",
            "warn_default_encoding",
            "-W",
            "error::EncodingWarning",
            "-c",
            program,
        ],
        cwd=root,
        env={**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout) == [{"city": "Cañon City", "state": "CO"}]
