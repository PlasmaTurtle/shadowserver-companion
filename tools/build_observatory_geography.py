"""Build offline Observatory geography from downloaded Census 2025 archives.

No network or third-party dependencies. Pass the national Places Gazetteer ZIP
and cb_2025_us_state_5m KML ZIP from the source URLs embedded below.
"""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PLACES_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip"
STATES_URL = "https://www2.census.gov/geo/tiger/GENZ2025/kml/cb_2025_us_state_5m.zip"
SUFFIX = re.compile(r" (?:city|town|village|CDP|municipality|borough|comunidad|zona urbana)$")


def source(path, url, title):
    return {
        "publisher": "U.S. Census Bureau",
        "title": title,
        "url": url,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "retrieved_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "license": "U.S. government geographic data. Credit U.S. Census Bureau. No endorsement implied.",
    }


def places(path):
    with ZipFile(path) as archive:
        text = archive.read("2025_Gaz_place_national.txt").decode("utf-8-sig")
    grouped = defaultdict(list)
    for row in csv.DictReader(StringIO(text), delimiter="|"):
        name = SUFFIX.sub("", row["NAME"])
        key = row["USPS"] + "|" + " ".join(name.casefold().split())
        grouped[key].append(
            {
                "name": name,
                "official_name": row["NAME"],
                "region": row["USPS"],
                "geoid": row["GEOID"],
                "latitude": float(row["INTPTLAT"]),
                "longitude": float(row["INTPTLONG"]),
            }
        )
    unique = {key: values[0] for key, values in sorted(grouped.items()) if len(values) == 1}
    metadata = source(path, PLACES_URL, "2025 U.S. Gazetteer Files — Places")
    metadata.update(
        {
            "documentation_url": "https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2025.html",
            "coordinate_semantics": "INTPTLAT / INTPTLONG are representative internal points of Census places. They locate a reported city area approximately; they are not asset, business, or address coordinates.",
        }
    )
    return {
        "schema_version": 1,
        "source": metadata,
        "normalization": "Exact state postal code + | + casefolded city with collapsed whitespace. Census terminal city/town/village/CDP/municipality/borough/comunidad/zona urbana suffix removed. Ambiguous city/state pairs excluded; no fuzzy matching.",
        "counts": dict(sorted(Counter(item["region"] for item in unique.values()).items())),
        "ambiguous_keys": sorted(key for key, values in grouped.items() if len(values) > 1),
        "places": unique,
    }


def states(path):
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("cb_2025_us_state_5m.kml"))
    features = []
    for placemark in root.findall(".//{*}Placemark"):
        attrs = {item.attrib["name"]: item.text for item in placemark.findall(".//{*}SimpleData")}
        polygons = []
        for polygon in placemark.findall(".//{*}Polygon"):
            rings = []
            for coordinates in polygon.findall(".//{*}coordinates"):
                rings.append(
                    [
                        [round(float(value), 4) for value in point.split(",")[:2]]
                        for point in coordinates.text.split()
                    ]
                )
            polygons.append(rings)
        features.append(
            {
                "type": "Feature",
                "id": attrs["STATEFP"],
                "properties": {"name": attrs["NAME"], "postal": attrs["STUSPS"]},
                "geometry": {"type": "MultiPolygon", "coordinates": polygons},
            }
        )
    return {
        "schema_version": 1,
        "source": source(
            path, STATES_URL, "2025 Cartographic Boundary Files — States, 1:5,000,000"
        ),
        "semantics": "Geographic context only; shapes do not define legal or investigative jurisdiction. Coordinates rounded to four decimal places.",
        "states": sorted(features, key=lambda item: item["id"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--places-zip", required=True, type=Path)
    parser.add_argument("--states-kml-zip", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "static/geo")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in (
        ("places.json", places(args.places_zip)),
        ("states.json", states(args.states_kml_zip)),
    ):
        (args.output / name).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        print(f"Built {name}")


if __name__ == "__main__":
    main()
