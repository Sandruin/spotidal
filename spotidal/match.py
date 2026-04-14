from collections.abc import Sequence
from difflib import SequenceMatcher
import unicodedata

from spotidal.type.models import Album, Track


def normalize(s: str) -> str:
    return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('ascii')


def simple(input_string: str) -> str:
    return input_string.split('-')[0].strip().split('(')[0].strip().split('[')[0].strip()


def isrc_match(a: Track, b: Track) -> bool:
    if a.isrc and b.isrc:
        return a.isrc == b.isrc
    return False


def duration_match(a: Track, b: Track, tolerance: float = 2) -> bool:
    return abs(a.duration_s - b.duration_s) < tolerance


def name_match(a: Track, b: Track) -> bool:
    def exclusion_rule(pattern: str, track: Track) -> bool:
        in_name = pattern in track.name.lower()
        in_version = track.version is not None and pattern in track.version.lower()
        return in_name or in_version

    for pattern in ('instrumental', 'acapella', 'remix'):
        if exclusion_rule(pattern, a) != exclusion_rule(pattern, b):
            return False

    simple_a = simple(a.name.lower()).split('feat.')[0].strip()
    simple_b = simple(b.name.lower()).split('feat.')[0].strip()
    return simple_a == simple_b or normalize(simple_a) == normalize(simple_b)


def _split_artist_name(artist: str) -> Sequence[str]:
    if '&' in artist:
        return artist.split('&')
    elif ',' in artist:
        return artist.split(',')
    else:
        return [artist]


def _get_artist_names(item: Track | Album, do_normalize: bool = False) -> set[str]:
    result: list[str] = []
    for artist in item.artists:
        artist_name = normalize(artist.name) if do_normalize else artist.name
        result.extend(_split_artist_name(artist_name))
    return {simple(x.strip().lower()) for x in result}


def artist_match(a: Track | Album, b: Track | Album) -> bool:
    if _get_artist_names(a).intersection(_get_artist_names(b)):
        return True
    return _get_artist_names(a, True).intersection(_get_artist_names(b, True)) != set()


def match(a: Track, b: Track) -> bool:
    if not a.provider_id or not b.provider_id:
        return False
    return isrc_match(a, b) or (
        duration_match(a, b)
        and name_match(a, b)
        and artist_match(a, b)
    )


def test_album_similarity(a: Album, b: Album, threshold: float = 0.6) -> bool:
    return (
        SequenceMatcher(None, simple(a.name), simple(b.name)).ratio() >= threshold
        and artist_match(a, b)
    )
