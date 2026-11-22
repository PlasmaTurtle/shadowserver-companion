"""Reusable synthetic website capture fixtures and builders."""

import io
import time

from PIL import Image


def captured(status="captured"):
    output = io.BytesIO()
    Image.new("RGB", (1440, 900), "#101b2b").save(output, "PNG")
    return output.getvalue(), {
        "requested_url": "https://mail.example.com/",
        "final_url": "https://www.example.com/",
        "title": "Example business",
        "captured_at": "2026-11-11T20:00:00Z",
        "capture_status": status,
        "viewport": {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        "http_status": 200,
        "blocked_requests": 0,
    }


def done(jobs, identity):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        result = jobs.get(identity)
        if result["state"] not in ("queued", "running"):
            return result
        time.sleep(0.01)
    raise AssertionError("Capture did not finish")
