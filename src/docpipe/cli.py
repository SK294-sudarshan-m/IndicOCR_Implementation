"""`docpipe process ...` and `docpipe doctor`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ATTRIBUTION, MODEL_REVISION, Options, parse_pages


def _utf8_stdio() -> None:
    """The Windows console/pipe code page cannot print Devanagari; without this, print() raises UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


class _Version(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        print(f"docpipe {__version__}\n{ATTRIBUTION}\nIndicOCR model revision {MODEL_REVISION}")
        parser.exit()


def _pages(value: str) -> str:
    try:
        parse_pages(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="docpipe", description="Documents in, JSON and Markdown out. IndicOCR reads only the pixels.")
    parser.add_argument("--version", action=_Version, help="print version and the IndicOCR attribution")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
        p.add_argument("--model-dir", type=Path, help="IndicOCR model directory (default: ./models/indic-ocr or $DOCPIPE_MODEL_DIR)")

    proc = sub.add_parser("process", help="convert documents to document.json + document.md")
    proc.add_argument("inputs", nargs="+", type=Path, metavar="path", help="files or folders")
    proc.add_argument("--out", required=True, type=Path, help="output folder; one subfolder per input document")
    proc.add_argument("--dpi", type=int, default=200, help="render resolution for PDF pages sent to OCR (default 200)")
    proc.add_argument("--force-ocr", action="store_true", help="OCR every PDF page, ignoring text layers")
    proc.add_argument("--pages", type=_pages, help="PDF pages / TIFF frames to process, e.g. 1-5,8")
    proc.add_argument("--table-format", choices=["html", "markdown"], default="html")
    proc.add_argument("--max-megapixels", type=float, default=100.0, help="reject images (and lower PDF render dpi) beyond this size")
    common(proc)

    doc = sub.add_parser("doctor", help="check the installation and the model files")
    common(doc)
    return parser


def _options(args: argparse.Namespace) -> Options:
    opts = Options(device=args.device, model_dir=args.model_dir)
    if args.command == "process":
        opts.dpi = args.dpi
        opts.force_ocr = args.force_ocr
        opts.pages = args.pages
        opts.table_format = args.table_format
        opts.max_pixels = int(args.max_megapixels * 1_000_000)
    return opts


def _summary(result) -> str:
    if result.status == "error":
        return f"{result.error_type}: {result.message}"
    ocr = sum(1 for u in result.units if u.origin == "ocr")
    return f"{len(result.units)} units ({len(result.units) - ocr} native, {ocr} ocr), {result.timings.get('total_seconds', 0)}s"


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    args = build_parser().parse_args(argv)
    opts = _options(args)

    if args.command == "doctor":
        from . import doctor

        return doctor.run(opts)

    from .pipeline import process_batch

    def emit(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    def report(n: int, total: int, result, folder: Path) -> None:
        print(f"{result.status:<8} {result.source}  ->  {folder}  {_summary(result)}", flush=True)

    batch = process_batch(args.inputs, args.out, opts, emit=emit, on_document=report)
    for path in batch.skipped:
        print(f"skipped  {path}  (unsupported file type)", file=sys.stderr)
    counts = {s: sum(1 for r, _ in batch.documents if r.status == s) for s in ("ok", "partial", "error")}
    print(f"{len(batch.documents)} document(s): {counts['ok']} ok, {counts['partial']} partial, {counts['error']} error. Output: {args.out}")
    return 0 if counts["partial"] == counts["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
