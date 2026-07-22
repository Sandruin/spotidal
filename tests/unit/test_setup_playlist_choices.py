from spotidal.setup import _build_playlist_choices
from spotidal.type.models import Playlist


def _pl(provider_id, name):
    return Playlist(provider_id=provider_id, name=name, description="")


def test_existing_playlists_are_pre_checked_by_name():
    spotify_playlists = [_pl("sp-1", "Chill"), _pl("sp-2", "New Playlist")]
    tidal_playlists = [_pl("td-1", "Chill"), _pl("td-2", "New Playlist")]
    existing = [{"name": "Chill", "spotify_id": "sp-1", "tidal_id": "td-1"}]

    choices = _build_playlist_choices(
        spotify_playlists, tidal_playlists, "two-way", "spotify-to-tidal", existing,
    )

    by_name = {c["name"]: c for c in choices}
    chill = next(c for name, c in by_name.items() if name.startswith("Chill"))
    new = next(c for name, c in by_name.items() if name.startswith("New Playlist"))

    assert chill["enabled"] is True
    assert "already synced" in chill["name"]
    assert new["enabled"] is False
    assert "already synced" not in new["name"]


def test_new_tidal_only_playlist_is_not_pre_checked():
    spotify_playlists = [_pl("sp-1", "Chill")]
    tidal_playlists = [_pl("td-1", "Chill"), _pl("td-9", "Brand New Tidal Playlist")]
    existing = [{"name": "Chill", "spotify_id": "sp-1", "tidal_id": "td-1"}]

    choices = _build_playlist_choices(
        spotify_playlists, tidal_playlists, "two-way", "spotify-to-tidal", existing,
    )

    brand_new = next(c for c in choices if c["name"].startswith("Brand New Tidal Playlist"))
    assert brand_new["enabled"] is False
    assert "Tidal only" in brand_new["name"]


def test_existing_playlist_matched_by_id_when_renamed():
    # Simulates the config having a name recorded, but the live playlist name changed;
    # provider IDs still match so it should stay pre-checked.
    spotify_playlists = [_pl("sp-1", "Chill Vibes Renamed")]
    tidal_playlists = [_pl("td-1", "Chill Vibes Renamed")]
    existing = [{"name": "Chill", "spotify_id": "sp-1", "tidal_id": "td-1"}]

    choices = _build_playlist_choices(
        spotify_playlists, tidal_playlists, "two-way", "spotify-to-tidal", existing,
    )

    assert choices[0]["enabled"] is True
