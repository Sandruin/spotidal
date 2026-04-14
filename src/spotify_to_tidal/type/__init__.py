from spotify_to_tidal.type.config import SpotifyConfig, TidalConfig, PlaylistConfig, SyncConfig
from spotify_to_tidal.type.models import Album, Artist, Playlist, Track
from spotify_to_tidal.type.spotify import SpotifyTrack

from spotipy import Spotify
from tidalapi import Session

TidalID = str
SpotifyID = str
TidalSession = Session
SpotifySession = Spotify

__all__ = [
    "Album",
    "Artist",
    "Playlist",
    "Track",
    "SpotifyConfig",
    "TidalConfig",
    "PlaylistConfig",
    "SyncConfig",
    "TidalID",
    "SpotifyID",
    "SpotifySession",
    "TidalSession",
    "SpotifyTrack",
]
