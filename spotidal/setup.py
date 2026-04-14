import asyncio

from InquirerPy import inquirer

from spotidal.config import save_config
from spotidal.providers.spotify import SpotifyProvider
from spotidal.providers.tidal import TidalProvider
from spotidal.type.config import AppConfig, PlaylistEntry, SpotifyConfig, SyncConfig


def prompt_spotify_credentials(existing: SpotifyConfig | None) -> SpotifyConfig:
    print("\n=== Spotify Setup ===")
    print("Create API credentials at: https://developer.spotify.com/dashboard\n")

    client_id = inquirer.text(
        message="Client ID:",
        default=existing["client_id"] if existing else "",
    ).execute()

    client_secret = inquirer.text(
        message="Client Secret:",
        default=existing["client_secret"] if existing else "",
    ).execute()

    username = inquirer.text(
        message="Username:",
        default=existing["username"] if existing else "",
    ).execute()

    redirect_uri = inquirer.text(
        message="Redirect URI:",
        default=existing["redirect_uri"] if existing else "http://127.0.0.1:8888/callback",
    ).execute()

    return SpotifyConfig(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        redirect_uri=redirect_uri,
    )


def authenticate_spotify(spotify_config: SpotifyConfig) -> SpotifyProvider:
    """Authenticate with Spotify, re-prompting on failure."""
    while True:
        try:
            provider = SpotifyProvider.from_config(spotify_config)
            print("Connected to Spotify.\n")
            return provider
        except SystemExit:
            print("Authentication failed. Please check your credentials.\n")
            spotify_config = prompt_spotify_credentials(spotify_config)


def authenticate_tidal() -> TidalProvider:
    print("\n=== Tidal Setup ===")
    provider = TidalProvider.from_config()
    print("Connected to Tidal.\n")
    return provider


def prompt_sync_mode(existing: SyncConfig | None) -> str:
    default_mode = existing["mode"] if existing else "two-way"

    mode = inquirer.select(
        message="Sync mode:",
        choices=[
            {"name": "Two-way (keep both services in sync)", "value": "two-way"},
            {"name": "One-way (mirror from one service to the other)", "value": "one-way"},
        ],
        default="two-way" if default_mode == "two-way" else "one-way",
    ).execute()

    return mode


def prompt_direction(existing: SyncConfig | None) -> str:
    default_dir = existing["direction"] if existing else "spotify-to-tidal"

    direction = inquirer.select(
        message="Direction:",
        choices=[
            {"name": "Spotify -> Tidal", "value": "spotify-to-tidal"},
            {"name": "Tidal -> Spotify", "value": "tidal-to-spotify"},
        ],
        default=default_dir,
    ).execute()

    return direction


def _build_playlist_choices(
    spotify_playlists: list,
    tidal_playlists: list,
    mode: str,
    direction: str,
    existing_playlists: list[PlaylistEntry],
) -> tuple[list[dict], list[str]]:
    """Build unified playlist choices and list of pre-selected values.

    Returns (choices, default_values) where default_values are the 'value' strings
    of playlists that should be pre-checked.
    """
    # Index playlists by name
    spotify_by_name = {p.name: p for p in spotify_playlists}
    tidal_by_name = {p.name: p for p in tidal_playlists}
    all_names = sorted(set(spotify_by_name.keys()) | set(tidal_by_name.keys()))

    # Build set of previously selected playlist names for defaults
    existing_names = {e["name"] for e in existing_playlists if e.get("name")}
    # Also match by IDs for unnamed entries
    existing_spotify_ids = {e["spotify_id"] for e in existing_playlists if e.get("spotify_id")}
    existing_tidal_ids = {e["tidal_id"] for e in existing_playlists if e.get("tidal_id")}

    choices = []
    defaults = []

    for name in all_names:
        sp = spotify_by_name.get(name)
        td = tidal_by_name.get(name)

        # For one-way mode, only show source-side playlists
        if mode == "one-way":
            if direction == "spotify-to-tidal" and not sp:
                continue
            if direction == "tidal-to-spotify" and not td:
                continue

        # Build label annotation
        if sp and td:
            annotation = "on both"
        elif sp:
            annotation = "Spotify only"
        else:
            annotation = "Tidal only"

        # Value encodes both IDs for later extraction
        value = f"{sp.provider_id if sp else ''}|{td.provider_id if td else ''}|{name}"
        label = f"{name}  ({annotation})"

        choices.append({"name": label, "value": value})

        # Check if this was previously selected
        is_selected = (
            name in existing_names
            or (sp and sp.provider_id in existing_spotify_ids)
            or (td and td.provider_id in existing_tidal_ids)
        )
        if is_selected:
            defaults.append(value)

    return choices, defaults


def _parse_playlist_value(value: str) -> PlaylistEntry:
    """Parse an encoded playlist value back into a PlaylistEntry."""
    spotify_id, tidal_id, name = value.split("|", 2)
    return PlaylistEntry(
        name=name,
        spotify_id=spotify_id or None,
        tidal_id=tidal_id or None,
    )


def prompt_playlists(
    spotify: SpotifyProvider,
    tidal: TidalProvider,
    mode: str,
    direction: str,
    existing_playlists: list[PlaylistEntry],
) -> list[PlaylistEntry]:
    print("Loading playlists...")
    spotify_playlists = asyncio.run(spotify.get_playlists())
    tidal_playlists = asyncio.run(tidal.get_playlists())
    print(f"Found {len(spotify_playlists)} Spotify playlists, {len(tidal_playlists)} Tidal playlists.\n")

    choices, defaults = _build_playlist_choices(
        spotify_playlists, tidal_playlists, mode, direction, existing_playlists,
    )

    if not choices:
        print("No playlists found on either service.\n")
        return []

    selected = inquirer.checkbox(
        message="Select playlists to sync:",
        choices=choices,
        default=defaults,
        instruction="(Space to toggle, Enter to confirm)",
    ).execute()

    return [_parse_playlist_value(v) for v in selected]


def prompt_favorites(existing: SyncConfig | None) -> bool:
    default = existing["favorites"] if existing else False
    return inquirer.confirm(
        message="Sync favorites/liked songs?",
        default=default,
    ).execute()


def prompt_allow_deletions(existing: SyncConfig | None) -> bool:
    default = existing["allow_deletions"] if existing else False
    return inquirer.confirm(
        message="Allow deletion propagation?\n  (Removing a track on one side will remove it from the other)",
        default=default,
    ).execute()


def _print_summary(sync_config: SyncConfig):
    mode_label = "Two-way sync" if sync_config["mode"] == "two-way" else f"One-way ({sync_config['direction']})"
    print(f"\n=== Summary ===")
    print(f"  Mode:       {mode_label}")
    print(f"  Favorites:  {'Yes' if sync_config['favorites'] else 'No'}")
    if sync_config["mode"] == "two-way":
        print(f"  Deletions:  {'Yes' if sync_config['allow_deletions'] else 'No'}")
    print(f"  Playlists:  {len(sync_config['playlists'])} selected")
    for p in sync_config["playlists"]:
        print(f"    - {p['name']}")
    print()


def _prompt_save_action() -> str:
    return inquirer.select(
        message="What next?",
        choices=[
            {"name": "Save and run sync now", "value": "save_and_run"},
            {"name": "Save configuration only", "value": "save_only"},
            {"name": "Cancel without saving", "value": "cancel"},
        ],
    ).execute()


def run_wizard(
    existing_config: AppConfig | None,
    config_path: str,
) -> tuple[AppConfig, str]:
    """Run the interactive setup wizard.

    Returns (config, action) where action is "save_and_run", "save_only", or "cancel".
    """
    existing_spotify = existing_config["spotify"] if existing_config else None
    existing_sync = existing_config["sync"] if existing_config else None

    # Screen 1: Spotify credentials
    spotify_config = prompt_spotify_credentials(existing_spotify)
    spotify = authenticate_spotify(spotify_config)

    # Screen 2: Tidal authentication
    tidal = authenticate_tidal()

    # Screen 3: Sync mode
    mode = prompt_sync_mode(existing_sync)

    # Screen 3a: Direction (one-way only)
    if mode == "one-way":
        direction = prompt_direction(existing_sync)
    else:
        direction = existing_sync["direction"] if existing_sync else "spotify-to-tidal"

    # Screen 4: Playlist selection
    existing_playlists = existing_sync["playlists"] if existing_sync else []
    playlists = prompt_playlists(spotify, tidal, mode, direction, existing_playlists)

    # Screen 5: Favorites
    favorites = prompt_favorites(existing_sync)

    # Screen 6: Deletion behavior (two-way only)
    if mode == "two-way":
        allow_deletions = prompt_allow_deletions(existing_sync)
    else:
        allow_deletions = existing_sync["allow_deletions"] if existing_sync else False

    sync_config = SyncConfig(
        mode=mode,
        direction=direction,
        favorites=favorites,
        allow_deletions=allow_deletions,
        playlists=playlists,
    )

    config = AppConfig(
        config_version=2,
        spotify=spotify_config,
        sync=sync_config,
        max_concurrency=existing_config["max_concurrency"] if existing_config else 10,
        rate_limit=existing_config["rate_limit"] if existing_config else 10,
    )

    # Screen 7: Summary & save action
    _print_summary(sync_config)
    action = _prompt_save_action()

    if action != "cancel":
        save_config(config, config_path)

    return config, action
