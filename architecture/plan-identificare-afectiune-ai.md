# Plan: identificarea afecțiunii cu AI când dicționarul nu o găsește

**Stare:** aprobat și implementat (2026-10-04); pașii 1–5 din secțiunea 13 sunt făcuți, fără rularea testelor cu Postgres (vezi „Note de implementare”). Toate deciziile (D1–D4, secțiunea 2) sunt luate.

**Scop:** după ce pacientul scrie mesajul în chat, afecțiunea se caută ca azi în dicționar (`resolve_query()` peste `data/medical_conditions.txt`). Dacă dicționarul nu recunoaște nicio afecțiune, mesajul se trimite la un model AI gratuit (Hugging Face sau un model mic descărcat local), care încearcă să identifice afecțiunea. **Afecțiunea întoarsă de AI se folosește exact ca una venită din `medical_conditions.txt`**: în mesajul din chat, în căutare și în titlul PDF-ului final. Dacă nici modelul nu reușește, pacientul vede în chat că afecțiunea nu a putut fi identificată.

Planul are trei părți: **[Partea I — Ce se schimbă](#partea-i--ce-se-schimbă)**, **[Partea II — Implementare](#partea-ii--implementare)** și **[Partea III — Riscuri și verificare](#partea-iii--riscuri-și-verificare)**.

----------------------------------------------------------------------------------------------------

## Partea I — Ce se schimbă

### 1. Fluxul văzut de pacient

```text
mesaj ──► resolve_query() (dicționar)
            │
            ├─ afecțiune găsită ──► „✅ Am identificat afecțiunea: **Gripa**.”                     (neschimbat)
            │
            └─ nicio afecțiune ──► model AI ──► afecțiune (nume + sinonime)
                                        │
                                        ├─ identificată ──► „✅ Am identificat afecțiunea (cu ajutorul AI): **Hipertiroidism**.
                                        │                     O caut și după denumirile: tiroidă hiperactivă, hyperthyroidism.”
                                        │                   → căutare + titlul PDF „Remedii naturiste pentru hipertiroidism”
                                        │
                                        └─ neidentificată / AI indisponibil ──► „⚠️ Nu am putut identifica afecțiunea din mesaj.” (+ D2)
```

- **1.1.** Pasul AI rulează **doar** când semnalul „Căutare afecțiuni” (A) este bifat și dicționarul nu a găsit **nicio** afecțiune în **niciun** segment al mesajului. Dicționarul rămâne prima sursă (D1).
- **1.2. Identificare permisivă, inclusiv din simptome (D1).** Modelul nu e restricționat: recunoaște afecțiunea numită altfel decât în dicționar (perifraze ca „tiroida care merge prea repede”, denumiri în altă limbă, greșeli de scriere peste toleranța fuzzy, denumiri populare) **și** deduce afecțiunea cea mai probabilă din simptome („am febră și tuse de 3 zile” → de ex. Gripa). Rămâne „neidentificată” doar când mesajul nu descrie nicio problemă de sănătate sau modelul nu poate propune nimic.
- **1.3. Afecțiunea AI = o afecțiune din dicționar.** Modelul întoarce, pentru fiecare segment al mesajului (părțile despărțite prin virgulă), numele afecțiunii și câteva sinonime (română + engleză), adică exact forma unei linii din `medical_conditions.txt`. Din ele se construiește un `Condition(name, terms)` obișnuit, iar segmentul devine un segment recunoscut ca afecțiune întreagă (`whole_condition=True`). De acolo, totul merge pe drumul existent, fără ramuri speciale:
  - **chat:** același mesaj „Am identificat afecțiunea …”, cu mențiunea „(cu ajutorul AI)” și cu sinonimele, ca pentru dicționar;
  - **semnalul lexical L:** expresia segmentului = SAU între numele și sinonimele afecțiunii (regula 4.2.1 din [plan-tipuri-cautare-selectabile.md](plan-tipuri-cautare-selectabile.md)), la fel ca la o afecțiune din dicționar;
  - **semnalele P1/P2:** numele afecțiunii se caută în `primary_medical_conditions` / `secondary_medical_conditions` (vezi 1.4);
  - **PDF:** titlul devine „Remedii naturiste pentru <afecțiunea AI>” (cerință explicită; vezi 9.1).
- **1.4. P1/P2 — limita inevitabilă.** Coloanele `primary_medical_conditions` / `secondary_medical_conditions` conțin doar numele canonice din dicționar, scrise la indexare. De aceea:
  - dacă numele sau un sinonim întors de AI este **exact** un termen din dicționar (ex. AI întoarce „hipertiroidie”, care e sinonim al „Hipertiroidism”), P1/P2 se calculează cu numele canonic al acelei afecțiuni — altfel afecțiunea ar fi în dicționar, dar n-ar puncta;
  - altfel P1 = P2 = 0 pentru toate fragmentele (nu există fragmente indexate pe un nume necunoscut indexului); afecțiunea contează prin L, prin semantic și în chat/PDF. Nicio afecțiune AI nu se aruncă.
- **1.5.** Ordinea mesajelor în chat:
  1. mesajul pacientului;
  2. „🔍 Caut rapid în cele N documente…” (`POST /api/messages`, instantaneu, ca azi);
  3. „✅ Am identificat afecțiunea (cu ajutorul AI): …” **sau** „⚠️ Nu am putut identifica afecțiunea…” (`POST /api/search`, înaintea fragmentelor);
  4. fragmentele (sau mesajul de la D2).

  Apelul AI stă în `POST /api/search`, ca ecoul mesajului și anunțul „Caut rapid” să rămână instantanee. Cele 1–5 secunde ale apelului se adaugă la căutare, sub indicatorul de încărcare existent.

### 2. Decizii

- **D1 — confirmat (revizuit).** Dicționarul e primul; AI doar când dicționarul nu găsește nimic; modelul e permisiv și poate deduce afecțiunea și din simptome; afecțiunea AI apare în titlul PDF.
- **D3 — confirmat: `gemma3:1b` local.** Backendul principal este `gemma3:1b` (~0,8 GB) rulat local prin Ollama; Hugging Face (router, `HF_TOKEN`) rămâne fallback doar când modelul local e indisponibil (secțiunea 3 și 5.2). Testul 9.3 verifică calitatea, nu mai alege modelul.
- **D4 — confirmat.** Fără token, timeout, eroare HTTP sau JSON invalid → „neidentificată”, cu motivul în log; căutarea nu eșuează din cauza pasului AI.

#### D2 — confirmat: V2 (căutarea continuă, procente recalculate)

Când AI-ul nu identifică afecțiunea (sau nu e disponibil):

- **2.1.** În chat apare „⚠️ Nu am putut identifica afecțiunea din mesaj. Caut după textul mesajului.”, iar căutarea continuă cu semnalele B/C bifate (P1 = P2 = 0 pentru toate fragmentele).
- **2.2.** Procentul de relevanță se raportează la scorul maxim al semnalelor care **au putut** contribui, adică fără A: cu A+B+C bifate, maximul devine cel al lui B+C (2), nu 8. Fără această corecție, cel mai bun fragment ar avea cel mult 25%, chiar dacă e exact pe subiect.
- **2.3.** Doar A bifat → fără afecțiune nu poate puncta niciun fragment: căutarea se oprește cu „⚠️ Nu am putut identifica afecțiunea din mesaj. Scrieți denumirea afecțiunii (ex. gripă, hipertensiune).” (în locul „Nu am găsit fragmente relevante…” de azi).
- **2.4.** A debifat → pasul AI nu rulează și nu apare niciun mesaj despre afecțiune (ca azi).
- **2.5.** Titlul PDF fără afecțiune identificată rămâne ca azi: „Remedii naturiste pentru <textul tastat>”.

----------------------------------------------------------------------------------------------------

## Partea II — Implementare

### 3. Configurare — `src/backend/config.py`, `docker-compose.yaml`, `README.md`

| Variabilă | Implicit | Rol |
|---|---|---|
| `CONDITION_AI_BACKENDS` | `local,huggingface` | Lista ordonată de backenduri: `huggingface`, `local`, `local,huggingface` (local întâi, HF dacă localul e indisponibil) sau gol (pas dezactivat — folosit în evaluări și teste) |
| `CONDITION_AI_HF_MODEL` | după 9.3 | Modelul HF (prin `HF_API_BASE`, `HF_TOKEN`, deja existente) |
| `CONDITION_AI_LOCAL_MODEL` | `gemma3:1b` | Modelul Ollama local |
| `CONDITION_AI_LOCAL_BASE` | `http://localhost:11434/v1` | Adresa Ollama (în Docker: `http://ollama:11434/v1`) |
| `CONDITION_AI_TIMEOUT_SECONDS` | `10` | Timeout per backend |
| `CONDITION_AI_MAX_OUTPUT_TOKENS` | `300` | Răspunsul e un JSON mic |

Fallback-ul din `local,huggingface` se aplică doar la **indisponibilitate** (eroare, timeout, JSON invalid), nu și când localul răspunde corect „nicio afecțiune” — altfel orice mesaj fără afecțiune ar costa și un apel HF.

### 4. Promptul — `src/backend/ai/prompts/condition_identification_system.md` (nou)

- intrare: segmentele mesajului, numerotate;
- ieșire, **doar** JSON: `{"segments": [{"index": 1, "name": "Hipertiroidism", "synonyms": ["tiroida hiperactiva", "hyperthyroidism"]}]}`; segmentele fără afecțiune lipsesc din listă; cel mult 8 sinonime, fără diacritice obligatorii (ca în `medical_conditions.txt`);
- `name` = denumirea medicală uzuală în română, scrisă ca în dicționar (prima literă mare);
- **permisiv** (D1): dacă segmentul descrie simptome, se întoarce afecțiunea cea mai probabilă care le explică; un singur nume per segment;
- segmentul lipsește doar când nu descrie nicio problemă de sănătate;
- 4–6 exemple scurte, inclusiv cu simptome („am febră și tuse de 3 zile” → Gripa) și negative („ce plante sunt bune?” → `{"segments": []}`).

Promptul trebuie să rămână scurt: modelele locale < 1 GB au context mic și urmează mai prost instrucțiunile lungi.

### 5. Modulul nou — `src/backend/ai/condition_ai.py`

- **5.1.** `identify_conditions(resolved: ResolvedQuery) -> AIConditionResult`, cu `resolved: ResolvedQuery` (cererea completată, vezi 5.4), `conditions: tuple[Condition, ...]`, `backend: str`, `reason: str` (`identified` / `none` / `disabled` / `no_token` / `timeout` / `error`).
- **5.2. Backendurile.** Ambele printr-un `ResponsesClient` din `ai/client.py` (deja folosit pentru HF și Ollama la raport), fiecare cu propriul `ProviderConfig` (HF: `HF_API_BASE` + `CONDITION_AI_HF_MODEL`; local: `CONDITION_AI_LOCAL_BASE` + `CONDITION_AI_LOCAL_MODEL`, fără cheie) și un `Settings` derivat prin `dataclasses.replace()` (timeout, `max_output_tokens`, `ai_stream=False`). Se folosește `complete_json()`, care validează JSON-ul și ridică `AIUnavailable`. Independent de `AI_PROVIDER`-ul raportului. Se încearcă backendurile în ordinea din `CONDITION_AI_BACKENDS`, cu regula de fallback de la secțiunea 3.
- **5.3. Validare minimă (de formă, nu de conținut):** `index` valid; `name` șir nevid de cel mult 100 de caractere; `synonyms` listă de șiruri (altfel goală), trunchiată la 8, fără duplicate și fără numele însuși. Nu se verifică dacă afecțiunea există în dicționar (cerința de la 1.3).
- **5.4. Completarea cererii:** `with_ai_conditions(resolved, answers) -> ResolvedQuery` înlocuiește segmentele identificate cu `QuerySegment(text, conditions=(Condition(name, (name, *synonyms)),), remainder="", whole_condition=True)`; celelalte segmente rămân neschimbate. Maparea pe numele canonic pentru P1/P2 (1.4) se face aici: dacă `name` sau un sinonim este exact un termen din dicționar, `Condition.name` devine numele canonic al acelei afecțiuni, iar termenii AI se adaugă la termenii ei.
- **5.5.** Cache `lru_cache` (128 de intrări) pe textul normalizat al segmentelor; erorile nu se pun în cache.
- **5.6.** Log fără textul mesajului (regula din `config.py`): `condition_ai_completed backend=… reason=… segments=… identified=<nume> mapped_to_dictionary=<da/nu> duration_ms=…`.

### 6. Starea pe sesiune — `src/backend/core/models.py`

- **6.1.** `HealthProfile.ai_conditions: tuple[dict, ...] = ()` — pentru fiecare segment identificat: `{"index", "name", "terms"}`. `replace_health_problem()` / `set_health_problem()` îl golesc, ca un mesaj nou să nu moștenească afecțiunea celui vechi.
- **6.2.** `as_dict()` îl include, deci ajunge în `PendingSearch.profile` și de acolo la raport și la PDF.
- **6.3.** Funcție comună `resolved_for(profile) -> ResolvedQuery` (în `ai/condition_ai.py`): `resolve_query(health_problem)` + `with_ai_conditions(…, profile.ai_conditions)`. O folosesc căutarea, mesajul din chat și PDF-ul, ca toate trei să vadă aceleași afecțiuni.

### 7. Căutarea

- **7.1.** `ai/search.py` — `rank()` primește opțional `resolved: ResolvedQuery | None = None`; dacă lipsește, îl calculează ca azi cu `resolve_query(query)`. `condition_names` și `lexical_queries()` lucrează pe el, deci afecțiunea AI intră automat în P1/P2 și L.
- **7.2.** `ai/retrieval.py` — `Retriever.collect()` trimite `resolved_for(profile)` la `rank()`.
- **7.3.** (D2 = V2) Funcția nouă `effective_signals(signals, resolved)` din `ai/search.py` întoarce semnalele cu A oprit când cererea nu are nicio afecțiune (nici din dicționar, nici de la AI). O folosesc atât `rank()` (ponderile din `weights()`), cât și `Retriever.collect()` (plafonul procentului, `max_score()`), ca scorul și procentul să rămână consistente.

### 8. Chatul — `src/backend/web/main.py`

- **8.1.** `post_message()`: neschimbat.
- **8.2.** `post_search()`, înainte de `retriever.collect()`: dacă A e bifat, `CONDITION_AI_BACKENDS` nu e gol și `resolve_query(health_problem).conditions` e gol → `identify_conditions()`; rezultatul se scrie în `session.profile.ai_conditions`, apoi se adaugă mesajul de la 1.5 pas 3 și se aplică D2 (2.1–2.3).
- **8.3.** `_condition_identified_message()` primește `ResolvedQuery`-ul completat și un marcaj „cu ajutorul AI”; altfel aceleași reguli (inclusiv „O caut și după denumirile: …”, pentru că afecțiunea AI e `whole_condition`).
- **8.4.** Apelul AI se face **în afara** `session.lock` (lockul se eliberează pe durata apelului și se reia pentru scriere), ca alte cereri ale sesiunii să nu aștepte după rețea. La reluare se verifică că `health_problem` nu s-a schimbat între timp; altfel rezultatul se aruncă.

### 9. PDF, scripturi, model local

- **9.1. Titlul PDF (cerință explicită).** `reporting/pdf.py` — `condition_names_for()` primește profilul: întâi afecțiunile din dicționar (ca azi: `find_conditions()` apoi `resolve_query()`), iar dacă nu există, numele din `profile["ai_conditions"]`; aceeași restaurare a diacriticelor și același `_join_romanian()`. Rezultat: „Remedii naturiste pentru hipertiroidism”. Titlul e folosit deja pentru metadate, coperta și numele fișierului descărcat, deci toate trei se schimbă împreună.
- **9.2.** `scripts/evaluate_retrieval.py` rulează cu `CONDITION_AI_BACKENDS=` (gol): evaluări deterministe și gratuite.
- **9.3. Test de calitate** — `tmp/condition_ai_smoke.py`, ~40 de mesaje: perifraze, engleză, greșeli mari, denumiri populare, mesaje cu mai multe segmente, **mesaje doar cu simptome** (trebuie să dea o afecțiune plauzibilă) și mesaje fără nicio problemă de sănătate (trebuie să rămână neidentificate). Pentru `gemma3:1b` și, ca reper, pentru modelul HF se notează: identificări corecte, nume greșite sau inventate, JSON invalid, durata. Modelele din tabel:

  | Model | Backend | Mărime aprox. | Observații |
  |---|---|---|---|
  | `gemma3:1b` | local (Ollama) | ~0,8 GB | **ales (D3)**; multilingv |
  | `qwen3:0.6b` | local (Ollama) | ~0,5 GB | rapid; are mod „thinking”, care trebuie oprit (`/no_think`) |
  | `qwen2.5:0.5b` | local (Ollama) | ~0,4 GB | cel mai mic; probabil slab la română |
  | `gemma3:270m` | local (Ollama) | ~0,3 GB | doar ca reper inferior |
  | un model instruct de 7–30B | Hugging Face | — | reperul de calitate pentru modelele locale |

  Mărimile sunt orientative și se verifică la descărcare. Celelalte modele locale rămân alternative, dacă `gemma3:1b` dezamăgește. Modelele sub 1 GB sunt vizibil mai slabe la română, iar afecțiunea AI nu mai e filtrată prin dicționar (1.3), deci calitatea contează direct. Dacă `gemma3:1b` dă peste ~10% nume greșite, se inversează ordinea (`huggingface,local`) sau se rămâne doar pe HF — o schimbare de configurare, nu de cod.
- **9.4. Ollama local.** Pe Windows, pentru dezvoltare: Ollama instalat pe mașină, iar descărcarea modelului o rulezi tu, de exemplu `ollama pull gemma3:1b`. În Docker: serviciu nou `ollama` în `docker-compose.yaml` (imaginea oficială `ollama/ollama`, volum pentru modele, doar în rețeaua `internal`, fără port public, `mem_limit` ~2 GB), iar `app` primește `CONDITION_AI_LOCAL_BASE=http://ollama:11434/v1`. Pe CPU, un model de 1B răspunde la un JSON scurt în ~1–3 s; prima cerere după pornire încarcă modelul (câteva secunde), deci la startul aplicației se face o cerere de încălzire, ca la `warm_up_search`.
- **9.5. Alternativa fără Ollama** (doar dacă nu vrei un serviciu în plus): `llama-cpp-python` în procesul aplicației, cu un fișier GGUF în `data/model_cache`. Dezavantaje: o dependență nativă nouă (compilare pe unele platforme), încă ~1 GB RAM în containerul `app` (limita e 4 GB, împărțită cu modelul de embedding) și un client separat de `ResponsesClient`. Recomand Ollama.

### 10. Frontend

Nicio schimbare de cod: mesajele noi sunt mesaje text de asistent, afișate ca azi. De verificat doar că indicatorul de încărcare al `POST /api/search` acoperă și secundele în plus.

----------------------------------------------------------------------------------------------------

## Partea III — Riscuri și verificare

### 11. Riscuri

| Risc | Măsură |
|---|---|
| Modelul inventează sau greșește afecțiunea, care ajunge în căutare și în titlul PDF | Testul 9.3 și pragul de calitate; mesajul din chat spune „(cu ajutorul AI)”, deci pacientul vede afecțiunea înainte de raport și poate reformula |
| Afecțiunea dedusă din simptome e greșită (identificare permisivă, D1) | Mesajul din chat spune „(cu ajutorul AI)”, deci pacientul vede afecțiunea înainte de raport și poate reformula cu denumirea corectă |
| Afecțiune AI care nu e în index → fără P1/P2 | Maparea pe numele canonic (1.4, 5.4); în rest contează L și semantic |
| HF lent / indisponibil / credit epuizat | Timeout 10 s, fallback (secțiunea 3), apoi „neidentificată” (D4) |
| Model local lent la prima cerere | Încălzire la pornire (9.4) |
| Date medicale trimise la un terț | Doar la HF; mesajul ajunge deja la providerul AI pentru raport; se menționează în README; textul nu se loghează. Varianta locală nu trimite nimic în afară |
| Cost HF | Doar la mesajele nerecunoscute de dicționar + cache (5.5); un apel are ~300 de tokeni |
| O cerere nouă în timpul apelului AI | Verificarea de la 8.4 |

### 12. Teste

- **12.1.** `src/tests/unit/ai/test_condition_ai.py` (nou), cu `httpx` simulat: răspuns valid → `Condition` cu nume și sinonime, segment `whole_condition`; nume care e termen din dicționar → numele canonic pentru P1/P2; nume absent din dicționar → păstrat ca atare; JSON invalid / timeout / fără token / backend gol → motivul corect și nicio excepție; fallback local → HF doar la indisponibilitate; cache-ul nu păstrează erorile.
- **12.2.** `test_search.py`: `rank(..., resolved=…)` cu o afecțiune AI din dicționar punctează P1/P2; cu o afecțiune AI din afara dicționarului, L caută după numele și sinonimele ei.
- **12.3.** Teste pe `main.py`: dicționarul găsește → niciun apel AI; dicționarul nu găsește + AI găsește → mesajul „(cu ajutorul AI)” înaintea fragmentelor; AI nu găsește → mesajul de la 2.1 și fragmentele, cu procente raportate la maximul fără A (2.2); doar A bifat → oprire cu mesajul de la 2.3; mesaj nou → `ai_conditions` golit.
- **12.3.1.** `test_search.py`: `effective_signals()` oprește A doar când cererea nu are nicio afecțiune; în acest caz cel mai bun fragment poate ajunge la 100%.
- **12.4.** `test_pdf` (sau echivalentul): `report_title()` cu `ai_conditions` și fără afecțiune în dicționar → „Remedii naturiste pentru <afecțiunea AI>”; cu afecțiune în dicționar → neschimbat.
- **12.5.** `models.py`: `replace_health_problem()` golește `ai_conditions`.
- **12.6.** Manual, în browser: câte un mesaj pentru fiecare ramură din diagrama de la secțiunea 1, cu generarea PDF-ului pentru ramura „identificată”.

### 13. Ordinea de lucru

1. Prompt + `condition_ai.py` (ambele backenduri) + testele 12.1.
2. Instalarea Ollama și `ollama pull gemma3:1b` (de tine), apoi testul 9.3.
3. `models.py`, `search.py`, `retrieval.py` + testele 12.2, 12.5.
4. `main.py`, `pdf.py` + testele 12.3, 12.4.
5. `docker-compose.yaml` (serviciul `ollama`), README, `.env`, verificarea manuală 12.6.

Nu e nevoie de reindexare: indexul și numele canonice din `chunks` nu se schimbă.

----------------------------------------------------------------------------------------------------

## Note de implementare (2026-10-04)

- **Abateri de la plan:** (a) `ProviderConfig`/`_build_payload` primesc `temperature`; backendul local trimite `0.0`. Fără el, `gemma3:1b` a întors JSON invalid la ~40% din mesaje; cu el, la niciunul. (b) `ConditionDictionary.exact()` (nou) caută exact un termen din dicționar, pentru maparea pe numele canonic (1.4). (c) `CONDITION_AI_HF_MODEL` are implicit valoarea `HF_MODEL` (modelul HF de 7–30B pentru fallback rămâne de ales după 9.3). (d) Când `CONDITION_AI_BACKENDS` e gol și doar A e bifat, apare tot mesajul de la 2.3 (în loc de „Nu am găsit fragmente relevante”).
- **Test 9.3, `gemma3:1b` local** (`tmp/condition_ai_smoke.py --backend local`, 40 de mesaje, `temperature=0`): ~0,4 s per mesaj (cald), JSON valid la toate. Calitatea însă e slabă: din 28 de mesaje cu verdict clar, 13 corecte și 15 greșite; **toate mesajele fără problemă de sănătate** („buna ziua”, „care e capitala Frantei”, „asdf qwerty”…) au primit totuși o „afecțiune”, iar o parte din nume sunt inventate sau deformate („Stenoz renal”, „Nefrită renală” pentru pietre la rinichi). Depășește net pragul de ~10% din 9.3 → de ales: `CONDITION_AI_BACKENDS=huggingface,local` / doar `huggingface`, sau un model local mai mare (ex. `gemma3:4b`). Modelul HF nu a fost încă măsurat (cere `HF_TOKEN`).
- **Neexecutat aici:** testele din `test_search.py` (inclusiv `AIConditionRankTests`, noi) cer Postgres prin testcontainers, iar Docker nu a fost accesibil din mediul de lucru; rulează-le local. Verificarea manuală 12.6 în browser rămâne de făcut.

