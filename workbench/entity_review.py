"""Value-bound reminders for incomplete or prepopulated business details.

These reminders are independent of report certification. Historic nonempty
profile fields are treated as provided; changing and saving a field is review.
"""

from hashlib import sha256


REVIEW_FIELDS = {
    "name": "Entity / business name",
    "address": "Mailing address",
    "city": "Business city",
    "state": "Business state",
}


def value_hash(value):
    return sha256(str(value or "").encode("utf-8")).hexdigest()


def field_values(entity, profile):
    return {
        "name": entity["company"] or entity["domain"],
        **{field: str(profile.get(field) or "") for field in REVIEW_FIELDS if field != "name"},
    }


def review_summary(entity, profile, hostnames, decisions):
    values = field_values(entity, profile)
    hostname_names = {entity["domain"].casefold(), *(h["name"].casefold() for h in hostnames)}
    fields = []
    for field, label in REVIEW_FIELDS.items():
        value = values[field]
        digest = value_hash(value)
        decision = decisions.get(field)
        missing = not value.strip()
        prepopulated = field == "name" and value.casefold() in hostname_names
        status, reason = "provided", ""
        if decision and decision["value_hash"] == digest:
            status = decision["status"]
            if status == "pending":
                reason = "Missing business detail" if missing else "Check this business detail"
        elif decision:
            status, reason = "pending", "Changed since review"
        elif missing or prepopulated:
            status = "pending"
            reason = "Missing business detail" if missing else "Using the reported hostname"
        fields.append(
            {
                "field": field,
                "label": label,
                "value": value,
                "value_hash": digest,
                "status": status,
                "reason": reason,
                "can_confirm": not missing,
            }
        )
    return {"required": any(f["status"] == "pending" for f in fields), "fields": fields}
