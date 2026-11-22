"""Reusable synthetic scoring fixtures and builders."""

from modules.accretion.components.scoring_evidence import empty_cve

ID = "CVE-2026-1234"


def entry(tag=ID, **fields):
    source = {
        "hostname": "mail.example.com",
        "ip": "8.8.8.8",
        "region": "MN",
        "tag": tag,
        "severity": "critical",
        "timestamp": "2026-11-12T00:00:00Z",
        "port": 443,
        **fields,
    }
    return {
        "source": {"fields": source},
        "normalized": {
            "profile": {"capability": "eligible", "version_requirement": "cve_or_version"},
            "products": [{"product": "Acme", "version": "1.2"}],
        },
    }


def vetted(
    identifier=ID, *, score=9.8, kev=False, epss=0.1, ransomware="Unknown", status="available"
):
    row = empty_cve(identifier, status)
    row.update(
        cvss=score,
        severity="CRITICAL",
        catalog_stale=False,
        kev={"listed": kev, "entry": {"knownRansomwareCampaignUse": ransomware}, "stale": False},
        epss={"score": epss, "percentile": 0.999, "stale": False},
    )
    return row
