"""The text-layer validity heuristics and the per-page routing rule."""

from __future__ import annotations

import pytest
from make_fixtures import EN_P1, HI_P1, HI_P2

from docpipe.extractors.pdf import decide
from docpipe.quality import Thresholds, analyze_text, judge_text_layer, legacy_fonts

T = Thresholds()


def verdict(text: str, fonts=()):
    return judge_text_layer(text, fonts, T)


def test_healthy_english_and_hindi_pass():
    assert verdict(EN_P1).usable
    assert verdict(HI_P1 + " " + HI_P2).usable
    assert verdict("Price: ₹1,200 — 50% off (see §3.2), x ≤ y → ok “quoted” α β").usable  # rupee, maths, arrows, Greek


@pytest.mark.parametrize(
    "bad, expect",
    [
        ("".join(chr(0xE700 + i % 90) if i % 7 else " " for i in range(200)), "private-use characters"),
        ("hello ��� world " * 10, "replacement characters"),
        ("kgh Ùyªzk ÿÞÛ ãäåæ çèéê ëìíî " * 8, "outside the supported scripts"),
        (" ".join(["spacesweremissingfromthislineoftext" * 3] * 6), "words implausibly long"),  # lines with no word gaps
        (" ".join("abcdefghijklmnopqrstuvwxyz"), "words implausibly short"),
    ],
)
def test_bad_layers_are_rejected_with_a_reason(bad, expect):
    v = verdict(bad)
    assert not v.usable and expect in v.reason and v.reason.startswith("text layer failed validity check (")


def test_detached_combining_marks_are_caught():
    # 'विशाल' extracted as 'व' / newline / 'िशाल': the matra starts a line
    damaged = "भारत एक व\nिशाल देश है। यहाँ अनेक ल\nि\nप\nि है।"
    m = analyze_text(damaged)
    assert m["orphan_marks"] >= 3
    v = verdict(damaged)
    assert not v.usable and "combining marks detached" in v.reason


def test_stray_latin_letter_inside_an_indic_word_is_caught():
    text = "भारत एक विशाल देश है। यहाँ अनेकʟ भाषाएँ बोलीœ जाती हैं और हरƒ भाषा की अपनी लिपि है।"
    v = verdict(text)
    assert not v.usable and "stray non-Indic letters" in v.reason


def test_legacy_font_names_fail_a_text_layer_that_looks_fine():
    fonts = ["ABCDEF+KrutiDev010", "Arial-BoldMT", "DevLys 010"]
    assert legacy_fonts(fonts) == ["ABCDEF+KrutiDev010", "DevLys 010"]
    v = verdict(EN_P1, fonts)  # ASCII-mapped mojibake is indistinguishable from English by content
    assert not v.usable and "legacy Indic font" in v.reason
    assert legacy_fonts(["Nirmala UI", "Mangal", "Arial", "Times New Roman"]) == []


def test_arabic_script_is_accepted_with_a_caveat():
    v = verdict("یہ ایک اردو جملہ ہے جو دائیں سے بائیں لکھا جاتا ہے " * 3)
    assert v.usable and any("Arabic-script" in w for w in v.warnings)


def test_thresholds_are_the_documented_defaults():
    assert (T.min_chars, T.sparse_chars, T.image_cover, T.max_bad, T.max_foreign) == (20, 100, 0.5, 0.02, 0.15)


def _decide(text="", cover=0.0, paths=0, force=False, fonts=()):
    return decide(text, cover, lambda: paths, fonts, force, T)


def test_routing_rules():
    assert not _decide(EN_P1).ocr
    r = _decide("")
    assert (r.ocr, r.reason) == (False, "blank page (no text, no images)")
    assert _decide("", cover=0.9).reason == "no text layer" and _decide("", cover=0.9).ocr
    assert "vector graphics only" in _decide("", paths=500).reason and _decide("", paths=500).ocr
    assert not _decide("", paths=10).ocr  # a few rules and boxes are not outlined text

    short = _decide("Page 1")
    assert not short.ocr and "short text layer" in short.reason
    assert _decide("Page 1", cover=0.3).ocr  # short text plus real image content

    sparse = _decide("A caption under a big picture that has some words in it.", cover=0.8)
    assert sparse.ocr and "sparse" in sparse.reason and "80%" in sparse.reason
    assert not _decide(EN_P1 * 2, cover=0.8).ocr  # dense text over a big image is a searchable scan: trusted

    assert _decide(EN_P1, force=True).reason == "OCR forced by --force-ocr"
