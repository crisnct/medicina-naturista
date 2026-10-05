import json, re
rows = [json.loads(l) for l in open('tmp/icd10_work/icd10_ro.jsonl', encoding='utf-8')]
ext = {r['code'] for r in rows}
cm = set()
for line in open('tmp/icd10_work/icd10cm/icd10cm_order_2026.txt', encoding='latin-1'):
    c = line[6:13].strip()
    if len(c) == 3 and 'A00' <= c <= 'Q99':
        cm.add(c)
print('missing3', len(cm - ext), sorted(cm - ext))
bad = [r for r in rows if not re.match(r'^[A-Z][a-z]', r['title_ro']) or len(r['title_ro']) > 140]
print('bad', len(bad))
for r in bad[:40]:
    print(r['code'], r['title_ro'][:110])
