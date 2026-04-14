# spotidal

A command line tool for syncing playlists and liked songs between Spotify and Tidal. Supports one-way mirroring and full two-way sync with deletion detection. Optimised for periodic synchronisation of very large collections.

## Prerequisites

This is a [uv](https://docs.astral.sh/uv/) project. Install uv first if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Installation

Clone this repository:

```bash
git clone https://github.com/Sandruin/spotidal.git && cd spotidal
```

Dependencies are installed automatically on first `uv run`.

## Quick start

Run without arguments to enter the interactive setup wizard:

```bash
uv run spotify_to_tidal
```

The wizard walks you through:

1. **Spotify credentials** -- create an app at [developer.spotify.com](https://developer.spotify.com/dashboard), enter your client ID, secret, username, and redirect URI
2. **Tidal login** -- opens your browser for OAuth authentication
3. **Sync mode** -- two-way (keep both services in sync) or one-way (mirror from one to the other)
4. **Playlist selection** -- checkbox list of all your playlists from both services
5. **Favorites** -- whether to sync liked/saved songs
6. **Deletion behavior** -- (two-way only) whether removing a track on one side should remove it from the other

Your choices are saved to `config.yml`. At the end you can run the sync immediately or save and exit.

## Usage

```
spotify_to_tidal                # interactive setup wizard
spotify_to_tidal --setup        # same as above
spotify_to_tidal --autorun      # run sync using saved config (non-interactive, cron-friendly)
spotify_to_tidal --oneshot      # interactive one-shot sync (pick playlists without saving to config)
spotify_to_tidal --config FILE  # use a different config file (works with any mode)
```

## Sync modes

### One-way

- Mirrors the source playlist to the destination, including track ordering
- Tracks only on the destination side are left untouched
- Tracks removed from the source are **not** removed from the destination
- If the track order differs, the destination playlist is cleared and rewritten

### Two-way

- Tracks added to either side are copied to the other
- Track ordering is **not** synced; new tracks are appended to the end
- Deletions are detected via a local snapshot stored in `.cache.db`:
  - On the first run, a snapshot of all matched tracks is saved; no deletions are detected
  - On subsequent runs, if a track was in the previous snapshot but is now missing from one side, it is treated as a deletion and removed from the other side (if `allow_deletions` is enabled)
- If a track cannot be found on the other platform, it is logged to `songs_not_found.txt`


> **Note:** If you previously used this tool with read-only Spotify permissions, delete the `.cache` file in the project root and re-authenticate to grant write permissions needed for reverse or bidirectional sync.

## Acknowledgements

This project is a fork of [spotify2tidal/spotify_to_tidal](https://github.com/spotify2tidal/spotify_to_tidal). Thanks to the original authors and contributors for building the foundation this project is built on.

## AI disclaimer

Claude Code was used to accelerate development. All code was reviewed and approved manually.
