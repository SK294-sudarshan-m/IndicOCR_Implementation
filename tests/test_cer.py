"""The accuracy metric itself: a CER of 0.0 on every fixture is only meaningful if the metric can be non-zero."""

from __future__ import annotations

import unicodedata

from cer import cer, levenshtein, normalize


def test_cer_known_values():
    assert cer("abc", "abc") == 0.0
    assert cer("abc", "abd") == 1 / 3
    assert cer("abcd", "") == 1.0
    assert cer("ab", "abcd") == 1.0  # insertions count against the reference length
    assert levenshtein("kitten", "sitting") == 3


def test_cer_collapses_whitespace_and_normalises_to_nfc():
    assert cer("a  b\n c", "a b c") == 0.0
    decomposed = unicodedata.normalize("NFD", "दिल्ली क़")
    assert cer("दिल्ली क़", decomposed) == 0.0 and normalize(decomposed) == unicodedata.normalize("NFC", "दिल्ली क़")


def test_cer_sees_a_devanagari_error():
    assert 0 < cer("यहाँ अनेक भाषाएँ", "यहा अनेक भाषाए") < 0.2
