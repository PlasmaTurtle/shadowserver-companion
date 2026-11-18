"""Deterministic offline demonstration. Every account and report is synthetic."""
from datetime import date
from hashlib import sha256
import hmac
from io import BytesIO
import json
from pathlib import Path

from .client import ReportsClient
from .control import Operation
from .models import Credentials, QuerySpec, ReportSelection
from .schema import SchemaStore
from .transport import SignedTransport


class _Response(BytesIO):
    def __init__(self, raw, content_type):
        super().__init__(raw)
        self.status = 200
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(raw))}


class _SyntheticService:
    credentials = Credentials("SYNTHETIC-DEMO-KEY", "SYNTHETIC-DEMO-SECRET")
    day = date(2026, 11, 6)

    def __init__(self):
        self.revision = 1
        self.api_calls = 0
        self.download_calls = 0

    def api_open(self, request, timeout):
        self.api_calls += 1
        expected = hmac.new(self.credentials.secret.encode(), request.data, sha256).hexdigest()
        if not hmac.compare_digest(request.get_header("Hmac2"), expected):
            raise AssertionError("Synthetic request signature mismatch.")
        payload = json.loads(request.data)
        if payload.pop("apikey") != self.credentials.api_key:
            raise AssertionError("Synthetic key mismatch.")
        endpoint = request.full_url.removeprefix("https://transform.shadowserver.org/api2/")
        if endpoint == "test/ping":
            result = {"pong": "2026-11-07 12:00:00"}
        elif endpoint == "key/info":
            result = [{"status": "active", "access": ["reports"], "query_count": "0", "query_limit": "100"}]
        elif endpoint == "reports/subscribed":
            result = ["synthetic-example"]
        elif endpoint == "reports/types":
            result = [{"type": "scan_http_vulnerable", "description": "SYNTHETIC HTTP report", "url": "https://www.shadowserver.org/"}]
        elif endpoint == "reports/schema":
            result = {"timestamp": "string", "ip": "string", "hostname": "string", "future_column": "string"}
        elif endpoint == "reports/list":
            result = [{"file": "2026-11-06-synthetic-example.csv", "report": "synthetic-example",
                       "type": "scan_http_vulnerable", "timestamp": "2026-11-06",
                       "id": f"SYNTHETIC-NONFUNCTIONAL-{self.revision}?demo-only",
                       "url": "https://www.shadowserver.org/", "future_metadata": {"retained": True}}] if payload["date"] == "2026-11-06" else []
        elif endpoint == "reports/query":
            result = ["geo", "ip", "hostname", "tag", "type"] if payload.get("help") else [{"ip": "192.0.2.10", "hostname": "api.example", "tag": "synthetic"}]
        else:
            raise AssertionError("Unexpected synthetic API endpoint.")
        return _Response(json.dumps(result).encode(), "application/json")

    def download_open(self, request, timeout):
        self.download_calls += 1
        if request.has_header("Hmac2") or request.data:
            raise AssertionError("Signed context crossed into unsigned downloads.")
        if not request.full_url.startswith("https://dl.shadowserver.org/SYNTHETIC-NONFUNCTIONAL-"):
            raise AssertionError("Unexpected synthetic download origin.")
        raw = ('timestamp,ip,hostname,future_column\r\n'
               '2026-11-06 04:00:00,192.0.2.10,api.example,"synthetic line one\n'
               f'synthetic revision {self.revision}"\r\n').encode()
        return _Response(raw, "text/csv")


class _Opener:
    def __init__(self, function):
        self.open = function


def run_demo(output):
    """Exercise actual signing, catalog, downloader, schema and ledger offline."""
    from .download import ReportDownloader
    from .ledger import Ledger
    from .sync import sync_once

    root = Path(output).resolve()
    service = _SyntheticService()
    selection = ReportSelection(service.day, service.day, ("synthetic-example",), ("scan_http_vulnerable",))
    operation = Operation(timeout=120, max_requests=30, max_bytes=1024**2)
    with SignedTransport(lambda: service.credentials, backend=_Opener(service.api_open)) as transport:
        client = ReportsClient(transport)
        connection = client.check_connection(operation=operation)
        subscriptions = client.list_subscriptions(operation=operation)
        types = client.list_report_types(operation=operation)
        schema = SchemaStore(root / "schemas").capture("scan_http_vulnerable", client.get_schema("scan_http_vulnerable", operation=operation))
        downloader = ReportDownloader(root / "reports", opener=_Opener(service.download_open))
        root.mkdir(parents=True, exist_ok=True)
        with Ledger(root / "ledger.sqlite3", profile="synthetic-demo") as ledger:
            first = sync_once(client, downloader, ledger, selection, operation=operation)
            repeated = sync_once(client, downloader, ledger, selection, operation=operation)
            service.revision = 2
            revised = sync_once(client, downloader, ledger, selection, operation=operation)
        query = client.query_events(QuerySpec(service.day, service.day, {"geo": "XX"}), operation=operation)
    result = {"mode": "synthetic_offline_demo", "live_api_verified": False,
              "connection": connection, "subscriptions": subscriptions, "types": types,
              "schema": schema.public_dict(), "first_pull": first.public_dict(),
              "repeat_pull": repeated.public_dict(), "revised_pull": revised.public_dict(),
              "query": query.public_dict(), "api_requests": service.api_calls,
              "download_requests": service.download_calls}
    # This file contains safe outputs only. No fake/real credential or usable token.
    (root / "demo-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
