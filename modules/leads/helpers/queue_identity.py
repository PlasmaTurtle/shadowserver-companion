"""Stable queue identity shared by migration and current lead operations."""

import hashlib


def queue_id(import_id, domain):
    return hashlib.sha256((import_id + "\0" + domain).encode()).hexdigest()[:32]
