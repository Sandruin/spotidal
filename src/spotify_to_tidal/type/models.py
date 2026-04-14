from dataclasses import dataclass


@dataclass(frozen=True)
class Artist:
    name: str


@dataclass(frozen=True)
class Album:
    name: str
    artists: list[Artist]


@dataclass(frozen=True)
class Track:
    provider_id: str  # provider-specific ID (e.g. Spotify base62, Tidal int-as-str)
    name: str
    artists: list[Artist]
    album: Album
    isrc: str | None
    duration_s: float
    track_number: int  # position within the album (1-indexed)
    version: str | None
    available: bool


@dataclass(frozen=True)
class Playlist:
    provider_id: str
    name: str
    description: str
