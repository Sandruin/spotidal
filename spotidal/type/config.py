from typing import TypedDict, Literal


class SpotifyConfig(TypedDict):
    client_id: str
    client_secret: str
    username: str
    redirect_uri: str


class PlaylistEntry(TypedDict):
    name: str | None
    spotify_id: str | None
    tidal_id: str | None


class SyncConfig(TypedDict):
    mode: Literal["one-way", "two-way"]
    direction: Literal["spotify-to-tidal", "tidal-to-spotify"]
    favorites: bool
    allow_deletions: bool
    playlists: list[PlaylistEntry]


class AppConfig(TypedDict):
    config_version: int
    spotify: SpotifyConfig
    sync: SyncConfig
    max_concurrency: int
    rate_limit: int


class RuntimeConfig(TypedDict):
    allow_deletions: bool
    max_concurrency: int
    rate_limit: int
