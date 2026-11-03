"""Procurement ingestion framework: deterministic connectors that fetch, validate, normalise and hand
bundles to the database function procurement.ingest_bundle(). AI is used for discovery and reading
documentation, never for pagination, validation, money, dates or writes."""
VERSION = "0.1.0"
TRANSFORM_VERSION = "myb-procurement-0.1"
USER_AGENT = "MilitaryYellowBookIngest/0.1 (+https://github.com/skinyanjui/military-yellow-book)"
