"""Case-scoped, lossless and offline Companion Appendix data.

Source values are retained independently of their display text.  Only caller-
provided case evidence is traversed; this module never opens a database, shared
cache, network address, or a source-supplied filesystem path.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

VERSION = 1
PARTITIONS = (
    ("A", "Reported assets and observations", "introduction"),
    ("B", "Attribution records", "attribution"),
    ("C", "Vulnerability and exploitation records", "vulnerabilities"),
    ("D", "References and supporting material", "information"),
)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def stable_id(prefix, value):
    return prefix + "-" + digest(value)[:16]


def display_value(value):
    if value is None:
        return "null (supplied)"
    if value is False:
        return "false"
    if value is True:
        return "true"
    if value == "":
        return '"" (supplied empty string)'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return str(value)


def _part(value):
    # JSON Pointer escaping prevents a supplied column containing '/' from
    # colliding with a genuinely nested source field.
    return str(value).replace("~", "~0").replace("/", "~1")


def flatten_fields(value, path=""):
    """Ordered leaf fields, with stable JSON Pointer paths; empty containers stay."""
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from flatten_fields(child, path + "/" + _part(key))
    elif isinstance(value, (list, tuple)) and value:
        for index, child in enumerate(value):
            yield from flatten_fields(child, path + "/" + str(index))
    else:
        kind = (
            "null"
            if value is None
            else "boolean"
            if isinstance(value, bool)
            else "object"
            if isinstance(value, dict)
            else "array"
            if isinstance(value, (list, tuple))
            else "number"
            if isinstance(value, (float, int))
            else "string"
        )
        yield {
            "path": path or "/",
            "value": deepcopy(value),
            "text": display_value(value),
            "value_type": kind,
        }


class Appendix:
    def __init__(self):
        self.entries = []
        self.sources = []
        self._source_keys = {}

    def add(
        self,
        partition,
        kind,
        title,
        value,
        *,
        identity=None,
        source_ids=(),
        citations=(),
        referenced_by=(),
        owner=None,
        status=None,
    ):
        section_owner = owner or next(row[2] for row in PARTITIONS if row[0] == partition)
        identifier = stable_id(
            partition, identity if identity is not None else {"kind": kind, "value": value}
        )
        # Preserve each observation occurrence, even if identical rows or legacy
        # duplicate IDs exist. IDs remain deterministic for the saved ordering.
        existing = {item["id"] for item in self.entries}
        base, occurrence = identifier, 1
        while identifier in existing:
            occurrence += 1
            identifier = base + "-" + str(occurrence)
        entry = {
            "id": identifier,
            "partition": partition,
            "kind": kind,
            "owner": section_owner,
            "title": str(title),
            "fields": list(flatten_fields(value)),
            "source_ids": list(dict.fromkeys(source_ids)),
            "citations": list(dict.fromkeys(c for c in citations if c)),
            "referenced_by": list(dict.fromkeys(referenced_by)),
        }
        if status is not None:
            entry["status"] = status
        self.entries.append(entry)
        return entry

    def add_source(self, value, *, partition="D", referenced_by=(), citations=(), owner=None):
        """Print identical snapshots once while retaining every incoming edge."""
        body_hash = value.get("sha256") or value.get("body_sha256")
        revision = value.get("id") or value.get("snapshot_id") or value.get("revision_id")
        key = digest(
            {
                "body_hash": body_hash,
                "retrieved_at": value.get("retrieved_at"),
                "record": value.get("record"),
            }
            if body_hash
            else {
                "revision": revision,
                "metadata": {
                    k: v
                    for k, v in value.items()
                    if k not in {"referenced_by", "citations", "owner", "partition"}
                },
            }
        )
        if key in self._source_keys:
            entry = self._source_keys[key]
            entry["referenced_by"] = list(
                dict.fromkeys(entry["referenced_by"] + list(referenced_by))
            )
            entry["citations"] = list(
                dict.fromkeys(entry["citations"] + [c for c in citations if c])
            )
            source_id = str(revision or body_hash or key)
            entry["source_ids"] = list(dict.fromkeys(entry["source_ids"] + [source_id]))
            alias = {
                k: deepcopy(v) for k, v in value.items() if k not in {"record", "referenced_by"}
            }
            alias_id = digest(alias)
            if alias_id not in entry.setdefault("metadata_alias_hashes", []):
                alias_index = len(entry["metadata_alias_hashes"])
                entry["metadata_alias_hashes"].append(alias_id)
                entry["fields"].extend(
                    flatten_fields(alias, "/source_metadata_aliases/" + str(alias_index))
                )
            for source in self.sources:
                if source["id"] == entry["id"]:
                    source["referenced_by"] = list(entry["referenced_by"])
                    source["source_ids"] = list(entry["source_ids"])
            return entry
        entry = self.add(
            partition,
            "source_snapshot",
            value.get("title")
            or value.get("publisher")
            or value.get("provider")
            or "Captured source record",
            value,
            identity={"source": key},
            citations=citations,
            referenced_by=referenced_by,
            owner=owner,
        )
        entry["source_ids"] = [str(revision or body_hash or key)]
        self._source_keys[key] = entry
        self.sources.append(
            {
                "id": entry["id"],
                "source_ids": entry["source_ids"],
                "sha256": body_hash,
                "owner": entry["owner"],
                "referenced_by": entry["referenced_by"],
            }
        )
        return entry

    def model(self):
        return {
            "version": VERSION,
            "title": "Companion Appendix",
            "index": [
                {
                    "id": letter,
                    "title": title,
                    "owner": owner,
                    "entry_ids": [e["id"] for e in self.entries if e["partition"] == letter],
                }
                for letter, title, owner in PARTITIONS
            ],
            "entries": deepcopy(self.entries),
            "sources": deepcopy(self.sources),
        }


def appendix_nodes(model):
    """Native text nodes for both document renderers, after the sign-off page."""
    nodes = [
        {"kind": "page_break", "section_owner": "closing"},
        {
            "kind": "heading",
            "text": "Companion Appendix",
            "level": 1,
            "section_owner": "information",
            "anchor": "companion-appendix",
        },
        {
            "kind": "text",
            "text": "Detailed source records for this notification. Supplied empty and null values are identified explicitly; absent source fields are not invented.",
            "style": "body",
            "section_owner": "information",
        },
    ]
    for part in model["index"]:
        nodes.append(
            {
                "kind": "text",
                "text": part["id"]
                + " — "
                + part["title"]
                + " ("
                + str(len(part["entry_ids"]))
                + " records)",
                "style": "body",
                "section_owner": part["owner"],
                "target": "appendix-" + part["id"],
            }
        )
    descriptions_seen = {}
    for part in model["index"]:
        nodes.append(
            {
                "kind": "heading",
                "text": "Appendix " + part["id"] + " — " + part["title"],
                "level": 1,
                "section_owner": part["owner"],
                "anchor": "appendix-" + part["id"],
            }
        )
        if not part["entry_ids"]:
            nodes.append(
                {
                    "kind": "text",
                    "text": "No records of this type are included in this notification.",
                    "style": "body",
                    "section_owner": part["owner"],
                }
            )
        for entry in (e for e in model["entries"] if e["partition"] == part["id"]):
            owner = entry["owner"]
            nodes.append(
                {
                    "kind": "heading",
                    "text": entry["id"] + " · " + entry["title"],
                    "level": 2,
                    "section_owner": owner,
                    "anchor": entry["id"],
                }
            )
            if entry["referenced_by"]:
                nodes.append(
                    {
                        "kind": "text",
                        "style": "small",
                        "text": "Referenced by: " + ", ".join(entry["referenced_by"]),
                        "section_owner": owner,
                    }
                )
            if entry["citations"]:
                nodes.append(
                    {
                        "kind": "text",
                        "style": "small",
                        "text": "Sources: "
                        + " ".join("[" + str(c) + "]" for c in entry["citations"]),
                        "section_owner": owner,
                    }
                )
            if entry["source_ids"]:
                nodes.append(
                    {
                        "kind": "text",
                        "style": "small",
                        "text": "Source records: " + ", ".join(str(x) for x in entry["source_ids"]),
                        "section_owner": owner,
                    }
                )
            # Full descriptions are ordinary native paragraphs, not giant cells.
            # Flush field tables before and after a description to retain order.
            rows = []

            def flush():
                if rows:
                    nodes.append(
                        {
                            "kind": "table",
                            "headers": ["Source field / path", "Retained value"],
                            "rows": list(rows),
                            "widths": [2.0, 4.8],
                            "section_owner": owner,
                            "appendix_entry_id": entry["id"],
                        }
                    )
                    rows.clear()

            for field in entry["fields"]:
                is_description = (
                    field["value_type"] == "string"
                    and "description" in field["path"].lower()
                    and len(field["text"]) > 32
                )
                if is_description and field["text"] in descriptions_seen:
                    original_id, original_path = descriptions_seen[field["text"]]
                    rows.append(
                        [
                            {"text": field["path"]},
                            {
                                "text": "Identical published text reproduced in "
                                + original_id
                                + ", field "
                                + original_path
                                + ".",
                                "target": original_id,
                            },
                        ]
                    )
                    continue
                if is_description:
                    descriptions_seen[field["text"]] = (entry["id"], field["path"])
                if field["value_type"] == "string" and (
                    "description" in field["path"].lower() or len(field["text"]) > 1200
                ):
                    flush()
                    nodes.append(
                        {
                            "kind": "text",
                            "text": field["path"],
                            "style": "source_label",
                            "section_owner": owner,
                        }
                    )
                    nodes.append(
                        {
                            "kind": "text",
                            "text": field["text"],
                            "style": "body",
                            "section_owner": owner,
                        }
                    )
                else:
                    rows.append([{"text": field["path"]}, {"text": field["text"]}])
            flush()
    return nodes
