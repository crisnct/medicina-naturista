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

Files are handled one at a time: translate and replace; file names are kept. A folder that
directly contains Markdown files is renamed to its English name as soon as nothing below it
is still queued (--keep-names skips that); names an earlier run produced are kept.

A refused answer is translated again in smaller pieces (cut at the protected spans, then in
halves); only a piece refused at the smallest size is a rejection. The run stops at the first
rejected segment (file and line in the message, exit code 1); with
--keep-going it leaves the segment in Romanian instead, and a file with a segment the model cannot
translate reliably is not written (the original stays
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
import signal
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
# A request that uses this share of the context window is logged: the next one may not fit.
CONTEXT_WARNING_RATIO = 0.9
# A rejected chunk is translated again in smaller pieces; below this size it is refused for good.
MIN_PIECE_CHARS = 40
# The answer must keep at least this share of the source length, and not exceed this multiple.
# A short text varies more in length when translated (Lacramioarele is 13 characters, "Lily of the
# valley" 20, "Tears" 5), so below STRICT_RATIO_CHARS the floor is lower.
MIN_OUTPUT_RATIO = 0.4
MIN_SHORT_OUTPUT_RATIO = 0.25
MAX_OUTPUT_RATIO = 4
RATIO_MIN_CHARS = 12
STRICT_RATIO_CHARS = 40
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
            r"https?://(?:[^\s()\]>]|\([^\s()]*\))+",
            # A formula or unit with Pandoc subscripts or superscripts, as one word: Al~2~Be~3~O~18~,
            # H~2~O, Cr^3+^, m^2^. Given the markup the model rewrites it with Unicode subscripts
            # and may then repeat a blank until the token limit. Strikethrough (~~text~~) is not it.
            r"[\w()]*(?:(?:(?<![~\\])~[^~\s\\]+~(?!~)|\^[^^\s]+\^)[\w()]*)+",
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


class TranslationRejected(RuntimeError):
    """A segment failed validation and the run stops at the first one (see --keep-going)."""

    def __init__(self, line: int | None, reason: str) -> None:
        super().__init__(f"line {line}: {reason}")
        self.line = line
        self.reason = reason


@dataclass(slots=True)
class _Rejection:
    """Why one request was refused, kept until no smaller request has succeeded either."""

    request: str
    reason: str
    stats: str
    answer: str | None
    partial: str | None
    tail: str | None
    spans: dict[int, str]


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


# Noise that only separates or decorates text copied from web pages and is not kept: HTML line
# breaks, and what is left of an image whose path was removed: !{width="0.11in" height="0.1in"}.
# A model asked to keep a placeholder for each of them drops all of them. A run of them, with the
# blanks around it, becomes one space between words and nothing at the end of a line.
_NOISE = re.compile(r"(?:[ \t]*(?:!\{[^{}\n]*\}|<br\s*/?>))+[ \t]*", re.IGNORECASE)


def _drop_noise(match: re.Match[str]) -> str:
    after = match.string[match.end() : match.end() + 1]
    return "" if after in ("", "\n") else " "


_PLAIN_BRACKET = re.compile(r"(?<!\\)[\[\]]")


# A bracket without its partner, left where a link or a span was cut by a paragraph break, carries
# nothing. A model drops it, which breaks the bracket count that link targets are put back by.
# Escaped brackets (\[ and \]) are literal text and stay.
def _drop_stray_brackets(text: str) -> str:
    opened: list[int] = []
    stray: set[int] = set()
    for match in _PLAIN_BRACKET.finditer(text):
        if match.group(0) == "[":
            opened.append(match.start())
        elif opened:
            opened.pop()
        else:
            stray.add(match.start())
    stray.update(opened)
    if not stray:
        return text
    return "".join(char for position, char in enumerate(text) if position not in stray)


# A degree written as a Pandoc superscript, 96^o^ or 20^o^C, is plain text with the real sign. As a
# protected span in the middle of a sentence it was dropped by the model, with the figure's unit.
_DEGREE = re.compile(r"(?<=\d)\^[oº°]\^")


def _clean(text: str) -> str:
    return _drop_stray_brackets(_DEGREE.sub("°", _NOISE.sub(_drop_noise, text))).strip()


# A closing bracket that is a bracket of the text, not one of a [[n]] placeholder.
_BRACKET = re.compile(r"\[\[\d+\]\]|\]")


# The index just past the ")" that balances the "(" at `start`, or None. Targets such as
# javascript:void(0) contain parentheses of their own, which a pattern cannot match.
def _balanced_end(text: str, start: int) -> int | None:
    depth = 0
    for position in range(start, min(len(text), start + 2000)):
        char = text[position]
        if char == "\n":
            return None
        depth += (char == "(") - (char == ")")
        if depth == 0:
            return position + 1
    return None


_BRACKET_TOKEN = re.compile(r"\[\[\d+\]\]|\[|\]")


def _is_dead_target(target: str) -> bool:
    inner = target[1:-1].strip().lower()
    return inner in ("", "#") or inner.startswith("javascript:")


# Links that point nowhere, such as [text](javascript:void(0)) left by pages copied from a browser,
# carry no information. Their syntax is removed and the text kept: asked to keep the brackets of
# such a link the model sometimes drops them, and the answer would be rejected for nothing.
def _drop_dead_links(text: str) -> tuple[str, int]:
    cuts: list[tuple[int, int]] = []
    opened: list[int] = []
    skip_until = 0
    for match in _BRACKET_TOKEN.finditer(text):
        token = match.group(0)
        if match.start() < skip_until:
            continue
        if token == "[":
            opened.append(match.start())
        elif token == "]" and opened:
            open_at = opened.pop()
            start = match.end()
            end = _balanced_end(text, start) if text[start : start + 1] == "(" else None
            is_image = text[max(open_at - 1, 0) : open_at] == "!" and open_at > 0
            if end is not None and not is_image and _is_dead_target(text[start:end]):
                cuts += [(open_at, open_at + 1), (match.start(), end)]
                skip_until = end
    pieces: list[str] = []
    last = 0
    for begin, finish in sorted(cuts):
        pieces.append(text[last:begin])
        last = finish
    pieces.append(text[last:])
    return "".join(pieces), len(cuts) // 2


# Link targets never reach the model: given a placeholder it drops the link or its brackets, and
# the answer is rejected. Each "(target)" that follows a closing bracket is cut out and remembered
# by the index of that bracket, to be put back after the same bracket of the answer.
def _detach_link_targets(text: str) -> tuple[str, dict[int, str]]:
    parts: list[str] = []
    targets: dict[int, str] = {}
    last = 0
    index = -1
    for match in _BRACKET.finditer(text):
        if match.group(0) != "]" or match.start() < last:
            continue
        index += 1
        start = match.end()
        end = _balanced_end(text, start) if text[start : start + 1] == "(" else None
        if end is not None:
            parts.append(text[last:start])
            targets[index] = text[start:end]
            last = end
    parts.append(text[last:])
    return "".join(parts), targets


def _count_brackets(text: str) -> int:
    return sum(1 for match in _BRACKET.finditer(text) if match.group(0) == "]")


def _attach_link_targets(text: str, targets: dict[int, str]) -> str:
    parts: list[str] = []
    last = 0
    index = -1
    for match in _BRACKET.finditer(text):
        if match.group(0) != "]":
            continue
        index += 1
        if index in targets:
            parts.append(text[last : match.end()])
            parts.append(targets[index])
            last = match.end()
    parts.append(text[last:])
    return "".join(parts)


# Cuts text at what has to stay verbatim, as (is_verbatim, piece): the [[n]] placeholders and the
# syntax of links that have a target ("[" and "](target)"), so that only the words between are
# translated and nothing has to be kept by the model.
def _split_spans(text: str) -> list[tuple[bool, str]]:
    verbatim: list[tuple[int, int]] = []
    opened: list[int] = []
    skip_until = 0
    for match in _BRACKET_TOKEN.finditer(text):
        token = match.group(0)
        if match.start() < skip_until:
            continue
        if token == "[":
            opened.append(match.start())
        elif token == "]":
            if not opened:
                continue
            open_at = opened.pop()
            start = match.end()
            end = _balanced_end(text, start) if text[start : start + 1] == "(" else None
            if end is not None:
                verbatim += [(open_at, open_at + 1), (match.start(), end)]
                skip_until = end
        else:
            verbatim.append((match.start(), match.end()))
    pieces: list[tuple[bool, str]] = []
    last = 0
    for begin, finish in sorted(verbatim):
        if begin < last:
            continue
        if begin > last:
            pieces.append((False, text[last:begin]))
        pieces.append((True, text[begin:finish]))
        last = finish
    if last < len(text):
        pieces.append((False, text[last:]))
    return pieces


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
        self.output_tokens = 0
        self.output_seconds = 0.0
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

    # Ollama's own figures for the tokens it generated and the time that took, so the speed
    # excludes model loading and prompt processing.
    def add_output(self, tokens: int, seconds: float) -> None:
        self.output_tokens += tokens
        self.output_seconds += seconds

    @property
    def output_speed(self) -> float | None:
        return self.output_tokens / self.output_seconds if self.output_seconds > 0 else None

    # Tokens per wall-clock second since the first token, so time spent queued behind another
    # client counts. The speed above cannot show that: Ollama times only the generation itself.
    @property
    def output_throughput(self) -> float | None:
        generating = self._generating_since
        if generating is None or self.output_tokens <= 0:
            return None
        elapsed = time.monotonic() - generating
        return self.output_tokens / elapsed if elapsed >= MIN_ETA_SECONDS else None

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
            "progress file=%s/%s %.1f%% (%.0f/%s chars) elapsed=%s eta=%s speed=%s throughput=%s%s",
            self.file_index,
            self.file_count,
            100.0 * done / total if total else 100.0,
            done,
            total,
            format_duration(elapsed),
            eta,
            f"{speed:.1f} tok/s" if (speed := self.output_speed) is not None else "-- tok/s",
            f"{rate:.1f} tok/s" if (rate := self.output_throughput) is not None else "-- tok/s",
            waiting,
        )


# The chunks the model would receive for one text segment, found without calling it.
# A table row flattened into one line keeps its cells apart with escaped tildes glued to the text
# before them: name\~1400\~180, or just two cells, herb\~herbs. A model given the whole row
# translates the first cell and drops the rest, so the row is cut at the separators, only the cells
# with letters are translated and the row is joined again. A tilde after a blank is ordinary text
# ("aproximativ \~5 grame") and cuts nothing.
_ROW_SEPARATOR = re.compile(r"(?<=\S)\\~")


def _cells(text: str) -> list[str]:
    return _ROW_SEPARATOR.split(text)


def chunks_of(segment: str, max_chars: int) -> list[str]:
    found: list[str] = []
    for cell in _cells(_clean(segment)):
        masked, _ = _mask(cell.strip())
        if _LETTER.search(masked):
            found.extend(chunk for _, chunk in _split(masked, max_chars))
    return found


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
        stop_on_rejection: bool = False,
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
        self._stop_on_rejection = stop_on_rejection
        self._line: int | None = None
        self._protected: list[str] = []
        self.requests = 0
        self.cache_hits = 0
        self.failures = 0
        self.largest_request = 0
        self.context_used_max = 0
        self.dead_links_removed = 0
        self._answer: dict[str, object] = {}

    def plan(self, chunks: list[str]) -> None:
        """Count each distinct uncached chunk once, so progress has an honest denominator."""
        for chunk in chunks:
            key = _cache_key(self._model, chunk)
            if key not in self._planned and self._cache.get(key) is None:
                self._planned.add(key)
                self._progress.total += len(chunk)

    def __call__(self, text: str) -> str:
        return "\\~".join(self._translate_cell(cell) for cell in _cells(_clean(text)))

    # One cell, or the whole text when it is not a flattened row; the blanks around it are kept.
    def _translate_cell(self, cell: str) -> str:
        leading = cell[: len(cell) - len(cell.lstrip())]
        trailing = cell[len(cell.rstrip()) :]
        masked, protected = _mask(cell.strip())
        self._protected = protected
        if not _LETTER.search(masked):
            return cell
        pieces = []
        for separator, chunk in _split(masked, self._max_chars):
            translated = self._translate_chunk(chunk)
            if translated is None:
                # Untranslated Romanian is visible and fixable; a corrupted translation is not.
                self.failures += 1
                translated = chunk
            pieces.append(separator + translated)
        return leading + _unmask("".join(pieces), protected) + trailing

    def _translate_chunk(self, chunk: str) -> str | None:
        key = _cache_key(self._model, chunk)
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        # A failure is remembered for this run only; a later run may succeed (other model).
        if key in self._failed:
            return None
        self._progress.begin()
        stripped, dead = _drop_dead_links(chunk)
        self.dead_links_removed += dead
        result = self._translate(stripped, track=key in self._planned)
        if result is None:
            self._failed.add(key)
        else:
            self._cache.put(key, result)
        # A failed chunk still consumed its time, so it counts as done for the ETA.
        if key in self._planned:
            self._progress.advance(len(chunk))
        return result

    # One piece of text: asked as it is, and when the answer is refused, in smaller pieces. At
    # temperature 0 a repeated request gets the same answer, so a smaller request is the retry.
    def _translate(self, text: str, *, track: bool) -> str | None:
        key = _cache_key(self._model, text)
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        outcome = self._ask(text, track=track)
        result = outcome if isinstance(outcome, str) else self._shrink(text, outcome)
        if result is not None:
            self._cache.put(key, result)
        return result

    def _ask(self, text: str, *, track: bool) -> str | _Rejection:
        request, targets = _detach_link_targets(text)
        expected = Counter(_PLACEHOLDER.findall(request))
        rejection: _Rejection | None = None
        for _ in range(self._retries + 1):
            self._check_cancelled()
            output = self._chat(request, track=track)
            reason = (
                self._rejection(request, output, expected)
                if output is not None
                else str(self._answer.get("why", "no_output"))
            )
            # Targets go back after their brackets, so the answer must keep every bracket.
            if reason is None and output is not None and targets:
                wanted, found = _count_brackets(request), _count_brackets(output)
                if wanted != found:
                    reason = f"brackets(expected={wanted},found={found})"
            if reason is None and output is not None:
                return _attach_link_targets(output, targets)
            rejection = self._snapshot(request, output, str(reason))
        assert rejection is not None
        return rejection

    def _snapshot(self, request: str, output: str | None, reason: str) -> _Rejection:
        partial = self._answer.get("partial")
        return _Rejection(
            request=request,
            reason=reason,
            # Counts and the model's own statistics only; the text is logged on its own line.
            stats=" ".join(
                f"{name}={value}"
                for name, value in self._answer.items()
                if name not in ("why", "partial", "tail")
            ),
            answer=output,
            partial=None if partial is None else str(partial),
            tail=None if partial is None else str(self._answer.get("tail")),
            spans={int(n): self._protected[int(n)][:60] for n in _PLACEHOLDER.findall(request)},
        )

    # First the words between what must stay verbatim (placeholders, link syntax), so the model
    # keeps nothing; then two halves cut at a sentence, clause or word. Each piece is checked on its
    # own, and a piece that is refused at the smallest size ends the attempt.
    def _shrink(self, text: str, rejection: _Rejection) -> str | None:
        pieces = _split_spans(text)
        if any(verbatim for verbatim, _ in pieces):
            LOGGER.info(
                "retrying around %s protected span(s) line=%s reason=%s",
                sum(verbatim for verbatim, _ in pieces),
                self._line,
                rejection.reason,
            )
            out: list[str] = []
            for verbatim, piece in pieces:
                translated = piece if verbatim else self._translate_piece(piece)
                if translated is None:
                    return None
                out.append(translated)
            return "".join(out)
        if len(text) > MIN_PIECE_CHARS:
            halves = _split(text, len(text) // 2 + 1)
            if len(halves) > 1:
                LOGGER.info(
                    "retrying in %s smaller pieces line=%s reason=%s",
                    len(halves),
                    self._line,
                    rejection.reason,
                )
                joined: list[str] = []
                for separator, part in halves:
                    translated = self._translate(part, track=False)
                    if translated is None:
                        return None
                    joined.append(separator + translated)
                return "".join(joined)
        self._refuse(rejection)
        return None

    # A piece between verbatim spans; the blanks around it stay, and one without letters is not sent.
    def _translate_piece(self, piece: str) -> str | None:
        core = piece.strip()
        if not core or not _LETTER.search(_PLACEHOLDER.sub("", core)):
            return piece
        translated = self._translate(core, track=False)
        if translated is None:
            return None
        leading = piece[: len(piece) - len(piece.lstrip())]
        return leading + translated + piece[len(piece.rstrip()) :]

    # The one place a rejection is reported: the smallest request that still failed.
    def _refuse(self, rejection: _Rejection) -> None:
        LOGGER.warning(
            "translation rejected line=%s source_chars=%s reason=%s num_ctx=%s %s",
            self._line,
            len(rejection.request),
            rejection.reason,
            self._num_ctx,
            rejection.stats,
        )
        if self._log_answers:
            # The text itself comes from the corpus, hence the opt-out flag.
            LOGGER.warning(
                "rejected input line=%s: %r protected=%s",
                self._line,
                rejection.request[:400],
                rejection.spans,
            )
            if rejection.answer is not None:
                LOGGER.warning("rejected answer line=%s: %r", self._line, rejection.answer[:200])
            elif rejection.partial is not None:
                LOGGER.warning(
                    "rejected answer (cut off) line=%s: %r ... ends with %r",
                    self._line,
                    rejection.partial[:200],
                    rejection.tail,
                )
        if self._stop_on_rejection:
            raise TranslationRejected(self._line, rejection.reason)

    # Why an answer is unusable, or None when it is fine. Names the check and the counts, never
    # the text, so the log can explain a rejection without exposing the corpus.
    @staticmethod
    def _rejection(source: str, output: str, expected: Counter[str]) -> str | None:
        if not output:
            return "empty"
        found = Counter(_PLACEHOLDER.findall(output))
        if found != expected:
            return f"placeholders(expected={sum(expected.values())},found={sum(found.values())})"
        # Catches refusals, runaway repetition and answers that drop part of the text. Real
        # translations here keep 0.87 to 1.03 of the source length; below RATIO_MIN_CHARS a
        # word is too short to judge by length.
        if len(source) >= RATIO_MIN_CHARS:
            ratio = len(output) / len(source)
            floor = (
                MIN_OUTPUT_RATIO if len(source) >= STRICT_RATIO_CHARS else MIN_SHORT_OUTPUT_RATIO
            )
            if ratio < floor:
                return f"too_short(ratio={ratio:.2f})"
            if ratio > MAX_OUTPUT_RATIO:
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
                raw, truncated, final = self._read_stream(response, len(chunk), track=track)
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
        content = raw.strip()
        self._answer = {
            "output_chars": len(content),
            # Much more than output_chars means the answer is padded with blanks or line breaks.
            "raw_chars": len(raw),
            "done_reason": final.get("done_reason"),
            "prompt_tokens": final.get("prompt_eval_count"),
            "output_tokens": final.get("eval_count"),
        }
        tokens = int(str(final.get("eval_count") or 0))
        seconds = float(str(final.get("eval_duration") or 0)) / 1e9
        # Prompt and answer share the window. Ollama may leave out prompt tokens it reused from
        # its cache, so this can undercount, never overcount.
        used = int(str(final.get("prompt_eval_count") or 0)) + tokens
        self.context_used_max = max(self.context_used_max, used)
        if used >= self._num_ctx * CONTEXT_WARNING_RATIO:
            LOGGER.warning(
                "context nearly full: %s of %s tokens used by prompt and answer [%s]",
                used,
                self._num_ctx,
                self._context(len(chunk)),
            )
        if tokens > 0 and seconds > 0:
            self._progress.add_output(tokens, seconds)
            self._answer["tokens_per_s"] = round(tokens / seconds, 1)
        if truncated:
            self._answer["why"] = f"truncated(done_reason={final.get('done_reason')})"
            # The cut-off answer is not returned, but a rejection must be able to show it.
            self._answer["partial"] = content
            self._answer["tail"] = raw[-60:]
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
        return "".join(parts), truncated, final


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


@log_call
def english_name(name: str, translator: Callable[[str], str], done: PersistentMap) -> str:
    """English form of a folder name; `name` itself when it needs or allows no change."""
    # A name an earlier run produced is already English; translating it again could drift.
    if done.get(_name_key(name)) is not None:
        return name
    translated = " ".join(_UNSAFE_NAME.sub(" ", translator(name)).split()).strip(" .")
    # Case-only changes are ignored: on case-insensitive disks they are the same entry.
    if (
        not translated
        or len(translated) > MAX_NAME_CHARS
        or translated.casefold() == name.casefold()
    ):
        return name
    return translated


@log_call
def rename_to_english(
    directory: Path, translator: Callable[[str], str], done: PersistentMap
) -> Path:
    """Rename one folder to its English name; returns the path it has afterwards.

    Idempotent, so a run stopped before the rename finishes it on the next start. A name that
    is already taken is kept rather than overwritten.
    """
    candidate = directory.with_name(english_name(directory.name, translator, done))
    if candidate == directory:
        return directory
    if candidate.exists():
        LOGGER.warning("folder %s already exists; %s keeps its name", candidate, directory)
        return directory
    directory.rename(candidate)
    done.put(_name_key(candidate.name), "")
    LOGGER.info("renamed folder: %s -> %s", directory.name, candidate.name)
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
    for name in sorted({source.parent.name for source in sources}):
        if done.get(_name_key(name)) is None:
            translator.plan(chunks_of(name, max_chars))


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
        help="do not translate folder names (in-place mode only)",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="do not stop at the first rejected segment: retry it, leave it in Romanian, go on",
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
        default=0,
        help="extra identical requests after a refusal; only a timeout can change (default: %(default)s)",
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
        action=argparse.BooleanOptionalAction,
        default=True,
        help="log the first 200 characters of each rejected answer; it is derived from the "
        "text, so --no-log-rejected-answers turns it off (default: on)",
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
    current: Path | None = None
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
                    stop_on_rejection=not args.keep_going,
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
                    current = source
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
                        for directory in renamer.settle(source, withheld=blocked):
                            rename_to_english(directory, translator, done)
                # The last renames can fall after the final beat, and the planned names of a
                # withheld file are never needed: close with the figure of the work really done.
                if progress.total:
                    progress.total = progress.done
                    progress.report()
    except KeyboardInterrupt:
        LOGGER.error("Interrupted; files already written are complete.")
        return 130
    except TranslationRejected as exc:
        LOGGER.error(
            "Stopped at the first rejected segment: %s, line %s, reason %s. Nothing was written "
            "for this file; fix the text and run again, or pass --keep-going.",
            current,
            exc.line,
            exc.reason,
        )
        return 1
    except (OllamaError, ValueError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info(
        "done requests=%s largest_request=%s chars cached=%s failures=%s withheld_files=%s "
        "output_tokens=%s output_speed=%s output_throughput=%s context_used_max=%s/%s "
        "dead_links_removed=%s",
        translator.requests,
        translator.largest_request,
        translator.cache_hits,
        translator.failures,
        withheld,
        progress.output_tokens,
        f"{speed:.1f} tok/s" if (speed := progress.output_speed) is not None else "n/a",
        f"{rate:.1f} tok/s" if (rate := progress.output_throughput) is not None else "n/a",
        translator.context_used_max,
        args.num_ctx,
        translator.dead_links_removed,
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

    def on_interrupt(signum: int, frame: object) -> None:
        if cancel.is_set():
            # Second Ctrl+C: leave at once, with no exception and no traceback.
            logging.shutdown()
            os._exit(130)
        cancel.set()
        LOGGER.warning(
            "Ctrl+C: stopping at the next safe point (at most %.0f s; press again to exit now)",
            INTERRUPT_GRACE_SECONDS,
        )

    signal.signal(signal.SIGINT, on_interrupt)
    # The work runs in a thread because on Windows a blocking network read cannot be
    # interrupted by Ctrl+C; the main thread only waits in short steps, which can.
    worker = threading.Thread(target=work, name="translate", daemon=True)
    worker.start()
    deadline: float | None = None
    while worker.is_alive():
        worker.join(0.2)
        if cancel.is_set():
            deadline = deadline or time.monotonic() + INTERRUPT_GRACE_SECONDS
            if time.monotonic() >= deadline and worker.is_alive():
                # Stuck in a read with no data (model loading); finished files and cached
                # segments are already on disk, and a stale staging file is removed at the
                # next start.
                LOGGER.error("Stopped without waiting for Ollama; the segment in flight is lost.")
                logging.shutdown()
                os._exit(130)
    if failure:
        raise failure[0]
    return outcome[0]


if __name__ == "__main__":
    sys.exit(main())
