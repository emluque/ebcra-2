"""Constants shared across more than one package.

Kept separate from any single package so neither has to import from the
other's domain just to share a value — e.g. an ingestion client (cronista/)
importing from downstream derivations (calculated/) would run the wrong way
against how data flows through this pipeline.
"""

# dollar_blue_cronista holds two eras of data in the same table: legacy rows
# collected by a previous version of the system, up to and including this
# date, and — after calculated/pipeline.py's _AMBITO_BLUE_END_DATE boundary —
# live-scraped rows.
#
# Referenced by calculated/pipeline.py (bounds the legacy segment of
# dollar_blue_unified) and cronista/client.py (a defensive floor: a scraped
# row dated at or before this must never be upserted into the shared table).
CRONISTA_LEGACY_END_DATE = "2019-01-01"
