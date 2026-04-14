from spotify_to_tidal.type.config import SpotifyConfig, TidalConfig, PlaylistConfig, SyncConfig
from spotify_to_tidal.type.spotify import SpotifyTrack

from spotipy import Spotify
from tidalapi import Session, Track

TidalID = str
SpotifyID = str
TidalSession = Session
TidalTrack = Track
SpotifySession = Spotify

__all__ = [
    "SpotifyConfig",
    "TidalConfig",
    "PlaylistConfig",
    "SyncConfig",
    "TidalPlaylist",
    "TidalID",
    "SpotifyID",
    "SpotifySession",
    "TidalSession",
    "TidalTrack",
    "SpotifyTrack",
]
