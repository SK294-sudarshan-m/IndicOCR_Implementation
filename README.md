# docpipe

Local command-line tool and Python library that turns documents into structured text: for every input it writes one
`document.json` (the units carry their text and a Markdown-formatted `markdown` string; no .md files are written).

Anything that already contains machine-readable text is **parsed natively**. Anything that exists only as pixels
(scans, photos, image-only PDF pages, pictures embedded in Office files) goes through
[IndicOCR](https://huggingface.co/bodhan-ai/indic-ocr), which reads English and 22 Indian languages. IndicOCR only reads page
images and is slow on a CPU, so docpipe uses it only where it has to.

**Built with IndicOCR from Bodhan AI / AI4Bharat.**

Everything runs on your machine. Processing makes no network calls (the Hugging Face libraries are forced offline), and
there is no server: the IndicOCR license forbids hosting the model for third parties without Bodhan AI's written approval.

## Install (Windows, Python 3.11+)

From the project folder, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
# torch and torchvision must come from the same index, in one command (CPU build shown):
.\.venv\Scripts\python -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -e . --no-deps --no-build-isolation
```

Without the OCR stack (`torch`, `torchvision`, `transformers`, `accelerate`) docpipe still processes every native format;
only OCR is unavailable. `pip install -e .` alone installs just the native-format dependencies.

### One-time model download

The model is gated on Hugging Face. Accept the license on <https://huggingface.co/bodhan-ai/indic-ocr> with your account, then in
**your own terminal** (docpipe never handles credentials):

```powershell
hf auth login
hf download bodhan-ai/indic-ocr --revision cd50d301d0e17e8ecb32fc49c8ccbd7914dcfc25 --local-dir models\indic-ocr
```

**The revision is pinned on purpose.** docpipe imports the `idp_*.py` files from that directory and runs them, so it must be
the reviewed revision `cd50d301d0e17e8ecb32fc49c8ccbd7914dcfc25`, not whatever `main` is today. The directory is found via
`--model-dir`, then `%DOCPIPE_MODEL_DIR%`, then `.\models\indic-ocr`.
(On the development machine the directory was populated by copying an existing clone of that revision and downloading only
`weights/ocr/model-00001-of-00001.safetensors`, whose SHA-256 was checked against the LFS pointer. The full
`hf download` above is the documented route and was not itself run.)

Check everything:

```powershell
.\.venv\Scripts\docpipe doctor
```

It prints Python, torch, torchvision, transformers and accelerate versions, the chosen device and dtype, whether both weight
files are present, and the model directory; it exits non-zero with one concrete fix per problem.

## Use

```powershell
docpipe process input\ --out out\
docpipe process scan.pdf report.docx --out out\ --dpi 200 --pages 1-5
docpipe process scan.pdf --out out\ --force-ocr --table-format markdown
```

| option | default | meaning |
|---|---|---|
| `--out DIR` | required | one subfolder per input document |
| `--dpi N` | 200 | render resolution for PDF pages that go to OCR |
| `--force-ocr` | off | OCR every PDF page, ignoring text layers |
| `--pages 1-5,8` | all | PDF pages / multi-frame TIFF frames to process |
| `--table-format html\|markdown` | html | how IndicOCR writes tables |
| `--max-megapixels N` | 100 | reject images above this; lower PDF render dpi to stay under it |
| `--device auto\|cpu\|cuda` | auto | CUDA if available, else CPU |
| `--model-dir DIR` | see above | IndicOCR model directory |

Folders are searched recursively; unsupported files are listed and skipped. Progress goes to stderr; a one-line result per
document goes to stdout. The exit code is 1 if any document failed (the batch always finishes), otherwise 0.
Console output is forced to UTF-8, so Devanagari file names print correctly.

### LLM-as-judge (optional, sends images to the Anthropic API)

```powershell
docpipe process pdfs\ --out out\ --deterministic
docpipe judge out\ --pdfs pdfs\ --pages-per-pdf 3
```

For each PDF, `judge` picks up to 3 OCR pages spread evenly (first, middle, last), sends the page image and IndicOCR's text to
Claude Sonnet 5, and writes `judge_report.json` (default `output\judge_output\`). `how_to_read` and `overall_summary` come
first, and the OVERALL result is also printed to the console. Field names say what they are:
  `llm_quality_rating_out_of_10` (1 = unusable, 10 = perfect; averaged as `average_llm_quality_rating_out_of_10`),
  `llm_verdict` (good / acceptable / poor), `character_accuracy_percent`, `word_accuracy_percent` (and the matching
  `*_error_rate_percent`), `reading_order_correct`, `text_on_page_missing_from_ocr`, `misread_text` (each item has
  `ocr_text_says` and `page_actually_says`), `text_in_ocr_but_not_on_page`, `llm_judge_comments`, `llm_transcription`,
  and per call `llm_call_latency_seconds`, `llm_input_tokens`, `llm_output_tokens`. The structure is `judge_model_name`,
  `max_pages_judged_per_pdf`, `overall_summary`, then `pdfs[]` with `pdf_name`, `source_pdf_path`, `total_ocr_pages_in_pdf`,
  `judged_pages[]` (each with `page_number`) and, on failure, `error_message`.

Accuracy percentages are measured against the LLM's own transcription, not human ground truth. It needs `pip install anthropic` and
`ANTHROPIC_API_KEY` in the environment. **Page images leave your machine**: use it only on non-sensitive documents. The judge
is an LLM, not ground truth; spot-check its verdicts, especially for Hindi and Urdu.

As a library: `from docpipe.pipeline import process_batch; from docpipe.config import Options`.

## Input and output folders

Run everything from the project root. `input\` (put documents here) and `output\` are the defaults: OCR results go to `output\ocr_output\`, the judge report to `output\judge_output\`, so
these work with no paths:

```powershell
docpipe process                        # input\ -> output\ocr_output\
docpipe judge --pages-per-pdf 3        # judges output\ocr_output\ against input\, writes output\judge_output\judge_report.json
python scripts\fetch_sample_pdfs.py    # optional: download a few small real scanned PDFs into input\
```

Both folders are tracked by git through a `.gitkeep`; their contents are ignored so documents and results are never pushed.

## Output

For an input named `report.pdf`, `out\report.pdf\` contains only `document.json` (the folder is named after the full file name so that `a.pdf`
and `a.docx` do not collide):

- **`document.json`**: UTF-8, Unicode kept as characters (`ensure_ascii=False`).

| top-level field | meaning |
|---|---|
| `source`, `sha256`, `format` | the input as given, its SHA-256, the detected format |
| `status` | `ok`, `partial` (some units failed, see their `status`) or `error` (`error_type`, `message`, no units) |
| `unit_count`, `units[]` | see below |
| `warnings[]` | document-level notes (skipped tiny images, replaced characters, ...) |
| `timings` | `total_seconds`, `ocr_seconds`, `model_load_seconds`, `peak_rss_mb` |
| `tool_versions` | docpipe, Python, the parsing libraries used, and the OCR engine (device, dtype, model revision) when OCR ran |
| `model_attribution` | `Built with IndicOCR from Bodhan AI / AI4Bharat.` |

Each unit: `index` (0-based position), `kind` (`page`, `sheet`, `section`, `image`), `origin` (`native` or `ocr`), **`reason`**
(why that path was taken), `status`, `text`, `markdown`, `warnings[]`; plus `page` (1-based, PDF/TIFF/PPTX), `name` (sheet or
image name), and for PDF pages `page_width_pt`, `page_height_pt` and `text_layer` (the metrics behind the decision).
**OCR units** also carry `render_dpi` (`null` for image files, which are not rendered), `width_px`, `height_px` and `blocks[]`:
IndicOCR's block records unchanged (`order`, `label`, `type`, `bbox_xyxy`, `conf`, `text`). Boxes are in the pixels of
`width_px` x `height_px`, so for a PDF page multiply by `72 / render_dpi` to get points. Blocks IndicOCR detects but does not read
(headers, footers, figures, ...) stay in `blocks` with `text: ""`.

Example reasons: `no text layer`, `text layer valid (131 characters)`,
`text layer failed validity check (private-use characters 100%)`, `OCR forced by --force-ocr`, `blank page (no text, no images)`.

## Supported formats

| Format | Handling |
|---|---|
| PDF | per page: text layer if it passes the validity check, otherwise rendered and OCR'd (`--force-ocr` overrides) |
| PNG, JPEG, TIFF (multi-page), BMP, WEBP | EXIF rotation applied, converted to RGB (transparency flattened onto white), size-checked, OCR'd |
| DOCX | native paragraphs (headings, lists) and tables in document order; each embedded image OCR'd where it appears |
| XLSX | one unit per sheet, cached formula values; embedded images OCR'd |
| PPTX | native slide text and tables in slide order; pictures OCR'd |
| Markdown | native text; local and `data:` image links OCR'd; remote images are never fetched |
| DOC, XLS, PPT | reported `unsupported: needs LibreOffice` unless `soffice` is on PATH, then converted first |
| CSV, HTML, JSON, TXT, XML, ZIP, email, GIF | not supported; reported |

## The PDF text-layer decision

Per page, in this order (all thresholds in `quality.py`, recorded per unit in `text_layer`):

1. `--force-ocr` -> OCR.
2. No text: OCR if images cover at least 5% of the page or there are 50+ vector paths (outlined text); otherwise a blank native page.
3. Fewer than 20 characters, or fewer than 100 with images covering at least half the page: OCR if the page has image content.
4. Otherwise the text is checked and used only if it passes: at most 2% private-use / U+FFFD / control characters; at most 15%
   characters outside the supported scripts and common punctuation; no combining marks detached from their base letter and no
   Indic words containing stray non-Indic letters (the damage measured on a MuPDF-generated Hindi PDF); plausible word lengths;
   no known legacy Indic font (KrutiDev, DevLys, Chanakya, ...).
   A page that is mostly an image but has a dense, valid-looking text layer is trusted and given a warning, because that layer
   is usually a scanner's own OCR and cannot be verified.

Pages where the text layer is used are read by PyMuPDF with ligatures expanded and NBSP turned into spaces.

## Measured on this machine

Windows 11, Intel i5-1135G7 (4 cores / 8 threads), 15.7 GB RAM, no GPU, torch 2.14.0+cpu, transformers 5.17.0.
Full numbers are in `progress.txt`.

- OCR page (layout + recognizer, fp32): median 9.8 s over 20 pages (5-23 s); first model load 5-18 s.
- Peak RAM about 5.5 GB (float32; bfloat16 was 3.5 GB but 1.65x slower on this CPU).
- Render dpi: no accuracy difference from 100 to 300 dpi on the generated pages; 300 dpi is about 40% slower.
- Accuracy on a real scanned 1972 fax page (1 page, English): CER 0.6%, WER 1.0% against a Claude Sonnet 5
  transcription; the handwritten signature was missed. Generated Hindi/English pages: CER 0.0000.

`docpipe evaluate document.json --reference reference.txt` prints CER, WER, token F1, throughput and review flags.
`docpipe.metrics` also has field accuracy, exact match, IoU, reading-order distance and STP/HITL rates.

## Known limits

- **CPU speed.** IndicOCR's recognizer in this repo is the slow reference path (`HfRecognizer`, "orders of magnitude slower"
  than the vLLM path the model card benchmarks). Plan on tens of seconds per OCR page; native pages take milliseconds.
- **Reading order** can be wrong on complex multi-column layouts (an IndicOCR limitation). Native PDF text follows the file's
  own content order.
- **Handwriting** recognition is weak (IndicOCR's own statement); nothing here tunes for it.
- **Text layers cannot be proven right.** The checks catch the failures seen in practice, but ASCII-mapped legacy fonts are
  caught only by font name, Arabic-script (Urdu, Kashmiri, Sindhi) layers are accepted with a warning without a structural check,
  and text layers in other scripts (for example Chinese) are sent to OCR, which cannot read them. Use `--force-ocr` when in doubt.
- **Text inside pictures on a native PDF page is not OCR'd**: a page with a valid text layer is read as text only.
- DOCX headers, footers, footnotes and comments are not read; images inside table cells are OCR'd after the table.
  XLSX charts are not read. PPTX speaker notes are not read.
- A block longer than IndicOCR's 2048-token limit is cut off; the unit then carries a warning.
- OCR output was measured on clean, generated pages. Real scans will be worse.

## Tests

```powershell
.\.venv\Scripts\python -m pytest              # fast tier: fake OCR backend, no weights, no torch
.\.venv\Scripts\python -m pytest -m model     # model tier: real weights, several minutes on CPU
.\.venv\Scripts\python tests\make_fixtures.py fixtures   # write the generated fixtures to disk
```

Fixtures are generated by code (Hindi in Nirmala UI from `C:\Windows\Fonts`); nothing is downloaded or checked in.
Accuracy is character error rate (Levenshtein on NFC text, whitespace collapsed, over reference length); thresholds come from the
measured baseline and must not be loosened to make a run pass.

## License and attribution

docpipe's own code is provided as-is. The IndicOCR model is released under the
[Indic Open Model License v1.0](https://huggingface.co/bodhan-ai/indic-ocr/blob/main/Bodhan_AI_Open_Model_License.md):
internal use is free; hosting it for third parties needs Bodhan AI's prior written approval, and the prohibited uses in its
section 10 apply to everyone. Personal data in your documents remains your responsibility under India's DPDP Act.

**Built with IndicOCR from Bodhan AI / AI4Bharat.** (Also printed by `docpipe --version` and stored in every `document.json`.)
