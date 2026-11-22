"""Synthetic RDAP registration payloads and transport server."""

import json

import httpx

ARIN = "https://rdap.arin.net/registry/"


RIPE = "https://rdap.db.ripe.net/"


APNIC = "https://rdap.apnic.net/"


AFRINIC = "https://rdap.afrinic.net/rdap/"


LACNIC = "https://rdap.lacnic.net/rdap/"


IANA4 = "https://data.iana.org/rdap/ipv4.json"


IANA6 = "https://data.iana.org/rdap/ipv6.json"


def entity(domain="example.com", handle="TEST-ENTITY", roles=None):
    return {
        "objectClassName": "entity",
        "handle": handle,
        "roles": roles or ["registrant"],
        "vcardArray": [
            "vcard",
            [
                ["version", {}, "text", "4.0"],
                ["fn", {}, "text", "Synthetic Fixture Organization"],
                ["email", {}, "text", f"support@{domain}"],
            ],
        ],
    }


def network(domain="example.com", **changes):
    data = {
        "rdapConformance": ["rdap_level_0"],
        "objectClassName": "ip network",
        "handle": "SYNTHETIC-NET",
        "startAddress": "8.0.0.0",
        "endAddress": "8.255.255.255",
        "name": "SYNTHETIC FIXTURE",
        "entities": [entity(domain)],
        "notices": [{"title": "Terms", "description": ["https://registry.example.com/terms"]}],
    }
    data.update(changes)
    return data


def response(data=None, status=200, headers=None, raw=None):
    body = raw if raw is not None else json.dumps(data or {}).encode()
    return httpx.Response(
        status,
        headers={"content-type": "application/rdap+json", **(headers or {})},
        stream=httpx.ByteStream(body),
    )


class Server:
    def __init__(self):
        self.calls = []
        self.routes = {}
        self.bootstrap4 = {
            "version": "1.0",
            "services": [
                [["8.0.0.0/8"], [ARIN]],
                [["193.0.0.0/8"], [RIPE]],
                [["1.0.0.0/8"], [APNIC]],
                [["196.0.0.0/8"], [AFRINIC]],
                [["200.0.0.0/8"], [LACNIC]],
            ],
        }
        self.bootstrap6 = {"version": "1.0", "services": [[["2600::/12"], [ARIN]]]}

    def __call__(self, request):
        url = str(request.url)
        self.calls.append(url)
        if url == IANA4:
            return response(self.bootstrap4, headers={"content-type": "application/json"})
        if url == IANA6:
            return response(self.bootstrap6, headers={"content-type": "application/json"})
        item = self.routes.get(url)
        if callable(item):
            return item(request)
        if isinstance(item, dict):
            return response(item)
        raise AssertionError(f"Unexpected request: {url}")
