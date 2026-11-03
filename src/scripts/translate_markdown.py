r"""Translate every Markdown file of a folder from Romanian to English with a local Ollama model.

Only prose reaches the model. Front matter, fenced code, HTML comments (the PDF page
markers), table separators, Markdown markers, inline code and URLs are copied through
unchanged, so the output keeps the layout of the source. Nothing leaves the machine.

Requires a running Ollama with the model pulled: ollama pull translategemma:4b

    PYTHONPATH=src python src/scripts/translate_markdown.py "<folder>" [-o OUTPUT_FOLDER]

Without --output each file is replaced by its translation, and only once the whole file is
translated: the translation is staged in a temporary file next to the original, which the
atomic replacement then consumes. This destroys the Romanian text, so work on a copy; the
Romanian corpus under documents/ro is refused. With --output the sources are kept.

Files are handled one at a time: translate, replace, then rename the file to its English
name. A folder that directly contains Markdown files is renamed as soon as nothing below it
is still queued (--keep-names skips all renaming); names an earlier run produced are kept.

A file with a segment the model cannot translate reliably is not written (the original stays
intact) unless --allow-partial is given, and the exit code is 1, so an incomplete result is
never mistaken for a finished one. Progress, percent and an mm:ss ETA for the whole folder
(every file still to translate, plus the names) are logged every --progress-interval seconds
(default 10) from a background thread.

Two JSON-lines files outside the repository (next to --cache, default
~/.cache/medicina-naturista/) make a run resumable: accepted segments, so an interrupted run
continues at the segment where it stopped, and a digest of every file already replaced, so
a finished file is never translated twice. They hold corpus text: keep them out of git and
delete them when the corpus is no longer needed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import httpx

if __package__:
    from .script_files import _commit_outputs, _remove_temp, _temporary_path
    from .script_logging import log_call
else:
    from script_files import _commit_outputs, _remove_temp, _temporary_path
    from script_logging import log_call

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL = "translategemma:4b"
DEFAULT_HOST = "http://localhost:11434"
SYSTEM_PROMPT = (
    "You are a professional Romanian (ro) to English (en) translator. Your goal is to "
    "accurately convey the meaning and nuances of the original Romanian text while adhering "
    "to English grammar, vocabulary, and cultural sensitivities. Produce only the English "
    "translation, without any additional explanations or commentary. Please translate the "
    "following Romanian text into English:"
)
DEFAULT_PROGRESS_INTERVAL = 10
# A segment of 1800 characters plus its answer needs about 2K tokens; the model's own maximum
# (131072) would only reserve gigabytes of KV cache that translation never touches.
DEFAULT_NUM_CTX = 4096
# Prompt, template and slack on top of the characters that input and answer can occupy.
CONTEXT_RESERVE = 512
# Shorter measurements of the generation speed are too noisy to show as an ETA.
MIN_ETA_SECONDS = 2.0
# After Ctrl+C the worker gets this long to stop at a safe point before the process exits anyway.
INTERRUPT_GRACE_SECONDS = 5.0
# A request that makes Ollama load the model for longer than this is worth a warning.
LOAD_WARNING_SECONDS = 2.0
MAX_NAME_CHARS = 120
# Staging files live next to their destination; this prefix also identifies stale ones.
TEMP_PREFIX = ".translate-"
DEFAULT_CACHE = Path.home() / ".cache" / "medicina-naturista" / "translate_markdown.jsonl"

_LETTER = re.compile(r"[^\W\d_]")
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PLACEHOLDER = re.compile(r"\[\[(\d+)\]\]")
# Spans the model must not touch; each becomes a numbered placeholder and is restored after.
_PROTECTED = re.compile(
    "|".join(
        (
            r"`+[^`\n]+`+",
            r"<!--.*?-->",
            r"</?[A-Za-z][^<>\n]*>",
            r"(?<=\]\()[^)\n]*(?=\))",
            r"https?://[^\s)\]>]+",
        )
    )
)
_WRAPPING_FENCE = re.compile(r"\A```[\w-]*\n(.*?)\n```\Z", re.DOTALL)

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_VERBATIM = re.compile(
    "|".join(
        (
            r"\s*<!--.*-->\s*",
            r" {0,3}(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})",
            r"\s*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?\s*",
            r" {0,3}=+[ \t]*",
            r""" {0,3}\[[^\]^][^\]]*\]:[ \t]+\S+(?:[ \t]+(?:"[^"]*"|'[^']*'|\([^)]*\)))?[ \t]*""",
        )
    )
)
_YAML_LINE = re.compile(r"^(?:[\w.-]+\s*:|\s+\S|\s*-\s|\s*#|\s*$)")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_PIPE = re.compile(r"(?<!\\)\|")
_HEADING = re.compile(r"^( {0,3}#{1,6}[ \t]+)(.*)$")
_LIST_ITEM = re.compile(r"^(\s*(?:[-*+]|\d{1,9}[.)])[ \t]+(?:\[[ xX]\][ \t]+)?)(.*)$")
_QUOTE = re.compile(r"^(\s{0,3}(?:>[ \t]?)+)(.*)$")


class OllamaError(RuntimeError):
    """Ollama is unreachable or answered in a way no retry can fix."""


@dataclass(slots=True)
class _Paragraph:
    kind: str
    first: str
    rest: str
    lines: list[str]
    line: int = 0


# Collapses model line breaks where Markdown requires a single physical line.
def _one_line(text: str) -> str:
    return " ".join(text.split())


# YAML front matter is kept verbatim; a pair of horizontal rules around prose is not one.
def _front_matter_end(lines: list[str]) -> int:
    if not lines or lines[0].strip() != "---":
        return 0
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            return index + 1
        if not _YAML_LINE.match(lines[index]):
            return 0
    return 0


def _closes_fence(line: str, fence: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= len(fence) and set(stripped) == {fence[0]}


def _translate_cell(cell: str, translate: Callable[[str], str]) -> str:
    body = cell.strip()
    if not body:
        return cell
    leading = cell[: len(cell) - len(cell.lstrip())]
    trailing = cell[len(cell.rstrip()) :]
    translated = _PIPE.sub(r"\\|", _one_line(translate(body)))
    return leading + translated + trailing


# Cells are translated one by one: a pipe the model adds or drops would shift every column.
def _translate_row(line: str, translate: Callable[[str], str]) -> str:
    return "|".join(_translate_cell(cell, translate) for cell in _PIPE.split(line))


def _render(paragraph: _Paragraph, translate: Callable[[str], str]) -> list[str]:
    translated = translate("\n".join(paragraph.lines)).split("\n")
    return [paragraph.first + translated[0]] + [
        paragraph.rest + line if line else paragraph.rest.rstrip() for line in translated[1:]
    ]


@log_call
def translate_markdown(
    text: str,
    translate: Callable[[str], str],
    locate: Callable[[int | None], None] | None = None,
) -> str:
    """Translate the prose of `text`; structural lines pass through unchanged."""
    lines = text.split("\n")
    start = _front_matter_end(lines)
    out: list[str] = lines[:start]
    paragraph: _Paragraph | None = None
    fence: str | None = None
    comment_open = False

    def flush() -> None:
        nonlocal paragraph
        if paragraph is not None:
            if locate:
                locate(paragraph.line)
            out.extend(_render(paragraph, translate))
            paragraph = None

    for number, line in enumerate(lines[start:], start=start + 1):
        if fence is not None:
            out.append(line)
            if _closes_fence(line, fence):
                fence = None
            continue
        if comment_open:
            out.append(line)
            comment_open = "-->" not in line
            continue
        if not line.strip():
            flush()
            out.append(line)
            continue
        opening = _FENCE.match(line)
        if opening:
            flush()
            fence = opening.group(1)
            out.append(line)
            continue
        if "<!--" in line and "-->" not in line.split("<!--", 1)[1]:
            flush()
            comment_open = True
            out.append(line)
            continue
        if _VERBATIM.fullmatch(line):
            flush()
            out.append(line)
            continue
        if _TABLE_ROW.match(line):
            flush()
            if locate:
                locate(number)
            out.append(_translate_row(line, translate))
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            if locate:
                locate(number)
            out.append(heading.group(1) + _one_line(translate(heading.group(2))))
            continue
        item = _LIST_ITEM.match(line)
        if item:
            flush()
            paragraph = _Paragraph(
                "list", item.group(1), " " * len(item.group(1)), [item.group(2)], number
            )
            continue
        quote = _QUOTE.match(line)
        if quote:
            prefix, body = quote.groups()
            if paragraph is not None and paragraph.kind == "quote" and paragraph.first == prefix:
                paragraph.lines.append(body)
            else:
                flush()
                paragraph = _Paragraph("quote", prefix, prefix, [body], number)
            continue
        if paragraph is not None:
            paragraph.lines.append(line.strip())
        else:
            indent = line[: len(line) - len(line.lstrip())]
            paragraph = _Paragraph("plain", indent, indent, [line.strip()], number)
    flush()
    return "\n".join(out)


def _mask(text: str) -> tuple[str, list[str]]:
    protected: list[str] = []

    def hide(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"[[{len(protected) - 1}]]"

    return _PROTECTED.sub(hide, text), protected


def _unmask(text: str, protected: list[str]) -> str:
    return _PLACEHOLDER.sub(lambda match: protected[int(match.group(1))], text)


_BOUNDARIES = (
    re.compile(r"(?<=[.!?…])(\s+)"),
    re.compile(r"(?<=[,;:])(\s+)"),
    re.compile(r"(\s+)"),
)


# Alternating text and separator with every text at most `limit` long. Sentence boundaries
# come first, then clauses, then words; only a single word longer than the limit is cut.
def _fit(text: str, limit: int, level: int = 0) -> list[str]:
    if len(text) <= limit:
        return [text]
    if level == len(_BOUNDARIES):
        cuts = [text[start : start + limit] for start in range(0, len(text), limit)]
        return [part for cut in cuts for part in (cut, "")][:-1]
    parts = _BOUNDARIES[level].split(text)
    if len(parts) == 1:
        return _fit(text, limit, level + 1)
    fitted: list[str] = []
    for index, part in enumerate(parts):
        if index % 2:
            fitted.append(part)
        else:
            fitted.extend(_fit(part, limit, level + 1))
    return fitted


# Chunks of at most `limit` characters, each with the whitespace that preceded it in the source.
# The limit is the contract with the model context: no request may exceed it.
def _split(text: str, limit: int) -> list[tuple[str, str]]:
    parts = _fit(text, limit)
    chunks = [("", parts[0])]
    for separator, piece in zip(parts[1::2], parts[2::2], strict=True):
        before, current = chunks[-1]
        if len(current) + len(separator) + len(piece) <= limit:
            chunks[-1] = (before, current + separator + piece)
        else:
            chunks.append((separator, piece))
    return chunks


# Ollama's own message from a JSON error body; it names the problem (memory, context, model)
# without echoing the prompt.
def _error_text(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"])[:300]
    except (ValueError, KeyError, TypeError):
        return response.text[:200] or "no error message"


def _cache_key(model: str, chunk: str) -> str:
    return hashlib.sha256(f"{model}\0{SYSTEM_PROMPT}\0{chunk}".encode()).hexdigest()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def format_duration(seconds: float) -> str:
    """mm:ss; minutes are not wrapped, so 2 h 15 min reads 135:00."""
    total = max(0, round(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


class PersistentMap:
    """String map appended to a JSON-lines file entry by entry, or memory-only without a path."""

    def __init__(self, path: Path | None) -> None:
        self._entries: dict[str, str] = {}
        self._stream: TextIO | None = None
        self.loaded = 0
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        torn = False
        if path.exists() and path.stat().st_size:
            self._load(path)
            with path.open("rb") as raw:
                raw.seek(-1, os.SEEK_END)
                torn = raw.read(1) != b"\n"
        else:
            # Corpus text: readable by the owner only where the platform honours the mode.
            path.touch(mode=0o600)
        self._stream = path.open("a", encoding="utf-8")
        if torn:
            # A crash left a half line; end it so the next entry starts on its own line.
            self._stream.write("\n")

    def _load(self, path: Path) -> None:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    entry = json.loads(line)
                    self._entries[str(entry["k"])] = str(entry["t"])
                except (ValueError, KeyError, TypeError):
                    # Only a torn line can fail here; every complete line before it is valid.
                    continue
        self.loaded = len(self._entries)

    def get(self, key: str) -> str | None:
        return self._entries.get(key)

    def put(self, key: str, text: str) -> None:
        self._entries[key] = text
        if self._stream is not None:
            self._stream.write(json.dumps({"k": key, "t": text}, ensure_ascii=False) + "\n")
            # Flushed per entry: an interrupt must lose at most the segment in flight.
            self._stream.flush()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None


class ProgressReporter:
    """Logs percent and ETA on a fixed beat, measured on the text the model must translate.

    Progress moves with every streamed token, not only when a segment ends, and the speed
    behind the ETA is measured from the first token, so model loading is not billed to it.
    """

    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started: float | None = None
        self._generating_since: float | None = None
        self._inflight = 0.0
        self.total = 0
        self.done = 0
        self.file_index = 0
        self.file_count = 0

    # The clock starts with the first request, so planning and idle time are not billed.
    def begin(self) -> None:
        if self._started is None:
            self._started = time.monotonic()

    def token(self) -> None:
        if self._generating_since is None:
            self._generating_since = time.monotonic()

    # The answer is about as long as the source, so its length so far estimates the share of
    # the segment already translated; advance() replaces the estimate with the exact figure.
    def set_inflight(self, chars: float) -> None:
        self._inflight = chars

    def advance(self, chars: int) -> None:
        self.done += chars
        self._inflight = 0.0

    # A thread, not a hook on chunk completion: one CPU-bound answer can outlast the interval.
    def start(self) -> None:
        self._thread = threading.Thread(target=self._beat, name="progress", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _beat(self) -> None:
        while not self._stop.wait(self._interval):
            if self._started is not None:
                self.report()

    def report(self) -> None:
        # Plain reads from another thread: a one-token-stale value is harmless here.
        now = time.monotonic()
        total, started, generating = self.total, self._started, self._generating_since
        done = min(self.done + self._inflight, float(total)) if total else float(self.done)
        elapsed = 0.0 if started is None else now - started
        eta = "--:--"
        if generating is not None and done > 0 and now - generating >= MIN_ETA_SECONDS:
            eta = format_duration((total - done) / (done / (now - generating)))
        waiting = " (waiting for the model's first token)" if generating is None else ""
        LOGGER.info(
            "progress file=%s/%s %.1f%% (%.0f/%s chars) elapsed=%s eta=%s%s",
            self.file_index,
            self.file_count,
            100.0 * done / total if total else 100.0,
            done,
            total,
            format_duration(elapsed),
            eta,
            waiting,
        )


# The chunks the model would receive for one text segment, found without calling it.
def chunks_of(segment: str, max_chars: int) -> list[str]:
    masked, _ = _mask(segment.strip())
    if not _LETTER.search(masked):
        return []
    return [chunk for _, chunk in _split(masked, max_chars)]


# Every chunk translate_markdown would send for `text`.
def collect_chunks(text: str, max_chars: int) -> list[str]:
    found: list[str] = []

    def probe(segment: str) -> str:
        found.extend(chunks_of(segment, max_chars))
        return segment

    translate_markdown(text, probe)
    return found


class OllamaTranslator:
    """Callable Romanian-to-English translator with a segment cache and per-chunk validation."""

    def __init__(
        self,
        client: httpx.Client,
        model: str,
        *,
        cache: PersistentMap,
        progress: ProgressReporter,
        cancel: threading.Event,
        max_chars: int,
        retries: int,
        num_ctx: int,
        timeout: float,
        log_answers: bool = False,
    ) -> None:
        self._client = client
        self._model = model
        self._cache = cache
        self._progress = progress
        self._cancel = cancel
        self._planned: set[str] = set()
        self._failed: set[str] = set()
        self._max_chars = max_chars
        self._retries = retries
        self._num_ctx = num_ctx
        self._timeout = timeout
        self._log_answers = log_answers
        self._line: int | None = None
        self.requests = 0
        self.cache_hits = 0
        self.failures = 0
        self.largest_request = 0
        self._answer: dict[str, object] = {}

    def plan(self, chunks: list[str]) -> None:
        """Count each distinct uncached chunk once, so progress has an honest denominator."""
        for chunk in chunks:
            key = _cache_key(self._model, chunk)
            if key not in self._planned and self._cache.get(key) is None:
                self._planned.add(key)
                self._progress.total += len(chunk)

    def __call__(self, text: str) -> str:
        source = text.strip()
        masked, protected = _mask(source)
        if not _LETTER.search(masked):
            return text
        pieces = []
        for separator, chunk in _split(masked, self._max_chars):
            translated = self._translate_chunk(chunk)
            if translated is None:
                # Untranslated Romanian is visible and fixable; a corrupted translation is not.
                self.failures += 1
                translated = chunk
            pieces.append(separator + translated)
        return _unmask("".join(pieces), protected)

    def _translate_chunk(self, chunk: str) -> str | None:
        key = _cache_key(self._model, chunk)
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        # A failure is remembered for this run only; a later run may succeed (other model, retries).
        if key in self._failed:
            return None
        expected = Counter(_PLACEHOLDER.findall(chunk))
        self._progress.begin()
        result = None
        for attempt in range(1, self._retries + 2):
            self._check_cancelled()
            output = self._chat(chunk, track=key in self._planned)
            reason = (
                self._rejection(chunk, output, expected)
                if output is not None
                else self._answer.get("why", "no_output")
            )
            if reason is None and output is not None:
                self._cache.put(key, output)
                result = output
                break
            # Counts and the model's own statistics only: the corpus text must not reach the logs.
            LOGGER.warning(
                "translation rejected line=%s attempt=%s/%s source_chars=%s reason=%s "
                "num_ctx=%s %s",
                self._line,
                attempt,
                self._retries + 1,
                len(chunk),
                reason,
                self._num_ctx,
                " ".join(
                    f"{name}={value}" for name, value in self._answer.items() if name != "why"
                ),
            )
            if self._log_answers and output is not None:
                # Opt-in: the model's own answer is derived from the corpus text.
                LOGGER.warning("rejected answer line=%s: %r", self._line, output[:200])
        else:
            self._failed.add(key)
        # A failed chunk still consumed its time, so it counts as done for the ETA.
        if key in self._planned:
            self._progress.advance(len(chunk))
        return result

    # Why an answer is unusable, or None when it is fine. Names the check and the counts, never
    # the text, so the log can explain a rejection without exposing the corpus.
    @staticmethod
    def _rejection(source: str, output: str, expected: Counter[str]) -> str | None:
        if not output:
            return "empty"
        found = Counter(_PLACEHOLDER.findall(output))
        if found != expected:
            return f"placeholders(expected={sum(expected.values())},found={sum(found.values())})"
        # Catches refusals, runaway repetition and answers that drop most of the text.
        if len(source) >= 40:
            ratio = len(output) / len(source)
            if ratio < 0.25:
                return f"too_short(ratio={ratio:.2f})"
            if ratio > 4:
                return f"too_long(ratio={ratio:.2f})"
        return None

    # Cancellation is checked only here and between streamed pieces, never while a file is
    # being published, so Ctrl+C cannot leave a half-written file behind.
    def _check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise KeyboardInterrupt

    # The source line of the unit being translated, so a rejection can be found in the file.
    def set_line(self, line: int | None) -> None:
        self._line = line

    # What the failed request looked like, to tell a size problem from a server problem.
    def _context(self, segment_chars: int) -> str:
        return f"model={self._model} segment_chars={segment_chars} num_ctx={self._num_ctx}"

    def _chat(self, chunk: str, *, track: bool) -> str | None:
        options = {
            "temperature": 0,
            "num_predict": len(chunk) // 2 + 256,
            "num_ctx": self._num_ctx,
        }
        payload = {
            "model": self._model,
            "stream": True,
            "keep_alive": "10m",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": chunk},
            ],
            "options": options,
        }
        self.requests += 1
        self.largest_request = max(self.largest_request, len(chunk))
        self._progress.set_inflight(0.0)
        self._answer = {}
        try:
            with self._client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code != 200:
                    response.read()
                    raise OllamaError(
                        f"Ollama answered HTTP {response.status_code}: {_error_text(response)} "
                        f"[{self._context(len(chunk))}]"
                    )
                content, truncated, final = self._read_stream(response, len(chunk), track=track)
        except httpx.TimeoutException as exc:
            self._answer = {"why": f"timeout({type(exc).__name__}, limit={self._timeout}s)"}
            return None
        except httpx.TransportError as exc:
            raise OllamaError(
                f"Ollama connection lost ({type(exc).__name__}: {exc}) "
                f"[{self._context(len(chunk))}]"
            ) from exc
        loaded = float(str(final.get("load_duration") or 0)) / 1e9
        if loaded >= LOAD_WARNING_SECONDS:
            # A load in the middle of a run means Ollama reloaded the model, for example because
            # another client asked for a different context size.
            LOGGER.warning(
                "ollama loaded the model during a request: load_duration=%.1fs [%s]",
                loaded,
                self._context(len(chunk)),
            )
        self._answer = {
            "output_chars": len(content),
            "done_reason": final.get("done_reason"),
            "prompt_tokens": final.get("prompt_eval_count"),
            "output_tokens": final.get("eval_count"),
        }
        if truncated:
            self._answer["why"] = f"truncated(done_reason={final.get('done_reason')})"
            return None
        wrapped = _WRAPPING_FENCE.match(content)
        return wrapped.group(1).strip() if wrapped and "```" not in chunk else content

    # Newline-delimited JSON; every line carries a piece of the answer, the last one the reason.
    def _read_stream(
        self, response: httpx.Response, source_chars: int, *, track: bool
    ) -> tuple[str, bool, dict[str, object]]:
        parts: list[str] = []
        final: dict[str, object] = {}
        length = 0
        truncated = False
        try:
            for line in response.iter_lines():
                self._check_cancelled()
                if not line:
                    continue
                data = json.loads(line)
                if "error" in data:
                    raise OllamaError(
                        f"Ollama error in the stream: {str(data['error'])[:300]} "
                        f"[{self._context(source_chars)}]"
                    )
                piece = str(data["message"]["content"])
                if piece:
                    parts.append(piece)
                    length += len(piece)
                    self._progress.token()
                    if track:
                        self._progress.set_inflight(min(length, source_chars))
                if data.get("done"):
                    final = data
                    truncated = data.get("done_reason") == "length"
        except (ValueError, KeyError, TypeError) as exc:
            raise OllamaError(
                f"Unexpected response format from Ollama ({type(exc).__name__}: {exc}) "
                f"[{self._context(source_chars)}]"
            ) from exc
        return "".join(parts).strip(), truncated, final


@log_call
def check_model(client: httpx.Client, model: str) -> None:
    """Fail before any work if the daemon is down or the model is not installed."""
    try:
        response = client.get("/api/tags")
        response.raise_for_status()
        installed = {str(entry["name"]) for entry in response.json()["models"]}
    except httpx.TransportError as exc:
        raise OllamaError(
            f"Cannot reach Ollama at {client.base_url} ({type(exc).__name__}). "
            "Start it or pass --host."
        ) from exc
    except (httpx.HTTPStatusError, ValueError, KeyError, TypeError) as exc:
        raise OllamaError(f"Unexpected answer from Ollama model list ({exc!r}).") from exc
    if (model if ":" in model else f"{model}:latest") not in installed:
        raise OllamaError(f"Model {model} is not installed. Run: ollama pull {model}")


def _markdown_files(source: Path) -> list[Path]:
    # Staging files from a killed run match *.md too; they are never sources.
    return [path for path in sorted(source.rglob("*.md")) if not path.name.startswith(TEMP_PREFIX)]


# In-place work on the Romanian corpus would put English into documents/ro, which is not in git.
def _reject_romanian_corpus(source: Path) -> None:
    if any(a == "documents" and b == "ro" for a, b in zip(source.parts, source.parts[1:])):
        raise ValueError(
            "In-place translation would overwrite the Romanian corpus in documents/ro. "
            "Copy it to documents/en first, or pass --output."
        )


@log_call
def plan_jobs(source: Path, output: Path | None) -> list[tuple[Path, Path]]:
    """Pair every Markdown file under the source folder with its destination (itself in place)."""
    source = source.resolve()
    if not source.is_dir():
        raise ValueError(f"Source must be a folder: {source}")
    if output is None:
        _reject_romanian_corpus(source)
        return [(path, path) for path in _markdown_files(source)]
    target = output.resolve()
    if target.is_file():
        raise ValueError(f"Output must be a folder: {target}")
    if target == source or target.is_relative_to(source):
        raise ValueError(f"Output must be outside the source folder: {target}")
    return [(path, target / path.relative_to(source)) for path in _markdown_files(source)]


@log_call
def remove_stale_temps(jobs: list[tuple[Path, Path]]) -> None:
    """Delete staging files a killed run left beside the destinations."""
    for directory in sorted({target.parent for _, target in jobs}):
        if directory.is_dir():
            for stale in sorted(directory.glob(f"{TEMP_PREFIX}*.md")):
                LOGGER.warning("removing stale temporary file %s", stale)
                _remove_temp(stale)


@log_call
def translate_file(
    source: Path, target: Path, translator: OllamaTranslator, *, allow_partial: bool
) -> str | None:
    """Translate `source` and publish it as `target` (the same path when in place).

    The staged temporary file is consumed by the atomic replacement and removed on any
    failure, so neither a half file nor a leftover remains. Returns the SHA-256 of the
    published bytes, or None when failed segments withheld publication.
    """
    before = translator.failures
    translated = translate_markdown(
        source.read_text(encoding="utf-8-sig"), translator, translator.set_line
    )
    translator.set_line(None)
    failed = translator.failures - before
    if failed:
        LOGGER.warning("%s segment(s) could not be translated in %s", failed, source)
        if not allow_partial:
            LOGGER.warning(
                "%s not written; rerun, or pass --allow-partial to keep a partial result", target
            )
            return None
    data = translated.encode("utf-8")
    staged = _temporary_path(target.parent, prefix=TEMP_PREFIX, suffix=".md")
    try:
        staged.write_bytes(data)
        _commit_outputs({target: staged})
    except BaseException:
        _remove_temp(staged)
        raise
    return _digest(data)


def _name_key(name: str) -> str:
    return "name:" + _digest(name.encode())


# The .pdf marker stays: extract_pdf_markdown.py names its output <book>.pdf.md.
def _split_name(name: str, *, is_file: bool) -> tuple[str, str]:
    if not is_file:
        return name, ""
    stem, suffix = (name[:-3], name[-3:]) if name.lower().endswith(".md") else (name, "")
    if stem.lower().endswith(".pdf"):
        return stem[:-4], stem[-4:] + suffix
    return stem, suffix


@log_call
def english_name(
    name: str, translator: Callable[[str], str], done: PersistentMap, *, is_file: bool
) -> str:
    """English form of a file or folder name; `name` itself when it needs or allows no change."""
    # A name an earlier run produced is already English; translating it again could drift.
    if done.get(_name_key(name)) is not None:
        return name
    stem, tail = _split_name(name, is_file=is_file)
    translated = " ".join(_UNSAFE_NAME.sub(" ", translator(stem)).split()).strip(" .")
    # Case-only changes are ignored: on case-insensitive disks they are the same entry.
    if (
        not translated
        or len(translated) > MAX_NAME_CHARS
        or translated.casefold() == stem.casefold()
    ):
        return name
    return translated + tail


@log_call
def rename_to_english(
    path: Path, translator: Callable[[str], str], done: PersistentMap, *, is_file: bool
) -> Path:
    """Rename one file or folder to its English name; returns the path it has afterwards.

    Idempotent, so a run stopped right after publishing a file finishes the rename on the next
    start. A name that is already taken is kept rather than overwritten.
    """
    candidate = path.with_name(english_name(path.name, translator, done, is_file=is_file))
    if candidate == path:
        return path
    kind = "file" if is_file else "folder"
    if candidate.exists():
        LOGGER.warning("%s %s already exists; %s keeps its name", kind, candidate, path)
        return path
    path.rename(candidate)
    done.put(_name_key(candidate.name), "")
    LOGGER.info("renamed %s: %s -> %s", kind, path.name, candidate.name)
    return candidate


class FolderRenamer:
    """Says when a folder can be renamed: nothing queued below it and none of its files withheld.

    A folder renamed earlier would invalidate the path of every file still queued under it.
    """

    def __init__(self, root: Path, sources: list[Path]) -> None:
        self._root = root
        self._parents = {source.parent for source in sources}
        self._pending: Counter[Path] = Counter()
        self._blocked: set[Path] = set()
        for source in sources:
            self._pending.update(self._chain(source))

    # The folders from the file's own up to the root, deepest first.
    def _chain(self, source: Path) -> list[Path]:
        chain = [source.parent]
        while chain[-1] != self._root:
            chain.append(chain[-1].parent)
        return chain

    def settle(self, source: Path, *, withheld: bool) -> list[Path]:
        """Record that `source` needs no more work; return the folders now free, deepest first."""
        if withheld:
            self._blocked.add(source.parent)
        free = []
        for directory in self._chain(source):
            self._pending[directory] -= 1
            if (
                self._pending[directory] == 0
                and directory in self._parents
                and directory not in self._blocked
            ):
                free.append(directory)
        return free


# Names are part of the work too: planning them keeps the ETA honest on folders of short files.
def plan_names(
    translator: OllamaTranslator, done: PersistentMap, sources: list[Path], max_chars: int
) -> None:
    names = {(source.name, True) for source in sources}
    names |= {(source.parent.name, False) for source in sources}
    for name, is_file in sorted(names):
        if done.get(_name_key(name)) is None:
            translator.plan(chunks_of(_split_name(name, is_file=is_file)[0], max_chars))


def _host(value: str) -> str:
    value = value.strip().rstrip("/")
    return value if "://" in value else f"http://{value}"


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate Markdown files from Romanian to English with local Ollama."
    )
    parser.add_argument(
        "source", type=Path, help="folder to translate (searched recursively for *.md)"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="write translations here and keep the sources (default: replace each source)",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help="Ollama model (default: %(default)s)"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", DEFAULT_HOST),
        help="Ollama URL (default: $OLLAMA_HOST or %(default)s)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="with --output: replace existing outputs"
    )
    parser.add_argument(
        "--keep-names",
        action="store_true",
        help="do not translate file and folder names (in-place mode only)",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="publish a file even if some segments stayed in Romanian",
    )
    parser.add_argument(
        "--max-chars",
        type=_positive,
        default=1800,
        help="largest text sent in one request (default: %(default)s)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="extra attempts for a rejected translation (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=_positive,
        default=600,
        help="seconds to wait for one answer (default: %(default)s)",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE,
        help="segment cache file; the finished-files list sits next to it (default: %(default)s)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="skip the segment cache (the list of finished files is still kept)",
    )
    parser.add_argument(
        "--progress-interval",
        type=_positive,
        default=DEFAULT_PROGRESS_INTERVAL,
        help="seconds between progress lines (default: %(default)s)",
    )
    parser.add_argument(
        "--num-ctx",
        type=_positive,
        default=DEFAULT_NUM_CTX,
        help="model context size in tokens (default: %(default)s)",
    )
    parser.add_argument(
        "--log-rejected-answers",
        action="store_true",
        help="also log the first 200 characters of each rejected answer (derived from the text)",
    )
    parser.add_argument("--debug", action="store_true", help="trace function entry and parameters")
    args = parser.parse_args(argv)
    if args.retries < 0:
        parser.error("--retries must not be negative")
    # Input and answer together can reach --max-chars tokens in the worst case (about one
    # character per token), so a larger segment would be truncated silently by the model.
    if args.max_chars + CONTEXT_RESERVE > args.num_ctx:
        parser.error(f"--num-ctx must be at least --max-chars + {CONTEXT_RESERVE}")
    return args


def _already_done(
    source: Path, target: Path, *, in_place: bool, overwrite: bool, done: PersistentMap
) -> bool:
    if in_place:
        # Keyed by content, not path: a finished file is English now and must not be redone.
        return done.get(_digest(source.read_bytes())) is not None
    return target.exists() and not overwrite


def _run(args: argparse.Namespace, cancel: threading.Event) -> int:
    in_place = args.output is None
    withheld = 0
    try:
        jobs = plan_jobs(args.source, args.output)
        if not jobs:
            raise ValueError(f"No Markdown files found in {args.source}")
        remove_stale_temps(jobs)
        # trust_env=False: the daemon is local and must never be reached through a proxy.
        with httpx.Client(
            base_url=_host(args.host),
            timeout=httpx.Timeout(args.timeout, connect=10),
            trust_env=False,
        ) as client:
            check_model(client, args.model)
            with (
                closing(PersistentMap(None if args.no_cache else args.cache)) as cache,
                closing(
                    PersistentMap(args.cache.with_suffix(".done.jsonl") if in_place else None)
                ) as done,
                closing(ProgressReporter(args.progress_interval)) as progress,
            ):
                if cache.loaded:
                    LOGGER.info("cache: %s segments loaded from %s", cache.loaded, args.cache)
                translator = OllamaTranslator(
                    client,
                    args.model,
                    cache=cache,
                    progress=progress,
                    max_chars=args.max_chars,
                    retries=args.retries,
                    num_ctx=args.num_ctx,
                    timeout=args.timeout,
                    log_answers=args.log_rejected_answers,
                    cancel=cancel,
                )
                todo: set[Path] = set()
                for source, target in jobs:
                    if not _already_done(
                        source, target, in_place=in_place, overwrite=args.overwrite, done=done
                    ):
                        todo.add(source)
                        translator.plan(
                            collect_chunks(source.read_text(encoding="utf-8-sig"), args.max_chars)
                        )
                rename = in_place and not args.keep_names
                if rename:
                    plan_names(translator, done, [source for source, _ in jobs], args.max_chars)
                    renamer = FolderRenamer(args.source.resolve(), [source for source, _ in jobs])
                LOGGER.info(
                    "plan: %s of %s file(s) to translate, %s characters for the model",
                    len(todo),
                    len(jobs),
                    progress.total,
                )
                if in_place and todo:
                    LOGGER.warning(
                        "in-place mode: %s file(s) will be replaced by their translation "
                        "once each is complete",
                        len(todo),
                    )
                progress.file_count = len(jobs)
                progress.start()
                for index, (source, target) in enumerate(jobs, start=1):
                    progress.file_index = index
                    blocked = False
                    if source in todo:
                        LOGGER.info(
                            "[%s/%s] %s",
                            index,
                            len(jobs),
                            source if in_place else f"{source} -> {target}",
                        )
                        digest = translate_file(
                            source, target, translator, allow_partial=args.allow_partial
                        )
                        if digest is None:
                            withheld += 1
                            blocked = True
                        else:
                            if in_place:
                                done.put(digest, "")
                            progress.report()
                    else:
                        LOGGER.info("[%s/%s] skip, already done: %s", index, len(jobs), target)
                    if rename:
                        if not blocked:
                            rename_to_english(source, translator, done, is_file=True)
                        for directory in renamer.settle(source, withheld=blocked):
                            rename_to_english(directory, translator, done, is_file=False)
                # The last renames can fall after the final beat, and the planned names of a
                # withheld file are never needed: close with the figure of the work really done.
                if progress.total:
                    progress.total = progress.done
                    progress.report()
    except KeyboardInterrupt:
        LOGGER.error("Interrupted; files already written are complete.")
        return 130
    except (OllamaError, ValueError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info(
        "done requests=%s largest_request=%s chars cached=%s failures=%s withheld_files=%s",
        translator.requests,
        translator.largest_request,
        translator.cache_hits,
        translator.failures,
        withheld,
    )
    return 1 if translator.failures or withheld else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cancel = threading.Event()
    outcome: list[int] = []
    failure: list[BaseException] = []

    def work() -> None:
        try:
            outcome.append(_run(args, cancel))
        except BaseException as exc:
            failure.append(exc)

    # The work runs in a thread because on Windows a blocking network read cannot be
    # interrupted by Ctrl+C; the main thread only sleeps in short steps, which can.
    worker = threading.Thread(target=work, name="translate", daemon=True)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(0.2)
    except KeyboardInterrupt:
        LOGGER.warning(
            "Ctrl+C: stopping at the next safe point (at most %.0f s; press again to exit now)",
            INTERRUPT_GRACE_SECONDS,
        )
        cancel.set()
        try:
            worker.join(INTERRUPT_GRACE_SECONDS)
        except KeyboardInterrupt:
            pass
        if worker.is_alive():
            # Stuck in a read with no data (model loading); finished files and cached segments
            # are already on disk, and a stale staging file is removed at the next start.
            LOGGER.error("Stopped without waiting for Ollama; the segment in flight is lost.")
            logging.shutdown()
            os._exit(130)
    if failure:
        raise failure[0]
    return outcome[0]


if __name__ == "__main__":
    sys.exit(main())
