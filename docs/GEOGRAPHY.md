# Distance data and meaning

SERA resolves a buyer's ZIP code, city, or state **offline**. Location queries are
not sent to a geocoder. The bundled lookup is derived from the U.S. Census
Bureau's [2026 Gazetteer files](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html),
retrieved October 27, 2026. Census identifies these coordinates as representative
internal points. They approximate area centers; they are not exact geometric
centroids, building coordinates, or postal delivery locations.

The bundle covers 52 state-level areas (the 50 states, District of Columbia, and
Puerto Rico), 32,363 Census places, and 33,791 ZIP Code Tabulation Areas (ZCTAs).
Island Areas are not included in these national Census files. ZCTAs approximate
ZIP delivery areas. Some USPS ZIP codes, including PO-box-only and newly assigned
codes, do not have a ZCTA. An absent ZIP produces a helpful error rather than an
invented position.

## Sources and preparation

- [States archive](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2026_Gazetteer/2026_Gaz_state_national.zip)
- [Places archive](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2026_Gazetteer/2026_Gaz_place_national.zip)
- [ZCTA archive](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2026_Gazetteer/2026_Gaz_zcta_national.zip)

`data/geography_2026.json` retains state abbreviations/names, place names, five-digit
ZCTA identifiers (as strings, preserving leading zeros), and the source's
`INTPTLAT` / `INTPTLONG` values. Geographic legal suffixes such as `city`, `CDP`,
and `metropolitan government (balance)` are removed for search aliases. The full
official place name remains in every row. Three common catalog aliases map Boise
to Boise City, Honolulu to Urban Honolulu, and Nashville to Nashville-Davidson.
No coordinates were invented, rounded, or inferred from fictional addresses.
The JSON includes SHA-256 checksums of the original extracted text files under
`source_sha256` for provenance. The file is approximately 2.9 MB and adds no
runtime dependency or visitor network request. U.S. Census government data are
public domain; attribution is retained here.

## Resolution and distance rules

1. A five-digit ZIP in the supplied origin takes precedence, including in a
   combined entry such as `Boston, MA 02108`. ZIP+4 uses the five-digit ZCTA.
   Multiple distinct ZIPs require clarification.
2. A state name or abbreviation uses that state's representative point.
3. A city can include an abbreviation or full state name. A city alone is
   accepted only when it identifies a single place. Ambiguous place names require
   clarification; SERA does not choose the largest or first result.
4. Each fictional practice uses its city's representative point, because these
   demo practices have no actual property address. All 50 catalog entries resolve.
5. Great-circle distance uses the Haversine formula and mean Earth radius
   3,958.7613 miles. It is approximate **straight-line distance**, not a driving
   route, travel time, or claim about a practice's address. A city origin and a
   practice in the same city share a point and therefore show zero miles.

Unknown practice locations return no distance. Unknown or ambiguous buyer origins
raise a readable validation error. Coordinates must be finite and fall within
latitude/longitude bounds. Distance calculations do not change any practice's
evidence or financial facts.
