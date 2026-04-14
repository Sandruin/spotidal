import asyncio
import math
import sys
import time
import traceback

import requests
import spotipy
from tqdm import tqdm
from tqdm.asyncio import tqdm as atqdm

from spotidal.match import match, simple
from spotidal.type.models import Album, Artist, Playlist, Track

SPOTIFY_SCOPES = 'playlist-read-private, playlist-modify-private, playlist-modify-public, user-library-read, user-library-modify'


class SpotifyProvider:
    def __init__(self, session: spotipy.Spotify):
        self._session = session
        self._user_id: str | None = None

    @classmethod
    def from_config(cls, config: dict) -> 'SpotifyProvider':
        print("Opening Spotify session")
        credentials_manager = spotipy.SpotifyOAuth(
            username=config['username'],
            scope=SPOTIFY_SCOPES,
            client_id=config['client_id'],
            client_secret=config['client_secret'],
            redirect_uri=config['redirect_uri'],
            requests_timeout=2,
            open_browser=config.get('open_browser', True),
        )
        try:
            credentials_manager.get_access_token(as_dict=False)
        except spotipy.SpotifyOauthError:
            sys.exit(f"Error opening Spotify session; could not get token for username: {config['username']}")
        return cls(spotipy.Spotify(oauth_manager=credentials_manager))

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

    # -- WriteProvider implementation --

    async def _repeat_on_request_error(self, function, *args, remaining=5, **kwargs):
        try:
            return await function(*args, **kwargs)
        except (spotipy.exceptions.SpotifyException, requests.exceptions.RequestException) as e:
            if remaining:
                print(f"{str(e)} occurred, retrying {remaining} times")
            else:
                print(f"{str(e)} could not be recovered")

            if isinstance(e, requests.exceptions.RequestException) and e.response is not None:
                print(f"Response message: {e.response.text}")
                print(f"Response headers: {e.response.headers}")

            if not remaining:
                print("Aborting sync")
                print(f"The following arguments were provided:\n\n {str(args)}")
                print(traceback.format_exc())
                sys.exit(1)
            sleep_schedule = {5: 1, 4: 10, 3: 60, 2: 5 * 60, 1: 10 * 60}
            time.sleep(sleep_schedule.get(remaining, 1))
            return await self._repeat_on_request_error(function, *args, remaining=remaining - 1, **kwargs)

    async def search_track(self, source_track: Track) -> Track | None:
        """Search Spotify for a track matching the source track."""
        def _search():
            query = simple(source_track.name) + ' ' + simple(source_track.artists[0].name)
            results = self._session.search(q=query, type='track', limit=10)
            for item in results['tracks']['items']:
                normalized = self._normalize_track(item)
                if match(normalized, source_track):
                    return normalized
            return None

        return await asyncio.to_thread(_search)

    async def create_playlist(self, name: str, description: str) -> Playlist:
        raw = self._session.user_playlist_create(self._get_user_id(), name, public=False, description=description)
        return self._normalize_playlist(raw)

    async def add_tracks_to_playlist(self, playlist: Playlist, track_ids: list[str]) -> None:
        uris = [f'spotify:track:{tid}' for tid in track_ids]
        offset = 0
        chunk_size = 100
        with tqdm(desc="Adding new tracks to Spotify playlist", total=len(uris)) as progress:
            while offset < len(uris):
                count = min(chunk_size, len(uris) - offset)
                self._session.playlist_add_items(playlist.provider_id, uris[offset:offset + chunk_size])
                offset += count
                progress.update(count)

    async def clear_playlist(self, playlist: Playlist) -> None:
        self._session.playlist_replace_items(playlist.provider_id, [])

    async def add_favorite_track(self, track_id: str) -> None:
        self._session.current_user_saved_tracks_add(tracks=[track_id])

    async def remove_tracks_from_playlist(self, playlist: Playlist, track_ids: list[str]) -> None:
        uris = [f'spotify:track:{tid}' for tid in track_ids]
        # Spotify allows removing up to 100 tracks per call
        for i in range(0, len(uris), 100):
            self._session.playlist_remove_all_occurrences_of_items(playlist.provider_id, uris[i:i + 100])

    async def remove_favorite_track(self, track_id: str) -> None:
        self._session.current_user_saved_tracks_delete(tracks=[track_id])
