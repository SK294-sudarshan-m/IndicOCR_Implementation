"""Image files: normalisation (EXIF, RGB, alpha), frames, size guard."""

from __future__ import annotations

from PIL import Image

from docpipe.config import Options
from docpipe.render import normalize


def test_png_goes_to_ocr_as_rgb(process, engine):
    doc = process("hi_page.png")
    assert doc.status == "ok" and doc.format == "png"
    (unit,) = doc.units
    assert unit.kind == "image" and unit.origin == "ocr"
    assert unit.render_dpi is None  # not rendered from anything
    assert engine.calls[0]["mode"] == "RGB"
    assert (unit.width_px, unit.height_px) == engine.calls[0]["size"]


def test_exif_rotation_is_applied_before_ocr(process, engine, fx):
    with Image.open(fx / "hi_photo_exif.jpg") as stored:
        assert stored.width > stored.height  # stored sideways
    doc = process("hi_photo_exif.jpg")
    (unit,) = doc.units
    assert engine.calls[0]["size"][0] < engine.calls[0]["size"][1]  # upright (portrait) by the time OCR sees it
    assert unit.width_px < unit.height_px


def test_multipage_tiff_is_one_unit_per_frame(process, engine):
    doc = process("en_two_pages.tif")
    assert [(u.kind, u.page) for u in doc.units] == [("page", 1), ("page", 2)]
    assert len(engine.calls) == 2
    only_second = process("en_two_pages.tif", pages="2")
    assert [u.page for u in only_second.units] == [2] and len(engine.calls) == 3


def test_transparent_png_is_flattened_onto_white():
    rgba = Image.new("RGBA", (8, 8), (255, 0, 0, 0))  # fully transparent red
    flat = normalize(rgba)
    assert flat.mode == "RGB" and flat.getpixel((0, 0)) == (255, 255, 255)
    palette = Image.new("P", (4, 4))
    assert normalize(palette).mode == "RGB"
    assert normalize(Image.new("I;16", (4, 4), 65535)).getpixel((0, 0)) == (255, 255, 255)


def test_oversized_image_is_rejected_before_decoding(process, engine):
    doc = process("huge.png")
    assert doc.status == "error" and doc.error_type == "ImageTooLarge"
    assert "12000x9000" in doc.message and "108 megapixels" in doc.message and "--max-megapixels" in doc.message
    assert engine.calls == []
    assert Image.MAX_IMAGE_PIXELS == 89478485  # Pillow's own guard is restored


def test_an_oversized_tiff_frame_fails_that_frame_not_the_earlier_ones(tmp_path):
    from fakes import FakeEngine

    from docpipe.pipeline import process_document

    path = tmp_path / "mixed_sizes.tif"
    small, big = Image.new("RGB", (300, 300), "white"), Image.new("RGB", (600, 600), "white")
    small.save(path, save_all=True, append_images=[big])
    engine = FakeEngine()
    doc = process_document(path, "mixed_sizes.tif", Options(max_pixels=200_000), engine)
    assert doc.status == "partial"
    assert [(u.page, u.status) for u in doc.units] == [(1, "ok"), (2, "error")]
    assert doc.units[1].error_type == "ImageTooLarge" and len(engine.calls) == 1


def test_pixel_cap_is_configurable(process):
    doc = process("hi_page.png", max_pixels=1_000_000)
    assert doc.status == "error" and doc.error_type == "ImageTooLarge"


def test_file_that_is_not_an_image(process):
    doc = process("fake.png")
    assert doc.status == "error" and doc.error_type == "CorruptFile"
    assert "PNG" in doc.message


def test_options_default_cap_is_100_megapixels():
    assert Options().max_pixels == 100_000_000
