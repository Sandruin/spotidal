import asyncio
import traceback

import requests

from spotidal.errors import SyncAbortError

RETRY_SLEEP_SCHEDULE = [1, 10, 60, 5 * 60, 10 * 60]


async def repeat_on_request_error(
    function,
    *args,
    retryable_exceptions: tuple[type[Exception], ...] = (requests.exceptions.RequestException,),
    max_retries: int = 5,
    **kwargs,
):
    """Retry an async function on transient request errors with exponential backoff.

    Raises SyncAbortError after exhausting retries.
    """
    for attempt in range(max_retries):
        try:
            return await function(*args, **kwargs)
        except retryable_exceptions as e:
            remaining = max_retries - attempt - 1
            if remaining:
                print(f"{e} occurred, retrying {remaining} more time(s)")
            else:
                print(f"{e} could not be recovered")

            if isinstance(e, requests.exceptions.RequestException) and e.response is not None:
                print(f"Response message: {e.response.text}")
                print(f"Response headers: {e.response.headers}")

            if not remaining:
                print(f"The following arguments were provided:\n\n {args}")
                print(traceback.format_exc())
                raise SyncAbortError(f"Aborting sync after {max_retries} failed attempts") from e

            await asyncio.sleep(RETRY_SLEEP_SCHEDULE[attempt])
