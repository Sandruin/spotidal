import asyncio
import math
import sys
import time
import traceback
import webbrowser

import requests
import tidalapi
import yaml
from tqdm import tqdm
from tqdm.asyncio import tqdm as atqdm

from spotidal.match import match, simple, test_album_similarity
from spotidal.type.models import Album, Artist, Playlist, Track


class TidalProvider:
    def __init__(self, session: tidalapi.Session):
        self._session = session

    @classmethod
    def from_config(cls, config: dict | None = None) -> 'TidalProvider':
        print("Opening Tidal session")
        try:
            with open('.session.yml', 'r') as session_file:
                previous_session = yaml.safe_load(session_file)
        except OSError:
            previous_session = None

        session = tidalapi.Session(config=config) if config else tidalapi.Session()
        if previous_session:
            try:
                if session.load_oauth_session(
                    token_type=previous_session['token_type'],
                    access_token=previous_session['access_token'],
                    refresh_token=previous_session['refresh_token'],
                ):
                    if not session.check_login():
                        sys.exit("Could not connect to Tidal")
                    return cls(session)
            except Exception as e:
                print("Error loading previous Tidal Session: \n" + str(e))

        login, future = session.login_oauth()
        print('Login with the webbrowser: ' + login.verification_uri_complete)
        url = login.verification_uri_complete
        if not url.startswith('https://'):
            url = 'https://' + url
        webbrowser.open(url)
        future.result()
        with open('.session.yml', 'w') as f:
            yaml.dump({
                'session_id': session.session_id,
                'token_type': session.token_type,
                'access_token': session.access_token,
                'refresh_token': session.refresh_token,
            }, f)
        if not session.check_login():
            sys.exit("Could not connect to Tidal")
        return cls(session)

    @property
    def name(self) -> str:
        return 'Tidal'

    @staticmethod
    def _normalize_track(t: tidalapi.Track) -> Track:
        album = t.album if t.album else None
        return Track(
            provider_id=str(t.id),
            name=t.name,
            artists=[Artist(name=a.name) for a in t.artists],
            album=Album(
                name=album.name if album else '',
                artists=[Artist(name=a.name) for a in (album.artists if album else [])],
            ),
            isrc=t.isrc,
            duration_s=t.duration,
            track_number=getattr(t, 'track_num', 0),
            version=t.version,
            available=t.available,
        )

    @staticmethod
    def _normalize_playlist(p: tidalapi.Playlist) -> Playlist:
        return Playlist(
            provider_id=str(p.id),
            name=p.name,
            description=getattr(p, 'description', '') or '',
        )

    # -- Internal pagination helper (absorbed from tidalapi_patch.py) --

    @staticmethod
    async def _get_all_chunks(url, session, parser, params=None):
        if params is None:
            params = {}

        def _make_request(offset: int = 0):
            new_params = params
            new_params['offset'] = offset
            return session.request.map_request(url, params=new_params)

        first_chunk_raw = _make_request()
        limit = first_chunk_raw['limit']
        total = first_chunk_raw['totalNumberOfItems']
        items = session.request.map_json(first_chunk_raw, parse=parser)

        if len(items) < total:
            offsets = [limit * n for n in range(1, math.ceil(total / limit))]
            extra_results = await atqdm.gather(
                *[asyncio.to_thread(lambda offset: session.request.map_json(_make_request(offset), parse=parser), offset) for offset in offsets],
                desc="Fetching additional data chunks"
            )
            for extra_result in extra_results:
                items.extend(extra_result)
        return items

    # -- Internal playlist modification helpers --

    @staticmethod
    def _remove_indices_from_playlist(playlist: tidalapi.UserPlaylist, indices):
        headers = {'If-None-Match': playlist._etag}
        index_string = ",".join(map(str, indices))
        playlist.request.request('DELETE', f'{playlist._base_url % playlist.id}/items/{index_string}', headers=headers)
        playlist._reparse()

    # -- Internal retry helper --

    async def _repeat_on_request_error(self, function, *args, remaining=5, **kwargs):
        try:
            return await function(*args, **kwargs)
        except (tidalapi.exceptions.TooManyRequests, requests.exceptions.RequestException) as e:
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

    # -- ReadProvider implementation --

    async def get_playlists(self, exclude_ids: set[str] | None = None) -> list[Playlist]:
        print("Loading playlists from Tidal user")
        params = {"limit": 10}
        raw_playlists = await self._get_all_chunks(
            f"users/{self._session.user.id}/playlists",
            session=self._session,
            parser=self._session.user.playlist.parse_factory,
            params=params,
        )
        return [self._normalize_playlist(p) for p in raw_playlists]

    async def get_playlist_tracks(self, playlist: Playlist) -> list[Track]:
        print(f"Loading tracks from Tidal playlist '{playlist.name}'")
        # Need the raw tidalapi playlist for internal API access
        raw_playlist = self._session.playlist(playlist.provider_id)
        params = {"limit": 20}
        raw_tracks = await self._get_all_chunks(
            f"{raw_playlist._base_url % raw_playlist.id}/tracks",
            session=self._session,
            parser=self._session.parse_track,
            params=params,
        )
        return [self._normalize_track(t) for t in raw_tracks]

    async def get_favorite_tracks(self) -> list[Track]:
        print("Loading existing favorite tracks from Tidal")
        favorites = self._session.user.favorites
        params = {
            "limit": 100,
            "order": "DATE",
            "orderDirection": "ASC",
        }
        raw_tracks = await self._get_all_chunks(
            f"{favorites.base_url}/tracks",
            session=self._session,
            parser=self._session.parse_track,
            params=params,
        )
        return [self._normalize_track(t) for t in raw_tracks]

    async def get_playlist_by_id(self, playlist_id: str) -> Playlist:
        raw = self._session.playlist(playlist_id=playlist_id)
        return self._normalize_playlist(raw)

    # -- WriteProvider implementation --

    async def search_track(self, source_track: Track) -> Track | None:
        """Search Tidal for a track matching the source track. Tries album search first, then standalone."""
        result = await self._search_by_album(source_track)
        if result:
            return result
        return await self._search_standalone(source_track)

    async def _search_by_album(self, source_track: Track) -> Track | None:
        def _search():
            if source_track.album and source_track.album.artists:
                query = simple(source_track.album.name) + " " + simple(source_track.album.artists[0].name)
                album_result = self._session.search(query, models=[tidalapi.album.Album])
                source_album = Album(name=source_track.album.name, artists=source_track.album.artists)
                for album in album_result['albums']:
                    tidal_album = Album(name=album.name, artists=[Artist(name=a.name) for a in album.artists])
                    if album.num_tracks >= source_track.track_number and test_album_similarity(source_album, tidal_album):
                        album_tracks = album.tracks()
                        if len(album_tracks) < source_track.track_number:
                            assert not len(album_tracks) == album.num_tracks
                            continue
                        track = album_tracks[source_track.track_number - 1]
                        normalized = self._normalize_track(track)
                        if match(normalized, source_track):
                            return normalized
            return None

        return await asyncio.to_thread(_search)

    async def _search_standalone(self, source_track: Track) -> Track | None:
        def _search():
            query = simple(source_track.name) + ' ' + simple(source_track.artists[0].name)
            for track in self._session.search(query, models=[tidalapi.media.Track])['tracks']:
                normalized = self._normalize_track(track)
                if match(normalized, source_track):
                    return normalized
            return None

        return await asyncio.to_thread(_search)

    async def create_playlist(self, name: str, description: str) -> Playlist:
        raw = self._session.user.create_playlist(name, description)
        return self._normalize_playlist(raw)

    async def add_tracks_to_playlist(self, playlist: Playlist, track_ids: list[str]) -> None:
        raw_playlist = self._session.playlist(playlist.provider_id)
        int_ids = [int(tid) for tid in track_ids]
        offset = 0
        chunk_size = 20
        with tqdm(desc="Adding new tracks to Tidal playlist", total=len(int_ids)) as progress:
            while offset < len(int_ids):
                chunk = int_ids[offset:offset + chunk_size]
                count = len(chunk)
                for attempt in range(3):
                    try:
                        raw_playlist.add(chunk)
                        break
                    except requests.exceptions.HTTPError as e:
                        if e.response is not None and e.response.status_code == 412 and attempt < 2:
                            time.sleep(1)
                            raw_playlist = self._session.playlist(playlist.provider_id)
                        else:
                            raise
                offset += count
                progress.update(count)

    async def clear_playlist(self, playlist: Playlist) -> None:
        raw_playlist = self._session.playlist(playlist.provider_id)
        chunk_size = 20
        with tqdm(desc="Erasing existing tracks from Tidal playlist", total=raw_playlist.num_tracks) as progress:
            while raw_playlist.num_tracks:
                indices = range(min(raw_playlist.num_tracks, chunk_size))
                self._remove_indices_from_playlist(raw_playlist, indices)
                progress.update(len(indices))

    async def add_favorite_track(self, track_id: str) -> None:
        self._session.user.favorites.add_track(int(track_id))

    async def remove_tracks_from_playlist(self, playlist: Playlist, track_ids: list[str]) -> None:
        raw_playlist = self._session.playlist(playlist.provider_id)
        track_id_set = set(track_ids)
        # Find indices of tracks to remove by matching IDs
        all_tracks = raw_playlist.tracks()
        indices_to_remove = [i for i, t in enumerate(all_tracks) if str(t.id) in track_id_set]
        if indices_to_remove:
            # Remove in chunks from end to start so indices stay valid
            chunk_size = 20
            for i in range(0, len(indices_to_remove), chunk_size):
                self._remove_indices_from_playlist(raw_playlist, indices_to_remove[i:i + chunk_size])

    async def remove_favorite_track(self, track_id: str) -> None:
        self._session.user.favorites.remove_track(int(track_id))
