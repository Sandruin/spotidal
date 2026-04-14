import asyncio
from unittest.mock import MagicMock, patch, PropertyMock

import requests

from spotidal.providers.tidal import TidalProvider
from spotidal.type.models import Playlist


def _make_412_error():
    response = MagicMock()
    response.status_code = 412
    return requests.exceptions.HTTPError(response=response)


def _make_500_error():
    response = MagicMock()
    response.status_code = 500
    return requests.exceptions.HTTPError(response=response)


def _make_tidal_provider(mocker):
    """Create a TidalProvider with a mocked session."""
    mock_session = MagicMock()
    return TidalProvider(mock_session)


def test_add_tracks_retries_on_412(mocker):
    """When a 412 occurs, the method should re-fetch the playlist and retry the chunk."""
    provider = _make_tidal_provider(mocker)
    playlist = Playlist(provider_id="test-playlist-id", name="Test", description="")

    mock_raw_playlist = MagicMock()
    # First call to add() raises 412, second succeeds
    mock_raw_playlist.add.side_effect = [_make_412_error(), None]

    mock_fresh_playlist = MagicMock()
    mock_fresh_playlist.add.return_value = []

    # First session.playlist() returns the original, second returns a fresh one
    provider._session.playlist.side_effect = [mock_raw_playlist, mock_fresh_playlist]

    with patch("asyncio.sleep", return_value=None):
        asyncio.run(provider.add_tracks_to_playlist(playlist, ["1", "2", "3"]))

    # Original playlist was tried first
    mock_raw_playlist.add.assert_called_once_with([1, 2, 3])
    # After 412, a fresh playlist was fetched and the chunk was retried
    mock_fresh_playlist.add.assert_called_once_with([1, 2, 3])


def test_add_tracks_412_retry_limit(mocker):
    """After 3 failed attempts with 412, the error should propagate."""
    provider = _make_tidal_provider(mocker)
    playlist = Playlist(provider_id="test-playlist-id", name="Test", description="")

    mock_playlist = MagicMock()
    mock_playlist.add.side_effect = [_make_412_error(), _make_412_error(), _make_412_error()]

    provider._session.playlist.return_value = mock_playlist

    import pytest
    with patch("asyncio.sleep", return_value=None):
        with pytest.raises(requests.exceptions.HTTPError):
            asyncio.run(provider.add_tracks_to_playlist(playlist, ["1", "2"]))

    # 3 attempts: initial + 2 retries
    assert mock_playlist.add.call_count == 3


def test_add_tracks_non_412_error_not_retried(mocker):
    """Non-412 HTTP errors should not be retried."""
    provider = _make_tidal_provider(mocker)
    playlist = Playlist(provider_id="test-playlist-id", name="Test", description="")

    mock_raw_playlist = MagicMock()
    mock_raw_playlist.add.side_effect = _make_500_error()

    provider._session.playlist.return_value = mock_raw_playlist

    import pytest
    with pytest.raises(requests.exceptions.HTTPError):
        asyncio.run(provider.add_tracks_to_playlist(playlist, ["1", "2"]))

    # Only 1 attempt, no retry
    assert mock_raw_playlist.add.call_count == 1


def test_add_tracks_chunked_412_mid_stream(mocker):
    """412 on a later chunk should retry only that chunk, not restart from the beginning."""
    provider = _make_tidal_provider(mocker)
    playlist = Playlist(provider_id="test-playlist-id", name="Test", description="")

    # Generate 30 track IDs (will be split into chunks of 20 + 10)
    track_ids = [str(i) for i in range(1, 31)]

    mock_raw_playlist = MagicMock()
    # First chunk (20) succeeds, second chunk (10) raises 412
    mock_raw_playlist.add.side_effect = [None, _make_412_error()]

    mock_fresh_playlist = MagicMock()
    mock_fresh_playlist.add.return_value = []

    provider._session.playlist.side_effect = [mock_raw_playlist, mock_fresh_playlist]

    with patch("asyncio.sleep", return_value=None):
        asyncio.run(provider.add_tracks_to_playlist(playlist, track_ids))

    # First chunk succeeded on original playlist
    first_call_args = mock_raw_playlist.add.call_args_list[0][0][0]
    assert first_call_args == list(range(1, 21))

    # Second chunk failed on original, retried on fresh playlist
    retry_args = mock_fresh_playlist.add.call_args_list[0][0][0]
    assert retry_args == list(range(21, 31))
