"""Reusable synthetic entity dns fixtures and builders."""

import httpx
from attribution import Settings
from attribution.google_dns import GooglePublicDnsProvider
from attribution.models import json_bytes


def answer(name, kind, values=(), **updates):
    number = {"A": 1, "AAAA": 28}[kind]
    result = {
        "Status": 0,
        "TC": False,
        "RD": True,
        "RA": True,
        "AD": False,
        "CD": False,
        "Question": [{"name": name, "type": number}],
        "Answer": [{"name": name, "type": number, "TTL": 300, "data": value} for value in values],
    }
    result.update(updates)
    return result


class DNSFixture:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.gate = None
        self.records = {}

    def __call__(self, request):
        assert request.url.host == "dns.google" and request.url.scheme == "https"
        assert request.url.path == "/resolve"
        assert request.url.params["cd"] == "false"
        assert request.url.params["edns_client_subnet"] == "0.0.0.0/0"
        name, kind = request.url.params["name"], request.url.params["type"]
        assert name.endswith(".") and kind in ("A", "AAAA")
        self.calls.append((name, kind))
        if self.gate:
            self.gate.wait(2)
        if self.fail:
            return httpx.Response(
                503, headers={"retry-after": "600"}, stream=httpx.ByteStream(b"{}")
            )
        data = self.records.get(
            (name, kind),
            answer(name, kind, ["8.8.8.8"] if kind == "A" else ["2606:4700:4700::1111"]),
        )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=httpx.ByteStream(json_bytes(data)),
        )

    def factory(self, evidence, settings, **kwargs):
        return GooglePublicDnsProvider(
            evidence,
            Settings(timeout=2, operation_budget=6, interval=0),
            transport=httpx.MockTransport(self),
            **kwargs,
        )
