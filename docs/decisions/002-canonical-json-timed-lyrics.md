# ADR-002: Persist timed lyrics as canonical JSON sidecars

## Status

Accepted

## Context

The lyrics editor can select a Musixmatch TTML upgrade, and the queue endpoint
accepts that selected representation. Persisting the selected XML directly
created `.ttml` sidecars that media scans and WhisperX alignment did not treat
as canonical lyrics. The stage cue endpoint could parse those files, but that
only hid the persistence inconsistency until a rescan or downstream task.

## Decision

Normalize TTML/XML input at the lyrics sidecar storage boundary by parsing it
into WhisperX-style segments and writing `<media-stem>.json`. Keep `.lrc` and
`.txt` as source formats for optional WhisperX alignment, and keep TTML parsing
available for accepted input and legacy cue compatibility. Do not include `.ttml`
in durable sidecar discovery or sidecar classification.

## Consequences

- TTML upgrades and WhisperX output use the same JSON filesystem contract.
- Media rescans rediscover timed lyrics through the existing `.json` path.
- A failed or invalid TTML conversion rejects only that save request; no XML
  sidecar is left behind.
- Existing legacy `.ttml` files are no longer considered canonical scan
  sidecars and should be re-imported or converted to JSON.
