"""Reusable synthetic scheduling fixtures and builders."""

from datetime import datetime, timezone
from types import SimpleNamespace

from modules.accretion.components.scheduling import DEFAULTS, AcquisitionSchedule
from modules.workspace.components.store import Store

NOW = datetime(2026, 11, 13, 7, tzinfo=timezone.utc)


class Acquisition:
    def __init__(self, store):
        self.store = store
        self.calls = []
        self.active = False

    def busy(self):
        return self.active

    def scheduled(self, config, start, end, *, cancel_event, queued):
        self.calls.append((start, end))
        with self.store.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO imports(id,fingerprint,sha256,name,path,created_at,status,config) VALUES('scheduled-import','fingerprint','sha','report.csv','originals/report.csv',?,'queued','{}')",
                (NOW.isoformat(),),
            )
        queued({"import_id": "scheduled-import"})


def scheduler(tmp_path, **values):
    store = Store(tmp_path / "data")
    network = Acquisition(store)
    catalog = SimpleNamespace(status=lambda: {"bootstrap_complete": True})
    result = AcquisitionSchedule(store, network, catalog, clock=lambda: NOW)
    result.configure(
        {
            **DEFAULTS,
            "enabled": True,
            "reference": False,
            "subscription": "fixture",
            "report_types": ["scan_http_vulnerable"],
            **values,
        }
    )
    return result, network, store
