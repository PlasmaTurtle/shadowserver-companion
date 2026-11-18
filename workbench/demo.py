"""Opt-in, explicitly synthetic workspace. Never queries a sample IP or hostname."""

import csv
import hashlib
import io
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont
from attribution.models import json_bytes

from workbench.intake import UnvalidatedEntry, ValidatedEntry, ValidatedLeads
from .primitives import dump, now, uid
from .reporting import default_draft, finalize
from .cases import Cases
from .closing import close_case


def demonstration_attribution(name, domain, ip, *, evaluated=True):
    """Complete synthetic evidence; never represents a real registry lookup."""
    retrieved = now()
    record = {
        "notice": "Synthetic evidence for demonstration only. No registry lookup was performed.",
        "demo_contact": "contact@" + domain,
        "name": name,
        "startAddress": ip,
        "endAddress": ip,
        "ipVersion": "v4",
    }
    match = {
        "target_domain": domain,
        "matched_domain": domain,
        "field_path": "/demo_contact",
        "field_type": "email",
        "value": record["demo_contact"],
    }
    proof = {
        "ip": ip,
        "registry": "DEMONSTRATION RECORD",
        "source_url": "https://example.com/registration-demo",
        "retrieved_at": retrieved,
        "protocol": "SYNTHETIC",
        "attribution": {
            "root_domain": domain,
            "matched_domain": domain,
            "field": match["field_path"],
            "value": match["value"],
        },
        "record": record,
        "body_sha256": hashlib.sha256(json_bytes(record)).hexdigest(),
        "evidence": {
            "method": "rdap",
            "ip": ip,
            "source_name": "DEMONSTRATION RECORD",
            "source_url": "https://example.com/registration-demo",
            "retrieved_at": retrieved,
            "match": match,
            "details": {"network_start": ip, "network_end": ip},
            "from_cache": False,
        },
    }
    if evaluated:
        proof["evaluated_at"] = now()
        proof["validated_by"] = "Demonstration evaluator (synthetic)"
    return proof


def seed_demo(store, intake):
    if store.one("SELECT id FROM leads LIMIT 1"):
        return
    profile = store.settings()
    profile.update(
        analyst_name="Demo Analyst",
        agency="DEMONSTRATION WORKSPACE",
        department="Synthetic workflow examples",
        office="No real exposure assessed",
        watch_inbox=False,
    )
    with store.transaction() as db:
        db.execute("UPDATE settings SET value=? WHERE key=?", (dump(profile), "profile"))
    names = [
        ("Cedarworks Supply", "cedarworks.example", 4, "new"),
        ("Northfield Manufacturing", "northfield.example", 3, "in_progress"),
        ("Riverside Partners", "riverside.example", 5, "pending_notification"),
        ("Pinecrest Services", "pinecrest.example", 2, "notification_completed"),
        ("Harbor Point Group", "harborpoint.example", 3, "closed"),
    ]
    rows = []
    for n, (name, domain, count, status) in enumerate(names):
        for j in range(count):
            rows.append(
                {
                    "report_type": "scan_http_vulnerable",
                    "timestamp": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                    # Public exemplars exercise the real notification gate.
                    # These addresses are never queried or attributed as fact;
                    # every source row, proof and report is marked synthetic.
                    "ip": f"8.8.8.{10 + n * 10 + j}",
                    "protocol": "tcp",
                    "port": 443,
                    "hostname": ("mail." if j % 2 else "") + domain,
                    "tag": "eol-php",
                    "version": "7.3.25",
                    "asn": 64496,
                    "geo": "US",
                    "region": "North Carolina",
                    "city": ["Charlotte", "Asheville", "Raleigh"][n % 3],
                    "http": "PHP/7.3.25",
                    "source_note": "SYNTHETIC DEMONSTRATION — not a Shadowserver observation",
                }
            )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    import_id = intake.enqueue("demonstration-observations.csv", output.getvalue().encode())["id"]
    with store.transaction() as db:
        db.execute(
            "UPDATE imports SET status='done',stage='Demonstration data',message='Synthetic sample; no external lookups performed',rows_read=?,valid_rows=?,groups_total=5,groups_done=5,qualified=5 WHERE id=?",
            (len(rows), len(rows), import_id),
        )
    rowno = 2
    for n, (name, domain, count, status) in enumerate(names):
        subset = rows[rowno - 2 : rowno - 2 + count]
        entries = [
            ValidatedEntry(
                UnvalidatedEntry("demonstration-observations.csv", "CSV", rowno + j, r),
                r["ip"],
                False,
            )
            for j, r in enumerate(subset)
        ]
        rowno += count
        group = ValidatedLeads(domain, entries)
        # The first fixture deliberately lacks a decision time so its card
        # demonstrates a pending review. The other synthetic records are complete.
        attribution = demonstration_attribution(name, domain, entries[0].ip, evaluated=n != 0)
        lead_id = intake.accept_group(import_id, group, attribution, demo=True)
        cases = Cases(store)
        case_id = cases.create(lead_id)["case_id"] if status != "new" else None
        lead = store.lead(lead_id)
        d = default_draft(lead, profile)
        d.update(
            company=name,
            contact_name="IT Service Desk",
            contact_email="it@" + domain,
            address="Demonstration address\nNorth Carolina",
            notes="Synthetic record for exploring the workflow.",
        )
        d["narrative"] = (
            "DEMONSTRATION: These synthetic observations illustrate a notification for reported end-of-life PHP. No real organization, service, or exposure has been assessed."
        )
        with store.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO entity_profiles VALUES(?,?)",
                (
                    lead_id,
                    dump(
                        {
                            "contact_name": "IT Service Desk",
                            "contact_email": "it@" + domain,
                            "address": "Demonstration address\nNorth Carolina",
                            "city": ["Charlotte", "Asheville", "Raleigh"][n % 3],
                            "state": "North Carolina",
                        }
                    ),
                ),
            )
            db.execute(
                "UPDATE leads SET company=?,status=?,draft=?,draft_revision=1 WHERE id=?",
                (name, "new" if status == "new" else "in_progress", dump(d), lead_id),
            )
            db.execute(
                "UPDATE cases SET title=?,draft=?,draft_revision=1,contact_name=?,contact_email=? WHERE id=?",
                (
                    f"November outreach · {name}",
                    dump(d),
                    "IT Service Desk",
                    "it@" + domain,
                    case_id,
                ),
            )
            db.execute(
                "INSERT INTO jobs(id,import_id,domain,payload,status,attempts) VALUES(?,?,?,?,?,?)",
                (
                    uid(),
                    import_id,
                    domain,
                    dump([asdict(e) for e in entries]),
                    "qualified",
                    dump([{"ip": entries[0].ip, "status": "synthetic"}]),
                ),
            )
        if case_id:
            with store.transaction() as db:
                entity = dict(db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())
                cases.repository.pin_entity(
                    db, case_id, entity, cases.repository.entities.profile(db, lead_id)
                )
        if status in ("pending_notification", "notification_completed", "closed"):
            evidence_id = uid()
            relative = f"evidence/{evidence_id}.png"
            canvas = Image.new("RGB", (1200, 660), "#f5f7fa")
            draw = ImageDraw.Draw(canvas)

            def font(size):
                for path in (
                    "C:/Windows/Fonts/arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                ):
                    try:
                        return ImageFont.truetype(path, size)
                    except OSError:
                        pass
                return ImageFont.load_default(size=size)

            draw.rectangle((0, 0, 1200, 100), fill="#18324e")
            draw.text(
                (45, 30), "DEMONSTRATION — SYNTHETIC WEBSITE EVIDENCE", fill="white", font=font(26)
            )
            draw.text((60, 160), name, fill="#18324e", font=font(46))
            draw.text((60, 250), "Contact our technology team", fill="#446482", font=font(30))
            draw.text((60, 315), "it@" + domain, fill="#2563eb", font=font(28))
            draw.text(
                (60, 430),
                "This illustration is not an actual website screenshot.",
                fill="#68798c",
                font=font(24),
            )
            draw.text(
                (60, 475),
                "Replace it with your own evidence in a working notification.",
                fill="#68798c",
                font=font(24),
            )
            canvas.save(store.path(relative))
            with store.transaction() as db:
                db.execute(
                    "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        evidence_id,
                        lead_id,
                        "website",
                        "demo-evidence.png",
                        relative,
                        relative,
                        "Demonstration hostname page",
                        "https://example.com/demo",
                        now(),
                        hashlib.sha256(store.path(relative).read_bytes()).hexdigest(),
                        1,
                        case_id,
                    ),
                )
                d.update(website_verified=True, reviewed=True)
                db.execute("UPDATE leads SET draft=? WHERE id=?", (dump(d), lead_id))
                db.execute("UPDATE cases SET draft=? WHERE id=?", (dump(d), case_id))
            from .section_validation import SectionReviews, SECTIONS

            for key in SECTIONS:
                SectionReviews(store).validate(case_id, key, cases.view(case_id)["draft_revision"])
            finalized = finalize(store, lead_id)
            case = cases.view(case_id)["case"]
            if status == "pending_notification":
                cases.plan(
                    case_id,
                    {
                        "expected_version": case["version"],
                        "contact_name": "IT Service Desk",
                        "contact_role": "Technology team",
                        "contact_email": "it@" + domain,
                        "contact_phone": "",
                        "next_action": "Call the technology team",
                        "follow_up_date": datetime.now(timezone.utc).date().isoformat(),
                    },
                )
            else:
                lead = cases.attempt(
                    case_id,
                    {
                        "expected_version": case["version"],
                        "report_id": finalized["id"],
                        "occurred_at": now(),
                        "channel": "email",
                        "outcome": "acknowledged",
                        "recipient": "IT Service Desk",
                        "destination": "it@" + domain,
                        "recorded_by": "Demo Analyst",
                        "information_source": "administrative",
                        "notes": "Synthetic example: the technology team acknowledged receiving the notification.",
                    },
                )
                if status == "closed":
                    lead = cases.attempt(
                        case_id,
                        {
                            "expected_version": lead["case"]["version"],
                            "report_id": finalized["id"],
                            "occurred_at": now(),
                            "channel": "phone",
                            "outcome": "recipient_update",
                            "recipient": "IT Service Desk",
                            "destination": "",
                            "recorded_by": "Demo Analyst",
                            "information_source": "recipient_reported",
                            "notes": "Synthetic example: the recipient reported scheduling a software upgrade.",
                        },
                    )
                    close_case(
                        store,
                        case_id,
                        {
                            "expected_version": lead["case"]["version"],
                            "reviewed": True,
                            "closed_by": "Demo Analyst",
                            "disposition": "notified",
                            "conclusion": "DEMONSTRATION: The technology team acknowledged receipt and reported a planned software upgrade. Remediation was not independently verified. Outreach concluded.",
                        },
                    )
