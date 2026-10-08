"""For every candidate species found in the corpus, counts the occurrences whose
±300-character window holds a medicinal word; writes latin -> [hits, total, best window]."""
import json, re
from pathlib import Path
rows = [json.loads(l) for l in open("tmp/herbs_candidates.jsonl", encoding="utf-8")]
WORDS = re.compile(r"(trat|leac|ceai|infuz|decoct|tinctur|remedi|medic|vindec|boal|boli|afect|durer|tuse|diure|laxat|calmant|antisept|cataplasm|unguent|vulnerar|febr|digest|reuma|astring|expector|sedativ|tonic|util|folos|herb|tea|tincture|remed|treat|heal|cure|dose|dosage|pain|cough|wound|antibio|antifung|inflam|use[ds]? )", re.I)
docs = {}
out = {}
for r in rows:
    names = [r["latin"], *r.get("written", [])]
    hits = total = 0; best = None
    for d in r["corpus_documents"]:
        text = docs.get(d) or docs.setdefault(d, Path("medicina-naturista-documente/data/documents", d).read_text(encoding="utf-8", errors="replace"))
        for n in names:
            for m in re.finditer(re.escape(n), text):
                total += 1
                window = " ".join(text[max(0, m.start()-300):m.end()+300].split())
                if WORDS.search(window):
                    hits += 1
                    best = best or window
                elif best is None and total == 1:
                    first = window
    out[r["latin"]] = [hits, total, best]
json.dump(out, open("tmp/herbs_work/medicinal_context.json", "w", encoding="utf-8"), ensure_ascii=False)
no = [k for k, v in out.items() if v[1] and not v[0]]
print("corpus species:", sum(1 for v in out.values() if v[1]), "without medicinal context:", len(no))
print("; ".join(no))
