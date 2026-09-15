# ADR-001: Keep lyrics contracts, providers, and orchestration separate

## Status

Accepted

## Context

The modular lyrics-provider refactor introduced shared types, an inference module,
built-in provider implementations, and a custom-provider loader. The old
implementations remained in `services/lyrics_service.py`, so the service could
construct a legacy `LyricsPayload` while modular providers returned
`services.lyrics_types.LyricsPayload`.

## Decision

Use `services/lyrics_types.py` as the single source of truth for
`InferredSong`, `LyricsPayload`, and the provider protocols. Keep metadata
inference in `lyrics_inference.py`, built-in network providers in
`lyrics_providers.py`, custom loading in `lyrics_provider_loader.py`, and
`lyrics_service.py` limited to provider orchestration and cue/sidecar parsing.

Resolution remains Musixmatch-first, but a result is accepted only when its
returned track title and artist confidently match the requested metadata. The
provider uses Musixmatch's app-mobile endpoint and mobile client headers; a
configured token that is incompatible or expired is replaced with a short-lived
mobile token and reused in-process until the API rejects it. If Musixmatch does
not resolve matching lyrics, NetEase, LRCLib, and loaded custom providers run
concurrently and the highest-scoring normalized payload is selected. Plain
string results from custom providers are normalized into the shared
`LyricsPayload` type.

The service continues to import and expose the shared contracts and provider
classes through its module namespace so existing consumers do not need to
change imports immediately.

## Consequences

- There is one runtime payload class, avoiding `isinstance` mismatches between
  built-in and custom-provider results.
- Provider implementations can evolve without growing the orchestration module.
- Existing route, CLI, and service imports of `services.lyrics_service` remain
  compatible.
- New provider behavior should be tested in `lyrics_providers.py` or through
  the service orchestration tests, not added to the orchestration module.
