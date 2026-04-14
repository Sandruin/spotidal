import asyncio

from spotidal import sync as _sync
from spotidal.cache import MatchFailureDatabase, SyncSnapshotDatabase, TrackMatchCache
from spotidal.config import backfill_playlist_ids, build_runtime_config, save_config
from spotidal.providers.spotify import SpotifyProvider
from spotidal.providers.tidal import TidalProvider
from spotidal.type.config import AppConfig, PlaylistEntry


def run_sync(config: AppConfig, config_path: str):
    """Execute sync based on saved configuration (non-interactive)."""
    spotify = SpotifyProvider.from_config(config["spotify"])
    tidal = TidalProvider.from_config()
    failure_cache = MatchFailureDatabase()
    runtime_config = build_runtime_config(config)
    sync_config = config["sync"]

    pairs = _build_playlist_pairs(config["sync"]["playlists"], spotify, tidal)

    if sync_config["mode"] == "two-way":
        snapshot_db = SyncSnapshotDatabase()
        if pairs:
            _sync.sync_playlists_bidirectional_wrapper(
                spotify, tidal, pairs, failure_cache, snapshot_db, runtime_config,
            )
        if sync_config["favorites"]:
            _sync.sync_favorites_bidirectional_wrapper(
                spotify, tidal, failure_cache, snapshot_db, runtime_config,
            )
    else:
        direction = sync_config["direction"]
        if direction == "tidal-to-spotify":
            source, dest = tidal, spotify
            pairs = [(td, sp) for sp, td in pairs]
        else:
            source, dest = spotify, tidal
        cache = TrackMatchCache()
        if pairs:
            _sync.sync_playlists_wrapper(source, dest, pairs, cache, failure_cache, runtime_config)
        if sync_config["favorites"]:
            _sync.sync_favorites_wrapper(source, dest, cache, failure_cache, runtime_config)

    backfill_playlist_ids(config, spotify, tidal, config_path)


def run_oneshot(config: AppConfig | None, config_path: str):
    """Interactive one-shot sync: prompt for everything, run once, don't save sync selections."""
    from spotidal.setup import (
        authenticate_spotify,
        authenticate_tidal,
        prompt_allow_deletions,
        prompt_direction,
        prompt_favorites,
        prompt_playlists,
        prompt_spotify_credentials,
        prompt_sync_mode,
    )

    # Auth: use existing creds or prompt and persist them
    if config and config.get("spotify"):
        spotify_config = config["spotify"]
    else:
        spotify_config = prompt_spotify_credentials(None)

    spotify = authenticate_spotify(spotify_config)
    tidal = authenticate_tidal()

    # Persist creds if they weren't saved yet
    if not config or not config.get("spotify"):
        if not config:
            config = {
                "config_version": 2,
                "spotify": spotify_config,
                "sync": {
                    "mode": "two-way",
                    "direction": "spotify-to-tidal",
                    "favorites": True,
                    "allow_deletions": False,
                    "playlists": [],
                },
                "max_concurrency": 10,
                "rate_limit": 10,
            }
        else:
            config["spotify"] = spotify_config
        save_config(config, config_path)

    # Prompt sync choices (ephemeral - not saved to config)
    mode = prompt_sync_mode(None)
    direction = prompt_direction(None) if mode == "one-way" else "spotify-to-tidal"
    playlists = prompt_playlists(spotify, tidal, mode, direction, [])
    favorites = prompt_favorites(None)
    allow_deletions = prompt_allow_deletions(None) if mode == "two-way" else False

    runtime_config = build_runtime_config(config)
    runtime_config["allow_deletions"] = allow_deletions
    failure_cache = MatchFailureDatabase()

    pairs = _build_playlist_pairs(playlists, spotify, tidal)

    if mode == "two-way":
        snapshot_db = SyncSnapshotDatabase()
        if pairs:
            _sync.sync_playlists_bidirectional_wrapper(
                spotify, tidal, pairs, failure_cache, snapshot_db, runtime_config,
            )
        if favorites:
            _sync.sync_favorites_bidirectional_wrapper(
                spotify, tidal, failure_cache, snapshot_db, runtime_config,
            )
    else:
        if direction == "tidal-to-spotify":
            source, dest = tidal, spotify
            pairs = [(td, sp) for sp, td in pairs]
        else:
            source, dest = spotify, tidal
        cache = TrackMatchCache()
        if pairs:
            _sync.sync_playlists_wrapper(source, dest, pairs, cache, failure_cache, runtime_config)
        if favorites:
            _sync.sync_favorites_wrapper(source, dest, cache, failure_cache, runtime_config)


def _build_playlist_pairs(
    entries: list[PlaylistEntry],
    spotify: SpotifyProvider,
    tidal: TidalProvider,
) -> list[tuple]:
    """Resolve playlist entries into (SpotifyPlaylist, TidalPlaylist|None) pairs."""
    pairs = []
    for entry in entries:
        spotify_id = entry.get("spotify_id")
        tidal_id = entry.get("tidal_id")

        try:
            sp_playlist = asyncio.run(spotify.get_playlist_by_id(spotify_id)) if spotify_id else None
            td_playlist = asyncio.run(tidal.get_playlist_by_id(tidal_id)) if tidal_id else None
        except Exception as e:
            name = entry.get("name", spotify_id or tidal_id)
            print(f"Warning: could not load playlist '{name}': {e}. Skipping.")
            continue

        pairs.append((sp_playlist, td_playlist))

    return pairs
