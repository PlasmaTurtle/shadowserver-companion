"""Immutable website evidence shared by qualification, Leads and reports.

Browser work belongs to Tools. This boundary retains its output before an entity
exists, binds a successful capture after qualification, and adopts the exact
original and preview into a case. Display and adoption never recapture a website.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from modules.tools.components.filesystem import read_contained_file
from modules.tools.components.website_capture import download_activity, web_url
from modules.workspace.components.primitives import uid
from .image_evidence import metadata_path, remove_screenshot, write_screenshot


def is_usable_capture(metadata):
    """A rendered public or login page is usable; diagnostics are not."""
    if metadata.get("capture_status") not in {"captured", "login_required"}:
        return False
    status = metadata.get("http_status")
    if not isinstance(status, int) or not (200 <= status < 400 or status in {401, 407}):
        return False
    try:
        web_url(metadata["final_url"])
    except (KeyError, TypeError, ValueError):
        return False
    readiness = metadata.get("load_readiness")
    return not readiness or bool(
        readiness.get("document_loaded") and readiness.get("document_ready")
    )


def related_capture(metadata, root_domain):
    """The loaded site must stay within the attributed domain's family."""
    try:
        final = urlsplit(web_url(metadata["final_url"])).hostname
        root = urlsplit(web_url("https://" + root_domain.rstrip("."))).hostname.casefold()
        host = final.casefold().rstrip(".")
        return host == root or host.endswith("." + root)
    except (KeyError, TypeError, ValueError):
        return False


def capture_metadata(metadata):
    """Retain capture provenance with a bounded projection of browser download events."""
    normalized = dict(metadata)
    if "download_activity" in normalized:
        normalized.pop("download_activity")
        normalized.update(download_activity(metadata))
    return normalized


def prepare(store, png, metadata, *, root_domain):
    """Write capture files before a short publication transaction."""
    metadata = json.loads(
        json.dumps(capture_metadata(metadata), ensure_ascii=False, allow_nan=False)
    )
    requested = web_url(metadata["requested_url"])
    final = web_url(metadata["final_url"]) if metadata.get("final_url") else ""
    root = root_domain.casefold().rstrip(".")
    if not related_capture({"final_url": requested}, root):
        raise ValueError("Capture request does not belong to its source domain")
    if not metadata.get("captured_at") or not metadata.get("capture_status"):
        raise ValueError("Capture has no recorded time or outcome")
    identity = uid()
    files = write_screenshot(store, identity, root + "-viewport.png", png, website_capture=metadata)
    reference = {
        "id": identity,
        "root_domain": root,
        "requested_url": requested,
        "final_url": final,
        "capture_status": metadata["capture_status"],
        "captured_at": metadata["captured_at"],
        **files,
    }
    return reference


def publish(db, reference):
    """Publish prepared files inside the caller's guarded transaction."""
    db.execute(
        "INSERT INTO website_captures("
        + ",".join(reference)
        + ") VALUES("
        + ",".join("?" for _ in reference)
        + ")",
        tuple(reference.values()),
    )


def retain(store, png, metadata, *, root_domain):
    """Save a new immutable revision; failed publication removes its files."""
    reference = prepare(store, png, metadata, root_domain=root_domain)
    try:
        with store.transaction() as db:
            publish(db, reference)
    except BaseException:
        remove_screenshot(store, reference)
        raise
    return reference


def _checked(store, reference):
    raw = read_contained_file(store.root, reference["path"], sha256=reference["sha256"])
    preview_bytes = read_contained_file(
        store.root, reference["preview_path"], sha256=reference["preview_sha256"]
    )
    encoded = read_contained_file(
        store.root, reference["metadata_path"], sha256=reference["metadata_sha256"]
    )
    metadata = json.loads(encoded)
    if (
        metadata.get("sha256") != reference["sha256"]
        or metadata.get("preview_sha256") != reference["preview_sha256"]
    ):
        raise ValueError("Website capture metadata differs from its retained image")
    capture = metadata.get("website_capture") or {}
    if any(
        capture.get(key) != reference[key]
        for key in ("requested_url", "final_url", "captured_at", "capture_status")
    ):
        raise ValueError("Website capture metadata differs from its retained provenance")
    return {**reference, "capture": capture}, raw, preview_bytes, encoded


def get(store, capture_id, *, db=None):
    """Return a reference only after checking original, derivative and metadata."""
    if db is None:
        with store.read_snapshot() as db:
            return get(store, capture_id, db=db)
    row = db.execute("SELECT * FROM website_captures WHERE id=?", (capture_id,)).fetchone()
    if row is None:
        raise KeyError("Retained website capture not found")
    return _checked(store, dict(row))[0]


def preview(store, capture_id, *, original=False):
    with store.read_snapshot() as db:
        row = db.execute("SELECT * FROM website_captures WHERE id=?", (capture_id,)).fetchone()
        if row is None:
            raise KeyError("Retained website capture not found")
        _, raw, thumbnail, _ = _checked(store, dict(row))
        return raw if original else thumbnail


def source_matches(store, item):
    """Check adopted evidence metadata against its immutable capture revision.

    Manual uploads have no capture association and retain the existing image
    integrity contract. A missing or edited adopted metadata copy cannot turn a
    diagnostic capture into report evidence or replace its URL/time provenance.
    """
    metadata = item.get("source_metadata") or {}
    with store.read_snapshot() as db:
        association = db.execute(
            "SELECT capture_id FROM website_capture_cases WHERE evidence_id=?", (item["id"],)
        ).fetchone()
        capture_id = (
            association["capture_id"] if association else metadata.get("website_capture_id")
        )
        if capture_id is None:
            return True
        row = db.execute("SELECT * FROM website_captures WHERE id=?", (capture_id,)).fetchone()
        if row is None:
            return False
        try:
            reference = dict(row)
            integrity = item.get("file_integrity") or {}
            encoded = read_contained_file(
                store.root, reference["metadata_path"], sha256=reference["metadata_sha256"]
            )
            return (
                metadata == json.loads(encoded)
                and item["sha256"] == reference["sha256"]
                and item["path"] == reference["path"]
                and item["preview_path"] == reference["preview_path"]
                and integrity.get("path_sha256") == reference["sha256"]
                and integrity.get("preview_path_sha256") == reference["preview_sha256"]
            )
        except (OSError, ValueError, KeyError, TypeError):
            return False


def bind(db, capture_id, entity_id, *, root_domain):
    """Bind a complete admitted lead; the caller owns qualification/ownership."""
    row = db.execute("SELECT * FROM website_captures WHERE id=?", (capture_id,)).fetchone()
    if row is None or row["root_domain"] != root_domain.casefold().rstrip("."):
        raise ValueError("Website capture does not belong to the qualified domain")
    if row["capture_status"] not in {"captured", "login_required"} or not related_capture(
        dict(row), root_domain
    ):
        raise ValueError("Website capture does not show a functioning related site")
    db.execute(
        "INSERT OR IGNORE INTO website_capture_entities VALUES(?,?)", (capture_id, entity_id)
    )


def merge_entities(db, source_id, target_id):
    """Transfer display/adoption ownership; capture and case revisions stay intact."""
    db.execute(
        "INSERT OR IGNORE INTO website_capture_entities SELECT capture_id,? "
        "FROM website_capture_entities WHERE entity_id=?",
        (target_id, source_id),
    )
    db.execute("DELETE FROM website_capture_entities WHERE entity_id=?", (source_id,))


def latest_for_entity(db, entity_id, *, root_domain=None):
    args = [entity_id]
    scope = ""
    if root_domain is not None:
        scope = " AND c.root_domain=?"
        args.append(root_domain.casefold().rstrip("."))
    row = db.execute(
        "SELECT c.* FROM website_captures c JOIN website_capture_entities e ON e.capture_id=c.id "
        "WHERE e.entity_id=?" + scope + " ORDER BY c.captured_at DESC,c.rowid DESC LIMIT 1",
        args,
    ).fetchone()
    return dict(row) if row else None


def recent_for_host(store, entity_id, requested_url, *, since):
    """Return a verified, bound capture for the exact request within the caller's freshness limit."""
    with store.read_snapshot() as db:
        row = db.execute(
            "SELECT c.id FROM website_capture_entities e JOIN website_captures c ON c.id=e.capture_id "
            "WHERE e.entity_id=? AND c.requested_url=? AND julianday(c.captured_at) BETWEEN julianday(?) AND julianday('now') "
            "ORDER BY c.captured_at DESC,c.rowid DESC LIMIT 1",
            (entity_id, requested_url, since.isoformat()),
        ).fetchone()
        if row:
            try:
                reference = get(store, row["id"], db=db)
                if is_usable_capture(reference["capture"]):
                    return reference
            except (KeyError, ValueError, OSError):
                pass
    return None


def projection(db, entity_id, *, root_domain=None):
    """Show the entity's current website independently of any particular intake."""
    return _public_capture(latest_for_entity(db, entity_id, root_domain=root_domain))


def _public_capture(capture):
    """Public read projection; filesystem details stay with evidence storage."""
    if capture is None:
        return None
    return {
        key: capture[key]
        for key in (
            "id",
            "root_domain",
            "requested_url",
            "final_url",
            "captured_at",
            "capture_status",
            "sha256",
        )
    } | {"image_url": "/api/website-evidence/" + capture["id"] + "/image"}


def _scope_captures(db, entity_id, entry_ids):
    """Resolve retained evidence from the admissions for these exact source rows."""
    scopes = {}
    for row in db.execute(
        """SELECT DISTINCT e.root_domain,e.import_id,e.hostname,j.status,
                  json_extract(j.qualification,'$.website.id') job_capture,
                  CASE WHEN json_valid(a.evidence_ref)
                       THEN json_extract(a.evidence_ref,'$.website_capture_id') END admitted_capture
           FROM json_each(?) selected JOIN entries e ON e.id=selected.value
           LEFT JOIN jobs j ON j.import_id=e.import_id AND j.domain=e.root_domain
           LEFT JOIN awareness_admission_events a ON a.import_id=e.import_id
               AND a.source_key=e.id AND a.state='admitted'
           WHERE e.lead_id=?""",
        (json.dumps(entry_ids), entity_id),
    ):
        key = row["root_domain"], row["import_id"], row["status"], row["job_capture"]
        hosts, claimed = scopes.setdefault(key, (set(), set()))
        try:
            host = urlsplit(web_url("https://" + row["hostname"].strip().rstrip("."))).hostname
        except ValueError:
            continue
        hosts.add(host)
        if row["admitted_capture"]:
            claimed.add(row["admitted_capture"])

    by_root = {}
    for (root, _import_id, job_status, job_capture), (hosts, claimed) in scopes.items():
        if not claimed and job_status == "qualified" and job_capture:
            claimed.add(job_capture)
        if not claimed and job_status not in (None, "qualified"):
            continue
        sql = """SELECT c.* FROM website_capture_entities b
                 JOIN website_captures c ON c.id=b.capture_id
                 WHERE b.entity_id=? AND c.root_domain=?"""
        args = [entity_id, root]
        if claimed:
            sql += " AND c.id IN (SELECT value FROM json_each(?))"
            args.append(json.dumps(sorted(claimed)))
        matches = [
            capture
            for capture in db.execute(sql, args)
            if urlsplit(capture["requested_url"]).hostname.rstrip(".") in hosts
        ]
        # Old imports and directly created cases may have only the entity binding.
        # Ambiguous revisions cannot establish which image supported that scope.
        if claimed or len(matches) == 1:
            by_root.setdefault(root, []).extend(matches)
    return {
        root: max(captures, key=lambda c: (c["captured_at"], c["id"]))
        for root, captures in by_root.items()
        if captures
    }


def scope_projection(db, entity_id, root_domain, entry_ids):
    """Show a lead's admitted evidence, including observations from a consolidated queue."""
    return _public_capture(_scope_captures(db, entity_id, entry_ids).get(root_domain))


def reference_for_evidence(item):
    """Export the selected evidence revision without exposing storage details.

    Browser captures retain their requested/loaded URL and original capture ID.
    Manual screenshots retain their stated source and evidence identity without
    inventing browser observations. Inclusion and domain scope belong to callers.
    """
    metadata = item.get("source_metadata") or {}
    capture = metadata.get("website_capture") or item.get("capture") or {}
    reference = {"evidence_id": item["id"], "sha256": item["sha256"]}
    if capture:
        reference.update(
            {
                key: capture.get(key, "")
                for key in ("requested_url", "final_url", "captured_at", "capture_status")
            }
        )
        if metadata.get("website_capture_id"):
            reference["capture_id"] = metadata["website_capture_id"]
    else:
        reference.update(
            source_url=item.get("source_url", ""), captured_at=item.get("captured_at", "")
        )
    return reference


def export_references(store, evidence):
    """Read metadata for selected website evidence; never select newer captures."""
    references = []
    for source in evidence:
        item = dict(source)
        if item.get("kind") != "website" or not item.get("included"):
            continue
        if "source_metadata" not in item:
            with store.read_snapshot() as db:
                capture = db.execute(
                    "SELECT c.metadata_sha256 FROM website_capture_cases a "
                    "JOIN website_captures c ON c.id=a.capture_id WHERE a.evidence_id=?",
                    (item["id"],),
                ).fetchone()
            digest = capture["metadata_sha256"] if capture else None
            item["source_metadata"] = json.loads(
                read_contained_file(store.root, metadata_path(item["id"]), sha256=digest)
            )
        references.append(reference_for_evidence(item))
    return references


def attach(store, db, capture_id, case_id):
    """Adopt exact retained bytes; caller guards case editability/version."""
    prior = db.execute(
        "SELECT evidence_id FROM website_capture_cases WHERE capture_id=? AND case_id=?",
        (capture_id, case_id),
    ).fetchone()
    if prior:
        return prior["evidence_id"]
    capture = get(store, capture_id, db=db)
    case = db.execute("SELECT entity_id FROM cases WHERE id=?", (case_id,)).fetchone()
    if (
        case is None
        or db.execute(
            "SELECT 1 FROM case_groups WHERE case_id=? AND root_domain=?",
            (case_id, capture["root_domain"]),
        ).fetchone()
        is None
    ):
        raise ValueError("Website capture is outside this notification's scope")
    identity = uid()
    # Each evidence row has its own metadata name, while the image bytes and
    # provenance remain the retained capture. Frozen report packages copy both.
    encoded = read_contained_file(
        store.root, capture["metadata_path"], sha256=capture["metadata_sha256"]
    )
    store.path(metadata_path(identity)).write_bytes(encoded)
    db.execute(
        "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            identity,
            case["entity_id"],
            "website",
            capture["root_domain"] + "-viewport.png",
            capture["path"],
            capture["preview_path"],
            "Website viewport · " + capture["root_domain"],
            capture["final_url"] or capture["requested_url"],
            capture["captured_at"],
            capture["sha256"],
            int(
                is_usable_capture(capture["capture"])
                and related_capture(capture["capture"], capture["root_domain"])
            ),
            case_id,
        ),
    )
    db.execute("INSERT INTO website_capture_cases VALUES(?,?,?)", (capture_id, case_id, identity))
    return identity


def adopt_for_case(store, db, case_id):
    """Adopt the admitted revisions for selected observations and preserve earlier evidence."""
    case = db.execute("SELECT entity_id FROM cases WHERE id=?", (case_id,)).fetchone()
    if case is None:
        raise ValueError("Notification case not found")
    entries = db.execute(
        """SELECT ce.entry_id FROM case_entries ce
           LEFT JOIN case_entry_conditions cc ON cc.case_id=ce.case_id AND cc.entry_id=ce.entry_id
           WHERE ce.case_id=? AND (cc.conditions IS NULL OR json_array_length(cc.conditions)>0)""",
        (case_id,),
    )
    captures = _scope_captures(db, case["entity_id"], [row["entry_id"] for row in entries])
    return [attach(store, db, capture["id"], case_id) for capture in captures.values()]


def validate_retained(store, *, checkpoint=None):
    """Verify pre-case captures as well as adopted captures during restore."""
    with store.read_snapshot() as db:
        for row in db.execute("SELECT * FROM website_captures"):
            if checkpoint:
                checkpoint("Verifying retained website captures")
            _checked(store, dict(row))
        for row in db.execute(
            "SELECT a.evidence_id,c.metadata_sha256 FROM website_capture_cases a "
            "JOIN website_captures c ON c.id=a.capture_id"
        ):
            if checkpoint:
                checkpoint("Verifying adopted website provenance")
            read_contained_file(
                store.root,
                metadata_path(row["evidence_id"]),
                sha256=row["metadata_sha256"],
            )
