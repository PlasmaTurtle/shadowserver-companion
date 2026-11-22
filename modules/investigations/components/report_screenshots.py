"""Required website evidence for the selected recipient report scope."""

from urllib.parse import urlsplit

from modules.tools.components.network_identity import root_domain


def relevant_screenshots(lead):
    """Select included website images tied to a domain in this report.

    Manually attached screenshots identify their source URL. Automated captures
    additionally retain the browser's actual destination and usable-page result.
    Neither a different site's image nor a saved challenge/error page satisfies
    the report's website evidence requirement.
    """
    from .website_evidence import is_usable_capture

    roots = {
        str(group.get("root_domain") or "").casefold().rstrip(".")
        for group in lead.get("domain_groups", [])
    } - {""}
    result = []
    for item in lead.get("evidence", []):
        if not item.get("included") or item.get("kind") != "website":
            continue
        capture = item.get("capture") or item.get("source_metadata", {}).get("website_capture")
        if capture and not is_usable_capture(capture):
            continue
        try:
            url = urlsplit((capture or {}).get("final_url") or item.get("source_url") or "")
            host = url.hostname or ""
            if url.scheme not in {"http", "https"} or not host or url.username or url.password:
                continue
            if root_domain(host.casefold().rstrip(".")) not in roots:
                continue
        except ValueError:
            continue
        result.append(item)
    return result


def screenshot_readiness(lead):
    return {
        "key": "website_screenshot",
        "label": "Include a website screenshot for a domain in this report",
        "ok": bool(relevant_screenshots(lead)),
    }


def intact_screenshot(item):
    """Both retained originals and report previews must match their digests."""
    metadata = item.get("source_metadata") or {}
    integrity = item.get("file_integrity") or {}
    return bool(
        item.get("sha256")
        and metadata.get("sha256") == item["sha256"]
        and integrity.get("path_sha256") == item["sha256"]
        and metadata.get("preview_sha256")
        and integrity.get("preview_path_sha256") == metadata["preview_sha256"]
        and integrity.get("capture_source_matches", True)
    )
