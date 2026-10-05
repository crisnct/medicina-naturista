import json, sys
rows = [json.loads(l) for l in open("tmp/herbs_candidates.jsonl", encoding="utf-8")]
hints = json.load(open("tmp/herbs_work/corpus_ro_names.json", encoding="utf-8"))
start, end = int(sys.argv[1]), int(sys.argv[2])
src = {"FR X": "F", "dictionar": "D", "corpus": "C", "EMA": "E", "literatura RO": "L"}
for i, r in enumerate(rows[start:end], start):
    o = {"spontan": "S", "spontan (introdus)": "I", None: "-"}.get(r["origin"], r["origin"])
    g = {"planta": "", "ciuperca": "F:", "lichen": "Li:", "alga": "A:", "muschi": "M:"}[r["group"]]
    h = "/".join(list(hints.get(r["latin"], {}))[:2])
    ro = r["ro"] or ""
    alts = "/".join(r["ro_alternatives"][:2])
    print(f"{i}|{g}{r['latin']}|{o}{r['gbif_ro_occurrences']}|{''.join(src[s] for s in r['sources'])}|{ro}|{alts}|{h}")
