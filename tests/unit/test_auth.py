# tests/unit/test_auth.py

import pytest
import spotipy
from spotidal.errors import AuthenticationError
from spotidal.providers.spotify import SpotifyProvider, SPOTIFY_SCOPES


def test_open_spotify_session(mocker):
    mock_spotify_oauth = mocker.patch(
        "spotidal.providers.spotify.spotipy.SpotifyOAuth", autospec=True
    )
    mock_spotify_instance = mocker.patch(
        "spotidal.providers.spotify.spotipy.Spotify", autospec=True
    )

    mock_config = {
        "username": "test_user",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "redirect_uri": "http://127.0.0.1/",
        "open_browser": True,
    }

    mock_oauth_instance = mock_spotify_oauth.return_value
    mock_oauth_instance.get_access_token.return_value = "mock_access_token"

    provider = SpotifyProvider.from_config(mock_config)

    mock_spotify_oauth.assert_called_once_with(
        username="test_user",
        scope=SPOTIFY_SCOPES,
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="http://127.0.0.1/",
        requests_timeout=2,
        open_browser=True,
    )

    mock_spotify_instance.assert_called_once_with(oauth_manager=mock_oauth_instance)
    assert provider._session == mock_spotify_instance.return_value


def test_open_spotify_session_oauth_error(mocker):
    mock_spotify_oauth = mocker.patch(
        "spotidal.providers.spotify.spotipy.SpotifyOAuth", autospec=True
    )
    mock_spotify_oauth.return_value.get_access_token.side_effect = (
        spotipy.SpotifyOauthError("mock error")
    )

    mock_config = {
        "username": "test_user",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "redirect_uri": "http://127.0.0.1/",
    }

    with pytest.raises(AuthenticationError):
        SpotifyProvider.from_config(mock_config)
