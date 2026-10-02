#!/usr/bin/env python3
"""Fix OCR / typing errors in the Romanian Markdown sources of data/documents.

Four rules, each one conservative and driven by a Romanian dictionary (the
Hunspell ``ro_RO`` word list, expanded and folded to ASCII to match the corpus,
whose diacritics were already folded by clean_documents.py) plus word counts
taken from the corpus itself:

1. **Join split words** -- "pen tru" -> "pentru", "tratam ent" -> "tratament".
   Two words separated by one space are joined when the result is a dictionary
   word and at least one half is not a word (not in the dictionary, or a lone
   letter other than a/o/i). A pair that is itself frequent is left alone.
2. **Split run-together words** -- "dinacest" -> "din acest". Only unknown rare
   tokens are touched, and every piece must be a frequent dictionary word (or one
   of a short list of function words), so suffixes and prefixes ("ului", "anti")
   never become words of their own.
3. **Typos** -- an unknown rare token one edit (insertion, deletion,
   substitution, transposition) away from a clearly more frequent dictionary word
   ("mediicament" -> "medicament"). Ties are left alone.
4. **Old orthography** -- "cind" -> "cand", "pina" -> "pana", "sint" -> "sunt"
   (the old i/a spelling of the folded diacritics).

Only files detected as Romanian are rewritten (English books and OCR'd images are
skipped). Capitalised words (names) are never touched. Lines holding URLs or
e-mail addresses are skipped. Dry-run by default: nothing is written without
``--apply``. Every change is written to a TSV report (file, line, rule, before,
after) so it can be reviewed or reverted.

    python scripts/fix_spelling.py --hunspell-dir <dir with ro_RO.dic/.aff>
    python scripts/fix_spelling.py --hunspell-dir <dir> --apply
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data" / "documents"

FOLD = str.maketrans({"ă": "a", "â": "a", "î": "i", "ș": "s", "ş": "s", "ț": "t", "ţ": "t",
                      "Ă": "a", "Â": "a", "Î": "i", "Ș": "s", "Ț": "t"})
WORD = re.compile(r"[A-Za-z]+")
# A token is a letter run that is not glued to digits, paths, e-mails or hyphen compounds.
TOKEN = re.compile(r"(?<![A-Za-z0-9_@/:#\\-])[A-Za-z]+(?![A-Za-z0-9_@/:#\\-])")
SKIP_LINE = re.compile(r"https?:|www\.|@|\.(?:com|ro|org|net)\b", re.I)

ROMANIAN_STOPWORDS = set("si de la in cu pentru se este sa care un o din pe nu mai sau sunt au ca a ce prin dar fi cel".split())
ENGLISH_STOPWORDS = set("the and of is to in that for with as are this by from or be it on".split())

# Short words allowed as one piece of a run-together token.
FUNCTION_WORDS = set("de la in cu si sa se ca pe un o a ai nu mai din dar tot sau ce iar prin fara spre dupa intre care este sunt prea unui unei".split())
# Prefixes that must never be peeled off a word ("contraexemplu" is one word).
PREFIXES = set("contra anti auto bio supra ultra extra intra inter para pseudo semi super trans poli mono micro macro mega neuro hidro termo foto electro multi post infra hiper hipo sub pre pro non ante circum".split())
# Tokens that look run-together but are real words missing from the dictionary.
KEEP = {"plantain", "organela", "fizicala"}
# Old i/a spelling of the folded diacritics; words shorter than 6 letters are listed
# explicitly because the generic rule would also rewrite OCR fragments ("tirea").
OLD_ORTHOGRAPHY = {"sint": "sunt", "sintem": "suntem", "sinteti": "sunteti", "cind": "cand", "rind": "rand",
                   "pina": "pana", "cimp": "camp", "virf": "varf", "vind": "vand", "avind": "avand",
                   "intii": "intai", "singe": "sange", "pinza": "panza", "cirpa": "carpa"}
OLD_SWAPS = (("in", "an"), ("im", "am"), ("ir", "ar"), ("ii", "ai"))


def fold(word: str) -> str:
    return word.translate(FOLD).lower()


def build_dictionary(hunspell_dir: Path) -> tuple[set[str], set[str]]:
    """Expand ro_RO.dic with the ro_RO.aff affixes into ASCII-folded word sets.

    Returns (everything, common): ``common`` leaves out proper names (entries that
    only exist capitalised), so a name never becomes the result of a correction."""
    suffixes: dict[str, list] = collections.defaultdict(list)
    prefixes: dict[str, list] = collections.defaultdict(list)
    current = None
    for line in (hunspell_dir / "ro_RO.aff").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] in ("SFX", "PFX") and parts[2] in ("Y", "N") and parts[3].isdigit():
            current = (parts[0], parts[1])
            continue
        if len(parts) >= 5 and parts[0] in ("SFX", "PFX") and (parts[0], parts[1]) == current:
            _, flag, strip, add, cond = parts[:5]
            strip = "" if strip == "0" else strip
            add = ("" if add == "0" else add).split("/")[0]
            regex = None
            if cond != ".":
                regex = re.compile(cond + "$" if parts[0] == "SFX" else "^" + cond)
            (suffixes if parts[0] == "SFX" else prefixes)[flag].append((strip, add, regex))
    words: set[str] = set()
    common: set[str] = set()
    for line in (hunspell_dir / "ro_RO.dic").read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        stem, _, flags = line.partition("/")
        stem = stem.strip()
        forms = {stem}
        for flag in flags:
            for strip, add, regex in suffixes.get(flag, ()):
                if (regex and not regex.search(stem)) or (strip and not stem.endswith(strip)):
                    continue
                forms.add(stem[:len(stem) - len(strip)] + add)
        for flag in flags:
            for strip, add, regex in prefixes.get(flag, ()):
                for base in list(forms):
                    if not regex or regex.search(base):
                        forms.add(add + base)
        for form in forms:
            if form.isalpha():
                words.add(fold(form))
                if not stem[:1].isupper():
                    common.add(fold(form))
    return words, common


def detect_language(text: str) -> str:
    words = [w.lower() for w in WORD.findall(text)]
    if not words:
        return "none"
    ro = sum(w in ROMANIAN_STOPWORDS for w in words) / len(words)
    en = sum(w in ENGLISH_STOPWORDS for w in words) / len(words)
    return "ro" if ro > en * 1.5 else ("en" if en > ro * 1.5 else "mix")


def apply_case(original: str, replacement: str) -> str | None:
    if original.islower():
        return replacement
    if original.isupper():
        return replacement.upper()
    return None  # Titlecase / mixed: names, left alone


class Fixer:
    def __init__(self, dictionary: set[str], common: set[str], counts: collections.Counter,
                 bigrams: collections.Counter):
        self.dict = dictionary
        self.common = common
        self.counts = counts
        self.bigrams = bigrams

    # -- rule 1 -------------------------------------------------------------
    def _is_nonword(self, frag: str) -> bool:
        low = frag.lower()
        if len(low) == 1:
            return low not in "aoi"
        return low not in self.dict

    def join_pair(self, left: str, right: str) -> str | None:
        if right.isupper() and len(right) == 1:
            return None  # "vitamin A", "hepatita B"
        same_case = (left.islower() or left.istitle()) and right.islower() or (left.isupper() and right.isupper())
        if not same_case:
            return None
        joined = left + right
        low = joined.lower()
        if len(low) < 5 or not (low in self.common or (left.istitle() and low in self.dict)):
            return None
        if not (self._is_nonword(left) or self._is_nonword(right)):
            return None
        pair = self.bigrams.get((left.lower(), right.lower()), 0)
        if pair >= 3 and pair * 2 >= self.counts.get(low, 0):
            return None
        return joined

    def join_line(self, line: str) -> tuple[str, list]:
        changes: list = []
        for _ in range(4):
            tokens = list(TOKEN.finditer(line))
            out: list[str] = []
            pos = 0
            i = 0
            changed = False
            while i < len(tokens):
                tok = tokens[i]
                nxt = tokens[i + 1] if i + 1 < len(tokens) else None
                if nxt is not None and line[tok.end():nxt.start()] == " ":
                    joined = self.join_pair(tok.group(), nxt.group())
                    if joined:
                        out.append(line[pos:tok.start()])
                        out.append(joined)
                        pos = nxt.end()
                        changes.append(("join", f"{tok.group()} {nxt.group()}", joined))
                        changed = True
                        i += 2
                        continue
                i += 1
            if not changed:
                break
            out.append(line[pos:])
            line = "".join(out)
        return line, changes

    # -- rule 2 -------------------------------------------------------------
    def _piece_ok(self, piece: str) -> bool:
        if piece in FUNCTION_WORDS:
            return True
        return len(piece) >= 5 and piece in self.common and self.counts.get(piece, 0) >= 100 and piece not in PREFIXES

    def split_token(self, low: str) -> list[str] | None:
        if len(low) < 8 or low in self.dict or low in KEEP or self.counts.get(low, 0) > 3:
            return None
        best: list[str] | None = None
        best_score = 0
        n = len(low)
        for i in range(2, n - 1):
            left, rest = low[:i], low[i:]
            if not self._piece_ok(left):
                continue
            options = [[rest]] if self._piece_ok(rest) else []
            for j in range(2, len(rest) - 1):
                mid, tail = rest[:j], rest[j:]
                if self._piece_ok(mid) and self._piece_ok(tail):
                    options.append([mid, tail])
            for opt in options:
                pieces = [left] + opt
                if all(p in FUNCTION_WORDS for p in pieces):
                    continue
                score = min(self.counts.get(p, 10 ** 6 if p in FUNCTION_WORDS else 0) for p in pieces) / len(pieces)
                if score > best_score:
                    best, best_score = pieces, score
        return best

    # -- rule 3 / 4 ---------------------------------------------------------
    def edits1(self, word: str) -> set[str]:
        letters = "abcdefghijklmnopqrstuvwxyz"
        splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
        deletes = {a + b[1:] for a, b in splits if b}
        transposes = {a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1}
        replaces = {a + c + b[1:] for a, b in splits if b for c in letters}
        inserts = {a + c + b for a, b in splits for c in letters}
        return (deletes | transposes | replaces | inserts) - {word}

    def typo_fix(self, low: str) -> str | None:
        if len(low) < 5 or low in self.dict or low in KEEP or self.counts.get(low, 0) > 2:
            return None
        own = self.counts.get(low, 0)
        cands = []
        for word in self.edits1(low):
            freq = self.counts.get(word, 0)
            if word not in self.common or freq < max(100, 30 * own):
                continue
            transposed = len(word) == len(low) and sorted(word) == sorted(low)
            if len(low) < 7 and not transposed:
                continue
            # an edit touching the last two letters is more likely an inflection than a typo
            tail = 0
            while tail < min(len(word), len(low)) and word[-1 - tail] == low[-1 - tail]:
                tail += 1
            if tail < 2:
                continue
            if word[0] != low[0] and freq < 300:
                continue
            cands.append((freq, word))
        if not cands:
            return None
        cands.sort(reverse=True)
        if len(cands) > 1 and cands[0][0] < 5 * cands[1][0]:
            return None
        return cands[0][1]

    def old_orthography_fix(self, low: str) -> str | None:
        if low in OLD_ORTHOGRAPHY:
            return OLD_ORTHOGRAPHY[low]
        if len(low) < 6 or low in self.dict or low in KEEP:
            return None
        variants: set[str] = set()
        for old, new in OLD_SWAPS:
            if old not in low:
                continue
            variants.add(low.replace(old, new))
            for m in re.finditer(old, low):
                variants.add(low[:m.start()] + new + low[m.end():])
        good = {v for v in variants if v in self.common and self.counts.get(v, 0) >= max(3, 3 * self.counts.get(low, 0))}
        return good.pop() if len(good) == 1 else None

    def fix_tokens(self, line: str):
        changes: list = []

        def repl(match: re.Match) -> str:
            tok = match.group()
            low = tok.lower()
            if tok.istitle() and len(tok) > 1 or (tok.isupper() and len(tok) < 6) or low in self.dict:
                return tok
            pieces = self.split_token(low)
            if pieces:
                new = apply_case(tok, " ".join(pieces))
                if new:
                    changes.append(("split", tok, new))
                    return new
            fix = self.old_orthography_fix(low)
            rule = "orthography"
            if not fix:
                fix, rule = self.typo_fix(low), "typo"
            if fix:
                new = apply_case(tok, fix)
                if new:
                    changes.append((rule, tok, new))
                    return new
            return tok

        return TOKEN.sub(repl, line), changes

    def fix_line(self, line: str):
        if SKIP_LINE.search(line):
            return line, []
        line, c1 = self.join_line(line)
        line, c2 = self.fix_tokens(line)
        return line, c1 + c2


def read_text(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hunspell-dir", type=Path, required=True, help="directory holding ro_RO.dic and ro_RO.aff")
    parser.add_argument("--docs", type=Path, default=DOCS)
    parser.add_argument("--report", type=Path, default=ROOT / "var" / "spelling_changes.tsv")
    parser.add_argument("--apply", action="store_true", help="write the corrections (default: dry run)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    dictionary, common = build_dictionary(args.hunspell_dir)
    print(f"dictionary: {len(dictionary):,} forms ({len(common):,} excluding proper names)")

    files: list[tuple[Path, str]] = []
    counts: collections.Counter = collections.Counter()
    bigrams: collections.Counter = collections.Counter()
    for path in sorted(args.docs.rglob("*")):
        if not path.is_file():
            continue
        text = read_text(path)
        if detect_language(text) != "ro":
            continue
        files.append((path, text))
        for line in text.splitlines():
            words = [w.lower() for w in WORD.findall(line)]
            counts.update(words)
            bigrams.update(zip(words, words[1:]))
    print(f"romanian files: {len(files)}")

    fixer = Fixer(dictionary, common, counts, bigrams)
    rule_totals: collections.Counter = collections.Counter()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    changed_files = 0
    with open(args.report, "w", encoding="utf-8") as report:
        report.write("file\tline\trule\tbefore\tafter\n")
        for path, text in files:
            lines = text.splitlines(keepends=True)
            new_lines = []
            file_changes = 0
            for number, raw in enumerate(lines, 1):
                body = raw.rstrip("\r\n")
                ending = raw[len(body):]
                fixed, changes = fixer.fix_line(body)
                new_lines.append(fixed + ending)
                for rule, before, after in changes:
                    rule_totals[rule] += 1
                    file_changes += 1
                    report.write(f"{path.relative_to(args.docs)}\t{number}\t{rule}\t{before}\t{after}\n")
            if file_changes:
                changed_files += 1
                if args.apply:
                    with open(path, "w", encoding="utf-8", newline="") as handle:
                        handle.write("".join(new_lines))
    print(f"changes: {sum(rule_totals.values()):,} in {changed_files} files  {dict(rule_totals)}")
    print(f"report: {args.report}")
    print("applied" if args.apply else "dry run (use --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
