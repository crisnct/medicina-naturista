"""Applies tmp/herbs_work/regional_knowledge.txt to data/herbs.jsonl (adds and
removes regional names) and records the additions as "cunostinte" in
tmp/herbs_work/herbs_provenance.jsonl."""
import json
from pathlib import Path
herbs_path, prov_path = Path("data/herbs.jsonl"), Path("tmp/herbs_work/herbs_provenance.jsonl")
herbs = [json.loads(l) for l in herbs_path.read_text(encoding="utf-8").splitlines()]
prov = {json.loads(l)["latin"]: json.loads(l) for l in prov_path.read_text(encoding="utf-8").splitlines()}
by_latin = {h["latin"]: h for h in herbs}
added = removed = 0
for line in Path("tmp/herbs_work/regional_knowledge.txt").read_text(encoding="utf-8").splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    op, rest = line[0], line[2:]
    latin, names = rest.split("|")
    herb = by_latin[latin]
    for name in names.split(";"):
        assert name.isascii() and "," not in name, name
        if op == "+":
            assert name.lower() != herb["ro"].lower() and name not in herb["ro_regional"], (latin, name)
            herb["ro_regional"].append(name)
            prov[latin]["ro_regional_from"][name] = "cunostinte"
            added += 1
        else:
            assert name in herb["ro_regional"], (latin, name)
            herb["ro_regional"].remove(name)
            prov[latin]["ro_regional_from"].pop(name, None)
            removed += 1
herbs_path.write_text("".join(json.dumps(h, ensure_ascii=False) + "\n" for h in herbs), encoding="utf-8", newline="\n")
prov_path.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in prov.values()), encoding="utf-8", newline="\n")
print(f"added {added}, removed {removed}")
