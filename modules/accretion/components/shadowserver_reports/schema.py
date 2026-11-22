"""Optional local schema snapshots and diagnostics; never coerces report data."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from .errors import ConfigurationError, StorageError


@dataclass(frozen=True)
class SchemaSnapshot:
    report_type: str
    sha256: str
    path: str
    captured_at: str
    previous_sha256: str | None
    added_fields: tuple[str, ...]
    removed_fields: tuple[str, ...]
    changed_fields: tuple[str, ...]

    def public_dict(self):
        return asdict(self)


class SchemaStore:
    """Content-addressed snapshots of the API's field-to-type maps.

    The current pointer is updated atomically. Historical snapshots are immutable.
    A schema change is informational and never alters a downloaded file.
    """
    def __init__(self, root):
        self.root = Path(root)

    def capture(self, report_type, schema):
        if not isinstance(report_type, str) or not report_type.strip() or not isinstance(schema, dict):
            raise ConfigurationError("A report type and schema object are required.")
        if not all(isinstance(key, str) for key in schema):
            raise ConfigurationError("Schema field names must be strings.")
        try:
            raw = json.dumps(schema, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
        except (TypeError, ValueError, RecursionError):
            raise ConfigurationError("Schema must contain finite JSON values.") from None
        digest = sha256(raw).hexdigest()
        group = self.root / sha256(report_type.encode()).hexdigest()
        path = group / (digest + ".json")
        latest = group / "current.json"
        previous = None
        previous_schema = {}
        try:
            group.mkdir(parents=True, exist_ok=True)
            if latest.exists():
                pointer = json.loads(latest.read_text(encoding="utf-8"))
                previous = pointer["sha256"]
                if not isinstance(previous, str) or len(previous) != 64 or any(c not in "0123456789abcdef" for c in previous):
                    raise ValueError
                earlier = (group / (previous + ".json")).read_bytes()
                if sha256(earlier).hexdigest() != previous:
                    raise ValueError
                previous_schema = json.loads(earlier)
                if not isinstance(previous_schema, dict):
                    raise ValueError
            if path.exists():
                if sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError
            else:
                self._publish(path, raw, replace=False)
            captured = datetime.now(timezone.utc).isoformat()
            self._publish(latest, json.dumps({"sha256": digest, "captured_at": captured}).encode(), replace=True)
        except (OSError, ValueError, KeyError, TypeError):
            raise StorageError("Schema cache could not be read or written safely.") from None
        return SchemaSnapshot(report_type, digest, str(path.resolve()), captured, previous,
                              tuple(sorted(set(schema) - set(previous_schema))) if previous else (),
                              tuple(sorted(set(previous_schema) - set(schema))),
                              tuple(sorted(k for k in set(schema) & set(previous_schema) if schema[k] != previous_schema[k])))

    @staticmethod
    def _publish(path, raw, *, replace):
        fd, temporary = tempfile.mkstemp(prefix=".schema-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if replace:
                os.replace(temporary, path)
            else:
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if path.read_bytes() != raw:
                        raise ValueError
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
