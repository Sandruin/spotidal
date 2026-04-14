A command line tool for syncing playlists between Spotify and Tidal. Due to various performance optimisations, it is particularly suited for periodic synchronisation of very large collections.

Installation
-----------
Clone this git repository and then run:

```bash
python3 -m pip install -e .
```

Setup
-----
0. Rename the file example_config.yml to config.yml
0. Go [here](https://developer.spotify.com/documentation/general/guides/authorization/app-settings/) and register a new app on developer.spotify.com.
0. Copy and paste your client ID and client secret to the Spotify part of the config file
0. Copy and paste the value in 'redirect_uri' of the config file to Redirect URIs at developer.spotify.com and press ADD
0. Enter your Spotify username to the config file

Usage
----

### One-way sync (default)

Mirrors playlists from Spotify to Tidal:

```bash
spotify_to_tidal
```

Sync a specific playlist:

```bash
spotify_to_tidal --uri 1ABCDEqsABCD6EaABCDa0a # accepts playlist id or full playlist uri
```

Sync just your 'Liked Songs':

```bash
spotify_to_tidal --sync-favorites
```

### Reverse sync

Same as one-way but from Tidal to Spotify. Requires a Tidal playlist ID:

```bash
spotify_to_tidal --reverse --uri <tidal_playlist_id>
```

### Bidirectional sync

Keeps both Spotify and Tidal in sync with each other:

```bash
spotify_to_tidal --sync
spotify_to_tidal --sync --uri <spotify_playlist_id>
spotify_to_tidal --sync --sync-favorites
```

See example_config.yml for more configuration options, and `spotify_to_tidal --help` for more options.

Sync modes
----------

### One-way sync (default / `--reverse`)

- Mirrors the source playlist to the destination, including track ordering
- Tracks only on the destination side are left untouched
- Tracks removed from the source are **not** removed from the destination
- If the track order differs, the destination playlist is cleared and rewritten

### Bidirectional sync (`--sync`)

- Tracks added to either side are copied to the other
- Track ordering is **not** synced; new tracks are appended to the end
- Deletions are detected via a local snapshot stored in `.cache.db`:
  - On the first run, a snapshot of all matched tracks is saved; no deletions are detected
  - On subsequent runs, if a track was in the previous snapshot but is now missing from one side, it is treated as a deletion and removed from the other side too
- If a track cannot be found on the other platform, it will not be synced (logged to `songs_not_found.txt`)

> **Note:** If you previously used this tool with read-only Spotify permissions, you will need to delete the `.cache` file in the project root and re-authenticate to grant the additional write permissions required for reverse or bidirectional sync.

---

#### Join our amazing community as a code contributor
<br><br>
<a href="https://github.com/spotify2tidal/spotify_to_tidal/graphs/contributors">
  <img class="dark-light" src="https://contrib.rocks/image?repo=spotify2tidal/spotify_to_tidal&anon=0&columns=25&max=100&r=true" />
</a>
