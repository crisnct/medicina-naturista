"""Coverage gaps taken from the corpus disease dictionary (Jacques Martel).

Heading form in that document is `## NUMELE BOLII` (all caps). Two gap signals:
  * uppercase headings the dictionary does not recognise (missed chapter titles);
  * capitalised disease names used in the running text that the dictionary does not
    recognise (a name a book treats as a condition).

The file has a double encoding, repaired in memory. Read-only.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from backend.ai.conditions import load_dictionary  # noqa: E402

SOURCE = next((ROOT / "data" / "documents" / "Diverse").glob("Jacques Martel*/*.md"), None)
HEADING = re.compile(r"^\s{2,4}#{2,4}\s+(.+?)\s*$")
# a condition name as written mid-sentence: a capitalised noun phrase
INLINE = re.compile(r"\b([A-ZĂÂÎȘȚ][a-zăâîșț]{4,}(?:\s+[a-zăâîșț]{4,}){0,2})\b")
# words that start a sentence or are abstract, not disease names
STOPWORDS = {
    "aceasta", "acesta", "aceste", "acestea", "acest", "această", "acest", "aceeași", "același",
    "acum", "adeseori", "ajung", "aleg", "altfel", "astfel", "atunci", "așadar", "așa",
    "bineinteles", "cand", "când", "cateodata", "câteodată", "chiar", "cineva", "cuiva",
    "desigur", "deci", "devenind", "devin", "dimpotriva", "doi", "doar", "dupa", "după",
    "exista", "există", "faptul", "fiecare", "fiind", "foarte", "frica", "frică", "iar",
    "intr", "într", "însă", "insa", "lucru", "lucruri", "mai", "multe", "multi", "mulți",
    "nimic", "nimeni", "noastre", "nostru", "orice", "oricine", "partea", "pentru", "poate",
    "pot", "prin", "prima", "primul", "sau", "sentiment", "sentimente", "simt", "situatie",
    "situație", "stare", "starea", "toate", "toata", "toată", "totul", "trebuie", "unele",
    "uneori", "unora", "voi", "vom", "vreau", "vrea", "zone", "zona", "zona", "emotii",
    "emoții", "emotie", "emoție", "gand", "gând", "ganduri", "gânduri", "traire", "trăire",
    "trairi", "trăiri", "ajutor", "ajutorul", "boala", "boală", "boală", "bolile", "cauza",
    "cauzele", "tratament", "tratamentul", "remediu", "sfat", "sfaturi", "persoana",
    "persoanele", "omul", "oamenii", "viața", "viata", "vindecare", "vindecarea", "sanatate",
    "sănătate", "dragoste", "iubire", "iubirea", "constiinta", "conștiința", "energie",
    "energia", "spirit", "spiritul", "suflet", "sufletul", "minte", "mintea", "corp",
    "corpul", "dumnezeu", "univers", "universul", "legea", "planul", "adevar", "adevărul",
    "accept", "acceptarea", "acceptând", "acționez", "afectează", "alergia", "alergia",
    "angoasa", "angoasa", "anxietatea", "acneea", "acumularea", "albastru", "albul",
}
NOISE = re.compile(
    r"(?i)^(introducere|cuprins|prefata|capitol|partea|bibliografie|index|nota|despre|"
    r"multumiri|anexa|concluzii|pagina|table|contents|dedicatie|glosar|exprimari|total|"
    r"vindecare|sanatate|dragoste|frica|iubire|constiinta|energie|spirit|suflet|minte|"
    r"corp|boala|bolile|simptom|simptome|cauza|cauzele|tratament|remediu|ajutor|sfat|"
    r"martel|jacques|dumnezeu|univers|legea|planul|adevar|omul|oameni|viața|viata)"
)


def repair(text: str) -> str:
    try:
        return text.encode("latin-1", errors="strict").decode("utf-8", errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def normalize(value: str) -> str:
    table = str.maketrans("ăâîșțşţĂÂÎȘȚŞŢ", "aaiststAAISTST")
    return " ".join(re.findall(r"[^\W_]+", repair(value).translate(table).lower(), flags=re.UNICODE))


def main() -> int:
    if SOURCE is None or not SOURCE.exists():
        print("reference document not found")
        return 1
    text = repair(SOURCE.read_text(encoding="utf-8", errors="replace"))
    dictionary = load_dictionary()
    known = {normalize(item.name) for item in dictionary.conditions}
    known |= {normalize(term) for item in dictionary.conditions for term in item.terms}

    headings: set[str] = set()
    inline: collections.Counter[str] = collections.Counter()
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            title = re.sub(r"[*_`\[\]]", "", match.group(1)).strip(" .:;—-")
            # an uppercase heading is a disease chapter; lowercase ones are structure
            if title and title == title.upper() and len(title.split()) <= 5:
                if not NOISE.match(title) and any(ch.isalpha() for ch in title):
                    headings.add(title)
            continue
        if line.startswith("#") or len(line) > 200:
            continue
        for candidate in INLINE.findall(line):
            words = normalize(candidate).split()
            if not words or words[0] in STOPWORDS or words[-1] in STOPWORDS:
                continue
            if len(words) > 3:
                continue
            inline[candidate] += 1

    missing_headings = sorted((h for h in headings if normalize(h) not in known), key=normalize)
    missing_inline = sorted(
        (name for name, count in inline.items() if count >= 8 and normalize(name) not in known),
        key=normalize,
    )

    print(f"uppercase headings found      : {len(headings)}")
    print(f"headings NOT in dictionary    : {len(missing_headings)}")
    print(f"text names (3+ uses) NOT in dict: {len(missing_inline)}\n")
    print("--- headings missing (first 60) ---")
    for name in missing_headings[:60]:
        print(f"  {name}")
    print("\n--- frequent text names missing (first 60) ---")
    for name in missing_inline[:60]:
        print(f"  {name}")

    out = Path(__file__).resolve().parent / "gaps_from_corpus.txt"
    out.write_text("\n".join([*missing_headings, *missing_inline]) + "\n", encoding="utf-8")
    print(f"\nwritten: {out} ({len(missing_headings) + len(missing_inline)} names)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
