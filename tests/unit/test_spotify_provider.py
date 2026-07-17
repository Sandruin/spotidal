import asyncio

from spotidal.providers.spotify import SpotifyProvider
from spotidal.type.models import Playlist


def _spotify_track(track_id="track-1"):
    return {
        "id": track_id,
        "name": "Song",
        "artists": [{"name": "Artist"}],
        "album": {
            "name": "Album",
            "artists": [{"name": "Album Artist"}],
        },
        "external_ids": {"isrc": "ABC123"},
        "duration_ms": 180000,
        "track_number": 1,
        "type": "track",
    }


def test_extract_tracks_skips_items_without_track_key():
    items = [
        {"track": _spotify_track("valid")},
        {"item": _spotify_track("new-shape")},
        {"added_at": "2026-01-01T00:00:00Z"},
        {"track": None},
    ]

    assert SpotifyProvider._extract_tracks(items) == [
        _spotify_track("valid"),
        _spotify_track("new-shape"),
    ]


def test_get_playlist_tracks_skips_incomplete_spotify_items():
    session = _SessionStub(
        {
            "items": [
                {"track": _spotify_track("valid")},
                {"track": {**_spotify_track("missing-id"), "id": None}},
            ],
            "next": None,
            "limit": 100,
            "total": 2,
        }
    )
    provider = SpotifyProvider(session)

    tracks = asyncio.run(provider.get_playlist_tracks(Playlist("playlist-1", "Playlist", "")))

    assert [track.provider_id for track in tracks] == ["valid"]


class _SessionStub:
    def __init__(self, playlist_tracks_response):
        self._playlist_tracks_response = playlist_tracks_response

    def playlist_tracks(self, **kwargs):
        return self._playlist_tracks_response
