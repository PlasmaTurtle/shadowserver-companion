"""Offline business-field validation against the bundled U.S. place catalog."""

from email.headerregistry import Address
from email.errors import MessageError
from functools import lru_cache
import json
from pathlib import Path
import re

import idna

STATE_NAMES = dict(
    zip(
        "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR".split(),
        [
            "Alabama",
            "Alaska",
            "Arizona",
            "Arkansas",
            "California",
            "Colorado",
            "Connecticut",
            "Delaware",
            "District of Columbia",
            "Florida",
            "Georgia",
            "Hawaii",
            "Idaho",
            "Illinois",
            "Indiana",
            "Iowa",
            "Kansas",
            "Kentucky",
            "Louisiana",
            "Maine",
            "Maryland",
            "Massachusetts",
            "Michigan",
            "Minnesota",
            "Mississippi",
            "Missouri",
            "Montana",
            "Nebraska",
            "Nevada",
            "New Hampshire",
            "New Jersey",
            "New Mexico",
            "New York",
            "North Carolina",
            "North Dakota",
            "Ohio",
            "Oklahoma",
            "Oregon",
            "Pennsylvania",
            "Rhode Island",
            "South Carolina",
            "South Dakota",
            "Tennessee",
            "Texas",
            "Utah",
            "Vermont",
            "Virginia",
            "Washington",
            "West Virginia",
            "Wisconsin",
            "Wyoming",
            "Puerto Rico",
        ],
        strict=True,
    )
)


def clean(value):
    return " ".join(str(value or "").split())


@lru_cache(maxsize=1)
def place_catalog():
    data = json.loads(
        (Path(__file__).resolve().parent.parent / "static/geo/entity-places.json").read_text()
    )
    return {
        state: {clean(city).casefold(): city for city in cities}
        for state, cities in data["states"].items()
    }


def state_code(value):
    value = clean(value)
    if not value:
        return ""
    upper = value.upper()
    if upper in STATE_NAMES:
        return upper
    for code, name in STATE_NAMES.items():
        if value.casefold() == name.casefold():
            return code
    raise ValueError("Choose a U.S. state or territory from the location list.")


def locations(state="", q="", limit=60):
    code = state_code(state)
    needle = clean(q).casefold()
    catalog = place_catalog()
    rows = []
    for region in [code] if code else sorted(catalog):
        for key, city in catalog.get(region, {}).items():
            if not needle or key.startswith(needle):
                rows.append({"city": city, "state": region})
                if len(rows) >= limit:
                    return rows
    return rows


def merge_profiles(source, target):
    """Fill missing target fields without constructing a new city/state pairing."""
    merged = {**source, **{key: value for key, value in target.items() if value}}
    merged["city"], merged["state"] = target.get("city", ""), target.get("state", "")
    source_city, target_city = clean(source.get("city")), clean(target.get("city"))
    try:
        source_state, target_state = (
            state_code(source.get("state")),
            state_code(target.get("state")),
        )
    except ValueError:
        return merged
    if source_city and (
        not source_state or source_city.casefold() not in place_catalog().get(source_state, {})
    ):
        return merged
    if target_state and source_state != target_state:
        return merged
    if target_city and target_city.casefold() != source_city.casefold():
        return merged
    if source_city and not target_city:
        merged["city"] = place_catalog()[source_state][source_city.casefold()]
    if source_state and not target_state:
        merged["state"] = source_state
    return merged


def validate_profile(values, *, previous=None):
    values = dict(values)
    previous = previous or {}
    city, state = clean(values.get("city")), clean(values.get("state"))
    # Existing imported values are preserved while unrelated contact fields change.
    # A user editing location must choose a recognized pair.
    if (city, state) != (clean(previous.get("city")), clean(previous.get("state"))):
        code = state_code(state)
        catalog = place_catalog()
        if city:
            candidates = [catalog.get(code, {})] if code else catalog.values()
            if not any(city.casefold() in names for names in candidates):
                raise ValueError(
                    "Choose a recognized city and matching state. Mailing address remains free text."
                )
            city = next(names[city.casefold()] for names in candidates if city.casefold() in names)
        values["city"], values["state"] = city, code
    email = str(values.get("contact_email") or "").strip()
    if email:
        try:
            if len(email) > 254 or any(ord(c) < 32 or ord(c) == 127 for c in email):
                raise ValueError
            address = Address(addr_spec=email)
            domain = idna.encode(address.domain, uts46=True, std3_rules=True).decode("ascii")
            if (
                not address.username
                or len(address.username.encode("utf-8")) > 64
                or "." not in domain
            ):
                raise ValueError
            if domain.endswith(".") or len(domain) > 253:
                raise ValueError
        except MessageError, ValueError, TypeError, UnicodeError:
            raise ValueError(
                "Enter one valid email address, such as contact@example.com."
            ) from None
    values["contact_email"] = email
    phone = str(values.get("contact_phone") or "").strip()
    if phone:
        main = re.sub(r"\s*(?:ext\.?|x|#)\s*\d{1,10}$", "", phone, flags=re.I)
        digits = re.sub(r"\D", "", main)
        if (
            not re.fullmatch(r"\+?[0-9 ().-]+", main)
            or not 7 <= len(digits) <= 15
            or main.count("(") != main.count(")")
            or main.count("(") > 1
            or ("(" in main and main.index("(") > main.index(")"))
        ):
            raise ValueError(
                "Enter a valid phone number with 7–15 digits; an extension is optional."
            )
        if len(set(digits)) == 1 or (main.startswith("+") and digits.startswith("0")):
            raise ValueError("Enter a valid phone number, not a placeholder.")
        national = digits[1:] if len(digits) == 11 and digits.startswith("1") else digits
        if main.startswith("+1") and len(digits) != 11:
            raise ValueError("A +1 phone number needs a ten-digit national number.")
        if not main.startswith("+") or main.startswith("+1"):
            if len(national) == 10 and (
                national[0] not in "23456789" or national[3] not in "23456789"
            ):
                raise ValueError(
                    "Enter a valid North American area code and exchange, or use + and the country code."
                )
            if len(national) == 7 and national[0] not in "23456789":
                raise ValueError("Enter a valid local exchange, or use + and the country code.")
    values["contact_phone"] = phone
    return values
