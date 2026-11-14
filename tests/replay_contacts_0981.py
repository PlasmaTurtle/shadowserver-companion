"""Replay retained public captures without network access or copying website HTML.

Usage: python tests/replay_contacts_0981.py --manifest prior-summary.json --output replay.json
The manifest's results must contain result_path entries produced by the live evaluator.
Unknown pages remain explicitly unresolved; replay does not fabricate live coverage.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.contact_discovery import ContactDiscovery, DiscoveryLimits, FetchResponse
from workbench.contact_discovery.policy import DiscoveryError


class CapturedWebsite:
    def __init__(self, result_path):
        self.saved = json.loads(result_path.read_text())
        self.responses, self.sources, self.missing = {}, [], []
        for snapshot in self.saved["snapshots"]:
            path = result_path.parent / (snapshot["sha256"] + ".body.txt")
            body = path.read_bytes()
            if sha256(body).hexdigest() != snapshot["sha256"]:
                raise ValueError(f"Capture integrity mismatch: {path}")
            headers = {"content-type": snapshot.get("content_type", "")}
            if snapshot.get("redirect_url"):
                headers["location"] = snapshot["redirect_url"]
            self.responses[snapshot["url"]] = FetchResponse(
                snapshot["status_code"],
                headers,
                body,
                snapshot.get("truncated", False),
            )
            self.sources.append(
                {
                    key: snapshot.get(key)
                    for key in (
                        "url",
                        "retrieved_at",
                        "status_code",
                        "sha256",
                        "truncated",
                        "captured_bytes",
                    )
                }
            )

    def fetch(self, url, **_kwargs):
        if url not in self.responses:
            self.missing.append(url)
            raise DiscoveryError(
                "replay_missing", "This page was not retained in the original capture set."
            )
        return self.responses[url]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    hashes = {
        name: sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            "workbench/contact_discovery/engine.py",
            "workbench/contact_discovery/extract.py",
            "workbench/contact_discovery/policy.py",
        )
    }
    summary = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "method": "Offline bounded engine replay against SHA-256-verified retained website responses; no live network requests.",
        "source_hashes": hashes,
        "limits": asdict(DiscoveryLimits()),
        "results": [],
    }
    for item in json.loads(args.manifest.read_text())["results"]:
        path = Path(item["result_path"])
        fetcher = CapturedWebsite(path)
        if not fetcher.responses:
            continue
        saved = fetcher.saved
        result = ContactDiscovery(fetcher=fetcher).discover(
            saved["root_hostname"],
            aliases=saved.get("aliases", []),
        )
        summary["results"].append(
            {
                "domain": saved["root_hostname"],
                "original_result": str(path),
                "status": result["status"],
                "outcome": result["outcome"],
                "requests": result["request_count"],
                "bytes": result["bytes_received"],
                "contacts": [
                    {
                        k: c.get(k)
                        for k in (
                            "kind",
                            "value",
                            "purpose",
                            "routing_label",
                            "recommended_for_outreach",
                        )
                    }
                    for c in result["candidates"]
                ],
                "captured_sources": fetcher.sources,
                "missing_replay_pages": fetcher.missing,
                "coverage": [
                    {k: c.get(k) for k in ("url", "state", "status_code")}
                    for c in result["coverage"]
                ],
            }
        )
    summary["source_unchanged_at_end"] = all(
        sha256((ROOT / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sites": len(summary["results"]),
                "source_unchanged_at_end": summary["source_unchanged_at_end"],
            }
        )
    )


if __name__ == "__main__":
    main()
