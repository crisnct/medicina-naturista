"""Recognize scanned page images with PaddleOCR (PP-OCRv6 medium, on the GPU).

PaddleOCR cannot share the project's environment (it needs numpy<2.4), so it runs in `.venv-ocr`
as a child process (pdf_paddle_worker.py), started on the first page that needs it and stopped,
releasing its GPU memory, when the session closes. Install it from requirements-ocr.txt.

On the 2026-11-27 benchmark (aiWork/ocr-bench/results.md) it made 30 errors per 1000 words on
hand-checked pages, against 72 for the vision model and 259 for Tesseract. Nothing falls back to
another engine: without the environment, the models or a free GPU the run stops with the cause.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import IO, NamedTuple

if __package__:
    from .script_logging import log_call
else:
    from script_logging import log_call


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("pdf_paddle_worker.py")
INTERPRETER = (
    PROJECT_ROOT / ".venv-ocr" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
)
# Rows below this score are specks and stains read as text; CJK characters come from the same
# specks ("参", "十"), never from a Romanian or English book.
MIN_ROW_SCORE = 0.5
CJK = re.compile(r"[⺀-鿿가-힯豈-﫿＀-￯]")
# Calibrated on the 45 benchmark pages: every page whose letter-weighted mean row score was below
# 0.975, or with more than 2% of its letters in rows scored below 0.90, was a degraded print or a
# handwritten slide (54-136 errors per 1000 words); every other page passed. Word-level checks
# (dictionary, split or merged words) did not separate good pages from bad ones.
MIN_MEAN_SCORE = 0.975
LOW_ROW_SCORE = 0.90
MAX_LOW_SHARE = 0.02
GPU_FULL = (
    "GPU-ul nu are memorie liberă pentru PaddleOCR (folosește până la 6 GB); oprește modelele "
    "încărcate în Ollama sau vLLM și pornește din nou extragerea."
)


class Image(NamedTuple):
    width: int
    height: int
    # Raw RGB bytes, row by row: no PNG encoding on either side of the pipe.
    rgb: bytes


class Row(NamedTuple):
    text: str
    # Pixels of the image sent to recognize: x0, y0, x1, y1.
    box: tuple[float, float, float, float]
    score: float


@dataclass(frozen=True, slots=True)
class Confidence:
    mean: float
    low_share: float

    @property
    def uncertain(self) -> bool:
        return self.mean < MIN_MEAN_SCORE or self.low_share > MAX_LOW_SHARE


# Measured on every recognized row, before clean_rows, as in the calibration.
@log_call
def measure(rows: list[Row]) -> Confidence:
    weights = [sum(c.isalnum() for c in row.text) for row in rows]
    total = sum(weights)
    if not total:
        # A blank page is reported as having no text, not as an uncertain one.
        return Confidence(1.0, 0.0)
    mean = sum(row.score * weight for row, weight in zip(rows, weights)) / total
    low = sum(weight for row, weight in zip(rows, weights) if row.score < LOW_ROW_SCORE)
    return Confidence(round(mean, 4), round(low / total, 4))


@log_call
def clean_rows(rows: list[Row]) -> list[Row]:
    kept = []
    for row in rows:
        text = " ".join(CJK.sub("", row.text).split())
        if text and row.score >= MIN_ROW_SCORE:
            kept.append(row._replace(text=text))
    return kept


class PaddleSession:
    """One worker process per extraction run; every failure stops the run with its cause."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._log: IO[bytes] | None = None
        # One request at a time on the pipe: pages are read on a background thread, and a turned
        # page is read again from the main thread.
        self._lock = threading.Lock()

    def __enter__(self) -> PaddleSession:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _tail(self) -> str:
        if self._log is None:
            return ""
        self._log.seek(0)
        lines = self._log.read().decode("utf-8", "replace").strip().splitlines()
        return " | ".join(lines[-5:])

    @log_call
    def _start(self) -> subprocess.Popen[bytes]:
        if not INTERPRETER.is_file():
            raise RuntimeError(
                f"PaddleOCR nu este instalat: lipsește {INTERPRETER}. Pașii sunt în "
                "requirements-ocr.txt."
            )
        LOGGER.info("Pornesc PaddleOCR (%s).", INTERPRETER.parent.parent.name)
        # Paddle's own log goes to a temporary file and is quoted only when the worker fails.
        self._log = tempfile.TemporaryFile()
        # -I keeps this project's PYTHONPATH and current directory out of the other environment.
        self._process = subprocess.Popen(
            [str(INTERPRETER), "-I", str(WORKER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._log,
        )
        self._receive()
        return self._process

    def _receive(self) -> dict:
        assert self._process is not None and self._process.stdout is not None
        line = self._process.stdout.readline()
        if not line:
            code = self._process.wait()
            raise RuntimeError(f"PaddleOCR s-a oprit (cod {code}): {self._tail()}")
        reply = json.loads(line)
        if "error" in reply:
            if reply.get("memory"):
                raise RuntimeError(GPU_FULL)
            raise RuntimeError(f"PaddleOCR: {reply['error']}")
        return reply

    def _call(self, operation: str, image: Image) -> dict:
        with self._lock:
            process = self._process or self._start()
            assert process.stdin is not None
            header = {
                "op": operation,
                "width": image.width,
                "height": image.height,
                "size": len(image.rgb),
            }
            try:
                process.stdin.write(json.dumps(header).encode("ascii") + b"\n")
                process.stdin.write(image.rgb)
                process.stdin.flush()
            except OSError as exc:
                raise RuntimeError(f"PaddleOCR nu mai răspunde ({exc}): {self._tail()}") from exc
            return self._receive()

    @staticmethod
    def _rows(reply: dict) -> list[Row]:
        return [Row(text, tuple(box), score) for text, box, score in reply["rows"]]

    @log_call
    def read(self, image: Image) -> tuple[int, list[Row] | None]:
        """The counter-clockwise turn (0/90/180/270) that makes a scanned page upright and, when
        it is already upright, its rows; a turned page must be turned and sent to `recognize`."""
        reply = self._call("read", image)
        angle = int(reply["angle"]) % 360
        return angle, None if angle else self._rows(reply)

    @log_call
    def recognize(self, image: Image) -> list[Row]:
        """Every recognized text row, with its box in image pixels and its score."""
        return self._rows(self._call("recognize", image))

    # The worker exits when its input closes, which releases the GPU memory it holds.
    @log_call
    def close(self) -> None:
        process, self._process = self._process, None
        try:
            if process is not None:
                if process.stdin is not None:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass
                try:
                    process.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    LOGGER.warning("PaddleOCR nu s-a oprit în 60 s; procesul este închis forțat.")
                    process.kill()
                    process.wait()
                if process.stdout is not None:
                    process.stdout.close()
        finally:
            if self._log is not None:
                self._log.close()
                self._log = None
