import asyncio
import shutil

import yaml

from spotidal.providers.spotify import SpotifyProvider
from spotidal.providers.tidal import TidalProvider
from spotidal.type.config import AppConfig, RuntimeConfig


def load_config(config_path: str) -> AppConfig | None:
    """Load and return config, or None if file doesn't exist."""
    try:
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        return None

    if raw is None:
        return None

    if "config_version" not in raw:
        raw = _migrate_v1_config(raw, config_path)

    return raw


def save_config(config: AppConfig, config_path: str):
    """Write the config to a YAML file."""
    data = {
        "config_version": config["config_version"],
        "spotify": dict(config["spotify"]),
        "sync": {
            "mode": config["sync"]["mode"],
            "direction": config["sync"]["direction"],
            "favorites": config["sync"]["favorites"],
            "allow_deletions": config["sync"]["allow_deletions"],
            "playlists": [dict(p) for p in config["sync"]["playlists"]],
        },
        "max_concurrency": config["max_concurrency"],
        "rate_limit": config["rate_limit"],
    }
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"Configuration saved to {config_path}")


def build_runtime_config(config: AppConfig) -> RuntimeConfig:
    """Build the runtime config dict that sync functions expect."""
    return RuntimeConfig(
        allow_deletions=config["sync"]["allow_deletions"],
        max_concurrency=config.get("max_concurrency", 10),
        rate_limit=config.get("rate_limit", 10),
    )


def backfill_playlist_ids(
    config: AppConfig,
    spotify: SpotifyProvider,
    tidal: TidalProvider,
    config_path: str,
):
    """After sync, look up IDs for any playlists that were created and save them to config."""
    entries = config["sync"]["playlists"]
    needs_spotify = any(not e.get("spotify_id") for e in entries)
    needs_tidal = any(not e.get("tidal_id") for e in entries)

    if not needs_spotify and not needs_tidal:
        return

    spotify_by_name = {}
    tidal_by_name = {}

    if needs_spotify:
        spotify_playlists = asyncio.run(spotify.get_playlists())
        spotify_by_name = {p.name: p for p in spotify_playlists}

    if needs_tidal:
        tidal_playlists = asyncio.run(tidal.get_playlists())
        tidal_by_name = {p.name: p for p in tidal_playlists}

    updated = False
    for entry in entries:
        name = entry.get("name")
        if not name:
            continue
        if not entry.get("spotify_id") and name in spotify_by_name:
            entry["spotify_id"] = spotify_by_name[name].provider_id
            print(f"Saved Spotify ID for '{name}' to config")
            updated = True
        if not entry.get("tidal_id") and name in tidal_by_name:
            entry["tidal_id"] = tidal_by_name[name].provider_id
            print(f"Saved Tidal ID for '{name}' to config")
            updated = True

    if updated:
        save_config(config, config_path)


def _migrate_v1_config(old: dict, config_path: str) -> AppConfig:
    """Migrate v1 config (no config_version) to v2 format."""
    playlists = []
    for item in old.get("sync_playlists") or []:
        playlists.append({
            "name": None,
            "spotify_id": item.get("spotify_id", ""),
            "tidal_id": item.get("tidal_id"),
        })

    new_config = {
        "config_version": 2,
        "spotify": old["spotify"],
        "sync": {
            "mode": "one-way",
            "direction": "spotify-to-tidal",
            "favorites": old.get("sync_favorites_default", True),
            "allow_deletions": False,
            "playlists": playlists,
        },
        "max_concurrency": old.get("max_concurrency", 10),
        "rate_limit": old.get("rate_limit", 10),
    }

    backup_path = config_path + ".v1.bak"
    shutil.copy2(config_path, backup_path)
    print(f"Migrated config to v2 format. Old config backed up to {backup_path}")

    with open(config_path, "w") as f:
        yaml.dump(new_config, f, default_flow_style=False, sort_keys=False)

    return new_config
