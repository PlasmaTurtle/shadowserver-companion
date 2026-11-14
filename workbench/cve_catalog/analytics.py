"""Incremental local product and field indexes; all counts are distinct CVEs."""

from collections import defaultdict
import hashlib
import json
import re
import sqlite3
import threading

from .products import products_for_record, record_versions
from .risk_policy import check_schema, freshness, UnsupportedRiskSchema

FIELDS = {
    "weakness": "Weakness (CWE)",
    "attack_vector": "Attack vector",
    "privileges": "Privileges required",
    "interaction": "User interaction",
    "cvss_version": "CVSS version",
    "metric_source": "Assessment source",
    "publication_year": "Publication year",
    "status": "Record status",
    "reference_type": "Reference type",
    "ssvc_exploitation": "SSVC exploitation",
    "ssvc_automatable": "SSVC automatable",
    "ssvc_impact": "SSVC technical impact",
}
_index_guard = threading.Lock()
_index_locks = {}

SCOPES = {"critical", "critical_kev", "kev", "all"}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def ensure_schema(db):
    schema = db.execute("SELECT value FROM metadata WHERE key='analytics_schema'").fetchone()
    if (
        schema
        and json.loads(schema[0]) == 2
        and db.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name IN ('catalog_raw_updated','catalog_raw_deleted','catalog_raw_inserted')"
        ).fetchone()[0]
        == 3
    ):
        return
    if schema and json.loads(schema[0]) not in (1, 2):
        raise ValueError("Catalog analytics was created by a newer application")
    # Separate additive tables leave the original catalog readable by 0.9.83.
    statements = [
        "CREATE TABLE IF NOT EXISTS catalog_overview(id TEXT PRIMARY KEY,description TEXT NOT NULL,status TEXT NOT NULL,published TEXT NOT NULL,modified TEXT NOT NULL,severity TEXT NOT NULL,score REAL)",
        "CREATE INDEX IF NOT EXISTS catalog_overview_severity ON catalog_overview(severity,status)",
        "CREATE INDEX IF NOT EXISTS catalog_overview_scope ON catalog_overview(severity,status,id,modified,score)",
        "CREATE INDEX IF NOT EXISTS catalog_overview_modified ON catalog_overview(modified)",
        "CREATE TABLE IF NOT EXISTS catalog_indexed(cve_id TEXT PRIMARY KEY,raw_sha256 TEXT NOT NULL,nvd_kev INTEGER NOT NULL,error TEXT)",
        "CREATE INDEX IF NOT EXISTS catalog_indexed_kev ON catalog_indexed(nvd_kev,cve_id,error)",
        "CREATE TABLE IF NOT EXISTS catalog_products(id TEXT PRIMARY KEY,vendor TEXT NOT NULL,product TEXT NOT NULL,search_text TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS catalog_product_aliases(product_id TEXT NOT NULL,vendor TEXT NOT NULL,product TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(product_id,vendor,product,kind))",
        "CREATE TABLE IF NOT EXISTS catalog_product_cves(product_id TEXT NOT NULL,cve_id TEXT NOT NULL,sources TEXT NOT NULL,rule_count INTEGER NOT NULL,PRIMARY KEY(product_id,cve_id))",
        "CREATE INDEX IF NOT EXISTS catalog_product_cves_cve ON catalog_product_cves(cve_id)",
        "CREATE INDEX IF NOT EXISTS catalog_product_cves_cover ON catalog_product_cves(cve_id,product_id)",
        "CREATE TABLE IF NOT EXISTS catalog_facets(field TEXT NOT NULL,value TEXT NOT NULL,cve_id TEXT NOT NULL,PRIMARY KEY(field,value,cve_id))",
        "CREATE INDEX IF NOT EXISTS catalog_facets_cve ON catalog_facets(cve_id,field,value)",
        "CREATE TABLE IF NOT EXISTS catalog_cvss(cve_id TEXT NOT NULL,ordinal INTEGER NOT NULL,version TEXT NOT NULL,source TEXT NOT NULL,type TEXT NOT NULL,score REAL,severity TEXT,vector TEXT NOT NULL,details_json TEXT NOT NULL,PRIMARY KEY(cve_id,ordinal))",
        "CREATE TABLE IF NOT EXISTS catalog_changes(id INTEGER PRIMARY KEY AUTOINCREMENT,cve_id TEXT NOT NULL,changed_at TEXT NOT NULL,source_modified TEXT NOT NULL,previous_sha256 TEXT NOT NULL,current_sha256 TEXT NOT NULL,fields_json TEXT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS catalog_changes_cve ON catalog_changes(cve_id,id)",
    ]
    statements.extend(
        [
            "CREATE TRIGGER IF NOT EXISTS catalog_raw_inserted AFTER INSERT ON records BEGIN UPDATE metadata SET value='0' WHERE key='analytics_cursor'; END",
            "CREATE TRIGGER IF NOT EXISTS catalog_raw_updated AFTER UPDATE OF raw_json,raw_sha256,description,status,published,modified,severity,score ON records BEGIN DELETE FROM catalog_indexed WHERE cve_id=NEW.id; DELETE FROM catalog_overview WHERE id=NEW.id; UPDATE metadata SET value='0' WHERE key='analytics_cursor'; END",
            "CREATE TRIGGER IF NOT EXISTS catalog_raw_deleted AFTER DELETE ON records BEGIN DELETE FROM catalog_indexed WHERE cve_id=OLD.id; DELETE FROM catalog_overview WHERE id=OLD.id; DELETE FROM catalog_product_cves WHERE cve_id=OLD.id; DELETE FROM catalog_facets WHERE cve_id=OLD.id; DELETE FROM catalog_cvss WHERE cve_id=OLD.id; END",
        ]
    )
    for statement in statements:
        db.execute(statement)
    db.execute("INSERT OR REPLACE INTO metadata VALUES('analytics_schema','2')")
    db.execute("INSERT OR REPLACE INTO metadata VALUES('analytics_cursor','0')")


def cvss_assessments(cve):
    items = []
    metrics = cve.get("metrics") or {}
    if not isinstance(metrics, dict):
        return items
    for name in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        values = metrics.get(name) or []
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("cvssData"), dict):
                continue
            data = item["cvssData"]
            score = data.get("baseScore")
            if (
                not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not 0 <= score <= 10
            ):
                continue
            items.append(
                {
                    "version": str(data.get("version") or name),
                    "source": str(item.get("source") or "Unknown"),
                    "type": str(item.get("type") or ""),
                    "score": score,
                    "severity": str(
                        data.get("baseSeverity") or item.get("baseSeverity") or "UNKNOWN"
                    ),
                    "vector": str(data.get("vectorString") or ""),
                    "details": data,
                }
            )
    return items


def selected_assessment(items):
    if not items:
        return None
    version = items[0]["version"]
    selected = [item for item in items if item["version"] == version]
    return next((item for item in selected if item["type"] == "Primary"), selected[0])


def index_record(db, cve, digest):
    identifier = cve["id"]
    db.execute(
        "INSERT OR REPLACE INTO catalog_overview SELECT id,description,status,published,modified,severity,score FROM records WHERE id=?",
        (identifier,),
    )
    products = products_for_record(cve) if cve.get("vulnStatus") != "Rejected" else {}
    for table in ("catalog_product_cves", "catalog_facets", "catalog_cvss"):
        db.execute(f"DELETE FROM {table} WHERE cve_id=?", (identifier,))
    for product in products.values():
        db.execute(
            "INSERT OR IGNORE INTO catalog_products VALUES(?,?,?,?)",
            (
                product["id"],
                product["vendor"].replace("_", " "),
                product["product"].replace("_", " "),
                (product["vendor"] + " " + product["product"]).replace("_", " ").casefold(),
            ),
        )
        db.executemany(
            "INSERT OR IGNORE INTO catalog_product_aliases VALUES(?,?,?,?)",
            [(product["id"], *alias) for alias in product["aliases"]],
        )
        db.execute(
            "INSERT INTO catalog_product_cves VALUES(?,?,?,?)",
            (product["id"], identifier, compact(sorted(product["sources"])), product["rule_count"]),
        )
    facets = defaultdict(set)
    facets["publication_year"].add(str(cve.get("published", ""))[:4])
    facets["status"].add(str(cve.get("vulnStatus", "Unknown")))
    for item in cve.get("weaknesses", []) or []:
        for value in item.get("description", []) if isinstance(item, dict) else []:
            if isinstance(value, dict) and re.fullmatch(r"CWE-\d+", str(value.get("value", ""))):
                facets["weakness"].add(value["value"])
    for item in cve.get("references", []) or []:
        if isinstance(item, dict):
            facets["reference_type"].update(
                str(tag) for tag in item.get("tags", []) if isinstance(tag, str)
            )
    assessments = cvss_assessments(cve)
    for ordinal, item in enumerate(assessments):
        db.execute(
            "INSERT INTO catalog_cvss VALUES(?,?,?,?,?,?,?,?,?)",
            (
                identifier,
                ordinal,
                item["version"],
                item["source"],
                item["type"],
                item["score"],
                item["severity"],
                item["vector"],
                compact(item["details"]),
            ),
        )
        facets["metric_source"].add(item["source"])
        facets["cvss_version"].add(item["version"])
    chosen = selected_assessment(assessments)
    if chosen:
        data, version = chosen["details"], chosen["version"]
        for field, key in (
            ("attack_vector", "attackVector"),
            ("privileges", "privilegesRequired"),
            ("interaction", "userInteraction"),
        ):
            if data.get(key):
                # Different CVSS vocabularies are labeled, never silently averaged.
                facets[field].add(version + " · " + str(data[key]))
    metrics = cve.get("metrics", {}) or {}
    for item in metrics.get("ssvcV203", []) if isinstance(metrics, dict) else []:
        data = item.get("ssvcData", {}) if isinstance(item, dict) else {}
        for option in data.get("options", []) if isinstance(data, dict) else []:
            if isinstance(option, dict):
                for field, key in (
                    ("ssvc_exploitation", "exploitation"),
                    ("ssvc_automatable", "automatable"),
                    ("ssvc_impact", "technicalImpact"),
                ):
                    if option.get(key):
                        facets[field].add(str(option[key]))
    db.executemany(
        "INSERT INTO catalog_facets VALUES(?,?,?)",
        [
            (field, value, identifier)
            for field, values in facets.items()
            for value in values
            if value
        ],
    )
    db.execute(
        "INSERT OR REPLACE INTO catalog_indexed VALUES(?,?,?,NULL)",
        (identifier, digest, int(bool(cve.get("cisaExploitAdd")))),
    )


def _summary(value):
    text = compact(value)
    return {
        "text": text[:2000],
        "truncated": len(text) > 2000,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def journal_change(db, old, new, old_digest, new_digest, changed_at):
    changed = []
    for field, label in (
        ("vulnStatus", "Status"),
        ("descriptions", "Description"),
        ("metrics", "Assessments"),
        ("weaknesses", "Weaknesses"),
        ("affected", "Affected products and versions"),
        ("configurations", "CPE applicability"),
        ("references", "References"),
        ("cisaExploitAdd", "KEV date added"),
    ):
        before, after = old.get(field), new.get(field)
        if before != after:
            left, right = _summary(before), _summary(after)
            changed.append(
                {
                    "field": field,
                    "label": label,
                    "before": left["text"],
                    "after": right["text"],
                    "before_truncated": left["truncated"],
                    "after_truncated": right["truncated"],
                    "before_sha256": left["sha256"],
                    "after_sha256": right["sha256"],
                }
            )
    if changed:
        db.execute(
            "INSERT INTO catalog_changes(cve_id,changed_at,source_modified,previous_sha256,current_sha256,fields_json) VALUES(?,?,?,?,?,?)",
            (new["id"], changed_at, new["lastModified"], old_digest, new_digest, compact(changed)),
        )


class CatalogAnalytics:
    def index_status(self):
        if not self.db.is_file():
            return {"ready": False, "indexed": 0, "total": 0, "remaining": 0, "errors": 0}
        with self.connection() as db:
            total = db.execute("SELECT count(*) FROM records").fetchone()[0]
            indexed, errors = db.execute(
                "SELECT count(CASE WHEN error IS NULL THEN 1 END),count(error) FROM catalog_indexed"
            ).fetchone()
            indexed = min(
                indexed, db.execute("SELECT count(*) FROM catalog_overview").fetchone()[0]
            )
            return {
                "ready": indexed == total and total > 0,
                "indexed": indexed,
                "total": total,
                "remaining": max(0, total - indexed - errors),
                "errors": errors,
            }

    def build_index(self, *, cancel_event=None, progress=None, batch_size=250):
        with _index_guard:
            lock = _index_locks.setdefault(str(self.db), threading.Lock())
        if not lock.acquire(blocking=False):
            return self.index_status()
        try:
            return self._build_index(
                cancel_event=cancel_event, progress=progress, batch_size=batch_size
            )
        finally:
            lock.release()

    def _build_index(self, *, cancel_event=None, progress=None, batch_size=250):
        from .transport import cancelled

        progress = progress or (lambda value: None)
        if not self.db.is_file():
            return self.index_status()
        if not 1 <= batch_size <= 1000:
            raise ValueError("Invalid index batch size")
        state = self.index_status()
        if state["ready"]:
            with self.connection() as db:
                self.put_metadata(
                    "analytics_cursor",
                    db.execute("SELECT coalesce(max(rowid),0) FROM records").fetchone()[0],
                    db=db,
                )
            self._analyze_index()
            return state
        with self.connection() as db:
            cursor = self.metadata("analytics_cursor", 0, db=db)
        while True:
            cancelled(cancel_event)
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute(
                    "SELECT r.rowid,r.id,r.raw_json,r.raw_sha256,i.raw_sha256 AS indexed_sha FROM records r LEFT JOIN catalog_indexed i ON i.cve_id=r.id WHERE r.rowid>? ORDER BY r.rowid LIMIT ?",
                    (cursor, batch_size),
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    cancelled(cancel_event)
                    db.execute(
                        "INSERT OR REPLACE INTO catalog_overview SELECT id,description,status,published,modified,severity,score FROM records WHERE id=?",
                        (row["id"],),
                    )
                    if row["indexed_sha"] != row["raw_sha256"]:
                        raw = row["raw_json"]
                        if hashlib.sha256(raw.encode()).hexdigest() != row["raw_sha256"]:
                            db.execute(
                                "INSERT OR REPLACE INTO catalog_indexed VALUES(?,?,0,?)",
                                (row["id"], row["raw_sha256"], "Record hash mismatch"),
                            )
                        else:
                            cve = json.loads(raw)
                            if not isinstance(cve, dict) or cve.get("id") != row["id"]:
                                raise ValueError("Catalog index record identity mismatch")
                            index_record(db, cve, row["raw_sha256"])
                    cursor = row["rowid"]
                self.put_metadata("analytics_cursor", cursor, db=db)
            progress(
                {
                    "phase": "indexing",
                    "records": cursor,
                    "message": f"Indexing products and fields: {cursor:,} CVEs",
                }
            )
        state = self.index_status()
        if state["ready"]:
            self._analyze_index()
        return state

    def _analyze_index(self):
        # Once per index schema, after background backfill. These small statistics
        # let SQLite start KEV queries from the rare KEV population.
        with self.connection() as db:
            if self.metadata("analytics_analyzed", 0, db=db) == 2:
                return
            for name in (
                "catalog_overview",
                "catalog_indexed",
                "catalog_product_cves",
                "catalog_products",
                "catalog_facets",
            ):
                db.execute("ANALYZE " + name)
            self.put_metadata("analytics_analyzed", 2, db=db)

    def _risk_sql(self, db):
        # The attached feeds and catalog counts share one stable read snapshot.
        if not db.in_transaction:
            db.execute("BEGIN")
        risk = self.folder / "risk.sqlite3"
        if risk.is_file():
            try:
                db.execute("ATTACH DATABASE ? AS risk", (risk.as_uri() + "?mode=ro",))
                check_schema(db, attached=True)
                states = {
                    row[0]: json.loads(row[1])
                    for row in db.execute(
                        "SELECT key,value FROM risk.metadata WHERE key IN ('kev','epss')"
                    )
                }
                state = states.get("kev", {})
                complete = bool(state.get("last_success_at"))
                if complete:
                    rows = db.execute("SELECT id,raw_json,raw_sha256 FROM risk.kev").fetchall()
                    if len(rows) != state.get("count"):
                        raise ValueError("Local KEV index is incomplete")
                    for row in rows:
                        if (
                            hashlib.sha256(row[1].encode()).hexdigest() != row[2]
                            or json.loads(row[1]).get("cveID") != row[0]
                        ):
                            raise ValueError("Local KEV index failed its integrity check")
                db.execute("SELECT id FROM risk.epss LIMIT 0")
                return {
                    "join": " LEFT JOIN risk.kev k ON k.id=r.id",
                    "score_join": " LEFT JOIN risk.epss e ON e.id=r.id",
                    "kev": "CASE WHEN k.id IS NOT NULL THEN 1 ELSE 0 END"
                    if complete
                    else "i.nvd_kev",
                    "epss": "e.score",
                    "percentile": "e.percentile",
                    "date": "e.score_date",
                    "model": "e.model_version",
                    "epss_sha": "e.raw_sha256",
                    "kev_json": "k.raw_json" if complete else "NULL",
                    "kev_sha": "k.raw_sha256" if complete else "NULL",
                    "kev_predicate": "r.id IN (SELECT id FROM risk.kev)"
                    if complete
                    else "i.nvd_kev=1",
                    "kev_source": "CISA KEV" if complete else "NVD embedded KEV",
                    "kev_state": state if complete else None,
                    "epss_state": states.get("epss", {}),
                }
            except UnsupportedRiskSchema:
                raise
            except sqlite3.Error, ValueError, TypeError, AttributeError:
                pass
        return {
            "join": "",
            "score_join": "",
            "kev": "i.nvd_kev",
            "epss": "NULL",
            "percentile": "NULL",
            "date": "NULL",
            "model": "NULL",
            "epss_sha": "NULL",
            "kev_json": "NULL",
            "kev_sha": "NULL",
            "kev_predicate": "i.nvd_kev=1",
            "kev_source": "NVD embedded KEV",
            "kev_state": None,
            "epss_state": {},
        }

    def _risk_source(self, provider, state):
        checked = state.get("last_success_at")
        return {
            "source": {
                "publisher": provider,
                "url": state.get("source_url"),
                "retrieved_at": checked,
                "sha256": state.get("sha256"),
                "count": state.get("count", 0),
                "score_date": state.get("score_date"),
                "model_version": state.get("model_version"),
                "catalog_version": state.get("catalog_version"),
                "date_released": state.get("date_released"),
            },
            **freshness("epss" if provider == "FIRST EPSS" else "kev", state, self.clock()),
        }

    def _where(self, scope, risk, product_id=""):
        if scope not in SCOPES:
            raise ValueError("Unknown outreach scope")
        clauses, args = ["r.status!='Rejected'", "i.error IS NULL"], []
        if scope in ("critical", "critical_kev"):
            clauses.append("r.severity='CRITICAL'")
        if scope in ("kev", "critical_kev"):
            clauses.append(risk["kev_predicate"])
        if product_id:
            clauses.append(
                "EXISTS(SELECT 1 FROM catalog_product_cves p WHERE p.cve_id=r.id AND p.product_id=?)"
            )
            args.append(product_id)
        return " AND ".join(clauses), args

    def _page(self, limit, offset):
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or not 0 <= offset <= 500000
        ):
            raise ValueError("Invalid catalog page")

    def products(self, query="", *, scope="critical", limit=40, offset=0):
        self._page(limit, offset)
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("Product search must be at most 200 characters")
        result = {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "index": self.index_status(),
        }
        if not self.db.is_file():
            return result
        with self.connection() as db:
            risk = self._risk_sql(db)
            where, args = self._where(scope, risk)
            if query.strip():
                for token in query.casefold().replace("_", " ").split()[:12]:
                    where += " AND p.search_text LIKE ? ESCAPE '\\'"
                    args.append(
                        "%"
                        + token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                        + "%"
                    )
            # A product text search starts with its small matching product set.
            # CROSS JOIN preserves that order instead of scanning every critical CVE first.
            join = " CROSS JOIN " if query.strip() else " JOIN "
            base = (
                " FROM catalog_products p"
                + join
                + "catalog_product_cves pc ON pc.product_id=p.id"
                + join
                + "catalog_overview r ON r.id=pc.cve_id JOIN catalog_indexed i ON i.cve_id=r.id"
                + risk["join"]
                + " WHERE "
                + where
            )
            result["total"] = db.execute("SELECT count(DISTINCT p.id)" + base, args).fetchone()[0]
            rows = db.execute(
                "SELECT p.id,p.vendor,p.product,count(*) AS cve_count,sum(r.severity='CRITICAL') AS critical_count,sum("
                + risk["kev"]
                + ") AS kev_count,max(r.modified) AS last_modified"
                + base
                + " GROUP BY p.id ORDER BY kev_count DESC,critical_count DESC,cve_count DESC,p.id LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
            for row in rows:
                item = dict(row)
                item["sources"] = [
                    r[0]
                    for r in db.execute(
                        "SELECT DISTINCT kind FROM catalog_product_aliases WHERE product_id=? ORDER BY kind",
                        (item["id"],),
                    )
                ]
                result["items"].append(item)
        return result

    def product_identity(self, product_id):
        if not isinstance(product_id, str) or not re.fullmatch(r"product:[a-f0-9]{24}", product_id):
            raise ValueError("Invalid product identifier")
        if not self.db.is_file():
            return None
        with self.connection() as db:
            row = db.execute(
                "SELECT id,vendor,product FROM catalog_products WHERE id=?", (product_id,)
            ).fetchone()
            if row is None:
                return None
            aliases = [
                dict(r)
                for r in db.execute(
                    "SELECT vendor,product,kind FROM catalog_product_aliases WHERE product_id=? ORDER BY kind,vendor,product",
                    (product_id,),
                )
            ]
        return {**dict(row), "aliases": aliases, "sources": sorted({a["kind"] for a in aliases})}

    def _records(self, db, risk, where, args, limit, offset):
        base = (
            " FROM catalog_overview r JOIN catalog_indexed i ON i.cve_id=r.id"
            + risk["join"]
            + risk["score_join"]
            + " WHERE "
            + where
        )
        total = db.execute("SELECT count(*)" + base, args).fetchone()[0]
        columns = ",".join(
            risk[key] + " AS " + alias
            for key, alias in (
                ("kev", "kev"),
                ("epss", "epss_score"),
                ("percentile", "epss_percentile"),
                ("date", "epss_date"),
                ("model", "epss_model"),
                ("epss_sha", "epss_sha"),
                ("kev_json", "kev_json"),
                ("kev_sha", "kev_sha"),
            )
        )
        rows = db.execute(
            "SELECT r.id,r.description,r.status,r.published,r.modified,r.severity,r.score,"
            + columns
            + base
            + " ORDER BY kev DESC,r.score DESC,r.modified DESC,r.id LIMIT ? OFFSET ?",
            [*args, limit, offset],
        ).fetchall()
        items = []
        for row in rows:
            value = {
                key: row[key]
                for key in (
                    "id",
                    "description",
                    "status",
                    "published",
                    "modified",
                    "severity",
                    "score",
                )
            }
            value.update({"kev": bool(row["kev"]), "kev_source": risk["kev_source"], "epss": None})
            if row["epss_score"] is not None:
                raw = {
                    "cve": row["id"],
                    "epss": row["epss_score"],
                    "percentile": row["epss_percentile"],
                    "date": row["epss_date"],
                    "model_version": row["epss_model"],
                }
                if hashlib.sha256(compact(raw).encode()).hexdigest() != row["epss_sha"]:
                    raise ValueError("Local EPSS record failed its integrity check")
                value["epss"] = {
                    "score": row["epss_score"],
                    "percentile": row["epss_percentile"],
                    "score_date": row["epss_date"],
                    "model_version": row["epss_model"],
                    "record_sha256": row["epss_sha"],
                    **self._risk_source("FIRST EPSS", risk["epss_state"]),
                }
            if risk["kev_state"] is not None:
                value["kev_detail"] = {
                    "listed": bool(row["kev"]),
                    "entry": json.loads(row["kev_json"]) if row["kev_json"] else None,
                    "record_sha256": row["kev_sha"],
                    **self._risk_source("CISA KEV", risk["kev_state"]),
                }
            items.append(value)
        return items, total

    def product(self, product_id, *, scope="critical", version="", limit=50, offset=0):
        self._page(limit, offset)
        product = self.product_identity(product_id)
        if product is None:
            return None
        if not isinstance(version, str) or len(version) > 200:
            raise ValueError("Reported version must be at most 200 characters")
        with self.connection() as db:
            risk = self._risk_sql(db)
            where, args = self._where(scope, risk, product_id)
            items, total = self._records(db, risk, where, args, limit, offset)
            for item in items:
                cve = self._indexed_record(db, item["id"])
                item["versions"], item["version_count"] = record_versions(cve, product_id, version)
                item["versions_truncated"] = item["version_count"] > len(item["versions"])
                item["references"] = [
                    ref for ref in cve.get("references", []) if isinstance(ref, dict)
                ][:20]
        return {
            "product": product,
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "index": self.index_status(),
        }

    def product_cve_ids(self, product_id, *, scope="all"):
        if not self.product_identity(product_id):
            return set()
        with self.connection() as db:
            risk = self._risk_sql(db)
            where, args = self._where(scope, risk, product_id)
            return {
                row[0]
                for row in db.execute(
                    "SELECT r.id FROM catalog_overview r JOIN catalog_indexed i ON i.cve_id=r.id"
                    + risk["join"]
                    + " WHERE "
                    + where,
                    args,
                )
            }

    def candidate_matches(self, product_id, version, *, cve_ids=None, scope="critical", limit=100):
        self._page(limit, 0)
        product = self.product_identity(product_id)
        if not product:
            return {"items": [], "total": 0, "truncated": False}
        if not isinstance(version, str) or len(version) > 200:
            raise ValueError("Reported version must be at most 200 characters")
        allowed = sorted(set(cve_ids)) if cve_ids is not None else None
        if allowed is not None and len(allowed) > 1000:
            raise ValueError("Compare at most 1,000 selected CVEs at a time")
        if allowed == []:
            return {"items": [], "total": 0, "truncated": False}
        items = []
        with self.connection() as db:
            risk = self._risk_sql(db)
            where, args = self._where(scope, risk, product_id)
            if allowed is not None:
                where += " AND r.id IN (" + ",".join("?" for _ in allowed) + ")"
                args.extend(allowed)
            rows, total = self._records(db, risk, where, args, limit, 0)
            for row in rows:
                cve = self._indexed_record(db, row["id"])
                versions, version_count = record_versions(cve, product_id, version)
                matches = [item["match"] for item in versions if item["match"]]
                states = {item["state"] for item in matches}
                state = (
                    "candidate"
                    if "candidate" in states
                    else "unresolved"
                    if "unresolved" in states or version_count > len(versions) or not states
                    else "not_matched"
                )
                reason = next(
                    (item["reason"] for item in matches if item["state"] == state),
                    "Additional version statements require inspection",
                )
                items.append(
                    {"cve_id": row["id"], "state": state, "reason": reason, "versions": versions}
                )
        return {"items": items, "total": total, "truncated": total > limit}

    def _indexed_record(self, db, cve_id):
        row = db.execute("SELECT raw_json,raw_sha256 FROM records WHERE id=?", (cve_id,)).fetchone()
        if row is None or hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
            raise ValueError("The local CVE record failed its integrity check")
        value = json.loads(row[0])
        if not isinstance(value, dict) or value.get("id") != cve_id:
            raise ValueError("The local CVE record does not match its identifier")
        return value

    def fields(self, field="weakness", *, scope="critical", product_id="", limit=30):
        if field not in FIELDS or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Unknown field or invalid result limit")
        result = {
            "field": field,
            "available_fields": [{"id": key, "label": value} for key, value in FIELDS.items()],
            "population": 0,
            "covered": 0,
            "missing": 0,
            "items": [],
            "index": self.index_status(),
            "unit": "distinct CVEs",
        }
        if not self.db.is_file():
            return result
        with self.connection() as db:
            risk = self._risk_sql(db)
            where, args = self._where(scope, risk, product_id)
            base = " FROM catalog_overview r JOIN catalog_indexed i ON i.cve_id=r.id" + risk["join"]
            result["population"] = db.execute(
                "SELECT count(*)" + base + " WHERE " + where, args
            ).fetchone()[0]
            result["covered"] = db.execute(
                "SELECT count(*)"
                + base
                + " WHERE "
                + where
                + " AND EXISTS(SELECT 1 FROM catalog_facets f WHERE f.cve_id=r.id AND f.field=?)",
                [*args, field],
            ).fetchone()[0]
            result["items"] = [
                dict(row)
                for row in db.execute(
                    "SELECT f.value,count(*) AS count"
                    + base
                    + " JOIN catalog_facets f ON f.cve_id=r.id WHERE "
                    + where
                    + " AND f.field=? GROUP BY f.value ORDER BY count DESC,f.value LIMIT ?",
                    [*args, field, limit],
                )
            ]
            result["missing"] = result["population"] - result["covered"]
        return result

    def field_records(self, field, value, *, scope="critical", product_id="", limit=25, offset=0):
        self._page(limit, offset)
        if field not in FIELDS or not isinstance(value, str) or len(value) > 500:
            raise ValueError("Invalid field selection")
        if not self.db.is_file():
            return {
                "items": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "index": self.index_status(),
            }
        with self.connection() as db:
            risk = self._risk_sql(db)
            where, args = self._where(scope, risk, product_id)
            where += " AND EXISTS(SELECT 1 FROM catalog_facets f WHERE f.cve_id=r.id AND f.field=? AND f.value=?)"
            items, total = self._records(db, risk, where, [*args, field, value], limit, offset)
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "index": self.index_status(),
        }

    def assessments(self, cve_id):
        if not self.db.is_file():
            return []
        with self.connection() as db:
            result = []
            for row in db.execute(
                "SELECT version,source,type,score,severity,vector,details_json FROM catalog_cvss WHERE cve_id=? ORDER BY ordinal",
                (cve_id,),
            ):
                value = dict(row)
                value["details"] = json.loads(value.pop("details_json"))
                result.append(value)
            return result

    def changes(self, *, cve_id="", limit=50, offset=0):
        self._page(limit, offset)
        result = {"items": [], "total": 0, "limit": limit, "offset": offset}
        if not self.db.is_file():
            return result
        with self.connection() as db:
            where, args = (" WHERE cve_id=?", [cve_id]) if cve_id else ("", [])
            result["total"] = db.execute(
                "SELECT count(*) FROM catalog_changes" + where, args
            ).fetchone()[0]
            for row in db.execute(
                "SELECT * FROM catalog_changes" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ):
                item = dict(row)
                item["fields"] = json.loads(item.pop("fields_json"))
                result["items"].append(item)
        return result
