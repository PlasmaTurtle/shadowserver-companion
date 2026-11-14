"""Demonstration evidence satisfies the real exhibit without bypassing checks."""

from copy import deepcopy
import socket

import pytest

from workbench.attribution_model import _item
from workbench.demo import demonstration_attribution


def item(proof):
    return _item(
        {"hostname": "example.test", "source": proof, "citation": 1},
        {},
        {"entries": [{"ip": "192.0.2.1", "source": {"fields": {"hostname": "mail.example.test"}}}]},
    )


def test_complete_demo_record_and_unvalidated_example_use_normal_policy(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Network request"))
    proof = demonstration_attribution("Synthetic Organization", "example.test", "192.0.2.1")
    display = item(proof)
    assert display["supported"] is True and display["review_required"] is False
    assert display["validated_by"] == "Demonstration evaluator (synthetic)"
    assert display["validated_at"]
    assert "Synthetic evidence" in proof["record"]["notice"]
    pending = demonstration_attribution(
        "Synthetic Organization", "example.test", "192.0.2.1", evaluated=False
    )
    assert item(pending)["review_required"] is True
    assert item(pending)["validated_at"] is None
    wrong = deepcopy(proof)
    wrong["record"]["startAddress"] = "192.0.2.2"
    wrong["record"]["endAddress"] = "192.0.2.2"
    assert item(wrong)["supported"] is False
