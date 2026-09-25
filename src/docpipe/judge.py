"""LLM-as-judge for OCR output: Claude looks at the page image and grades what IndicOCR extracted.

PRIVACY: every sampled page image and its OCR text are sent to the Anthropic API. Use it on public or non-sensitive
documents only. Nothing else in docpipe makes network calls. The key is read from ANTHROPIC_API_KEY, never stored.
"""

from __future__ import annotations

import base64
import json
import os
import re
import statistics
import time
from pathlib import Path

from .metrics import cer, wer
from .schema import DocumentResult

DEFAULT_MODEL = "claude-sonnet-5"
MAX_IMAGE_SIDE = 1568  # larger images are downscaled by the API anyway

PROMPT = """You are grading an OCR system. The image is one scanned document page. Below is the text the OCR system extracted from it.

Do two things:
1. Transcribe ALL text visible on the page exactly as printed, in natural reading order, in its original script(s). Do not translate, do not correct spelling, and do not copy from the OCR text.
2. Judge the OCR text against the page.

Reply with ONLY one JSON object, no markdown fences, no other text:
{"transcription": "<full page text>",
 "score": <integer 1-10, 10 = perfect, 1 = unusable>,
 "verdict": "good" | "acceptable" | "poor",
 "reading_order_ok": <true|false>,
 "missing_text": ["<short excerpt of text on the page that the OCR text lacks>", ...],
 "wrong_text": [{"ocr": "<what the OCR text says>", "actual": "<what the page says>"}, ...],
 "hallucinated_text": ["<OCR text that is not on the page>", ...],
 "notes": "<one or two sentences>"}
List at most 10 items in wrong_text and 10 in missing_text.

OCR TEXT:
<<<
__OCR__
>>>"""


def sample_indices(n: int, k: int) -> list[int]:
    """Deterministic, evenly spread positions: the first, the last and the ones between."""
    if n <= k:
        return list(range(n))
    if k == 1:
        return [0]
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def _render(pdf_path: Path, page_number: int) -> bytes:
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        page = doc[page_number - 1]
        longest_in = max(page.rect.width, page.rect.height) / 72
        dpi = max(50, min(200, int(MAX_IMAGE_SIDE / longest_in)))
        return page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")


def _parse(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the judge's reply")
    return json.loads(text[start : end + 1])


def _percent(error_rate: float) -> float:
    return round(max(0.0, min(100.0, 100 * (1 - error_rate))), 2)


def judge_page(client, model: str, png: bytes, ocr_text: str) -> dict:
    """One judged page, with self-explanatory field names."""
    started = time.perf_counter()
    message = client.messages.create(
        model=model,
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode()}},
                    {"type": "text", "text": PROMPT.replace("__OCR__", ocr_text)},
                ],
            }
        ],
    )
    latency = round(time.perf_counter() - started, 2)
    tokens_in, tokens_out = message.usage.input_tokens, message.usage.output_tokens
    if message.stop_reason == "max_tokens":
        raise ValueError(f"the judge's reply was cut off (page too dense for max_tokens); {latency}s, {tokens_in} in / {tokens_out} out tokens")
    raw = _parse("".join(b.text for b in message.content if b.type == "text"))
    transcription = raw.get("transcription", "")
    character_error, word_error = cer(transcription, ocr_text), wer(transcription, ocr_text)
    return {
        "llm_quality_rating_out_of_10": raw.get("score"),
        "llm_verdict": raw.get("verdict"),
        "reading_order_correct": raw.get("reading_order_ok"),
        "character_accuracy_percent": _percent(character_error),
        "word_accuracy_percent": _percent(word_error),
        "character_error_rate_percent": round(100 * character_error, 2),
        "word_error_rate_percent": round(100 * word_error, 2),
        "text_on_page_missing_from_ocr": raw.get("missing_text", []),
        "misread_text": [{"ocr_text_says": w.get("ocr"), "page_actually_says": w.get("actual")} for w in raw.get("wrong_text", []) if isinstance(w, dict)],
        "text_in_ocr_but_not_on_page": raw.get("hallucinated_text", []),
        "llm_judge_comments": raw.get("notes", ""),
        "llm_transcription": transcription,
        "llm_call_latency_seconds": latency,
        "llm_input_tokens": tokens_in,
        "llm_output_tokens": tokens_out,
    }


def _find_pdf(document: DocumentResult, pdfs_dir: Path | None) -> Path | None:
    for candidate in (Path(document.source), (pdfs_dir / Path(document.source).name) if pdfs_dir else None):
        if candidate is not None and candidate.is_file():
            return candidate
    return None


HOW_TO_READ = (
    "Ratings come from an LLM judge (see 'judge_model_name'): it looks at the page image, transcribes it, and compares the OCR text "
    "with the page. 'llm_quality_rating_out_of_10' is 1 (unusable) to 10 (perfect). Accuracy percentages are "
    "100 minus the error rate measured against the LLM's own transcription, NOT against human-verified ground truth, so "
    "they mean 'agreement with the LLM'. Only the sampled OCR pages were judged."
)
_AVG = statistics.mean


def _summarise(pages: list[dict]) -> dict:
    return {
        "average_llm_quality_rating_out_of_10": round(_AVG(j["llm_quality_rating_out_of_10"] for j in pages), 2),
        "average_character_accuracy_percent": round(_AVG(j["character_accuracy_percent"] for j in pages), 2),
        "average_word_accuracy_percent": round(_AVG(j["word_accuracy_percent"] for j in pages), 2),
        "average_character_error_rate_percent": round(_AVG(j["character_error_rate_percent"] for j in pages), 2),
        "average_word_error_rate_percent": round(_AVG(j["word_error_rate_percent"] for j in pages), 2),
        "number_of_pages_per_llm_verdict": {v: sum(1 for j in pages if j["llm_verdict"] == v) for v in ("good", "acceptable", "poor")},
        "number_of_pages_with_wrong_reading_order": sum(1 for j in pages if j["reading_order_correct"] is False),
        "total_llm_input_tokens": sum(j["llm_input_tokens"] for j in pages),
        "total_llm_output_tokens": sum(j["llm_output_tokens"] for j in pages),
        "total_llm_call_latency_seconds": round(sum(j["llm_call_latency_seconds"] for j in pages), 2),
        "average_llm_call_latency_seconds": round(_AVG(j["llm_call_latency_seconds"] for j in pages), 2),
    }


def run(output_dir: Path, pdfs_dir: Path | None = None, pages_per_pdf: int = 3, model: str = DEFAULT_MODEL, say=print, report_dir: Path | None = None) -> dict:
    """Judge ``pages_per_pdf`` OCR pages of every PDF result under ``output_dir``. Writes judge_report.json only, to ``report_dir`` (default: ``output_dir``)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set. Create a key at console.anthropic.com, run `setx ANTHROPIC_API_KEY ...` in your own terminal, then open a new terminal.")
    try:
        import anthropic
    except ImportError:
        raise SystemExit("the judge needs the anthropic package: pip install anthropic") from None
    client = anthropic.Anthropic()

    plan = []
    for path in sorted(output_dir.rglob("document.json")):
        document = DocumentResult.read(path)
        if document.format != "pdf" or document.status == "error":
            continue
        ocr_units = [u for u in document.units if u.origin == "ocr" and u.status == "ok" and u.page]
        plan.append((path, document, [ocr_units[i] for i in sample_indices(len(ocr_units), pages_per_pdf)], len(ocr_units)))
    say(f"judge: {model}; {sum(len(c) for _, _, c, _ in plan)} page(s) from {len(plan)} PDF(s) will be sent to the Anthropic API")

    report = {"how_to_read": HOW_TO_READ, "judge_model_name": model, "max_pages_judged_per_pdf": pages_per_pdf, "overall_summary": {}, "pdfs": []}
    for path, document, chosen, n_ocr in plan:
        entry = {"pdf_name": path.parent.name, "source_pdf_path": document.source, "total_ocr_pages_in_pdf": n_ocr, "judged_pages": []}
        pdf = _find_pdf(document, pdfs_dir)
        if pdf is None:
            entry["error_message"] = "source PDF not found; pass --pdfs"
        elif not chosen:
            entry["error_message"] = "no OCR pages in this document (text layer was used); nothing to judge"
        else:
            for unit in chosen:
                item = {"page_number": unit.page}
                say(f"  {entry['pdf_name']} p{unit.page}: calling {model} ...")
                try:
                    item.update(judge_page(client, model, _render(pdf, unit.page), unit.text))
                except Exception as exc:  # one failed page must not stop the run
                    item["error_message"] = f"{type(exc).__name__}: {str(exc)[:200]}"
                entry["judged_pages"].append(item)
                say(f"  {entry['pdf_name']} p{unit.page}: " + (item.get("error_message") or (
                    f"LLM quality rating {item['llm_quality_rating_out_of_10']}/10 ({item['llm_verdict']}) | character accuracy {item['character_accuracy_percent']}% | "
                    f"word accuracy {item['word_accuracy_percent']}% | LLM call {item['llm_call_latency_seconds']}s, {item['llm_input_tokens']} in / {item['llm_output_tokens']} out tokens")))
        ok = [j for j in entry["judged_pages"] if "error_message" not in j]
        if ok:
            entry.update(_summarise(ok))
        report["pdfs"].append(entry)

    all_pages = [j for d in report["pdfs"] for j in d["judged_pages"] if "error_message" not in j]
    report["overall_summary"] = {
        "number_of_pdfs_judged": sum(1 for d in report["pdfs"] if "average_llm_quality_rating_out_of_10" in d),
        "number_of_pages_judged": len(all_pages),
        **(_summarise(all_pages) if all_pages else {}),
    }
    report_dir = report_dir or output_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "judge_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    o = report["overall_summary"]
    if all_pages:
        say(f"OVERALL: LLM quality rating {o['average_llm_quality_rating_out_of_10']}/10 | character accuracy {o['average_character_accuracy_percent']}% | word accuracy {o['average_word_accuracy_percent']}% | verdicts {o['number_of_pages_per_llm_verdict']}")
        say(f"         {o['total_llm_input_tokens']} in / {o['total_llm_output_tokens']} out tokens, {o['total_llm_call_latency_seconds']}s LLM time ({o['number_of_pdfs_judged']} PDFs, {o['number_of_pages_judged']} pages)")
    say(f"report: {report_dir / 'judge_report.json'}")
    return report
