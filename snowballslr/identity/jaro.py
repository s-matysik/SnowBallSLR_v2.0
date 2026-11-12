"""Jaro-Winkler similarity without compiled dependencies.

Deduplication and GROBID reference matching compare normalised titles with
Jaro-Winkler. Version 1 used ``rapidfuzz``, a compiled extension that is not
available in the in-browser (Pyodide) runtime. This module is a pure-Python
implementation that returns the *same float, bit for bit,* as rapidfuzz's own
reference implementation (``rapidfuzz.distance.JaroWinkler_py.similarity``) with
default arguments; equality is enforced by ``tests/test_jaro.py`` rather than
assumed. Because a merge
score is written to the deduplication record, an approximate match would
break byte-identical replay between the CLI and the browser.

It is used unconditionally, not as a fallback. The compiled rapidfuzz wheel is
itself not platform-independent: on arm64 the compiler fuses the Winkler step
``s + p*w*(1 - s)`` into a single fused multiply-add, so the same two titles can
score differently in the last bit on different machines. CPython and Pyodide
evaluate this module with ordinary IEEE-754 double arithmetic everywhere, which
is what byte-identical replay across machines and runtimes requires.
"""

from __future__ import annotations

__all__ = ["jaro_similarity", "jaro_winkler_similarity"]


def jaro_similarity(s1: str, s2: str) -> float:
    len1, len2 = len(s1), len(s2)
    if not len1 and not len2:
        return 1.0
    if not len1 or not len2:
        return 0.0
    bound = max(len1, len2) // 2 - 1
    if bound < 0:
        bound = 0
    flagged1 = [False] * len1
    flagged2 = [False] * len2
    matches = 0
    for i, ch in enumerate(s1):
        lo = i - bound if i > bound else 0
        hi = i + bound + 1
        if hi > len2:
            hi = len2
        for j in range(lo, hi):
            if not flagged2[j] and s2[j] == ch:
                flagged1[i] = True
                flagged2[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    transpositions = 0
    j = 0
    for i in range(len1):
        if flagged1[i]:
            while not flagged2[j]:
                j += 1
            if s1[i] != s2[j]:
                transpositions += 1
            j += 1
    transpositions //= 2
    m = float(matches)
    return (m / len1 + m / len2 + (m - transpositions) / m) / 3.0


def jaro_winkler_similarity(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    sim = jaro_similarity(s1, s2)
    if sim > 0.7:
        prefix = 0
        for a, b in zip(s1[:4], s2[:4], strict=False):
            if a != b:
                break
            prefix += 1
        sim += prefix * prefix_weight * (1.0 - sim)
    return sim

