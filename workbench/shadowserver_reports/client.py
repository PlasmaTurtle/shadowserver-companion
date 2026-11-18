"""Typed report discovery and bounded research queries.

Manager selector mode follows Shadowserver's own report-manager.py: ``reports``
contains subscription names and ``types`` contains report family identifiers.
The explicit wiki mode uses singular ``type`` and permits one report family.
There are no automatic fallback requests that could broaden selected scope.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from .control import Operation
from .errors import ConfigurationError, ProtocolError
from .models import CatalogResult, QueryResult, QuerySpec, ReportDescriptor, ReportSelection


def _date_range(start: date, end: date) -> str:
    return start.isoformat() if start == end else f"{start.isoformat()}:{end.isoformat()}"


def _array(value, message):
    if not isinstance(value, list):
        raise ProtocolError(message)
    return value


def _numeric(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if str(number) == str(value).strip() and number >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


class ReportsClient:
    def __init__(self, transport, *, selector_style: str = "manager"):
        if selector_style not in ("manager", "wiki"):
            raise ConfigurationError("Unknown report selector compatibility mode.")
        self.transport = transport
        self.selector_style = selector_style

    def check_connection(self, *, operation: Operation | None = None) -> dict:
        """Return reachable status, access groups and numeric monthly diagnostics.

        User labels, request-IP restrictions, raw key metadata and the ping
        response are intentionally omitted. A zero quota is reported literally;
        it is never interpreted as unlimited.
        """
        operation = operation or Operation()
        self.transport.call("test/ping", {}, operation=operation)
        info = self.transport.call("key/info", {}, operation=operation)
        accounts = _array(info, "API key diagnostics have an unexpected shape.")
        summaries = []
        reports_access = False
        for account in accounts:
            if not isinstance(account, dict):
                raise ProtocolError("API key diagnostics have an unexpected shape.")
            access = account.get("access", [])
            if isinstance(access, str):
                access = access.replace(",", " ").split()
            if not isinstance(access, list) or not all(isinstance(v, str) for v in access):
                raise ProtocolError("API access information has an unexpected shape.")
            has_reports = "reports" in access
            reports_access = reports_access or has_reports
            summary = {"reports_access": has_reports,
                       "query_count": _numeric(account.get("query_count")),
                       "query_limit": _numeric(account.get("query_limit"))}
            # Normalize only recognized status values. Unknown data is explicitly
            # unknown instead of being copied into diagnostics.
            status = str(account.get("status", "")).lower()
            summary["status"] = status if status in ("active", "enabled", "disabled", "expired", "valid", "invalid", "0", "1") else "unknown"
            expiration = account.get("expiration")
            summary["expiration_utc"] = None
            if isinstance(expiration, str):
                try:
                    parsed = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    summary["expiration_utc"] = parsed.astimezone(timezone.utc).isoformat()
                except ValueError:
                    pass
            summaries.append(summary)
        return {"connected": True, "reports_access": reports_access, "accounts": summaries}

    def list_subscriptions(self, *, operation: Operation | None = None) -> list[str]:
        result = _array(self.transport.call("reports/subscribed", {}, operation=operation),
                        "API subscription listing has an unexpected shape.")
        if not all(isinstance(v, str) and v for v in result):
            raise ProtocolError("API subscription listing contains invalid entries.")
        return result

    def list_report_types(self, start: date | None = None, end: date | None = None,
                          *, operation: Operation | None = None) -> list:
        payload = {"detail": True}
        if start is None and end is not None:
            raise ConfigurationError("A start date is required when specifying an end date.")
        if start is not None:
            if end is not None and end < start:
                raise ConfigurationError("The end date must not precede the start date.")
            payload["date"] = _date_range(start, end or start)
        result = _array(self.transport.call("reports/types", payload, operation=operation),
                        "API report types have an unexpected shape.")
        for item in result:
            if not ((isinstance(item, str) and item) or
                    (isinstance(item, dict) and isinstance(item.get("type"), str) and item["type"])):
                raise ProtocolError("API report types contain invalid entries.")
        return result

    def get_schema(self, report_type: str, *, operation: Operation | None = None) -> dict:
        if not isinstance(report_type, str) or not report_type.strip():
            raise ConfigurationError("A report type is required for schema discovery.")
        result = self.transport.call("reports/schema", {"type": report_type}, operation=operation)
        if not isinstance(result, dict):
            raise ProtocolError("API report schema has an unexpected shape.")
        # The documented response is a field-to-type map, not necessarily a
        # formal JSON Schema document. Preserve it without interpreting types.
        return result

    def list_reports(self, selection: ReportSelection, *, operation: Operation | None = None) -> CatalogResult:
        operation = operation or Operation()
        if self.selector_style == "wiki" and len(selection.types) > 1:
            raise ConfigurationError("Wiki compatibility mode supports one report type per selection.")
        collected = []
        seen = set()
        day = selection.start
        while day <= selection.end:
            operation.check()
            remaining = selection.limit - len(collected)
            if remaining <= 0:
                return CatalogResult(tuple(collected), "partial", ("report_limit_reached",))
            # Keep each response conservatively bounded even when the caller's
            # total report budget spans many days. This is a client limit, not
            # an assertion of Shadowserver's authenticated account quota.
            request_limit = min(remaining, 1000)
            payload = {"date": day.isoformat(), "limit": request_limit}
            if selection.subscriptions:
                payload["reports"] = list(selection.subscriptions)
            if selection.types:
                if self.selector_style == "manager":
                    payload["types"] = list(selection.types)
                else:
                    payload["type"] = selection.types[0]
            result = _array(self.transport.call("reports/list", payload, operation=operation),
                            "API report listing has an unexpected shape.")
            if len(result) > request_limit:
                raise ProtocolError("API report listing exceeded its requested limit.")
            for item in result:
                report = self._descriptor(item, selection, day)
                # Identical repeated records do not create duplicate downloads.
                # Different download tokens are retained as distinct provenance.
                identity = (report.logical_id, report.source_fingerprint)
                if identity not in seen:
                    collected.append(report)
                    seen.add(identity)
            if len(result) == request_limit:
                return CatalogResult(tuple(collected), "partial", ("catalog_response_at_limit",))
            day += timedelta(days=1)
        return CatalogResult(tuple(collected), "complete")

    @staticmethod
    def _descriptor(item, selection: ReportSelection, day: date) -> ReportDescriptor:
        if not isinstance(item, dict):
            raise ProtocolError("API report listing contains invalid entries.")
        filename, subscription = item.get("file"), item.get("report")
        timestamp, identifier = item.get("timestamp"), item.get("id")
        report_type = item.get("type")
        if report_type is None and len(selection.types) == 1:
            report_type = selection.types[0]
        if not all(isinstance(v, str) and v for v in (filename, subscription, timestamp, identifier, report_type)):
            raise ProtocolError("API report listing is missing required report metadata.")
        try:
            report_day = date.fromisoformat(timestamp[:10])
        except ValueError:
            raise ProtocolError("API report listing contains an invalid report date.") from None
        if report_day != day:
            raise ProtocolError("API returned a report outside the requested date.")
        if selection.subscriptions and subscription not in selection.subscriptions:
            raise ProtocolError("API returned a report outside the selected subscription.")
        if selection.types and report_type not in selection.types:
            raise ProtocolError("API returned a report outside the selected report type.")
        return ReportDescriptor(filename, subscription, report_type, timestamp, identifier, dict(item))

    def query_events(self, spec: QuerySpec, *, operation: Operation | None = None) -> QueryResult:
        operation = operation or Operation()
        help_result = _array(self.transport.call("reports/query", {"help": True}, operation=operation),
                             "API query field listing has an unexpected shape.")
        if not all(isinstance(v, str) and v for v in help_result):
            raise ProtocolError("API query field listing contains invalid entries.")
        allowed = set(help_result)
        query = {**spec.scope, **spec.filters}
        if set(query) - allowed - {"require"}:
            raise ConfigurationError("Query contains fields not advertised by the API.")
        if "require" in query and (not isinstance(query["require"], str) or query["require"] not in allowed):
            raise ConfigurationError("Required query field is not advertised by the API.")
        if spec.facet is not None and spec.facet not in allowed:
            raise ConfigurationError("Facet field is not advertised by the API.")
        collected, seen_pages = [], set()
        for page in range(1, spec.max_pages + 1):
            operation.check()
            remaining = spec.max_records - len(collected)
            # A stable page size is essential: many page-based APIs compute
            # offset=(page-1)*limit. Shrinking the last request repeats earlier
            # records rather than retrieving the requested next page.
            limit = spec.page_size
            payload = {"date": _date_range(spec.start, spec.end), "query": query,
                       "sort": spec.sort, "limit": limit, "page": page}
            if spec.facet is not None:
                payload["facet"] = spec.facet
            result = _array(self.transport.call("reports/query", payload, operation=operation),
                            "API query results have an unexpected shape.")
            if not all(isinstance(record, dict) for record in result):
                raise ProtocolError("API query results contain invalid entries.")
            if len(result) > limit:
                raise ProtocolError("API query results exceeded the requested page size.")
            digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":"),
                                                 ensure_ascii=False).encode("utf-8")).hexdigest()
            if result and digest in seen_pages:
                return QueryResult(tuple(collected), "partial", page, ("repeated_page",))
            seen_pages.add(digest)
            collected.extend(result[:remaining])
            if len(collected) >= spec.max_records:
                return QueryResult(tuple(collected), "partial", page, ("record_limit_reached",))
            if len(result) < limit:
                return QueryResult(tuple(collected), "unknown", page, ("query_exhaustion_not_live_verified",))
        return QueryResult(tuple(collected), "partial", spec.max_pages, ("page_limit_reached",))
