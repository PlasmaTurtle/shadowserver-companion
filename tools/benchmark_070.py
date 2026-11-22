"""Offline performance fixture, runnable on Windows and other development hosts.

Run from the source checkout after installing development requirements:
    python tools/benchmark_070.py --output-dir benchmark-results

All observations, references and registration records are fictional. External
connections are blocked. This measures local work separately from acquisition;
it cannot establish real provider latency or a Windows result on a Linux host.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import socket
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "modules/attribution/components/engine/src"))

from tests.session_helpers import TestClient
from openpyxl import Workbook
from modules.accretion.components.intake import EntryValidator, CandidateGroup, read_entries
from tests.support.qualification import WhoisRecord, capture_website, registry_factory
from modules.workspace.components.api import create_app
from modules.library.components.intelligence_index import bank_index
from modules.library.components.repositories.sources import SourceRepository
from modules.accretion.components.report_profiles import (
    inventory_metadata,
    notification_eligibility,
    resolve_profile,
)
from modules.investigations.components.report_composition import compose
from modules.investigations.components.reporting import default_draft, render_pdf, render_docx
from modules.ui.components.presentation import document_policy
from modules.workspace.databases.workspace_defaults import DEFAULT_SETTINGS

STAMP = "2099-01-01T12:00:00Z"


def memory():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counter = Counters()
        counter.cb = ctypes.sizeof(counter)
        process = ctypes.windll.kernel32.GetCurrentProcess
        process.restype = wintypes.HANDLE
        get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        get_memory.restype = wintypes.BOOL
        if get_memory(process(), ctypes.byref(counter), counter.cb):
            return {
                "current_rss_bytes": int(counter.WorkingSetSize),
                "peak_rss_bytes": int(counter.PeakWorkingSetSize),
            }
        return {"peak_rss_bytes": None}
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    current = None
    if Path("/proc/self/status").is_file():
        match = re.search(r"^VmRSS:\s+(\d+) kB", Path("/proc/self/status").read_text(), re.M)
        if match:
            current = int(match[1]) * 1024
    return {
        "current_rss_bytes": current,
        "peak_rss_bytes": int(peak * (1 if sys.platform == "darwin" else 1024)),
    }


def machine():
    cpu = platform.processor()
    if Path("/proc/cpuinfo").is_file():
        match = re.search(r"^model name\s*:\s*(.+)", Path("/proc/cpuinfo").read_text(), re.M)
        if match:
            cpu = match[1]
    total_memory = None
    memory_limit = None
    if Path("/proc/meminfo").is_file():
        match = re.search(r"^MemTotal:\s+(\d+) kB", Path("/proc/meminfo").read_text(), re.M)
        if match:
            total_memory = int(match[1]) * 1024
    if Path("/sys/fs/cgroup/memory.max").is_file():
        value = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        memory_limit = int(value) if value.isdigit() else value
    if os.name == "nt":
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong)
                for name in (
                    "total_phys",
                    "avail_phys",
                    "total_page",
                    "avail_page",
                    "total_virtual",
                    "avail_virtual",
                    "extended",
                )
            ]

        state = Status()
        state.length = ctypes.sizeof(state)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            total_memory = int(state.total_phys)
    versions = {}
    for package in ("fastapi", "openpyxl", "reportlab", "python-docx", "pillow", "httpx"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unavailable"
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "python": sys.version,
        "physical_memory_bytes": total_memory,
        "cgroup_memory_limit_bytes": memory_limit,
        "packages": versions,
        "app_version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "native_windows_execution": os.name == "nt",
    }


def letters(number):
    result = ""
    while True:
        result = chr(97 + number % 26) + result
        number = number // 26 - 1
        if number < 0:
            return result


def domains(count):
    # Fictional names; all registry calls are substituted and sockets blocked.
    return ["benchmark" + letters(index) + ".com" for index in range(count)]


def source_record(cve_id):
    return {
        "id": cve_id,
        "source": "Synthetic benchmark provider",
        "verification_status": "published",
        "description": "SYNTHETIC BENCHMARK ONLY. A fictional service condition is used to measure local document generation. No real vulnerability or business is represented.",
        "description_contributor": "Synthetic benchmark provider",
        "public_url": "https://example.com/synthetic/" + cve_id,
        "retrieved_at": STAMP,
        "revision_id": "benchmark-" + cve_id,
        "intelligence_revision_id": "benchmark-" + cve_id,
        "cvss_assessments": [],
        "epss": 0,
        "epss_percentile": 0,
        "epss_date": "2099-01-01",
        "kev": None,
        "ransomware": {"status": "not_supplied", "label": "Not supplied"},
        "sources": [
            {
                "publisher": "Synthetic benchmark provider",
                "public_url": "https://example.com/synthetic/" + cve_id,
                "retrieved_at": STAMP,
            }
        ],
    }


def fixture(path, row_count, cve_count, group_count):
    names = domains(group_count)
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Synthetic scan")
    sheet.append(
        [
            "timestamp",
            "severity",
            "ip",
            "protocol",
            "port",
            "hostname",
            "tag",
            "version",
            "region",
            "city",
            "geo",
            "asn",
            "http_code",
            "latitude",
            "longitude",
            "future_zero",
            "future_false",
            "future_empty",
            "fixture",
        ]
    )
    for number in range(row_count):
        sheet.append(
            [
                STAMP,
                "critical",
                "8.8.8.8",
                "tcp",
                443,
                f"host{number}." + names[number % group_count],
                f"CVE-2099-{10000 + number % cve_count}",
                "Example/1.0 PHP/7.3.25",
                "North Carolina",
                "Charlotte",
                "US",
                64496,
                200,
                35.22,
                -80.84,
                0,
                False,
                None,
                "SYNTHETIC BENCHMARK",
            ]
        )
    workbook.save(path)
    return names


def report_fixture(asset_count, cve_count=3):
    cves = [f"CVE-2099-{10000 + i}" for i in range(cve_count)]
    entries, assets = [], []
    for index in range(asset_count):
        ip = f"192.0.{2 + index // 254}.{1 + index % 254}"
        fields = {
            "timestamp": STAMP,
            "severity": "critical",
            "ip": ip,
            "hostname": "mail.example.com",
            "protocol": "tcp",
            "port": 443,
            "tag": cves[index % cve_count],
            "version": "Example/1.0",
            "region": "North Carolina",
            "asn": 64496,
            "future_zero": 0,
            "future_false": False,
            "future_empty": None,
            "fixture": "SYNTHETIC BENCHMARK",
        }
        entries.append(
            {
                "id": f"benchmark-observation-{index}",
                "ip": ip,
                "private_ip": False,
                "source": {
                    "workbook": "synthetic-70-assets.xlsx",
                    "sheet": "Synthetic",
                    "row": index + 2,
                    "fields": fields,
                },
            }
        )
        assets.append(
            {
                **fields,
                "private_ip": False,
                "location": "Synthetic location",
                "first_seen": STAMP,
                "last_seen": STAMP,
            }
        )
    lead = {"entries": entries, "company": "Synthetic Benchmark Company", "domain": "example.com"}
    settings = {**DEFAULT_SETTINGS, "analyst_name": "Synthetic Benchmark Analyst"}
    draft = default_draft(lead, settings)
    draft.update(
        company=lead["company"],
        sender_name=settings["analyst_name"],
        narrative="Synthetic performance fixture. No real exposure or business is represented.",
        cve_records=[source_record(c) for c in cves],
        website_verified=True,
        reviewed=True,
    )
    proof = {
        "ip": entries[0]["ip"],
        "registry": "Synthetic benchmark provider",
        "protocol": "SYNTHETIC",
        "source_url": "https://example.com/synthetic/registration",
        "retrieved_at": STAMP,
        "evaluated_at": STAMP,
        "attribution": {"value": "admin@example.com", "root_domain": "example.com"},
        "record": {"organization": "Synthetic Benchmark Company", "contact": "admin@example.com"},
    }
    return {
        "draft": draft,
        "profile": settings,
        "domain": "example.com",
        "demo": True,
        "document_policy": document_policy(settings),
        "report_revision": 1,
        "draft_revision": 1,
        "cves": cves,
        "assets": assets,
        "evidence": [],
        "explainers": [],
        "qualified_lead": {
            "validated_leads": [{"hostname": "example.com", "entries": entries}],
            "whois": [proof],
        },
    }


def blocked(*args, **kwargs):
    raise AssertionError("Network connections are prohibited in this benchmark")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark-results"))
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--cves", type=int, default=1000)
    parser.add_argument("--groups", type=int, default=100)
    parser.add_argument("--assets", type=int, default=70)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not (
        1 <= args.groups <= args.rows <= 250000
        and 1 <= args.cves <= args.rows
        and 1 <= args.assets <= 1000
        and 1 <= args.repeats <= 10
    ):
        parser.error("Invalid fixture sizes")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "handling": "TLP:AMBER",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine": machine(),
        "fixture": {
            "rows": args.rows,
            "unique_cves": args.cves,
            "root_groups": args.groups,
            "report_assets": args.assets,
            "report_cves": 3,
            "all_synthetic": True,
        },
        "inventory": inventory_metadata(),
        "network": {
            "external_connections_allowed": False,
            "acquisition_latency_measured": False,
            "attribution_and_cve_providers": "in-process fixture responses",
            "website_capture": "labelled synthetic screenshot; no browser latency",
        },
        "measurements": {},
        "limits": [
            "This is host-specific developer benchmark evidence, not release acceptance.",
            "API timings use in-process ASGI requests including serialization; no browser first-paint timing is measured.",
            "Main-only PDF uses the normal include_appendix=False composition option.",
            "Report rendering uses a separate synthetic layout fixture; it does not certify a notification or verify its evidence.",
            "Fixture sizes in this record define the measured intake and document workloads.",
        ],
    }

    def timed(name, function, repeats=1):
        timings = []
        for _ in range(repeats):
            start = time.perf_counter()
            value = function()
            timings.append(time.perf_counter() - start)
        result["measurements"][name] = {
            "seconds": timings,
            "median_seconds": statistics.median(timings),
            **memory(),
        }
        print(name + ": " + str(round(statistics.median(timings), 4)) + " seconds", flush=True)
        return value

    with ExitStack() as stack:
        connect = socket.socket.connect

        def local_connect(sock, address):
            # Windows asyncio implements its wake-up socketpair over loopback.
            if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
                return connect(sock, address)
            return blocked()

        stack.enter_context(patch.object(socket.socket, "connect", local_connect))
        stack.enter_context(patch("socket.create_connection", blocked))
        temporary = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="companion-benchmark-"))
        )
        source = temporary / "benchmark-scan-http_vulnerable.xlsx"
        names = timed(
            "fixture_creation", lambda: fixture(source, args.rows, args.cves, args.groups)
        )
        originals = timed("workbook_read", lambda: list(read_entries(source, "")))
        validator = EntryValidator({"North Carolina"})
        valid = timed("structural_filter", lambda: validator.validate(originals))
        timed(
            "profile_and_critical_eligibility",
            lambda: [
                notification_eligibility(row.fields, resolve_profile(row.fields, source.name), {})
                for row in originals
            ],
        )
        grouped = timed("root_domain_grouping", lambda: CandidateGroup.group(valid))
        assert (
            len(originals) == args.rows and len(valid) == args.rows and len(grouped) == args.groups
        )
        records = {
            f"CVE-2099-{10000 + i}": source_record(f"CVE-2099-{10000 + i}")
            for i in range(args.cves)
        }

        class Registry:
            def lookup(self, ip):
                return WhoisRecord(
                    ip,
                    "Synthetic provider",
                    "https://example.com/synthetic/registration",
                    STAMP,
                    {
                        "entities": [
                            {
                                "roles": ["registrant"],
                                "vcardArray": [
                                    "vcard",
                                    [["email", {}, "text", "admin@" + name] for name in names],
                                ],
                            }
                        ]
                    },
                )

            def close(self):
                pass

        stack.enter_context(
            patch(
                "modules.accretion.components.intake_service.verify",
                lambda store, cve_id, *, local_only: deepcopy(records[cve_id]),
            )
        )
        app = create_app(
            temporary / "workspace",
            worker=False,
            attribution_factory=registry_factory(Registry),
            capture=capture_website,
        )
        intake, store = app.state.intake, app.state.store
        imported = intake.enqueue(source.name, source.read_bytes())
        timed("production_intake_with_fixture_providers", lambda: intake.process(imported["id"]))
        saved = store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
        assert saved["status"] == "done", saved["error"]
        assert saved["rows_read"] == args.rows and saved["valid_rows"] == args.rows
        assert store.one("SELECT count(*) n FROM entries")["n"] == args.rows
        result["fixture"]["saved_rows"] = saved["rows_read"]
        result["fixture"]["saved_groups"] = saved["groups_total"]
        with store.transaction() as db:
            for cve_id, record in records.items():
                SourceRepository(store).publish_intelligence(db, cve_id, record)
        bank = timed("cached_intelligence_index", lambda: bank_index(store), args.repeats)
        assert len(bank) == args.cves
        client = stack.enter_context(TestClient(app, base_url="http://127.0.0.1"))

        def request(path):
            response = client.get(path)
            response.raise_for_status()
            return response.json()

        cold = timed("eclipse_cold_api", lambda: request("/api/eclipse"))
        assert cold["counts"]["rows"] == args.rows
        warm = timed("eclipse_warm_api", lambda: request("/api/eclipse"), args.repeats)
        assert warm["counts"]["rows"] == args.rows

        def dashboard_queue():
            return request("/api/dashboard"), request("/api/cases"), request("/api/leads")

        queue = timed("dashboard_case_and_lead_queue_api", dashboard_queue, args.repeats)
        assert queue[0]["counts"]["observations"] == args.rows
        assert len(queue[2]) == args.groups and not queue[1]
        data = report_fixture(args.assets)
        data["composition"] = timed(
            "report_assembly_70_assets", lambda: compose(data), args.repeats
        )
        entries = data["composition"]["appendix"]["entries"]
        assert sum(e["kind"] == "observation" for e in entries) == args.assets
        result["fixture"]["appendix_entries"] = len(entries)
        result["fixture"]["appendix_fields"] = sum(len(e["fields"]) for e in entries)
        front = deepcopy(data)
        front["draft"]["include_appendix"] = False
        front["composition"] = compose(front)
        timed(
            "main_only_pdf_render_after_assembly",
            lambda: render_pdf(front, output / "BENCHMARK-front-only.pdf", temporary, draft=True),
            args.repeats,
        )
        timed(
            "complete_pdf_with_appendix_render",
            lambda: render_pdf(data, output / "BENCHMARK-complete.pdf", temporary, draft=True),
        )
        timed(
            "complete_docx_with_appendix_render",
            lambda: render_docx(data, output / "BENCHMARK-complete.docx", temporary),
        )
    measurements = result["measurements"]
    result["targets"] = {
        "cached_dashboard_queue_under_5_seconds": measurements["dashboard_case_and_lead_queue_api"][
            "median_seconds"
        ]
        < 5,
        "70_asset_main_pdf_after_assembly_under_3_seconds": measurements[
            "main_only_pdf_render_after_assembly"
        ]["median_seconds"]
        < 3,
        "windows_reference_workstation_verified": os.name == "nt",
    }
    result["artifacts"] = {
        p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in output.glob("BENCHMARK-*")
        if p.is_file()
    }
    result["final_memory"] = memory()
    (output / "performance-070.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"result": str(output / "performance-070.json"), "targets": result["targets"]}, indent=2
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
