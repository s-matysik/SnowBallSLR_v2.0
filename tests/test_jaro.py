"""Jaro-Winkler: pure-Python implementation against fixed values and rapidfuzz's reference."""

import random

import pytest

from snowballslr.identity.jaro import jaro_similarity, jaro_winkler_similarity

# Values computed with rapidfuzz.distance.JaroWinkler_py 3.14.5 and checked by hand
# for the classic textbook pairs. Exact float equality is intended.
FIXED = [
    ("", "", 1.0),
    ("", "a", 0.0),
    ("a", "", 0.0),
    ("a", "a", 1.0),
    ("abc", "xyz", 0.0),
    ("martha", "marhta", 0.9611111111111111),
    ("dwayne", "duane", 0.8400000000000001),
    ("dixon", "dicksonx", 0.8133333333333332),
    ("crate", "trace", 0.7333333333333334),
]


@pytest.mark.parametrize(("a", "b", "expected"), FIXED)
def test_fixed_values(a, b, expected):
    assert jaro_winkler_similarity(a, b) == expected


def test_symmetric_and_bounded():
    rnd = random.Random(7)
    for _ in range(2000):
        a = "".join(rnd.choice("abcde ") for _ in range(rnd.randrange(0, 12)))
        b = "".join(rnd.choice("abcde ") for _ in range(rnd.randrange(0, 12)))
        s = jaro_winkler_similarity(a, b)
        assert s == jaro_winkler_similarity(b, a)
        assert 0.0 <= s <= 1.0
        assert jaro_similarity(a, b) <= s


def _pairs(n, seed):
    rnd = random.Random(seed)
    words = ["the", "impact", "of", "social", "media", "marketing", "on", "consumer", "loyalty", "a", "systematic", "review", "of", "gamification", "in", "education", "evidence", "from", "structural", "equation", "modelling"]
    out = []
    for _ in range(n):
        a = " ".join(rnd.choice(words) for _ in range(rnd.randrange(1, 14)))
        b = list(a)
        for _ in range(rnd.randrange(0, 4)):
            if b:
                i = rnd.randrange(len(b))
                b[i] = rnd.choice("abcdefghij ")
        out.append((a, "".join(b) if rnd.random() < 0.7 else
                    " ".join(rnd.choice(words) for _ in range(rnd.randrange(1, 14)))))
    return out


def test_bit_equal_to_rapidfuzz_reference():
    ref = pytest.importorskip("rapidfuzz.distance.JaroWinkler_py")
    for a, b in _pairs(20000, 20261112):
        assert jaro_winkler_similarity(a, b) == ref.similarity(a, b), (a, b)
