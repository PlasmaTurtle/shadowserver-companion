"""Opt-in CI partitioning after pytest discovers the complete test inventory.

Whole modules stay together, preserving module fixtures and test order. Each CI
job has a separate checkout and workspace; no test state passes between shards.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path


def module_plan(paths, shards):
    if shards < 1:
        raise ValueError("Shard count must be positive")
    return {path: index % shards + 1 for index, path in enumerate(sorted(set(paths)))}


def pytest_addoption(parser):
    group = parser.getgroup("CI partitioning")
    group.addoption("--ci-shards", type=int, default=1)
    group.addoption("--ci-shard", type=int, default=1)


def pytest_configure(config):
    count, index = config.getoption("ci_shards"), config.getoption("ci_shard")
    if count < 1 or not 1 <= index <= count:
        from pytest import UsageError

        raise UsageError("Require --ci-shards >= 1 and 1 <= --ci-shard <= --ci-shards")


def pytest_collection_modifyitems(config, items):
    count, index = config.getoption("ci_shards"), config.getoption("ci_shard")
    paths = [item.path.relative_to(config.rootpath).as_posix() for item in items]
    plan = module_plan(paths, count)
    selected, deselected = [], []
    for item, path in zip(items, paths, strict=True):
        (selected if plan[path] == index else deselected).append(item)
    inventory = Counter(paths)
    manifest = {
        "shard": index,
        "shards": count,
        "collected_tests": len(items),
        "selected_tests": len(selected),
        "inventory_sha256": hashlib.sha256(
            "\n".join(sorted(item.nodeid for item in items)).encode()
        ).hexdigest(),
        "modules": [
            {"path": path, "shard": shard, "tests": inventory[path]} for path, shard in plan.items()
        ],
        "selected_nodeids": [item.nodeid for item in selected],
    }
    Path("shard-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    config._ci_shard_manifest = manifest
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected
    if not selected:
        from pytest import UsageError

        raise UsageError(f"CI shard {index}/{count} selected no tests")


def pytest_report_collectionfinish(config):
    manifest = getattr(config, "_ci_shard_manifest", None)
    if manifest is None:
        return None
    return (
        f"CI shard {manifest['shard']}/{manifest['shards']}: "
        f"{manifest['selected_tests']} of {manifest['collected_tests']} tests; "
        "whole modules retained (see shard-manifest.json)"
    )
