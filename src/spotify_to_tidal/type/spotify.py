from spotipy import Spotify
from typing import TypedDict, Literal


class SpotifyImage(TypedDict):
    url: str
    height: int
    width: int


class SpotifyFollower(TypedDict):
    href: str
    total: int


SpotifyID = str
SpotifySession = Spotify


class SpotifyArtist(TypedDict):
    external_urls: dict[str, str]
    followers: SpotifyFollower
    genres: list[str]
    href: str
    id: str
    images: list[SpotifyImage]
    name: str
    popularity: int
    type: str
    uri: str


class SpotifyAlbum(TypedDict):
    album_type: Literal["album", "single", "compilation"]
    total_tracks: int
    available_markets: list[str]
    external_urls: dict[str, str]
    href: str
    id: str
    images: list[SpotifyImage]
    name: str
    release_date: str
    release_date_precision: Literal["year", "month", "day"]
    restrictions: dict[Literal["reason"], str] | None
    type: Literal["album"]
    uri: str
    artists: list[SpotifyArtist]


class SpotifyTrack(TypedDict):
    album: SpotifyAlbum
    artists: list[SpotifyArtist]
    available_markets: list[str]
    disc_number: int
    duration_ms: int
    explicit: bool
    external_ids: dict[str, str]
    external_urls: dict[str, str]
    href: str
    id: str
    is_playable: bool
    linked_from: dict
    restrictions: dict[Literal["reason"], str] | None
    name: str
    popularity: int
    preview_url: str
    track_number: int
    type: Literal["track"]
    uri: str
