import asyncio
import math

import spotipy
from tqdm.asyncio import tqdm as atqdm

from spotify_to_tidal.type.models import Album, Artist, Playlist, Track


class SpotifyProvider:
    def __init__(self, session: spotipy.Spotify):
        self._session = session
        self._user_id: str | None = None

    @property
    def name(self) -> str:
        return 'Spotify'

    def _get_user_id(self) -> str:
        if self._user_id is None:
            self._user_id = self._session.current_user()['id']
        return self._user_id

    @staticmethod
    def _normalize_track(raw: dict) -> Track:
        album_raw = raw.get('album', {})
        return Track(
            provider_id=raw['id'],
            name=raw['name'],
            artists=[Artist(name=a['name']) for a in raw.get('artists', [])],
            album=Album(
                name=album_raw.get('name', ''),
                artists=[Artist(name=a['name']) for a in album_raw.get('artists', [])],
            ),
            isrc=raw.get('external_ids', {}).get('isrc'),
            duration_s=raw['duration_ms'] / 1000,
            track_number=raw.get('track_number', 0),
            version=None,
            available=True,
        )

    @staticmethod
    def _normalize_playlist(raw: dict) -> Playlist:
        return Playlist(
            provider_id=raw['id'],
            name=raw['name'],
            description=raw.get('description', ''),
        )

    async def _fetch_all_paginated(self, fetch_function) -> list[dict]:
        output = []
        results = fetch_function(0)
        output.extend([item['track'] for item in results['items'] if item['track'] is not None])

        if results['next']:
            offsets = [results['limit'] * n for n in range(1, math.ceil(results['total'] / results['limit']))]
            extra_results = await atqdm.gather(
                *[asyncio.to_thread(fetch_function, offset) for offset in offsets],
                desc="Fetching additional data chunks"
            )
            for extra_result in extra_results:
                output.extend([item['track'] for item in extra_result['items'] if item['track'] is not None])

        return output

    async def get_playlists(self, exclude_ids: set[str] | None = None) -> list[Playlist]:
        exclude_ids = exclude_ids or set()
        user_id = self._get_user_id()

        playlists = []
        print("Loading Spotify playlists")
        first_results = self._session.current_user_playlists()
        playlists.extend(first_results['items'])

        if first_results['next']:
            offsets = [first_results['limit'] * n for n in range(1, math.ceil(first_results['total'] / first_results['limit']))]
            extra_results = await atqdm.gather(
                *[asyncio.to_thread(self._session.current_user_playlists, offset=offset) for offset in offsets]
            )
            for extra_result in extra_results:
                playlists.extend(extra_result['items'])

        return [
            self._normalize_playlist(p) for p in playlists
            if p and p['owner']['id'] == user_id and p['id'] not in exclude_ids
        ]

    async def get_playlist_tracks(self, playlist: Playlist) -> list[Track]:
        fields = "next,total,limit,items(track(name,album(name,artists),artists,track_number,duration_ms,id,external_ids(isrc))),type"

        def _fetch(offset: int):
            return self._session.playlist_tracks(playlist_id=playlist.provider_id, fields=fields, offset=offset)

        print(f"Loading tracks from Spotify playlist '{playlist.name}'")
        raw_tracks = await self._fetch_all_paginated(_fetch)

        def _is_valid(item: dict) -> bool:
            return (
                item.get('type', 'track') == 'track'
                and 'album' in item
                and 'name' in item['album']
                and 'artists' in item['album']
                and len(item['album']['artists']) > 0
                and item['album']['artists'][0]['name'] is not None
            )

        return [self._normalize_track(t) for t in raw_tracks if _is_valid(t)]

    async def get_favorite_tracks(self) -> list[Track]:
        def _fetch(offset: int):
            return self._session.current_user_saved_tracks(offset=offset)

        print("Loading favorite tracks from Spotify")
        raw_tracks = await self._fetch_all_paginated(_fetch)
        raw_tracks.reverse()
        return [self._normalize_track(t) for t in raw_tracks]

    async def get_playlist_by_id(self, playlist_id: str) -> Playlist:
        raw = self._session.playlist(playlist_id=playlist_id)
        return self._normalize_playlist(raw)
