"""Stand-ins for the model so the fast tier needs neither weights nor torch."""

from __future__ import annotations

import os

from PIL import Image

from docpipe.model import OcrPage


class FakeEngine:
    """Implements docpipe.model.OcrEngine. Records what it was asked to read, at the moment it was asked."""

    def __init__(self, text: str = "FAKE OCR", fail_on: set[int] | None = None) -> None:
        self.text = text
        self.fail_on = fail_on or set()  # 1-based call numbers that raise
        self.calls: list[dict] = []
        self.load_seconds = 0.0
        self.closed = False

    def recognize(self, image_path: str) -> OcrPage:
        with Image.open(image_path) as im:
            width, height = im.size
            mode = im.mode
        self.calls.append({"path": image_path, "size": (width, height), "mode": mode, "existed": os.path.isfile(image_path)})
        if len(self.calls) in self.fail_on:
            raise RuntimeError("simulated recognizer crash")
        n = len(self.calls)
        blocks = [
            {"order": 0, "label": "Header", "type": "PageHeader", "bbox_xyxy": [0.0, 0.0, float(width), 40.0], "conf": 0.6, "text": ""},
            {"order": 1, "label": "Paragraph", "type": "Text", "bbox_xyxy": [10.0, 50.0, width - 10.0, height / 2], "conf": 0.9, "text": f"{self.text} {n}"},
            {"order": 2, "label": "Image", "type": "Picture", "bbox_xyxy": [10.0, height / 2, width - 10.0, height - 10.0], "conf": 0.8, "text": ""},
        ]
        return OcrPage(width, height, blocks, f"{self.text} {n}")

    def info(self) -> dict:
        return {"engine": "fake"}

    def close(self) -> None:
        self.closed = True


class ScriptedRecognizer:
    """A RecognizerBackend (idp_recognizer protocol): one canned string per crop, in order."""

    def __init__(self, texts=None) -> None:
        self.texts = list(texts or [])
        self.seen: list[tuple[tuple[int, int], str]] = []

    def transcribe(self, requests):
        out = []
        for request in requests:
            self.seen.append((request.image.size, request.prompt))
            out.append(self.texts[len(self.seen) - 1] if len(self.seen) <= len(self.texts) else f"crop {len(self.seen)}")
        return out

    def close(self) -> None:
        pass


class ThreeBlockLayout:
    """A LayoutBackend (idp_layout protocol): header, paragraph, figure. Blocks come from the model dir's own types."""

    def detect(self, image):
        from idp_types import Block

        w, h = image.size
        return [
            Block(0, "Header", "PageHeader", [0.0, 0.0, float(w), 40.0], 0.6),
            Block(1, "Paragraph", "Text", [10.0, 50.0, w - 10.0, h / 2], 0.9),
            Block(2, "Image", "Picture", [10.0, h / 2, w - 10.0, h - 10.0], 0.8),
        ]

    def close(self) -> None:
        pass
