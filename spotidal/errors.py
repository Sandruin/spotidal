class AuthenticationError(Exception):
    """Raised when authentication with a music provider fails."""


class SyncAbortError(Exception):
    """Raised when sync cannot continue due to unrecoverable API errors."""
