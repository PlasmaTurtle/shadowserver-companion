Bundled offline geography for ECLIPSE

states.json contains the U.S. Census Bureau 2025 cartographic state/equivalent
boundaries at 1:5,000,000, including all 56 Census state equivalents. Coordinates
are rounded to four decimal places. The selected jurisdiction supplies map
context and the initial camera extent; Fit entities includes every mapped entity
in the current view, including historical entities outside the selected states.
Geographic outlines do not establish legal or investigative jurisdiction.

places.json contains 31,914 unambiguous city/state representative points from the
2025 national Census Places Gazetteer across all 50 states, DC, and Puerto Rico.
Duplicate city names within the same state are excluded from positioning rather
than resolved arbitrarily. The map prefers the saved entity city/state. When no
complete city/state is saved, it uses the latest associated reported city/state
in the selected evidence, even when an older report has a more complete location.
These points are approximate city areas, never verified business/asset addresses.
Unplaced entities and all supporting records remain available. Multiple entities
at the same location are aggregated without fabricated geographic scatter.

The map uses Mercator latitude and a Pacific longitude seam so Alaska's Aleutian
islands stay together; there are no artificial state insets. Source coordinates
are preserved unchanged. The state geometry and Gazetteer are independent
datasets and their scales must not be interpreted as exact address boundaries.

Source URLs, retrieval timestamps, archive SHA-256 and government attribution
are embedded in places.json and states.json. Rebuild from the original ZIPs:
python tools/build_observatory_geography.py --places-zip <gazetteer.zip> --states-kml-zip <state-kml.zip>
The builder uses only Python's standard library. No map service or third-party
geocoding request is made during application use. U.S. Census Bureau credit does
not imply government endorsement of this software.

Entity location validation

entity-places.json contains 32,126 distinct place names grouped under 52 U.S.
state / District of Columbia / Puerto Rico postal codes from the 2025 Census
Places Gazetteer. Its source URL, retrieval date, archive SHA-256, normalization
and U.S. government data attribution are embedded in the JSON. It supplies
exact city/state validation and prefix autocomplete locally; it contains no
business addresses or inferred coordinates. Census places are not an exhaustive
postal-address locality list. Mailing address remains free text, and unchanged
legacy imported location values are preserved during unrelated contact edits.
