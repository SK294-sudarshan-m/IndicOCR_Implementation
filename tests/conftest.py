from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import make_fixtures  # noqa: E402
from fakes import FakeEngine  # noqa: E402

from docpipe.config import Options  # noqa: E402
from docpipe.pipeline import process_document  # noqa: E402


def pytest_configure(config):
    config._docpipe_rows = []


@pytest.fixture(scope="session")
def measurements(request) -> list[str]:
    """Model-tier CER/timing lines, printed at the end of the run."""
    return request.config._docpipe_rows


def pytest_terminal_summary(terminalreporter, config):
    if config._docpipe_rows:
        terminalreporter.section("model tier measurements")
        for row in config._docpipe_rows:
            terminalreporter.write_line(row)


@pytest.fixture(scope="session")
def fx(tmp_path_factory) -> Path:
    """Directory with every generated fixture."""
    if not make_fixtures.fonts_available():
        pytest.skip("needs Nirmala UI and Segoe MDL2 Assets in C:\\Windows\\Fonts")
    target = tmp_path_factory.mktemp("fixtures")
    make_fixtures.build(target)
    return target


@pytest.fixture(scope="session")
def truth(fx) -> dict:
    return json.loads((fx / "truth.json").read_text(encoding="utf-8"))


@pytest.fixture
def engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def process(fx, engine):
    """process(name, **option_overrides) -> DocumentResult, using the fake OCR engine."""

    def run(name: str, eng=None, **overrides):
        return process_document(fx / name, name, Options(**overrides), eng or engine)

    return run
