"""Native-only runs must stay fast and light: torch and transformers are never imported."""

from __future__ import annotations

import subprocess
import sys
import textwrap

SCRIPT = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from docpipe.config import Options
    from docpipe.pipeline import process_batch

    fx, out = Path(sys.argv[1]), Path(sys.argv[2])
    names = ["en_born_digital.pdf", "hi_born_digital.pdf", "book.xlsx", "blank.pdf"]
    batch = process_batch([fx / n for n in names], out, Options(model_dir=out / "no-model"))
    statuses = [d.status for d, _ in batch.documents]
    heavy = sorted(m for m in sys.modules if m.split(".")[0] in ("torch", "torchvision", "transformers", "accelerate", "safetensors"))
    print("STATUSES", statuses)
    print("HEAVY", heavy)
    sys.exit(0 if statuses == ["ok"] * len(names) and not heavy else 1)
    """
)


def test_native_run_never_imports_torch(fx, tmp_path):
    proc = subprocess.run([sys.executable, "-c", SCRIPT, str(fx), str(tmp_path)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "HEAVY []" in proc.stdout


def test_importing_the_package_is_light():
    proc = subprocess.run(
        [sys.executable, "-c", "import sys, docpipe.cli, docpipe.pipeline, docpipe.model; print(sorted(m for m in sys.modules if m.split('.')[0] in ('torch','transformers','fitz','pymupdf','docx','openpyxl','lxml','PIL')))"],
        capture_output=True, text=True,
    )
    assert proc.stdout.strip() == "[]", proc.stdout + proc.stderr
