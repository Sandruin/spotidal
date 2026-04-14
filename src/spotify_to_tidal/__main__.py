import asyncio
import yaml
import argparse
import sys

from spotify_to_tidal import sync as _sync
from spotify_to_tidal.cache import MatchFailureDatabase, TrackMatchCache
from spotify_to_tidal.providers.spotify import SpotifyProvider
from spotify_to_tidal.providers.tidal import TidalProvider

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.yml', help='location of the config file')
    parser.add_argument('--uri', help='synchronize a specific URI instead of the one in the config')
    parser.add_argument('--sync-favorites', action=argparse.BooleanOptionalAction, help='synchronize the favorites')
    parser.add_argument('--reverse', action='store_true', help='sync from Tidal to Spotify instead')
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    spotify = SpotifyProvider.from_config(config['spotify'])
    tidal = TidalProvider.from_config()

    if args.reverse:
        source, dest = tidal, spotify
    else:
        source, dest = spotify, tidal

    # Remap config playlist keys to generic source_id/dest_id
    for item in config.get('sync_playlists') or []:
        if 'spotify_id' in item and 'tidal_id' in item:
            if args.reverse:
                item['source_id'], item['dest_id'] = item.pop('tidal_id'), item.pop('spotify_id')
            else:
                item['source_id'], item['dest_id'] = item.pop('spotify_id'), item.pop('tidal_id')

    cache = TrackMatchCache()
    failure_cache = MatchFailureDatabase()

    if args.uri:
        source_playlist = asyncio.run(source.get_playlist_by_id(args.uri))
        dest_playlists = _sync.get_dest_playlists(dest)
        playlist_mapping = _sync.pick_dest_playlist(source_playlist, dest_playlists)
        _sync.sync_playlists_wrapper(source, dest, [playlist_mapping], cache, failure_cache, config)
        sync_favorites = args.sync_favorites
    elif args.sync_favorites:
        sync_favorites = True
    elif config.get('sync_playlists', None):
        playlists = _sync.get_playlists_from_config(source, dest, config)
        _sync.sync_playlists_wrapper(source, dest, playlists, cache, failure_cache, config)
        sync_favorites = args.sync_favorites is None and config.get('sync_favorites_default', True)
    else:
        playlists = _sync.get_user_playlist_mappings(source, dest, config)
        _sync.sync_playlists_wrapper(source, dest, playlists, cache, failure_cache, config)
        sync_favorites = args.sync_favorites is None and config.get('sync_favorites_default', True)

    if sync_favorites:
        _sync.sync_favorites_wrapper(source, dest, cache, failure_cache, config)

if __name__ == '__main__':
    main()
    sys.exit(0)
