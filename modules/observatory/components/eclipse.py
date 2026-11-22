"""Canonical, read-only Observatory projections.

Accretion owns admission, identity and association. This view reads its committed
records without reparsing imports, rerunning qualification or retiring findings.
Original imports and certified report snapshots remain separate evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from threading import RLock
from contextlib import closing
from csv import Error as CSVError
from datetime import date, datetime
import hashlib
from ipaddress import ip_address
import json
import math
import tempfile
from pathlib import Path

from modules.accretion.components.dark_matter import REASONS
from modules.accretion.components.api_jurisdiction import state_scope
from modules.entities.components.entity_validation import STATE_NAMES, state_code
from modules.library.components.intelligence_index import decorate_rows
from modules.ui.components.presentation import HANDLING
from modules.workspace.components.primitives import now

MAX_RECORDS = 100000
STATUS_BASIS = "Admission, attribution and current workflow are independent; observations retain their reported dates."


def density_band(count):
    return (
        "purple" if count > 1000 else "red" if count > 200 else "yellow" if count > 50 else "normal"
    )


def _support_projection(support):
    approved = support.get("approved_observation_count", 0)
    unknown = support.get("legacy_unknown_observation_count", 0)
    result = {
        key: support.get(key, 0 if key.endswith("count") else "")
        for key in (
            "reported_observation_count",
            "approved_observation_count",
            "legacy_unknown_observation_count",
            "reported_first_seen",
            "reported_last_seen",
            "approved_first_seen",
            "approved_last_seen",
        )
    }
    result["admission_state"] = (
        "admitted" if approved else "legacy_unknown" if unknown else "observed"
    )
    if not approved and unknown:
        result.update(
            admitted=False,
            dark_matter=False,
            status="qualification_unknown",
            intake_disposition="qualification_unknown",
            intake_reason="qualification_unknown",
            disposition_reason=_reason_label("qualification_unknown"),
        )
    return result


def _approved_fields(finding):
    facts = _json(finding.get("approved_facts"), {})
    return {key: facts[key] for key in ("version", "product", "protocol", "port") if facts.get(key)}


def _reason_label(reason):
    if reason == "qualification_unknown":
        return "Qualification provenance is unavailable for this legacy observation."
    return (
        REASONS.get(reason, reason.replace("_", " ").capitalize())
        if reason
        else "Not admitted by Accretion."
    )


def _text(value):
    return "" if value is None else str(value)


def _json(value, default):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def _day(value):
    try:
        return date.fromisoformat(_text(value)[:10]).isoformat()
    except (ValueError, TypeError):
        return ""


def _coordinates(fields):
    # Only explicit coordinate pairs are accepted. A city is not an IP location.
    for lat_key, lon_key in (("latitude", "longitude"), ("lat", "lon"), ("latitude", "long")):
        lat, lon = fields.get(lat_key), fields.get(lon_key)
        if lat in (None, "") or lon in (None, "") or isinstance(lat, bool) or isinstance(lon, bool):
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    return None, None


def _asn(value):
    value = _text(value).strip()
    if value.upper().startswith("AS"):
        value = value[2:]
    try:
        number = float(value)
        return (
            str(int(number))
            if math.isfinite(number) and number.is_integer() and 0 <= number <= 4294967295
            else ""
        )
    except (ValueError, OverflowError):
        return ""


class Eclipse:
    """One instance per workspace. All reads share a consistent SQLite snapshot."""

    def __init__(self, store, cache_files=4):
        self.store = store
        self._view_lock = RLock()
        self._view_base = None
        self._observed_reference_cache = None
        self._view_results = {}
        self._field_results = {}
        try:
            self._places = json.loads(
                (
                    Path(__file__).resolve().parents[3]
                    / "modules/observatory/static/geo/places.json"
                ).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            self._places = {}

    def _location(self, fields):
        latitude, longitude = _coordinates(fields)
        if latitude is not None:
            return (
                latitude,
                longitude,
                "reported_coordinates",
                "Coordinates supplied in the source report",
                "",
            )
        try:
            region = state_code(fields.get("region"))
        except ValueError:
            region = ""
        country = _text(fields.get("geo") or fields.get("country")).strip().upper()
        key = str(region) + "|" + " ".join(_text(fields.get("city")).casefold().split())
        place = (
            self._places.get("places", {}).get(key)
            if region
            and (
                country in ("", "US", "USA", "UNITED STATES")
                or (region == "PR" and country == "PR")
            )
            else None
        )
        if place:
            return (
                place["latitude"],
                place["longitude"],
                "city_area",
                "Reported city · U.S. Census representative point (approximate area, not an asset position)",
                self._places.get("source", {}).get("url", ""),
            )
        return (
            None,
            None,
            "unplaced",
            "No usable reported coordinates or unambiguous city-area match",
            "",
        )

    def _jurisdiction(self, db=None):
        """Saved geographic context, never a filter on historical evidence."""
        regions = self.store.settings(db).get("regions", [])
        states, unsupported = set(), []
        for region in regions:
            code = state_scope(region)
            if not code:
                unsupported.append(str(region))
                continue
            states.add(code)
        return {
            "states": sorted(states),
            "label": ", ".join(STATE_NAMES.get(code, code) for code in sorted(states))
            if len(states) <= 3
            else f"{len(states)} selected states/territories",
            "unsupported_regions": sorted(set(unsupported)),
            "basis": "Configured jurisdiction provides map context; all matching historical entities remain available. Geographic outlines do not define legal jurisdiction.",
        }

    def _entity_location(self, profile):
        """Current saved entity city area, never an inferred IP/business address."""
        profile = profile if isinstance(profile, dict) else {}
        city, region = _text(profile.get("city")), _text(profile.get("state"))
        latitude, longitude, basis, _, source_url = self._location(
            {"city": city, "region": region, "country": "US"}
        )
        placed = basis == "city_area"
        return {
            "city": city,
            "region": region,
            "country": "US" if city or region else "",
            "latitude": latitude,
            "longitude": longitude,
            "location_basis": "entity_city_area" if placed else "unplaced",
            "approximate": placed,
            "location_source": "Current saved entity profile city/state",
            "location_source_url": source_url,
            "location_temporal_basis": "current_saved_profile",
            "unplaced_reason": ""
            if placed
            else (
                "Save an entity city and state to place this entity."
                if not city or not region
                else "The saved city/state has no unambiguous supported city-area match."
            ),
        }

    def _exact_source_fields(self, source, imported):
        """Read historical provenance only when its exact source row is requested."""
        from modules.accretion.components.intake import read_entries
        from modules.accretion.components.api_import import MAX_API_DOWNLOAD

        path = self.store.path(imported["path"])
        with tempfile.TemporaryDirectory(prefix="observatory-source-") as folder:
            copy = Path(folder) / ("source" + path.suffix)
            checksum, size = hashlib.sha256(), 0
            with path.open("rb") as incoming, copy.open("wb") as output:
                while chunk := incoming.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_API_DOWNLOAD:
                        raise ValueError("Original report exceeds the import size limit")
                    checksum.update(chunk)
                    output.write(chunk)
            if checksum.hexdigest() != source["source_sha256"]:
                raise ValueError("Original report no longer matches its recorded fingerprint")
            with closing(read_entries(copy, source.get("sheet", ""))) as entries:
                for count, entry in enumerate(entries, 1):
                    if count > 250000:
                        raise ValueError("Original report exceeds the row limit")
                    if entry.row == source.get("row_number") and entry.sheet == source.get("sheet"):

                        def safe(value):
                            if isinstance(value, dict):
                                return {str(k): safe(v) for k, v in value.items()}
                            if isinstance(value, (list, tuple)):
                                return [safe(v) for v in value]
                            if isinstance(value, (datetime, date)):
                                return value.isoformat()
                            if isinstance(value, float) and not math.isfinite(value):
                                return None
                            return (
                                value
                                if value is None or isinstance(value, (str, int, float, bool))
                                else str(value)
                            )

                        return safe(entry.fields)
            raise ValueError("The requested source row is unavailable")

    def _build(self, detail_id=None, *, events=True, detail_finding_id="", detail_intake=""):
        """Compose canonical evidence and the archive's public read model."""
        from .observatory_dark_matter import append_records, project_record

        if detail_id and not detail_finding_id:
            archived = self.store.dark_matter.get(detail_id)
            if archived and not archived["promoted"]:
                row = project_record(archived, self._location)
                return {"observations": [row], "findings": []}, row
        with self.store.read_snapshot() as db:
            snapshot, detail = self._project(
                db,
                detail_id,
                events=events,
                detail_finding_id=detail_finding_id,
                detail_intake=detail_intake,
            )
        if detail_id is None:
            archived_rows = append_records(
                snapshot, self.store.dark_matter, self._location, limit=MAX_RECORDS
            )
            if archived_rows:
                from modules.library.components.catalog_outreach import decorate_observations

                decorate_rows(self.store, archived_rows, kind="observations")
                decorate_observations(self.store.root, archived_rows)
        return snapshot, detail

    def _project(self, db, detail_id=None, *, events=True, detail_finding_id="", detail_intake=""):
        from .observatory_queries import load

        (
            imports,
            entities,
            entity_profiles,
            groups,
            cases,
            condition_scopes,
            entry_cases,
            pending,
            densities,
            stats,
            raw,
            sources,
            memberships,
            exact_entry,
            overall,
        ) = load(db, detail_id, events=events)
        truncated = False

        warnings = (
            [
                f"Showing the first {MAX_RECORDS:,} canonical records; narrow the selection for additional records."
            ]
            if truncated
            else []
        )
        available = {}
        for identity, item in imports.items():
            try:
                available[identity] = self.store.path(item["path"]).is_file()
            except (OSError, ValueError):
                available[identity] = False

        def finding_work(finding, links):
            linked = {}
            case = cases.get(finding.get("handled_case_id"))
            if case:
                linked[case["id"]] = case
            for source in links:
                for entry_id in {source.get("entry_id"), source.get("source_key")} - {None, ""}:
                    for case in entry_cases.get(entry_id, []):
                        scope = condition_scopes.get((case["id"], entry_id))
                        # Legacy cases without condition capture are limited to an
                        # explicitly handled finding; never adopt a later CVE.
                        if scope is not None and finding.get("condition") in scope:
                            linked[case["id"]] = case
            linked_cases = sorted(
                linked.values(), key=lambda c: (c["updated_at"], c["id"]), reverse=True
            )
            active = next(
                (c for c in linked_cases if c["stage"] != "closed"),
                linked_cases[0] if linked_cases else None,
            )
            delivered = sorted(c["delivered_at"] for c in linked_cases if c["delivered_at"])
            admitted = bool(finding.get("admitted"))
            return {
                "case_id": active["id"] if active else None,
                "case_stage": active["stage"] if active else "",
                "delivered_at": delivered[0] if delivered and admitted else None,
                "status": "delivered"
                if admitted and delivered
                else "qualified"
                if admitted
                else "excluded",
                "workflow": finding.get("workflow", "unworked"),
            }, linked_cases

        rows, finding_rows = [], []
        attributions = {key: _json(value.get("attribution"), {}) for key, value in groups.items()}
        score_cache = {}
        for item in [*pending.values(), *cases.values()]:
            score_cache[item["id"]] = _json(item.get("intake_score"), {})
        for value in raw:
            fields = _json(value["summary"], {})
            normalized = _json(value["normalized"], {})
            observation_id = value["id"]
            finding_id = value.get("finding_id")
            identity = finding_id or observation_id
            links = sources[observation_id]
            source = next(
                (
                    item
                    for item in links
                    if item["source_key"]
                    == (value.get("finding_source_key") or value.get("source_key"))
                ),
                links[0] if links else {},
            )
            exact_source = next(
                (
                    item
                    for item in links
                    if detail_id and detail_id in {item.get("source_key"), item.get("entry_id")}
                ),
                None,
            )
            fields_error = ""
            resolved_fields = None
            if exact_source:
                source = exact_source
            if detail_id and detail_finding_id:
                requested_finding = next(
                    (f for f in memberships[observation_id] if f["id"] == detail_finding_id), None
                )
                if requested_finding is None:
                    return {}, None
                known_source = next(
                    (
                        item
                        for item in links
                        if item["source_key"] == requested_finding["latest_source_key"]
                    ),
                    None,
                )
                if known_source is not None:
                    source = known_source
                else:
                    # Older coalesced observations can have complementary report
                    # rows. Resolve the actual supporting row only on demand.
                    from modules.accretion.components.awareness import conditions

                    for candidate in links:
                        try:
                            original_fields = self._exact_source_fields(
                                candidate, imports.get(candidate.get("import_id"), {})
                            )
                            original_conditions = {
                                condition
                                for condition, _ in conditions(
                                    {"source": {"fields": original_fields}}
                                )
                            }
                            if requested_finding["condition"] in original_conditions:
                                source, resolved_fields = candidate, original_fields
                                break
                        except (OSError, ValueError, KeyError, CSVError):
                            continue
                    if resolved_fields is None:
                        fields_error = "The exact source row supporting this finding at the selected observation could not be verified."
                        resolved_fields = {}
            if resolved_fields is not None:
                fields = resolved_fields
            if (
                resolved_fields is None
                and detail_id
                and (
                    source.get("source_key") != value.get("source_key")
                    or any(isinstance(item, str) and len(item) >= 4096 for item in fields.values())
                )
            ):
                if exact_entry and isinstance(
                    (exact_entry.get("source") or {}).get("fields"), dict
                ):
                    fields = exact_entry["source"]["fields"]
                else:
                    try:
                        fields = self._exact_source_fields(
                            source, imports.get(source.get("import_id"), {})
                        )
                    except (OSError, ValueError, KeyError, CSVError):
                        fields = {}
                        fields_error = "Historical source fields are unavailable or failed their fingerprint check."
            imported = imports.get(source.get("import_id"), {})
            entity = entities.get(value["entity_id"], {})
            group = groups.get(value["root_domain"], {})
            attribution = attributions.get(value["root_domain"], {})
            review = attribution.get("review") or {}
            linked = {}
            for item in links:
                for entry_id in {item.get("entry_id"), item.get("source_key")} - {None, ""}:
                    linked.update((c["id"], c) for c in entry_cases.get(entry_id, []))
            for finding in memberships[observation_id]:
                case = cases.get(finding.get("handled_case_id"))
                if case:
                    linked[case["id"]] = case
            if value.get("handled_case_id") in cases:
                linked[value["handled_case_id"]] = cases[value["handled_case_id"]]
            linked_cases = sorted(
                linked.values(), key=lambda c: (c["updated_at"], c["id"]), reverse=True
            )
            active_case = next(
                (c for c in linked_cases if c["stage"] != "closed"),
                linked_cases[0] if linked_cases else None,
            )
            delivered = sorted(c["delivered_at"] for c in linked_cases if c["delivered_at"])
            admitted = bool(value.get("finding_admitted", value["admitted"]))
            status = (
                "delivered" if admitted and delivered else "qualified" if admitted else "excluded"
            )
            lead = pending.get(value["entity_id"] or value["root_domain"], {}) if admitted else {}
            score = score_cache.get(lead.get("id")) or score_cache.get(
                (active_case or {}).get("id"), {}
            )
            try:
                address = ip_address(value["ip"])
                address_text, valid_ip, nonpublic = address.compressed, True, not address.is_global
            except ValueError:
                address_text, valid_ip, nonpublic = value["ip"], False, False
            latitude, longitude, location_basis, location_source, location_source_url = (
                self._location(fields)
            )
            density_id = (
                "entity:" + value["entity_id"]
                if value["entity_id"]
                else "asset:" + value["asset_id"]
            )
            density = densities.get(density_id, {})
            support = stats.get(finding_id, {})
            support_days = sorted(filter(None, str(support.get("days") or "").split(",")))
            tag = (
                value.get("condition")
                or "; ".join(sorted({f["condition"] for f in memberships[observation_id]}))
                or _text(fields.get("tag"))
            )
            condition_workflows = {
                f["condition"]: {
                    **finding_work({**f, "admitted": f["admission_state"] == "admitted"}, links)[0],
                    "finding_id": f["id"],
                    "admitted": f["admission_state"] == "admitted",
                    "admission_state": f["admission_state"],
                    "intake_reason": "qualification_unknown"
                    if f["admission_state"] == "legacy_unknown"
                    else f["reason"],
                    "disposition_reason": _reason_label(
                        "qualification_unknown"
                        if f["admission_state"] == "legacy_unknown"
                        else f["reason"]
                    )
                    if f["admission_state"] != "admitted"
                    else "",
                }
                for f in memberships[observation_id]
            }
            if finding_id:
                found = next((f for f in memberships[observation_id] if f["id"] == finding_id), {})
                work, linked_cases = finding_work(found, links)
                status = work["status"]
                active_case = cases.get(work["case_id"])
                delivered = [work["delivered_at"]] if work["delivered_at"] else []
            from modules.accretion.components.intake.versions import entry_fields

            projected_fields = entry_fields(
                {"source": {"fields": fields}, "normalized": normalized}
            )
            products = normalized.get("products") or []
            product_names = list(
                dict.fromkeys(
                    _text(item.get("product") or item.get("name")).strip()
                    for item in products
                    if isinstance(item, dict) and (item.get("product") or item.get("name"))
                )
            )
            row = {
                "id": identity,
                "finding_id": finding_id,
                "observation_id": observation_id,
                "asset_id": value["asset_id"],
                "record_kind": "finding" if finding_id else "observation",
                "finding_ids": [f["id"] for f in memberships[observation_id]],
                "admitted_finding_ids": [
                    f["id"]
                    for f in memberships[observation_id]
                    if f["admission_state"] == "admitted"
                ],
                "unadmitted_finding_ids": [
                    f["id"]
                    for f in memberships[observation_id]
                    if f["admission_state"] != "admitted"
                ],
                "condition_admissions": {
                    f["condition"]: f["admission_state"] == "admitted"
                    for f in memberships[observation_id]
                },
                "finding_admission_states": {
                    f["id"]: f["admission_state"] for f in memberships[observation_id]
                },
                "finding_approved_fields": {
                    f["id"]: _approved_fields(f)
                    for f in memberships[observation_id]
                    if f["admission_state"] == "admitted"
                },
                "condition_findings": {
                    f["condition"]: f["id"] for f in memberships[observation_id]
                },
                "finding_kind": value.get("finding_kind", ""),
                "condition_workflows": condition_workflows,
                "ip": address_text,
                "ip_valid": valid_ip,
                "nonpublic_ip": nonpublic,
                "hostname": value["hostname"],
                "domain": value["root_domain"],
                "tag": tag,
                "reported_tag": _text(fields.get("tag")),
                "version": _text(projected_fields.get("version")),
                "product": _text(
                    "; ".join(product_names)
                    or fields.get("product")
                    or fields.get("application")
                    or fields.get("service")
                ),
                "product_versions": products,
                "protocol": _text(fields.get("protocol")),
                "port": _text(fields.get("port")),
                "asn": _asn(fields.get("asn")),
                "city": _text(fields.get("city")),
                "region": _text(fields.get("region")),
                "country": _text(fields.get("geo") or fields.get("country")),
                "latitude": latitude,
                "longitude": longitude,
                "location_basis": location_basis,
                "location_source": location_source,
                "location_source_url": location_source_url,
                "observed_at": value["observed_at"],
                "observed_day": _day(value["observed_at"]),
                "observed_days": support_days
                or ([_day(value["observed_at"])] if _day(value["observed_at"]) else []),
                "imported_at": imported.get("created_at", value["first_recorded_at"]),
                "first_indexed_at": min(
                    (finding["created_at"] for finding in memberships[observation_id]),
                    default=value["first_recorded_at"],
                ),
                "first_seen": value.get("first_seen") or value["observed_at"],
                "last_seen": value.get("last_seen") or value["observed_at"],
                "changed_at": value.get("changed_at") or value["first_recorded_at"],
                "fresh_at": value.get("changed_at")
                or max(
                    (f["changed_at"] for f in memberships[observation_id]),
                    default=value["first_recorded_at"],
                ),
                "admitted": admitted,
                "status": status,
                "workflow": value.get("workflow") or ("handled" if active_case else "unworked"),
                "intake_disposition": "lead" if admitted else "dark_matter",
                "dark_matter": not admitted,
                "intake_reason": value.get("finding_reason") or value["reason"],
                "disposition_reason": "Admitted finding; repeats and completed work retain approval."
                if admitted
                else _reason_label(value.get("finding_reason") or value["reason"]),
                "observation_count": support.get("observation_count", 1),
                "sightings": support.get("day_count", int(bool(_day(value["observed_at"])))),
                "density_id": density_id,
                "density_count": density.get("observation_count", 0),
                "density_band": density_band(density.get("observation_count", 0)),
                "admitted_density": density.get("admitted_count", 0),
                "dark_matter_density": density.get("dark_matter_count", 0),
                "legacy_unknown_density": density.get("legacy_unknown_density", 0),
                "qualification_density_basis": "Observations with incomplete qualification provenance overlap physical admission counts; do not add these categories.",
                "legacy_unknown_observation_count": int(
                    any(
                        f["admission_state"] == "legacy_unknown"
                        for f in memberships[observation_id]
                    )
                ),
                "density_days": density.get("day_count", 0),
                "temperature": score.get("temperature"),
                "_intake_cve_assessments": normalized.get("accretion_cves") or {},
                "entity_association_basis": value["association_basis"],
                "entity_id": value["entity_id"],
                "current_entity_id": value.get("current_entity_id"),
                "recorded_entity_id": value.get("recorded_entity_id"),
                "entity_name": entity.get("company") or entity.get("domain", ""),
                "case_id": active_case["id"] if active_case else None,
                "case_stage": active_case["stage"] if active_case else "",
                "lead_id": lead.get("id") if not active_case else None,
                "delivered_at": delivered[0] if delivered else None,
                "attribution_validated_at": review.get("reviewed_at")
                if review.get("decision") == "accept"
                else attribution.get("evaluated_at"),
                "individually_attributed": group.get("attribution_entry_id")
                in {v.get("entry_id") or v.get("source_key") for v in links},
                "source": {
                    "import_id": source.get("import_id"),
                    "workbook": source.get("workbook") or imported.get("name", ""),
                    "sheet": source.get("sheet", ""),
                    "row": source.get("row_number"),
                    "sha256": source.get("source_sha256", ""),
                    "source_key": source.get("source_key", ""),
                },
                "import_ids": sorted({v["import_id"] for v in links}),
                "source_available": available.get(source.get("import_id"), False),
                "original_url": f"/api/imports/{source['import_id']}/original"
                if available.get(source.get("import_id"))
                else None,
                "detail_url": f"/api/eclipse/observations/{identity}",
                "job_id": None,
            }
            if finding_id:
                row.update(_support_projection(support))
                row.update(_approved_fields(found))
            if detail_id:
                if detail_finding_id:
                    # The URL pins both the historical source observation and
                    # its selected condition; a co-observed approved condition
                    # must not make an excluded condition appear approved.
                    state = condition_workflows[requested_finding["condition"]]
                    condition_admitted = bool(state["admitted"])
                    row.update(
                        finding_id=detail_finding_id,
                        finding_ids=[detail_finding_id],
                        tag=requested_finding["condition"],
                        observation_admitted=admitted,
                        admitted=condition_admitted,
                        dark_matter=not condition_admitted
                        and state["admission_state"] != "legacy_unknown",
                        status=state["status"]
                        if condition_admitted
                        else "qualification_unknown"
                        if state["admission_state"] == "legacy_unknown"
                        else "excluded",
                        admission_state=state["admission_state"],
                        reported_observation_count=1,
                        approved_observation_count=int(condition_admitted),
                        legacy_unknown_observation_count=int(
                            state["admission_state"] == "legacy_unknown"
                        ),
                        intake_disposition="lead"
                        if condition_admitted
                        else "qualification_unknown"
                        if state["admission_state"] == "legacy_unknown"
                        else "dark_matter",
                    )
                    if condition_admitted:
                        row.update(_approved_fields(requested_finding))
                    if not condition_admitted:
                        row.update(
                            intake_reason=state["intake_reason"],
                            disposition_reason=state["disposition_reason"],
                        )
                if detail_intake == "dark_matter":
                    # Keep one source event while explicitly selecting its
                    # unadmitted memberships. Raw source fields below remain
                    # untouched, including any co-observed approved condition.
                    event_admitted = bool(value["admitted"])
                    scoped_finding_id = detail_finding_id or finding_id
                    excluded = [
                        finding
                        for finding in memberships[observation_id]
                        if (not scoped_finding_id or finding["id"] == scoped_finding_id)
                        and finding["admission_state"] != "admitted"
                    ]
                    if not excluded and event_admitted:
                        return {}, None
                    visible = excluded[:100]
                    reasons = sorted(
                        {
                            (
                                "qualification_unknown"
                                if finding["admission_state"] == "legacy_unknown"
                                else finding["reason"]
                                if event_admitted
                                else row.get("intake_reason")
                            )
                            or "Not admitted"
                            for finding in visible
                        }
                    )
                    row.update(
                        selection_context="dark_matter",
                        observation_admitted=event_admitted,
                        admitted=False,
                        dark_matter=True,
                        status="qualification_unknown"
                        if visible
                        and all(f["admission_state"] == "legacy_unknown" for f in visible)
                        else "excluded",
                        intake_disposition="dark_matter",
                        finding_ids=[finding["id"] for finding in visible],
                        admitted_finding_ids=[],
                        unadmitted_finding_ids=[finding["id"] for finding in visible],
                        selected_finding_count=len(excluded),
                        selected_findings_omitted=max(0, len(excluded) - len(visible)),
                        selected_findings=[
                            {
                                "id": finding["id"],
                                "condition": finding["condition"],
                                "admitted": False,
                                "admission_state": finding["admission_state"],
                                "reason": (
                                    finding["reason"]
                                    if event_admitted
                                    else row.get("intake_reason")
                                )
                                or "Not admitted",
                                "detail_url": f"/api/eclipse/observations/{observation_id}?finding_id={finding['id']}&intake=dark_matter",
                            }
                            for finding in visible
                        ],
                    )
                    if visible and all(f["admission_state"] == "legacy_unknown" for f in visible):
                        row.update(
                            dark_matter=False,
                            intake_disposition="qualification_unknown",
                            admission_state="legacy_unknown",
                        )
                    if visible:
                        row["tag"] = "; ".join(sorted(finding["condition"] for finding in visible))
                    if reasons:
                        row["intake_reasons"] = reasons
                        row["intake_reason"] = (
                            reasons[0] if len(reasons) == 1 else "multiple_exclusion_reasons"
                        )
                        row["disposition_reason"] = "; ".join(
                            _reason_label(reason) for reason in reasons
                        )
                row.update(
                    fields=fields,
                    attribution=attribution or None,
                    cases=linked_cases,
                    fields_error=fields_error,
                    requested_source_id=detail_id,
                )
                if fields_error:
                    row.update(source_available=False, original_url=None)
            rows.append(row)
            if not detail_id:
                for finding in memberships[observation_id]:
                    if finding["latest_observation_id"] != observation_id:
                        continue
                    finding_support = stats.get(finding["id"], {})
                    finding_admitted = bool(finding["admitted"])
                    finding_source = next(
                        (
                            item
                            for item in links
                            if item["source_key"] == finding["latest_source_key"]
                        ),
                        source,
                    )
                    finding_import = imports.get(finding_source.get("import_id"), {})
                    finding_rows.append(
                        {
                            **row,
                            "id": finding["id"],
                            "finding_id": finding["id"],
                            "finding_ids": [finding["id"]],
                            "record_kind": "finding",
                            "finding_kind": finding["kind"],
                            "source": {
                                "import_id": finding_source.get("import_id"),
                                "workbook": finding_source.get("workbook")
                                or finding_import.get("name", ""),
                                "sheet": finding_source.get("sheet", ""),
                                "row": finding_source.get("row_number"),
                                "sha256": finding_source.get("source_sha256", ""),
                                "source_key": finding_source.get("source_key", ""),
                            },
                            "imported_at": finding_import.get("created_at", row["imported_at"]),
                            "source_available": available.get(
                                finding_source.get("import_id"), False
                            ),
                            "original_url": f"/api/imports/{finding_source['import_id']}/original"
                            if available.get(finding_source.get("import_id"))
                            else None,
                            "tag": finding["condition"],
                            "admitted": finding_admitted,
                            "intake_reason": finding["reason"],
                            "disposition_reason": "Admitted finding; repeats and completed work retain approval."
                            if finding_admitted
                            else _reason_label(finding["reason"]),
                            "dark_matter": not finding_admitted,
                            "intake_disposition": "lead" if finding_admitted else "dark_matter",
                            **finding_work(finding, links)[0],
                            "lead_id": lead.get("id")
                            if not finding_work(finding, links)[0]["case_id"]
                            else None,
                            "workflow": finding["workflow"],
                            "first_seen": finding["first_seen"],
                            "last_seen": finding["last_seen"],
                            "changed_at": finding["changed_at"],
                            "first_indexed_at": finding["created_at"],
                            "fresh_at": finding["changed_at"],
                            "observation_count": finding_support.get("observation_count", 1),
                            "sightings": finding_support.get("day_count", 0),
                            **_support_projection(finding_support),
                            **_approved_fields(finding),
                            "detail_url": f"/api/eclipse/observations/{finding['id']}",
                        }
                    )
        decorate_rows(self.store, rows + finding_rows, kind="observations", db=db)
        from modules.library.components.catalog_outreach import decorate_observations

        decorate_observations(self.store.root, rows + finding_rows)
        statuses = Counter(r["status"] for r in rows)
        cases_by_entity = defaultdict(list)
        for case in cases.values():
            cases_by_entity[case["entity_id"]].append(case["id"])
        entity_list = [
            {
                "id": e["id"],
                "name": e["company"] or e["domain"],
                "domain": e["domain"],
                "case_ids": cases_by_entity[e["id"]],
                "map_location": self._entity_location(entity_profiles.get(e["id"], {})),
            }
            for e in entities.values()
            if not e["merged_into"]
        ]
        snapshot = {
            "schema_version": 3,
            "generated_at": now(),
            "status_basis": STATUS_BASIS,
            "handling": HANDLING,
            "jurisdiction": self._jurisdiction(db),
            "observations": rows,
            "findings": finding_rows,
            "entities": entity_list,
            "imports": [
                {k: v[k] for k in ("id", "name", "sha256", "created_at", "status")}
                for v in imports.values()
            ],
            "counts": {
                **overall,
                "rows": len(rows),
                "distinct_ips": len({r["ip"] for r in rows if r["ip_valid"]}),
                "qualified_rows": statuses["qualified"] + statuses["delivered"],
                "delivered_rows": statuses["delivered"],
                "review_rows": 0,
                "mapped_rows": sum(r["latitude"] is not None for r in rows),
                "unplaced_rows": sum(r["latitude"] is None for r in rows),
                "entities": len(entity_list),
                "dark_matter_rows": sum(r["dark_matter"] for r in rows),
                "legacy_unknown_findings": sum(
                    r.get("admission_state") == "legacy_unknown" for r in finding_rows
                ),
                "legacy_unknown_observation_count": sum(
                    bool(r.get("legacy_unknown_observation_count")) for r in rows
                ),
                "lead_rows": sum(r["admitted"] for r in rows),
                "unclassified_rows": 0,
            },
            "warnings": warnings,
            "coverage_complete": not truncated,
            "density_basis": "Distinct source observations per entity, or unresolved asset; separate from finding counts and outreach temperature.",
        }
        return snapshot, rows[0] if detail_id and rows else None

    def snapshot(self, *, product_id=""):
        snapshot = self._build()[0]
        if product_id:
            from modules.library.components.catalog_outreach import decorate_product_selection

            decorate_product_selection(self.store.root, snapshot, product_id)
        return snapshot

    def observed_references(self, *, limit=10, cve_offset=0, product_offset=0):
        from .observed_references import observed_references

        return observed_references(
            self,
            limit=limit,
            cve_offset=cve_offset,
            product_offset=product_offset,
            archive_limit=MAX_RECORDS,
        )

    def view(self, **filters):
        from .observatory_view import view

        return view(self, **filters)

    def intelligence(self, **filters):
        from .observatory_intelligence import project, validate_query

        validate_query(**filters)
        snapshot = self._build(events=True)[0]
        if filters.get("product_id"):
            from modules.library.components.catalog_outreach import decorate_product_selection

            decorate_product_selection(self.store.root, snapshot, filters["product_id"])
        return project(snapshot, **filters)

    def observation(self, identity, *, finding_id="", intake=""):
        if intake not in {"", "dark_matter"}:
            raise ValueError("Unknown observation intake context")
        return self._build(detail_id=identity, detail_finding_id=finding_id, detail_intake=intake)[
            1
        ]
