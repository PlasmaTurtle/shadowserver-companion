"""Local CVE catalog reads and explicit background synchronization controls."""

from __future__ import annotations

import re
import logging
import sqlite3
from typing import Literal
from fastapi import HTTPException, Query
from pydantic import BaseModel, StrictBool, SecretStr, Field, ConfigDict


class NVDKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=1, max_length=128)
    remember: StrictBool = False


class CatalogSettings(BaseModel):
    enabled: StrictBool


class CatalogAccess:
    """Keep optional reference-data failures outside the core startup boundary."""

    def __init__(self, factory):
        self.factory = factory
        self.manager = None
        self.automatic = False
        self.maintenance = None
        self._initialize()

    def _initialize(self):
        try:
            self.manager = self.factory()
            if self.maintenance is not None:
                self.manager.maintenance = self.maintenance
                risk = getattr(self.manager, "risk", None)
                if risk is not None:
                    risk.maintenance = self.maintenance
        except Exception as error:
            logging.getLogger(__name__).warning("CVE catalog unavailable: %s", type(error).__name__)
            self.manager = None

    def __getattr__(self, name):
        if self.manager is None:
            raise AttributeError(name)
        return getattr(self.manager, name)

    @property
    def catalog(self):
        if self.manager is None:
            raise ValueError("The local CVE catalog is unavailable; retry its download.")
        return self.manager.catalog

    def status(self):
        if self.manager is not None:
            try:
                return self.manager.status()
            except Exception as error:
                logging.getLogger(__name__).warning(
                    "CVE catalog unavailable: %s", type(error).__name__
                )
        return {
            "source": "NVD",
            "total": 0,
            "enabled": False,
            "bootstrap_complete": False,
            "stale": True,
            "last_error": "The local CVE catalog is unavailable. Retry its download.",
            "years_complete": [],
            "required_years": [],
            "last_success_at": None,
            "next_check_at": None,
            "db_bytes": 0,
            "running": False,
            "job": {"status": "error", "phase": None, "error": "Catalog unavailable"},
        }

    def start(self):
        self.automatic = True
        if self.manager is not None:
            try:
                self.manager.start()
            except Exception as error:
                logging.getLogger(__name__).warning(
                    "CVE catalog schedule unavailable: %s", type(error).__name__
                )
                self.close()
                self.manager = None

    def sync(self):
        if self.manager is None:
            self._initialize()
            if self.automatic:
                self.start()
        if self.manager is None:
            raise ValueError("The local CVE catalog is unavailable; check its storage and retry.")
        return self.manager.sync()

    def cancel(self):
        return self.manager.cancel() if self.manager is not None else self.status()

    def close(self):
        if self.manager is not None:
            try:
                self.manager.close()
            except Exception as error:
                logging.getLogger(__name__).warning(
                    "CVE catalog shutdown: %s", type(error).__name__
                )


def register(app, *, manager, outreach=None, workspace_root=None):
    from ..cve_catalog.credentials import NVDKeys

    keys = NVDKeys(workspace_root or app.state.store.root)

    @app.get("/api/nvd/credentials")
    def key_status():
        return keys.status()

    @app.put("/api/nvd/credentials")
    def key_save(body: NVDKeyUpdate):
        return keys.configure(body.api_key.get_secret_value(), remember=body.remember)

    @app.delete("/api/nvd/credentials")
    def key_remove():
        return keys.forget()

    @app.get("/api/cve-catalog")
    @app.get("/api/cve-catalog/status")
    def status():
        return {**manager.status(), "api_access": keys.status()}

    @app.get("/api/cve-catalog/search")
    def search(
        q: str = Query("", max_length=200),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=500_000),
        severity: str = Query("", max_length=16),
    ):
        selected = severity.strip().upper()
        if selected not in ("", "ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE", "UNKNOWN"):
            raise ValueError("Unknown CVE severity")
        return manager.catalog.search(
            query=q,
            limit=limit,
            offset=offset,
            severity=selected if selected not in ("", "ALL") else None,
        )

    @app.get("/api/cve-catalog/records/{cve_id}")
    def record(cve_id: str):
        identifier = cve_id.upper()
        if not re.fullmatch(r"CVE-\d{4}-\d{4,}", identifier):
            raise ValueError("Invalid CVE identifier")
        result = manager.catalog.get(identifier)
        if result is None:
            raise HTTPException(404, "CVE is not in this local catalog")
        from ..cve_catalog.analytics import cvss_assessments

        result["analysis"] = cvss_assessments(result["cve"])
        if getattr(manager, "risk", None) is not None:
            try:
                result["risk"] = manager.risk.store.get(identifier)
            except (
                OSError,
                sqlite3.Error,
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
            ) as error:
                logging.getLogger(__name__).warning(
                    "Local risk data unavailable for CVE detail: %s", type(error).__name__
                )
                result["risk"] = {
                    "epss": None,
                    "kev": None,
                    "available": False,
                    "error": "Local EPSS and KEV data is unavailable. Retry its download.",
                }
        return result

    @app.get("/api/cve-catalog/products")
    def products(
        q: str = Query("", max_length=200),
        scope: Literal["critical", "critical_kev", "kev", "all"] = "critical",
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0, le=500000),
    ):
        return manager.catalog.products(query=q, scope=scope, limit=limit, offset=offset)

    @app.get("/api/cve-catalog/products/{product_id}")
    def product(
        product_id: str,
        scope: Literal["critical", "critical_kev", "kev", "all"] = "critical",
        version: str = Query("", max_length=160),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=500000),
    ):
        result = manager.catalog.product(
            product_id, scope=scope, version=version, limit=limit, offset=offset
        )
        if result is None:
            raise HTTPException(404, "Product is not in this local index")
        return result

    @app.get("/api/cve-catalog/fields")
    def fields(
        field: str = Query("weakness", max_length=80),
        scope: Literal["critical", "critical_kev", "kev", "all"] = "critical",
        product_id: str = Query("", max_length=100),
        limit: int = Query(30, ge=1, le=100),
    ):
        return manager.catalog.fields(field=field, scope=scope, product_id=product_id, limit=limit)

    @app.get("/api/cve-catalog/fields/records")
    def field_records(
        field: str = Query("weakness", max_length=80),
        value: str = Query("", max_length=300),
        scope: Literal["critical", "critical_kev", "kev", "all"] = "critical",
        product_id: str = Query("", max_length=100),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=500000),
    ):
        return manager.catalog.field_records(
            field=field, value=value, scope=scope, product_id=product_id, limit=limit, offset=offset
        )

    @app.get("/api/cve-catalog/changes")
    def changes(
        cve_id: str = Query("", max_length=40),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=500000),
    ):
        return manager.catalog.changes(cve_id=cve_id, limit=limit, offset=offset)

    @app.get("/api/cve-catalog/index")
    def index_status():
        return manager.catalog.index_status()

    @app.post("/api/cve-catalog/index")
    def build_index():
        return manager.index()

    @app.post("/api/cve-catalog/risk/sync")
    def sync_risk():
        return manager.sync_risk()

    @app.post("/api/cve-catalog/risk/cancel")
    def cancel_risk():
        return manager.cancel_risk()

    if outreach is not None:

        @app.get("/api/cve-catalog/records/{cve_id}/observations")
        def record_observations(
            cve_id: str,
            limit: int = Query(50, ge=1, le=100),
            offset: int = Query(0, ge=0, le=500000),
        ):
            identifier = cve_id.upper()
            if not re.fullmatch(r"CVE-\d{4}-\d{4,}", identifier):
                raise ValueError("Invalid CVE identifier")
            return outreach.observations(cve_id=identifier, limit=limit, offset=offset)

        @app.get("/api/cve-catalog/products/{product_id}/observations")
        def product_observations(
            product_id: str,
            scope: Literal["critical", "critical_kev", "kev", "all"] = "critical",
            limit: int = Query(50, ge=1, le=100),
            offset: int = Query(0, ge=0, le=500000),
        ):
            return outreach.observations(
                product_id=product_id, scope=scope, limit=limit, offset=offset
            )

    @app.post("/api/cve-catalog/sync")
    def sync():
        return manager.sync()

    @app.post("/api/cve-catalog/cancel")
    def cancel():
        return manager.cancel()

    @app.post("/api/cve-catalog/settings")
    @app.put("/api/cve-catalog/settings")
    def settings(body: CatalogSettings):
        if manager.status().get("running"):
            raise HTTPException(409, "Wait for this catalog update to finish or cancel it first.")
        manager.catalog.set_enabled(body.enabled)
        if getattr(manager, "risk", None) is not None:
            manager.risk.store.put_metadata("enabled", body.enabled)
        return manager.status()
