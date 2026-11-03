"""Transcribe a scanned page image to Markdown with a local vision model served by Ollama.

Every failure is reported as None so the caller can fall back to Tesseract; nothing leaves
the machine and no page text is logged.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from typing import Any

import httpx
import numpy as np
import pymupdf

if __package__:
    from .pdf_headings import demote_run_in, drop_rules
    from .script_logging import log_call
else:
    from pdf_headings import demote_run_in, drop_rules
    from script_logging import log_call


LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL = "qwen3.5:9b"
RENDER_DPI = 170
# The printed area is found on a small preview; scan borders and the white margins around the
# text are not sent, which cuts the image from about 3000 tokens to 1200 at the same sharpness.
PREVIEW_DPI = 50
PREVIEW_BORDER = 0.04
INK_LEVEL = 150
RULE_SHARE = 0.45
CROP_PADDING = 12.0
LANGUAGES = {"ron": "Romanian", "eng": "English"}
# One page is a short bounded task, so thinking is off; num_predict leaves room for a dense page.
REQUEST_OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_predict": 4096}
# The model stays loaded between pages and is released explicitly when the run ends.
KEEP_ALIVE = "30m"
TIMEOUT = httpx.Timeout(600.0, connect=5.0)
PROMPT = (
    "Transcribe this scanned book page ({language}) into Markdown. Copy the text exactly as "
    "printed, keep the original spelling, and do not translate, summarize, correct or add "
    "anything. Use '##' for main headings and '###' for subheadings, never '#'. Use '-' for "
    "list items; use bold and italic only where the print shows them. Join the lines of a "
    "paragraph and repair words split by a hyphen at a line end. Omit the running header, the "
    "footer and the page number. Output only the Markdown."
)
FENCE = re.compile(r"\A```[a-z]*\s*\n|\n```\s*\Z")
HYPHEN_BREAK = re.compile(r"(\w)-\s+(\w)")
TOP_HEADING = re.compile(r"^# ", re.M)


# Only a lowercase continuation proves a word was split by the line break.
def _join_break(match: re.Match[str]) -> str:
    return match.group(1) + match.group(2) if match.group(2).islower() else match.group(0)


# The book title is the only top-level heading of the output file. Decorative rules and text
# that the model made a heading although it is a paragraph are cleaned here, so they never reach
# the heading levels.
def tidy_markdown(text: str) -> str:
    text = FENCE.sub("", text.strip()).strip()
    text = TOP_HEADING.sub("## ", HYPHEN_BREAK.sub(_join_break, text))
    return demote_run_in(drop_rules(text), 2)


# Rectangle around the printed area, or the whole page when it shows no ink at all.
def _printed_area(page: pymupdf.Page) -> pymupdf.Rect:
    preview = page.get_pixmap(dpi=PREVIEW_DPI, colorspace=pymupdf.csGRAY)
    gray = np.frombuffer(preview.samples, dtype=np.uint8).reshape(preview.height, preview.width)
    top, left = int(preview.height * PREVIEW_BORDER), int(preview.width * PREVIEW_BORDER)
    ink = gray[top : preview.height - top, left : preview.width - left] < INK_LEVEL
    # Long dark rules are scanner shadows, not text.
    ink[:, ink.mean(axis=0) > RULE_SHARE] = False
    ink[ink.mean(axis=1) > RULE_SHARE, :] = False
    rows, columns = np.nonzero(ink)
    if not len(columns):
        return page.rect
    scale = 72 / PREVIEW_DPI
    area = pymupdf.Rect(
        (columns.min() + left) * scale - CROP_PADDING,
        (rows.min() + top) * scale - CROP_PADDING,
        (columns.max() + 1 + left) * scale + CROP_PADDING,
        (rows.max() + 1 + top) * scale + CROP_PADDING,
    )
    return area & page.rect


class VisionSession:
    """Checks the Ollama service on first use; afterwards a failure only affects its page."""

    def __init__(self, model: str, language: str) -> None:
        base = os.environ.get("OLLAMA_API_BASE") or "http://localhost:11434/v1"
        self._url = base.rstrip("/").removesuffix("/v1")
        self._model = model
        self._language = LANGUAGES.get(language, language)
        self._http = httpx.Client(trust_env=False, follow_redirects=False)
        self._checked = False
        self._available = False

    def __enter__(self) -> VisionSession:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @log_call
    def _check(self) -> bool:
        wanted = self._model if ":" in self._model else f"{self._model}:latest"
        try:
            response = self._http.get(self._url + "/api/tags", timeout=TIMEOUT)
            response.raise_for_status()
            installed = {item.get("name") for item in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            LOGGER.warning("Vision service unavailable (%s); Tesseract is used instead.", exc)
            return False
        if wanted not in installed:
            LOGGER.warning("Vision model %s is not installed; Tesseract is used instead.", wanted)
            return False
        return True

    # Called from the main thread before any worker starts, so the check runs exactly once.
    @log_call
    def available(self) -> bool:
        if not self._checked:
            self._checked, self._available = True, self._check()
        return self._available

    # PyMuPDF pages are not thread-safe, so rendering stays on the caller's thread and only the
    # network round trip runs on workers.
    @staticmethod
    def render(page: pymupdf.Page) -> bytes:
        return page.get_pixmap(dpi=RENDER_DPI, clip=_printed_area(page)).tobytes("png")

    @log_call
    def transcribe_image(self, image: bytes) -> str | None:
        """Markdown for a rendered page, or None when the service or its answer cannot be used.

        Safe to call from several threads: it only uses the shared HTTP client."""
        message: dict[str, Any] = {
            "role": "user",
            "content": PROMPT.format(language=self._language),
            "images": [base64.b64encode(image).decode("ascii")],
        }
        try:
            response = self._http.post(
                self._url + "/api/chat",
                json={
                    "model": self._model,
                    "messages": [message],
                    "stream": False,
                    "think": False,
                    "keep_alive": KEEP_ALIVE,
                    "options": REQUEST_OPTIONS,
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            result = response.json()
            content = result["message"]["content"]
            truncated = result.get("done_reason") == "length"
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            LOGGER.warning("Vision transcription failed (%s).", type(exc).__name__)
            return None
        if truncated or not isinstance(content, str) or not content.strip():
            LOGGER.warning("Vision transcription was empty or cut off.")
            return None
        return tidy_markdown(content)

    # Releases the GPU memory the model holds; a failure here must not hide the run's outcome.
    @log_call
    def close(self) -> None:
        try:
            if self._available:
                self._http.post(
                    self._url + "/api/generate",
                    json={"model": self._model, "keep_alive": 0, "stream": False},
                    timeout=httpx.Timeout(30.0, connect=5.0),
                )
        except httpx.HTTPError as exc:
            LOGGER.warning("Vision model release failed (%s).", type(exc).__name__)
        finally:
            self._http.close()
