r"""Translate Markdown files from Romanian to English with a local Ollama model.

Only prose reaches the model. Front matter, fenced code, HTML comments (the PDF page
markers), table separators, Markdown markers, inline code and URLs are copied through
unchanged, so the output keeps the layout of the source. Nothing leaves the machine.

Requires a running Ollama with the model pulled: ollama pull translategemma:4b

    PYTHONPATH=src python src/scripts/translate_markdown.py "<file-or-directory>" [-o OUTPUT]

Default output: documents/ro/... becomes documents/en/...; elsewhere book.md becomes
book.en.md (a directory becomes <name>.en). Existing outputs are skipped unless --overwrite
is given. A segment the model cannot translate reliably stays in Romanian and the exit code
is 1, so an incomplete result is never mistaken for a finished one.

Every accepted translation is also appended to a JSON-lines cache outside the repository
(~/.cache/medicina-naturista/translate_markdown.jsonl; --cache to move it, --no-cache to
skip it), so an interrupted run resumes at the segment where it stopped. The cache holds
corpus text: keep it out of git and delete it when the corpus is no longer needed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
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
PROGRESS_EVERY = 50
DEFAULT_CACHE = Path.home() / ".cache" / "medicina-naturista" / "translate_markdown.jsonl"

_LETTER = re.compile(r"[^\W\d_]")
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
def translate_markdown(text: str, translate: Callable[[str], str]) -> str:
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
            out.extend(_render(paragraph, translate))
            paragraph = None

    for line in lines[start:]:
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
            out.append(_translate_row(line, translate))
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            out.append(heading.group(1) + _one_line(translate(heading.group(2))))
            continue
        item = _LIST_ITEM.match(line)
        if item:
            flush()
            paragraph = _Paragraph("list", item.group(1), " " * len(item.group(1)), [item.group(2)])
            continue
        quote = _QUOTE.match(line)
        if quote:
            prefix, body = quote.groups()
            if paragraph is not None and paragraph.kind == "quote" and paragraph.first == prefix:
                paragraph.lines.append(body)
            else:
                flush()
                paragraph = _Paragraph("quote", prefix, prefix, [body])
            continue
        if paragraph is not None:
            paragraph.lines.append(line.strip())
        else:
            indent = line[: len(line) - len(line.lstrip())]
            paragraph = _Paragraph("plain", indent, indent, [line.strip()])
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


# Sentence-packed chunks, each with the whitespace that preceded it in the source.
def _split(text: str, limit: int) -> list[tuple[str, str]]:
    parts = re.split(r"(?<=[.!?…])(\s+)", text)
    chunks = [("", parts[0])]
    for separator, sentence in zip(parts[1::2], parts[2::2], strict=True):
        before, current = chunks[-1]
        if len(current) + len(separator) + len(sentence) <= limit:
            chunks[-1] = (before, current + separator + sentence)
        else:
            chunks.append((separator, sentence))
    return chunks


# The model and prompt are part of the key: changing either must not serve stale translations.
def _cache_key(model: str, chunk: str) -> str:
    return hashlib.sha256(f"{model}\0{SYSTEM_PROMPT}\0{chunk}".encode()).hexdigest()


class SegmentCache:
    """Accepted translations by key, optionally appended to a JSON-lines file as they happen."""

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


class OllamaTranslator:
    """Callable Romanian-to-English translator with a segment cache and per-chunk validation."""

    def __init__(
        self,
        client: httpx.Client,
        model: str,
        *,
        cache: SegmentCache,
        max_chars: int,
        retries: int,
        num_ctx: int | None,
    ) -> None:
        self._client = client
        self._model = model
        self._cache = cache
        self._failed: set[str] = set()
        self._max_chars = max_chars
        self._retries = retries
        self._num_ctx = num_ctx
        self.requests = 0
        self.cache_hits = 0
        self.failures = 0
        self._started = time.monotonic()

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
        for attempt in range(1, self._retries + 2):
            output = self._chat(chunk)
            if output is not None and self._acceptable(chunk, output, expected):
                self._cache.put(key, output)
                return output
            # Lengths only: the corpus text must not reach the logs.
            LOGGER.warning(
                "translation rejected attempt=%s/%s source_chars=%s",
                attempt,
                self._retries + 1,
                len(chunk),
            )
        self._failed.add(key)
        return None

    @staticmethod
    def _acceptable(source: str, output: str, expected: Counter[str]) -> bool:
        if not output:
            return False
        if Counter(_PLACEHOLDER.findall(output)) != expected:
            return False
        # Catches refusals, runaway repetition and answers that drop most of the text.
        return len(source) < 40 or 0.25 <= len(output) / len(source) <= 4

    def _chat(self, chunk: str) -> str | None:
        options: dict[str, float | int] = {
            "temperature": 0,
            "num_predict": len(chunk) // 2 + 256,
        }
        if self._num_ctx is not None:
            options["num_ctx"] = self._num_ctx
        payload = {
            "model": self._model,
            "stream": False,
            "keep_alive": "10m",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": chunk},
            ],
            "options": options,
        }
        self.requests += 1
        if self.requests % PROGRESS_EVERY == 0:
            LOGGER.info(
                "progress requests=%s cached=%s failures=%s elapsed=%.0fs",
                self.requests,
                self.cache_hits,
                self.failures,
                time.monotonic() - self._started,
            )
        try:
            response = self._client.post("/api/chat", json=payload)
        except httpx.TimeoutException:
            return None
        except httpx.TransportError as exc:
            raise OllamaError(f"Ollama connection lost ({type(exc).__name__}).") from exc
        if response.status_code != 200:
            raise OllamaError(f"Ollama answered HTTP {response.status_code}: {response.text[:200]}")
        try:
            data = response.json()
            content = str(data["message"]["content"]).strip()
            truncated = data.get("done_reason") == "length"
        except (ValueError, KeyError, TypeError) as exc:
            raise OllamaError("Unexpected response format from Ollama.") from exc
        if truncated:
            return None
        wrapped = _WRAPPING_FENCE.match(content)
        return wrapped.group(1).strip() if wrapped and "```" not in chunk else content


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


# The corpus mirrors documents/ro under documents/en; the last such pair wins.
def default_output(source: Path) -> Path:
    parts = source.parts
    for index in range(len(parts) - 1, 0, -1):
        if parts[index] == "ro" and parts[index - 1] == "documents":
            return Path(*parts[:index], "en", *parts[index + 1 :])
    if source.is_dir():
        return source.with_name(f"{source.name}.en")
    return source.with_name(f"{source.stem}.en{source.suffix}")


@log_call
def plan_jobs(source: Path, output: Path | None) -> list[tuple[Path, Path]]:
    """Pair every source file with its destination, rejecting layouts that overwrite input."""
    source = source.resolve()
    if not source.exists():
        raise ValueError(f"Source not found: {source}")
    target = output.resolve() if output is not None else default_output(source)
    if source.is_file():
        if target.is_dir():
            target = target / source.name
        jobs = [(source, target)]
    else:
        if target.is_file():
            raise ValueError(f"Output must be a directory for a directory source: {target}")
        if target == source or target.is_relative_to(source):
            raise ValueError(f"Output must be outside the source directory: {target}")
        jobs = [(path, target / path.relative_to(source)) for path in sorted(source.rglob("*.md"))]
    if any(path == destination for path, destination in jobs):
        raise ValueError("Output would overwrite the source; choose another --output.")
    return jobs


@log_call
def translate_file(source: Path, target: Path, translator: OllamaTranslator) -> None:
    """Translate one file and publish it atomically, so a crash never leaves a half file."""
    translated = translate_markdown(source.read_text(encoding="utf-8-sig"), translator)
    staged = _temporary_path(target.parent, prefix=".translate-", suffix=".md")
    try:
        staged.write_text(translated, encoding="utf-8", newline="\n")
        _commit_outputs({target: staged})
    except BaseException:
        _remove_temp(staged)
        raise


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
    parser.add_argument("source", type=Path, help="Markdown file or directory (searched for *.md)")
    parser.add_argument("-o", "--output", type=Path, help="output file or directory")
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help="Ollama model (default: %(default)s)"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", DEFAULT_HOST),
        help="Ollama URL (default: $OLLAMA_HOST or %(default)s)",
    )
    parser.add_argument("--overwrite", action="store_true", help="replace existing outputs")
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
        help="segment cache file (default: %(default)s)",
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="neither read nor write the on-disk cache"
    )
    parser.add_argument("--num-ctx", type=_positive, help="override the model context size")
    parser.add_argument("--debug", action="store_true", help="trace function entry and parameters")
    args = parser.parse_args(argv)
    if args.retries < 0:
        parser.error("--retries must not be negative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        jobs = plan_jobs(args.source, args.output)
        if not jobs:
            raise ValueError(f"No Markdown files found in {args.source}")
        # trust_env=False: the daemon is local and must never be reached through a proxy.
        with httpx.Client(
            base_url=_host(args.host),
            timeout=httpx.Timeout(args.timeout, connect=10),
            trust_env=False,
        ) as client:
            check_model(client, args.model)
            with closing(SegmentCache(None if args.no_cache else args.cache)) as cache:
                if cache.loaded:
                    LOGGER.info("cache: %s segments loaded from %s", cache.loaded, args.cache)
                translator = OllamaTranslator(
                    client,
                    args.model,
                    cache=cache,
                    max_chars=args.max_chars,
                    retries=args.retries,
                    num_ctx=args.num_ctx,
                )
                for index, (source, target) in enumerate(jobs, start=1):
                    if target.exists() and not args.overwrite:
                        LOGGER.info("[%s/%s] skip, output exists: %s", index, len(jobs), target)
                        continue
                    LOGGER.info("[%s/%s] %s -> %s", index, len(jobs), source, target)
                    before = translator.failures
                    translate_file(source, target, translator)
                    if translator.failures > before:
                        LOGGER.warning(
                            "%s segment(s) left in Romanian in %s",
                            translator.failures - before,
                            target,
                        )
    except KeyboardInterrupt:
        LOGGER.error("Interrupted; files already written are complete.")
        return 130
    except (OllamaError, ValueError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info(
        "done requests=%s cached=%s failures=%s",
        translator.requests,
        translator.cache_hits,
        translator.failures,
    )
    return 1 if translator.failures else 0


if __name__ == "__main__":
    sys.exit(main())
