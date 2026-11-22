"""Synthetic report selections for guided workspace setup."""

import json

from modules.accretion.components.shadowserver_reports.demo import _Response, _SyntheticService


class SetupService(_SyntheticService):
    """The real signer/client sees state, national and unclassified selections."""

    def api_open(self, request, timeout):
        response = super().api_open(request, timeout)
        endpoint = request.full_url.removeprefix("https://transform.shadowserver.org/api2/")
        if endpoint == "reports/subscribed":
            return _Response(
                json.dumps(["US-NC", "US-SC", "united-states", "agency-custom"]).encode(),
                "application/json",
            )
        if endpoint == "reports/list":
            rows = json.loads(response.read())
            for row in rows:
                row["report"] = "US-NC"
                row["file"] = "2026-11-06-US-NC-scan_http_vulnerable.csv"
            return _Response(json.dumps(rows).encode(), "application/json")
        return response
