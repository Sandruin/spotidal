import asyncio
from collections.abc import Sequence
import datetime

from tqdm.asyncio import tqdm as atqdm
from tqdm import tqdm

from spotify_to_tidal.cache import MatchFailureDatabase, TrackMatchCache
from spotify_to_tidal.match import match
from spotify_to_tidal.providers.base import ReadProvider, ReadWriteProvider, WriteProvider
from spotify_to_tidal.type.models import Playlist, Track


def populate_track_match_cache(
    source_tracks_: Sequence[Track],
    dest_tracks_: Sequence[Track],
    cache: TrackMatchCache,
):
    """ Populate the track match cache with existing destination tracks corresponding to source tracks """
    def _populate_from_source(source_track: Track):
        for idx, dest_track in list(enumerate(dest_tracks)):
            if dest_track.available and match(dest_track, source_track):
                cache.insert(source_track.provider_id, dest_track.provider_id)
                dest_tracks.pop(idx)
                return

    def _populate_from_dest(dest_track: Track):
        for idx, source_track in list(enumerate(source_tracks)):
            if dest_track.available and match(dest_track, source_track):
                cache.insert(source_track.provider_id, dest_track.provider_id)
                source_tracks.pop(idx)
                return

    source_tracks = list(source_tracks_)
    dest_tracks = list(dest_tracks_)

    for track in dest_tracks:
        _populate_from_dest(track)
    for track in source_tracks:
        _populate_from_source(track)


def get_new_source_tracks(
    source_tracks: Sequence[Track],
    cache: TrackMatchCache,
    failure_cache: MatchFailureDatabase,
) -> list[Track]:
    """ Extracts only the tracks that have not already been seen in our caches """
    results = []
    for track in source_tracks:
        if not track.provider_id:
            continue
        if not cache.get(track.provider_id) and not failure_cache.has_match_failure(track.provider_id):
            results.append(track)
    return results


def get_dest_track_ids(
    source_tracks: Sequence[Track],
    cache: TrackMatchCache,
) -> list[str]:
    """ Gets list of corresponding destination track ids for each source track, ignoring duplicates """
    output = []
    seen_tracks: set[str] = set()

    for track in source_tracks:
        if not track.provider_id:
            continue
        dest_id = cache.get(track.provider_id)
        if dest_id:
            if dest_id in seen_tracks:
                track_name = track.name
                artist_names = ', '.join([a.name for a in track.artists])
                print(f'Duplicate found: Track "{track_name}" by {artist_names} will be ignored')
            else:
                output.append(dest_id)
                seen_tracks.add(dest_id)
    return output


async def search_new_tracks(
    dest: WriteProvider,
    source_tracks: Sequence[Track],
    playlist_name: str,
    cache: TrackMatchCache,
    failure_cache: MatchFailureDatabase,
    config: dict,
):
    """ Search for each source track on the destination provider and add results to the cache """
    async def _run_rate_limiter(semaphore):
        """ Leaky bucket algorithm for rate limiting. Periodically releases items from semaphore at rate_limit """
        rate_limit = config.get('rate_limit', 10)
        _sleep_time = config.get('max_concurrency', 10) / rate_limit / 4
        t0 = datetime.datetime.now()
        accumulated = 0.0
        while True:
            await asyncio.sleep(_sleep_time)
            t = datetime.datetime.now()
            dt = (t - t0).total_seconds()
            t0 = t
            accumulated += rate_limit * dt
            new_items = int(accumulated)
            accumulated -= new_items
            for _ in range(new_items):
                semaphore.release()

    async def _rate_limited_search(track: Track, semaphore) -> Track | None:
        await semaphore.acquire()
        result = await dest.search_track(track)
        if result:
            failure_cache.remove_match_failure(track.provider_id)
        return result

    tracks_to_search = get_new_source_tracks(source_tracks, cache, failure_cache)
    if not tracks_to_search:
        return

    task_description = f"Searching {dest.name} for {len(tracks_to_search)}/{len(source_tracks)} tracks in playlist '{playlist_name}'"
    semaphore = asyncio.Semaphore(config.get('max_concurrency', 10))
    rate_limiter_task = asyncio.create_task(_run_rate_limiter(semaphore))
    search_results = await atqdm.gather(
        *[_rate_limited_search(t, semaphore) for t in tracks_to_search],
        desc=task_description,
    )
    rate_limiter_task.cancel()

    song404 = []
    for idx, source_track in enumerate(tracks_to_search):
        if search_results[idx]:
            cache.insert(source_track.provider_id, search_results[idx].provider_id)
        else:
            song404.append(f"{source_track.provider_id}: {','.join([a.name for a in source_track.artists])} - {source_track.name}")
            color = ('\033[91m', '\033[0m')
            print(color[0] + f"Could not find the track on {dest.name}: " + song404[-1] + color[1])
            failure_cache.cache_match_failure(source_track.provider_id)
    file_name = "songs_not_found.txt"
    header = f"==========================\nPlaylist: {playlist_name} (not found on {dest.name})\n==========================\n"
    with open(file_name, "a", encoding="utf-8") as file:
        file.write(header)
        for song in song404:
            file.write(f"{song}\n")


async def sync_playlist(
    source: ReadProvider,
    dest: ReadWriteProvider,
    source_playlist: Playlist,
    dest_playlist: Playlist | None,
    cache: TrackMatchCache,
    failure_cache: MatchFailureDatabase,
    config: dict,
):
    """ Sync a single playlist from source to destination """
    source_tracks = await source.get_playlist_tracks(source_playlist)
    if not source_tracks:
        return

    if dest_playlist:
        old_dest_tracks = await dest.get_playlist_tracks(dest_playlist)
    else:
        print(f"No playlist found on {dest.name} corresponding to '{source_playlist.name}', creating new playlist")
        dest_playlist = await dest.create_playlist(source_playlist.name, source_playlist.description)
        old_dest_tracks = []

    populate_track_match_cache(source_tracks, old_dest_tracks, cache)
    await search_new_tracks(dest, source_tracks, source_playlist.name, cache, failure_cache, config)
    new_dest_track_ids = get_dest_track_ids(source_tracks, cache)

    old_dest_track_ids = [t.provider_id for t in old_dest_tracks]
    if new_dest_track_ids == old_dest_track_ids:
        print("No changes to write to playlist")
    elif new_dest_track_ids[:len(old_dest_track_ids)] == old_dest_track_ids:
        await dest.add_tracks_to_playlist(dest_playlist, new_dest_track_ids[len(old_dest_track_ids):])
    else:
        await dest.clear_playlist(dest_playlist)
        await dest.add_tracks_to_playlist(dest_playlist, new_dest_track_ids)


async def sync_favorites(
    source: ReadProvider,
    dest: ReadWriteProvider,
    cache: TrackMatchCache,
    failure_cache: MatchFailureDatabase,
    config: dict,
):
    """ Sync user favorites from source to destination """
    source_tracks = await source.get_favorite_tracks()
    old_dest_tracks = await dest.get_favorite_tracks()

    populate_track_match_cache(source_tracks, old_dest_tracks, cache)
    await search_new_tracks(dest, source_tracks, "Favorites", cache, failure_cache, config)

    existing_dest_ids = {t.provider_id for t in old_dest_tracks}
    new_ids = []
    for track in source_tracks:
        match_id = cache.get(track.provider_id)
        if match_id and match_id not in existing_dest_ids:
            new_ids.append(match_id)

    if new_ids:
        for dest_id in tqdm(new_ids, desc=f"Adding new tracks to {dest.name} favorites"):
            await dest.add_favorite_track(dest_id)
    else:
        print(f"No new tracks to add to {dest.name} favorites")


def sync_playlists_wrapper(
    source: ReadProvider,
    dest: ReadWriteProvider,
    playlists: list[tuple[Playlist, Playlist | None]],
    cache: TrackMatchCache,
    failure_cache: MatchFailureDatabase,
    config: dict,
):
    for source_playlist, dest_playlist in playlists:
        asyncio.run(sync_playlist(source, dest, source_playlist, dest_playlist, cache, failure_cache, config))


def sync_favorites_wrapper(
    source: ReadProvider,
    dest: ReadWriteProvider,
    cache: TrackMatchCache,
    failure_cache: MatchFailureDatabase,
    config: dict,
):
    asyncio.run(sync_favorites(source=source, dest=dest, cache=cache, failure_cache=failure_cache, config=config))


def get_dest_playlists(dest: ReadProvider) -> dict[str, Playlist]:
    playlists = asyncio.run(dest.get_playlists())
    return {p.name: p for p in playlists}


def pick_dest_playlist(
    source_playlist: Playlist,
    dest_playlists: dict[str, Playlist],
) -> tuple[Playlist, Playlist | None]:
    if source_playlist.name in dest_playlists:
        return (source_playlist, dest_playlists[source_playlist.name])
    return (source_playlist, None)


def get_user_playlist_mappings(
    source: ReadProvider,
    dest: ReadProvider,
    config: dict,
) -> list[tuple[Playlist, Playlist | None]]:
    exclude_ids = {x.split(':')[-1] for x in config.get('excluded_playlists', [])}
    source_playlists = asyncio.run(source.get_playlists(exclude_ids=exclude_ids))
    dest_playlists = get_dest_playlists(dest)
    return [pick_dest_playlist(p, dest_playlists) for p in source_playlists]


def get_playlists_from_config(
    source: ReadProvider,
    dest: ReadProvider,
    config: dict,
) -> list[tuple[Playlist, Playlist | None]]:
    output = []
    for item in config['sync_playlists']:
        source_id = item['source_id']
        dest_id = item['dest_id']
        try:
            source_playlist = asyncio.run(source.get_playlist_by_id(source_id))
        except Exception as e:
            print(f"Error getting {source.name} playlist {source_id}")
            raise e
        try:
            dest_playlist = asyncio.run(dest.get_playlist_by_id(dest_id))
        except Exception as e:
            print(f"Error getting {dest.name} playlist {dest_id}")
            raise e
        output.append((source_playlist, dest_playlist))
    return output
