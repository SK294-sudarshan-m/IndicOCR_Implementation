"""The command line: doctor, process, UTF-8 output."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from docpipe.config import MODEL_CODE_FILES, default_model_dir

REAL_MODEL = default_model_dir()


def run(*args: str, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, "PYTHONUTF8": "", **(env or {})}
    full_env.pop("PYTHONUTF8")
    return subprocess.run([sys.executable, "-m", "docpipe", *args], capture_output=True, env=full_env, cwd=cwd)


def text(data: bytes) -> str:
    return data.decode("utf-8")


def test_version_prints_the_required_attribution():
    proc = run("--version")
    assert proc.returncode == 0
    assert "Built with IndicOCR from Bodhan AI / AI4Bharat." in text(proc.stdout)


def test_doctor_reports_and_fails_with_fixes(tmp_path):
    empty = tmp_path / "empty-model-dir"
    empty.mkdir()
    proc = run("doctor", "--model-dir", str(empty), "--device", "cpu")
    out = text(proc.stdout)
    assert proc.returncode == 1
    for label in ("python", "torch", "torchvision", "transformers", "accelerate", "device", "dtype", "model dir", "layout weights", "OCR weights"):
        assert label in out
    assert "device         cpu" in out and "dtype          float32" in out
    assert "IndicOCR code files missing" in out and "fix:" in out


def test_doctor_names_the_hf_login_step_when_only_the_ocr_weights_are_missing(tmp_path):
    if not all((REAL_MODEL / f).is_file() for f in MODEL_CODE_FILES):
        pytest.skip("model code not present")
    partial = tmp_path / "partial"
    partial.mkdir()
    for f in MODEL_CODE_FILES:
        shutil.copy(REAL_MODEL / f, partial / f)
    layout = partial / "weights" / "layout"
    layout.mkdir(parents=True)
    (layout / "model.safetensors").write_bytes(b"stub")
    proc = run("doctor", "--model-dir", str(partial), "--device", "cpu")
    out = text(proc.stdout)
    assert proc.returncode == 1
    assert "OCR weights missing" in out and "hf auth login" in out and "hf download bodhan-ai/indic-ocr" in out
    assert "--revision cd50d301d0e17e8ecb32fc49c8ccbd7914dcfc25" in out
    assert "layout weights missing" not in out


@pytest.mark.model
def test_doctor_ok_with_real_model():
    proc = run("doctor")
    out = text(proc.stdout)
    assert proc.returncode == 0, out
    assert "OK: OCR is ready." in out and "OCR weights    1,654 MB" in out


def test_hindi_output_survives_a_cp1252_stdout(fx, tmp_path):
    """The default Windows code page cannot encode Devanagari; the CLI must not raise UnicodeEncodeError."""
    env = {"PYTHONIOENCODING": "cp1252"}
    control = subprocess.run([sys.executable, "-c", "print('हिंदी')"], capture_output=True, env={**os.environ, **env})
    assert b"UnicodeEncodeError" in control.stderr, "the control must fail, or this test proves nothing"

    proc = run("process", str(fx / "हिंदी_पाठ.txt"), "--out", str(tmp_path / "out"), env=env)
    assert proc.returncode == 0, text(proc.stderr)
    assert "UnicodeEncodeError" not in text(proc.stderr)
    assert "हिंदी_पाठ.txt" in text(proc.stdout) and "हिंदी_पाठ.txt" in text(proc.stderr)  # summary and progress lines
    assert (tmp_path / "out" / "हिंदी_पाठ.txt" / "document.json").is_file()


def test_exit_code_reflects_failures_but_the_batch_finishes(fx, tmp_path):
    ok = run("process", str(fx / "nested.json"), "--out", str(tmp_path / "a"))
    assert ok.returncode == 0 and "1 document(s): 1 ok, 0 partial, 0 error" in text(ok.stdout)
    mixed = run("process", str(fx / "corrupt.pdf"), str(fx / "nested.json"), str(fx / "encrypted.pdf"), "--out", str(tmp_path / "b"))
    out = text(mixed.stdout)
    assert mixed.returncode == 1
    assert "3 document(s): 1 ok, 0 partial, 2 error" in out
    assert "PasswordProtected: PDF is encrypted; no text or images were read." in out


def test_bad_pages_argument_is_rejected(fx, tmp_path):
    proc = run("process", str(fx / "nested.json"), "--out", str(tmp_path), "--pages", "3-1")
    assert proc.returncode == 2 and "invalid range" in text(proc.stderr)


def test_process_cli_options_reach_the_pipeline(fx, tmp_path):
    proc = run("process", str(fx / "en_born_digital.pdf"), "--out", str(tmp_path), "--pages", "2")
    assert proc.returncode == 0
    import json

    data = json.loads((tmp_path / "en_born_digital.pdf" / "document.json").read_text(encoding="utf-8"))
    assert [u["page"] for u in data["units"]] == [2]
