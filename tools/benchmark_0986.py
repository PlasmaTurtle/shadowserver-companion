"""Offline scaling audit of exact production queries; fictional data only.

Run with Python 3.14 and pinned development requirements. --root selects a
baseline checkout; only a directory marked by this script may be measured.
No live acquisition, browser rendering, OS-cache eviction or Windows result is
inferred. Trace/VM-step instrumentation runs separately from timed repetitions.
"""

from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import os
import platform
import tracemalloc

try:
    import resource
except ImportError:
    resource = None
import socket
import sqlite3
import statistics
import sys
import time
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--workspace", type=Path, required=True)
parser.add_argument("--groups", type=int, default=500)
parser.add_argument("--repeats", type=int, default=5)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--only", default="")
parser.add_argument("--measure-memory", action="store_true")
args = parser.parse_args()
if not 1 <= args.groups <= 20000 or not 1 <= args.repeats <= 9:
    parser.error("Invalid fixture size or repetition count")
sys.path.insert(0, str(args.root.resolve()))
sys.path.insert(0, str(args.root.resolve() / "components/attribution/src"))
from workbench.api import create_app
from workbench.store import Store
from workbench.lead_queue import association, LeadQueue
from workbench.services.case_queries import list_cases
from fastapi.testclient import TestClient

STAMP = "2099-01-01T12:00:00Z"
SOURCE = "performance-fixture.csv"
PER_GROUP = 8


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fields(index, offset):
    return {
        "timestamp": STAMP,
        "hostname": f"mail.perf{index:06d}.example",
        "ip": f"198.18.{(index // 250) % 256}.{index % 250 + 1}",
        "tag": f"CVE-2099-{10000 + index % 1000}",
        "version": f"1.{offset}",
        "severity": "critical",
        "region": "North Carolina",
        "city": "Charlotte",
        "port": 443,
        "protocol": "tcp",
        "geo": "US",
        "fixture": "FICTIONAL PERFORMANCE FIXTURE ONLY",
    }


def seed(folder):
    marker = folder / ".performance-fixture"
    if (folder / "workbench.sqlite3").exists():
        if not marker.is_file() or json.loads(marker.read_text()) != {
            "groups": args.groups,
            "entries_per_group": PER_GROUP,
        }:
            raise RuntimeError("Refusing to measure an unmarked or mismatched workspace")
        return
    folder.mkdir(parents=True, exist_ok=True)
    store = Store(folder)
    original = store.path("originals/" + SOURCE)
    with original.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields(0, 0)))
        writer.writeheader()
        for index in range(args.groups):
            for offset in range(PER_GROUP):
                writer.writerow(fields(index, offset))
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    with store.transaction() as db:
        db.execute(
            "INSERT INTO imports(id,fingerprint,sha256,name,path,created_at,status,config,rows_read,valid_rows,groups_total,groups_done,qualified) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "fixture",
                digest,
                digest,
                SOURCE,
                "originals/" + SOURCE,
                STAMP,
                "done",
                encoded(
                    {
                        "regions": ["North Carolina"],
                        "com_only": False,
                        "exclude_numeric_roots": False,
                    }
                ),
                args.groups * PER_GROUP,
                args.groups * PER_GROUP,
                args.groups,
                args.groups,
                args.groups,
            ),
        )
        for index in range(args.groups):
            entity = f"entity-{index:06d}"
            root = f"perf{index:06d}.example"
            case = f"case-{index:06d}"
            entries = []
            ids = []
            for offset in range(PER_GROUP):
                row = index * PER_GROUP + offset + 2
                data = fields(index, offset)
                entries.append(
                    {
                        "source": {"file": SOURCE, "sheet": "CSV", "row": row, "fields": data},
                        "ip": data["ip"],
                        "private_ip": False,
                    }
                )
                ids.append(hashlib.sha256(f"{digest}:CSV:{row}".encode()).hexdigest())
            draft = {
                "cve_records": [
                    {
                        "id": fields(index, 0)["tag"],
                        "description": "Synthetic record. " * 200,
                        "kev": index % 3 == 0,
                        "severity": "CRITICAL",
                    }
                ]
            }
            db.execute(
                "INSERT INTO leads(id,domain,company,status,created_at,updated_at,attribution,attribution_entry_id,demo) VALUES(?,?,?,?,?,?,?,?,1)",
                (
                    entity,
                    root,
                    "Fictional company " + str(index),
                    "in_progress",
                    STAMP,
                    STAMP,
                    "{}",
                    ids[0],
                ),
            )
            db.execute("INSERT INTO domain_groups VALUES(?,?,?,?)", (root, entity, ids[0], "{}"))
            db.execute(
                "INSERT INTO hostnames VALUES(?,?)",
                (entries[0]["source"]["fields"]["hostname"], root),
            )
            for identifier, entry in zip(ids, entries):
                data = entry["source"]["fields"]
                db.execute(
                    "INSERT INTO entries(id,lead_id,import_id,payload,ip,hostname,tag,version,observed_at,root_domain) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        identifier,
                        entity,
                        "fixture",
                        encoded(entry),
                        entry["ip"],
                        data["hostname"],
                        data["tag"],
                        data["version"],
                        STAMP,
                        root,
                    ),
                )
            db.execute(
                "INSERT INTO cases(id,entity_id,title,created_at,updated_at,draft) VALUES(?,?,?,?,?,?)",
                (case, entity, "Fictional notification", STAMP, STAMP, encoded(draft)),
            )
            db.executemany(
                "INSERT INTO case_entries VALUES(?,?)",
                [(case, i) for i in ids[: (PER_GROUP if index % 4 == 0 else 2)]],
            )
            db.execute(
                "INSERT INTO jobs(id,import_id,domain,payload,status) VALUES(?,?,?,?,?)",
                (f"job-{index:06d}", "fixture", root, encoded(entries), "qualified"),
            )
            db.execute(
                "INSERT INTO lead_queue(id,import_id,root_domain,payload,entity_id,qualified,association_state,status,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?,?,?)",
                (
                    f"queue-{index:06d}",
                    "fixture",
                    root,
                    encoded(entries),
                    entity,
                    "known",
                    ("pending", "deferred", "dismissed")[index % 3],
                    STAMP,
                    STAMP,
                ),
            )
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    marker.write_text(encoded({"groups": args.groups, "entries_per_group": PER_GROUP}))


def logical_digest(store):
    h = hashlib.sha256()
    with store.read_snapshot() as db:
        names = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for name in names:
            assert name.replace("_", "").isalnum()
            for row in db.execute("SELECT rowid,* FROM " + name + " ORDER BY rowid"):
                h.update(encoded([name, list(row)]).encode())
                h.update(b"\n")
    return h.hexdigest()


def rss():
    p = Path("/proc/self/status")
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    return None


def denied(*args, **kwargs):
    raise AssertionError("Network access is forbidden in the offline benchmark")


args.workspace = args.workspace.resolve()
seed(args.workspace)
started = time.perf_counter()
app = create_app(args.workspace, worker=False, report_processes=False)
startup = time.perf_counter() - started
store = app.state.store
before = logical_digest(store)
results = {}
with patch.object(socket.socket, "connect", denied), patch("socket.create_connection", denied):
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert (
            client.post(
                "/api/session/exchange",
                headers={
                    "X-Workbench-Launch": app.state.sessions.issue_launch(),
                    "Origin": "http://127.0.0.1",
                },
            ).status_code
            == 200
        )
        client.headers["X-Workbench-Token"] = client.get("/api/bootstrap").json()["token"]

        def request(path):
            r = client.get(path)
            r.raise_for_status()
            return r.json()

        def associations():
            with store.read_snapshot() as db:
                return [
                    association(
                        db,
                        f"perf{i:06d}.example" if i % 2 else f"unknown{i}.example",
                        [{"source": {"fields": fields(i, 0)}, "ip": fields(i, 0)["ip"]}],
                    )
                    for i in range(min(args.groups, 100))
                ]

        operations = {
            "associate_100_groups": associations,
            "pending_queue": lambda: LeadQueue(store).list(),
            "all_queue": lambda: LeadQueue(store).list("all"),
            "filtered_notification": lambda: list_cases(store, entity_id="entity-000001"),
            "navigation_counts": lambda: request("/api/navigation-counts"),
            "workspace_queue": lambda: request("/api/workspace/queue?as_of=2099-01-03"),
            "entities": lambda: request("/api/entities"),
        }
        for name, function in operations.items():
            if args.only and name not in args.only.split(","):
                continue
            wall = []
            cpu = []
            fingerprint = None
            for _ in range(args.repeats):
                start = time.perf_counter()
                cpu_start = time.process_time()
                value = function()
                wall.append(time.perf_counter() - start)
                cpu.append(time.process_time() - cpu_start)
                serialized = encoded(value).encode()
                digest = hashlib.sha256(serialized).hexdigest()
                assert fingerprint in (None, digest), (
                    name + " returned different data across read repetitions"
                )
                fingerprint = digest
            counters = {"sql": 0, "steps": 0}
            connect = store.connect

            def traced_connect():
                conn = connect()

                def trace(sql):
                    counters["sql"] += 1

                def progress():
                    counters["steps"] += 1000
                    return 0

                conn.set_trace_callback(trace)
                conn.set_progress_handler(progress, 1000)
                return conn

            with patch.object(store, "connect", traced_connect):
                instrumented = function()
                assert hashlib.sha256(encoded(instrumented).encode()).hexdigest() == fingerprint
            heap_peak = None
            if args.measure_memory:
                tracemalloc.start()
                try:
                    measured = function()
                    heap_peak = tracemalloc.get_traced_memory()[1]
                    assert hashlib.sha256(encoded(measured).encode()).hexdigest() == fingerprint
                finally:
                    tracemalloc.stop()
            sql_count = counters["sql"]
            vm_steps = counters["steps"]
            results[name] = {
                "wall_seconds": wall,
                "median_seconds": statistics.median(wall),
                "max_seconds": max(wall),
                "first_seconds": wall[0],
                "cpu_seconds": cpu,
                "sql_statements": sql_count,
                "approx_vm_steps": vm_steps,
                "python_heap_peak_bytes": heap_peak,
                "response_bytes": len(serialized),
                "response_sha256": fingerprint,
                "rss_bytes": rss(),
            }
            print(
                name,
                round(statistics.median(wall), 4),
                "s;",
                sql_count,
                "SQL;",
                vm_steps,
                "VM steps",
                flush=True,
            )
assert logical_digest(store) == before, "A read operation modified saved rows"
result = {
    "version": (args.root / "VERSION").read_text().strip(),
    "groups": args.groups,
    "observations": args.groups * PER_GROUP,
    "repetitions": args.repeats,
    "fixture": "Synthetic, 8 observations and one saved notification per entity; fixtures contain no real targets",
    "platform": platform.platform(),
    "logical_cpus": os.cpu_count(),
    "processor": platform.processor(),
    "python": sys.version,
    "sqlite": sqlite3.sqlite_version,
    "startup_seconds": startup,
    "logical_rows_sha256": before,
    "reads_preserved_rows": True,
    "database_bytes": store.db.stat().st_size,
    "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    * (1 if sys.platform == "darwin" else 1024)
    if resource
    else None,
    "measurements": results,
    "limits": [
        "No OS page-cache flush; first and repeated calls reported separately.",
        "SQL trace and approximate VM steps are from a separate instrumented call.",
        "Timings include production serialization for HTTP endpoints, but no browser or network latency.",
        "Synthetic scaling results do not establish native Windows or GPU performance.",
    ],
}
result["production_code_sha256"] = {
    name: hashlib.sha256((args.root / name).read_bytes()).hexdigest()
    for name in (
        "workbench/lead_queue.py",
        "workbench/intelligence_index.py",
        "workbench/workspace_queue.py",
        "workbench/migrations.py",
    )
}
result["limits"].append(
    "Optional traced Python heap measures allocations during one separate call, not native SQLite allocations or total RSS."
)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + "\n")
