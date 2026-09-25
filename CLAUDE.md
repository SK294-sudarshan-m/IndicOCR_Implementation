# docpipe

Ingestion router: native parsing for machine-readable content, IndicOCR (`models/indic-ocr`) only for pixels.
State lives in `progress.txt` (decisions, measurements) and `tests.json` (acceptance criteria). Read both first.

## Commands (PowerShell, from the project root)
- Setup: `.venv\Scripts\python -m pip install -e . --no-deps --no-build-isolation` (deps: see README)
- Fast tests (no weights, no torch): `.venv\Scripts\python -m pytest`
- Model tests (real weights, minutes on CPU): `.venv\Scripts\python -m pytest -m model`
- Fixtures on disk: `.venv\Scripts\python tests\make_fixtures.py <dir>`
- Run: `.venv\Scripts\docpipe process <path>... --out out` / `docpipe doctor`

## Gotchas
- Never touch the reference clone `C:\Users\User\Desktop\IndicOCR_Huggingface\indic-ocr`. Its `git status` already
  shows changes (baseline in tests/test_clone_untouched.py); use `git --no-optional-locks` there.
- `torch`/`transformers` must stay lazy: only `model.py` may import them, only inside `IndicOcrEngine._load`.
  `tests/test_no_torch.py` fails if a native run imports them.
- IndicOCR takes file PATHS, applies no EXIF rotation, and sets `Image.MAX_IMAGE_PIXELS=None` process-wide:
  `render.py` normalises images and enforces the pixel cap before any image reaches it.
- IndicOCR's `idp_*` modules are imported from the model dir at runtime (pinned revision in `config.py`).
- CPU dtype is float32 (faster than bfloat16 here); CUDA uses bfloat16. HfRecognizer is slow: ~20-30 s per page.
- PyMuPDF text of shaped Hindi can look fine but be damaged (detached matras, U+FFFD): `quality.py` catches it.
- Console: `cli.main` reconfigures stdout/stderr to UTF-8; write files as UTF-8 with `ensure_ascii=False`.
- Do not build a network service (model license forbids hosting for third parties). No network calls when processing:
  `model.py` forces HF offline mode.
- The OCR weight file needs the user's own `hf auth login`. Never read, print or store a token.
- Fixtures are generated (needs Nirmala UI + Segoe MDL2 Assets in C:\Windows\Fonts); nothing is checked in.
- Temp files: `render.Workspace` only; delete in `finally`. Tests assert none are left.
- Do not weaken a test or threshold to pass; investigate the pipeline (dpi, RGB/EXIF, order mismatch).
