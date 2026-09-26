"""Extract text from a PDF, including scanned ones.

A PDF made with OCR usually carries a hidden text layer, which is read directly
(fast, exact). Pages without a usable text layer (pure scans) fall back to OCR
when --ocr is given.

Usage:
    python scripts/extract_pdf_text.py input.pdf                 # text layer only
    python scripts/extract_pdf_text.py input.pdf -o out.txt      # write to a file
    python scripts/extract_pdf_text.py scan.pdf --ocr --lang ron+eng
    python scripts/extract_pdf_text.py doc.pdf --force-ocr       # ignore the existing text layer

OCR needs: pip install pytesseract pypdfium2, plus the Tesseract program
(https://github.com/UB-Mannheim/tesseract/wiki) with the language data, e.g. "ron".
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from pypdf import PdfReader

MIN_TEXT_CHARS = 20  # fewer characters than this on a page means "no text layer"
WINDOWS_TESSERACT = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")


def _configure_tesseract(pytesseract, tesseract_cmd: str | None) -> None:
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    elif not shutil.which("tesseract") and WINDOWS_TESSERACT.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(WINDOWS_TESSERACT)


def _ocr_page(args: tuple[Path, int, str, int, str | None]) -> str:
    pdf_path, page_index, lang, dpi, tesseract_cmd = args
    # One Tesseract thread per process: parallelism comes from processing pages side by side.
    os.environ["OMP_THREAD_LIMIT"] = "1"
    try:
        import pypdfium2
        import pytesseract
    except ImportError as exc:
        raise SystemExit(f"OCR indisponibil ({exc.name} lipsește). Rulați: pip install pytesseract pypdfium2") from exc
    _configure_tesseract(pytesseract, tesseract_cmd)
    pdf = pypdfium2.PdfDocument(str(pdf_path))
    try:
        image = pdf[page_index].render(scale=dpi / 72, grayscale=True).to_pil()
        return pytesseract.image_to_string(image, lang=lang).strip()
    finally:
        pdf.close()


def extract_text(
    pdf_path: Path,
    ocr: bool = False,
    lang: str = "ron+eng",
    dpi: int = 200,
    force_ocr: bool = False,
    tesseract_cmd: str | None = None,
    workers: int | None = None,
) -> str:
    reader = PdfReader(str(pdf_path))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    to_ocr = [
        index for index, text in enumerate(pages)
        if force_ocr or (ocr and len(text) < MIN_TEXT_CHARS)
    ]
    if to_ocr:
        workers = max(1, min(workers or os.cpu_count() or 1, len(to_ocr)))
        print(f"OCR pe {len(to_ocr)} pagini, {workers} procese în paralel...", file=sys.stderr)
        jobs = [(pdf_path, index, lang, dpi, tesseract_cmd) for index in to_ocr]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for done, (index, text) in enumerate(zip(to_ocr, pool.map(_ocr_page, jobs)), start=1):
                pages[index] = text
                print(f"  {done}/{len(to_ocr)} (pagina {index + 1})", file=sys.stderr)
    return "\n\n".join(pages)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Romanian diacritics on Windows consoles
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path, help="PDF-ul de citit")
    parser.add_argument("-o", "--output", type=Path, help="fișier .txt de ieșire (implicit: stdout)")
    parser.add_argument("--ocr", action="store_true", help="rulează OCR pe paginile fără strat de text")
    parser.add_argument("--force-ocr", action="store_true", help="rulează OCR pe toate paginile, ignorând stratul de text")
    parser.add_argument("--tesseract-cmd", help="calea către tesseract.exe, dacă nu e în PATH")
    parser.add_argument("--lang", default="ron+eng", help="limbile Tesseract (implicit: ron+eng)")
    parser.add_argument("--dpi", type=int, default=200, help="rezoluția pentru OCR; mai mic = mai rapid (implicit: 200)")
    parser.add_argument("--workers", type=int, help="numărul de procese paralele (implicit: nr. de nuclee)")
    args = parser.parse_args()

    if not args.pdf.is_file():
        raise SystemExit(f"Fișierul nu există: {args.pdf}")
    text = extract_text(args.pdf, args.ocr, args.lang, args.dpi, args.force_ocr, args.tesseract_cmd, args.workers)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Scris: {args.output} ({len(text)} caractere)", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
