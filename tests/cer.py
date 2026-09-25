"""Character error rate: Levenshtein distance on NFC text with whitespace collapsed, over reference length."""

from __future__ import annotations

import unicodedata


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    return levenshtein(ref, hyp) / max(1, len(ref))
