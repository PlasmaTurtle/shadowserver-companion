"""Availability checks against the immutable package inventory."""

import re


class ArtifactRepository:
    def __init__(self, store):
        self.store = store

    def _binding(self, kind, record, raw):
        from ..artifact_registry import verify_binding

        with self.store.read_snapshot() as db:
            verify_binding(db, kind, record, raw)

    def package_available(self, report):
        try:
            self.package_inventory(report)
            return True
        except ValueError, OSError, KeyError, TypeError:
            return False

    def package_inventory(self, report):
        from ..package_integrity import package_folder, validated_inventory
        from ..artifact_identity import report_identity

        manifest, raw = validated_inventory(
            package_folder(self.store.root, report["path"]),
            {"notification.pdf", "notification.docx", "snapshot.json"},
        )
        report_identity(report, manifest, self.store.resolve_entity)
        self._binding("report", report, raw)
        return manifest, raw

    def snapshot_inventory(self, report):
        """Verify historical content independently of rendered-file availability.

        This does not populate the full-package verification cache or authorize
        a download. A missing PDF must not hide an intact, correctly bound case
        snapshot, while the delivery and transfer paths still require all files.
        """
        from ..package_integrity import package_folder, parsed_manifest, read_member
        from ..artifact_identity import report_identity

        folder = package_folder(self.store.root, report["path"])
        manifest, raw = parsed_manifest(folder)
        files = manifest.get("files")
        digest = files.get("snapshot.json") if isinstance(files, dict) else None
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Certified report snapshot has no valid manifest digest")
        report_identity(report, manifest, self.store.resolve_entity)
        self._binding("report", report, raw)
        return manifest, read_member(folder, "snapshot.json", digest)

    def closure_inventory(self, record):
        from ..package_integrity import package_folder, validated_inventory
        from ..artifact_identity import closure_identity

        manifest, raw = validated_inventory(
            package_folder(self.store.root, record["path"]),
            {"closing-report.pdf", "closing-report.docx", "snapshot.json"},
        )
        closure_identity(record, manifest)
        self._binding("closure", record, raw)
        return manifest, raw

    def closure_available(self, record):
        try:
            self.closure_inventory(record)
            return True
        except OSError, ValueError, KeyError, TypeError:
            return False

    def work_log_available(self, report):
        try:
            manifest, _ = self.package_inventory(report)
            return {"work-log.pdf", "chronology.json"} <= manifest["files"].keys()
        except ValueError, OSError, KeyError, TypeError:
            return False
