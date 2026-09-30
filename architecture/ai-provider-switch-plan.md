# Plan — furnizor AI configurabil pentru generarea rețetelor (xAI Grok 4.3 / DeepSeek-V4-Flash)

**Stare:** propus, neimplementat · **Data:** 2026-09-30

**Notă (2026-09-30):** `fit_evidence_to_context()` a fost eliminată de [refactorizarea scorului](fragment-scoring-refactoring-plan.md): bugetul (acum 1.000.000 de caractere, măsurat pe textul dovezilor) este aplicat în `search.rank(max_chars=...)`. Bugetul per furnizor de mai jos se transmite deci prin `Retriever.collect()` către `rank(max_chars=...)`, nu printr-o funcție separată; restul deciziilor rămân valabile.

**Afectează:** secțiunea 9 din [fluxul de generare a raportului final](final-report-generation.md) (`XAIClient.generate()` / `complete_json()` din `src/medicina_naturista/ai/client.py`) și pasul 3.5 (`fit_evidence_to_context()`).

## 1. Scop

- Fragmentele selectate de pacient pot fi trimise, pe lângă xAI (`grok-4.3`), și către **`deepseek-ai/DeepSeek-V4-Flash:deepinfra`** prin routerul Hugging Face Inference Providers, autentificat cu un token HF.
- Opțional, același model (sau succesorul lui) se poate folosi **prin Ollama**.
- Toate variantele folosesc **Responses API** (`POST {base}/responses`), nu Chat Completions.
- Implementarea xAI existentă **rămâne neatinsă ca funcționalitate**: același payload, aceleași mesaje, aceleași teste. Furnizorii noi se adaugă lângă ea.
- Furnizorul activ se alege printr-o variabilă de mediu: **`AI_PROVIDER=xai|huggingface|ollama`**, implicit `xai`. Schimbarea cere repornirea aplicației (setările se citesc la pornire, ca toate celelalte din `config.py`).

## 2. Ce am verificat

| Subiect | Constatare | Consecință pentru plan |
|---|---|---|
| Responses API la Hugging Face | Routerul expune `https://router.huggingface.co/v1/responses` (beta), autentificare `Authorization: Bearer $HF_TOKEN` (token fine-grained cu permisiunea „Make calls to Inference Providers”). Furnizorul se alege prin sufixul modelului (`:deepinfra`). Suportă `instructions`, `input` cu roluri `system`/`developer`/`user`, `reasoning.effort`, structured outputs. | Protocolul este același ca la xAI → aceeași logică de client, alt `base_url`, altă cheie. |
| Format JSON la HF | Documentația HF arată structured outputs prin `response_format` (stil Chat Completions), nu prin `text.format` (stil Responses). Nu e clar dacă `text.format: json_object` este respectat pentru DeepInfra. | **De verificat în Faza 0.** Promptul de sistem cere deja „exclusiv un singur obiect JSON valid”, deci avem și plasă de siguranță prin parsare tolerantă (§6.2). |
| Context DeepSeek-V4-Flash | Modelul suportă 1M tokeni, DeepInfra declară 1024k, dar **prin routerul HF limita raportată este 64k tokeni** (thread deschis pe forumul HF, fără rezolvare). | Bugetul actual `MAX_CONTEXT_CHARS` (1 000 000 direct / 2 400 000 în Docker Compose ≈ 250k–600k tokeni) **nu încape**. Bugetul de context devine per furnizor (§6.3). |
| Mod de gândire DeepSeek V4 | Trei moduri: non-think, think high, think max (max recomandat cu ≥ 384k context). | `reasoning.effort` trebuie mapat/verificat la DeepInfra; tokenii de reasoning consumă din `max_output_tokens` → risc de răspuns `incomplete` (§9). |
| Ollama — Responses API | `/v1/responses` există din **Ollama v0.13.3**, doar varianta stateless (fără `previous_response_id`/`conversation`). Suportă `model`, `input`, `instructions`, `max_output_tokens`, `reasoning.effort`, `think`. `text.format` și `store` nu apar în documentație. | Același client; fără `store`, iar JSON-ul se obține prin prompt + parsare tolerantă (de confirmat în Faza 0 dacă `text.format` e acceptat). |
| DeepSeek-V4-Flash în Ollama | Pagina `ollama.com/library/deepseek-v4-flash` spune că modelul **a fost retras pe 2026-09-25**. Succesorul disponibil este **`deepseek-v4.1-flash:cloud`** — doar variantă cloud (rulează pe serverele Ollama), fără tag local. | Vezi verdictul de mai jos. |
| Rulare locală | V4-Flash are 284B parametri (13B activi); există GGUF-uri (unsloth), dar chiar și cuantizate cer ordinul a ~100 GB+ de RAM/VRAM. | Nerealist pe o mașină obișnuită. |

### Verdict „prin Ollama”

**Da, se poate, dar nu cu tokenul Hugging Face și nu prin DeepInfra.** Ollama nu este un proxy către Inference Providers; este un furnizor separat:

- **Ollama local + model `:cloud`** (`deepseek-v4.1-flash:cloud`): aplicația vorbește cu daemonul local (`http://localhost:11434/v1/responses`), iar daemonul, după `ollama signin`, trimite cererea la Ollama Cloud. Fragmentele părăsesc tot mașina — doar că ajung la Ollama, nu la DeepInfra.
- **Ollama Cloud direct** (`https://ollama.com` cu `OLLAMA_API_KEY`): fără daemon local. Documentația confirmă `https://ollama.com/api/chat`; dacă și `/v1/responses` este expus direct pe `ollama.com` rămâne **de verificat în Faza 0**.
- **Ollama complet local:** nu pentru DeepSeek V4 (dimensiune). Ar funcționa cu un model mic, dar calitatea și contextul ar fi mult sub Grok/DeepSeek — în afara acestui plan.

**Recomandare:** implementăm ambii furnizori noi, fiindcă după refactorul din §6 un furnizor în plus înseamnă doar o intrare de configurare. Ca furnizor principal alternativ recomand **`huggingface`** (exact modelul cerut, cu DeepInfra), cu condiția ca Faza 0 să confirme limita reală de context. `ollama` rămâne opțiunea pentru `deepseek-v4.1-flash:cloud` (context de 1M, fără limita de 64k a routerului HF).

## 3. Decizii propuse (de confirmat la review)

| # | Întrebare | Propunere |
|---|---|---|
| D1 | Numele variabilei de selecție | `AI_PROVIDER`, valori `xai` (implicit), `huggingface`, `ollama`. Valoare necunoscută → `ValueError` la pornire (fail fast, ca `_int()`/`_bool()` din `config.py`). |
| D2 | Cheile API | Fiecare furnizor își păstrează propria variabilă: `X_API_KEY` (neschimbat), `HF_TOKEN`, `OLLAMA_API_KEY` (necesară doar pentru `https://ollama.com`). Nicio cheie nu se reutilizează între furnizori. |
| D3 | Modelul Ollama implicit | `deepseek-v4.1-flash:cloud` (V4-Flash e retras din Ollama). Suprascriptibil prin `OLLAMA_MODEL`. |
| D4 | Bugetul de context | Bugetul efectiv = `min(MAX_CONTEXT_CHARS, <PROVIDER>_MAX_CONTEXT_CHARS)`. Implicit HF: `120000` caractere (≈ 64k tokeni − 20k ieșire − prompt de sistem, calibrat în Faza 0). xAI: fără limită proprie (comportament neschimbat). |
| D5 | Unde se aplică bugetul | Tot într-un singur loc, `fit_evidence_to_context()`, imediat după retrieval, astfel încât pacientul vede exact fragmentele trimise (regula actuală, pasul 3.5). Cu HF pacientul va vedea **mult mai puține fragmente** decât cu Grok. |
| D6 | Formatul JSON | Per furnizor, în cod (nu în `.env`): xAI `text.format: json_object` (ca acum); HF și Ollama după rezultatul Fazei 0 (`text.format`, `response_format` sau doar prompt). |
| D7 | Parsare tolerantă | Dacă `json.loads` eșuează, se mai încearcă o dată după eliminarea gardurilor ```` ```json ```` și decuparea între primul `{` și ultimul `}`. Se aplică tuturor furnizorilor; pentru Grok, care întoarce JSON curat, nu schimbă nimic. |
| D8 | Numele claselor | `XAIClient` rămâne (nume, constructor `XAIClient(settings)`, payload identic). Logica comună se mută într-o clasă de bază `ResponsesClient`; `XAIClient` devine subclasa ei. |

## 4. Arhitectura țintă

```
AI_PROVIDER ──► config.Settings ──► providers.provider_config(settings) ──► ProviderConfig
                                                                               │
web/main.py:  ai = create_ai_client(settings)  ◄───────────────────────────────┘
                 │
                 ├─ XAIClient          (base_url=https://api.x.ai/v1,               key=X_API_KEY)
                 ├─ ResponsesClient    (base_url=https://router.huggingface.co/v1,  key=HF_TOKEN)
                 └─ ResponsesClient    (base_url=http://localhost:11434/v1,         key=OLLAMA_API_KEY | —)
                         │
                         └─ POST {base_url}/responses  ──►  output[type=message].content[type=output_text]
                                                           ──► JSON ──► aceleași 5 secțiuni ──► create_pdf()
```

Tot ce urmează după parsarea JSON-ului (normalizarea secțiunilor, nutriția structurată, PDF, e-mail) rămâne identic pentru toți furnizorii.

## 5. Configurare

| Variabilă | Implicit | Folosită de | Rol |
|---|---|---|---|
| `AI_PROVIDER` | `xai` | toți | Furnizorul activ. |
| `X_API_KEY`, `XAI_MODEL`, `XAI_REASONING_EFFORT`, `XAI_API_BASE` | neschimbate | `xai` | Exact ca acum. |
| `HF_TOKEN` | — | `huggingface` | Token HF fine-grained, permisiunea „Make calls to Inference Providers”. |
| `HF_MODEL` | `deepseek-ai/DeepSeek-V4-Flash:deepinfra` | `huggingface` | Sufixul `:deepinfra` fixează furnizorul (fără sufix HF alege cel mai rapid). |
| `HF_API_BASE` | `https://router.huggingface.co/v1` | `huggingface` | |
| `HF_REASONING_EFFORT` | gol (nu se trimite) | `huggingface` | `low`/`medium`/`high`; se trimite doar dacă e setat, după ce Faza 0 confirmă maparea. |
| `HF_MAX_CONTEXT_CHARS` | `120000` | `huggingface` | Limita de context a furnizorului (D4). |
| `OLLAMA_API_BASE` | `http://localhost:11434/v1` | `ollama` | În Docker: `http://host.docker.internal:11434/v1`; pentru cloud direct: `https://ollama.com/v1` (dacă Faza 0 confirmă). |
| `OLLAMA_MODEL` | `deepseek-v4.1-flash:cloud` | `ollama` | |
| `OLLAMA_API_KEY` | — | `ollama` | Obligatorie doar când `OLLAMA_API_BASE` nu este local. |
| `OLLAMA_REASONING_EFFORT` | gol | `ollama` | |
| `OLLAMA_MAX_CONTEXT_CHARS` | fără limită proprie | `ollama` | Pentru modele locale mici trebuie setată (și `OLLAMA_CONTEXT_LENGTH` pe daemon). |
| `AI_MAX_OUTPUT_TOKENS` | `20000` | toți | Azi constanta `20000` din `generate()`; devine configurabilă fiindcă la HF concurează cu inputul în fereastra de 64k. |
| `AI_READ_TIMEOUT_SECONDS` | `300` | toți | Azi fix în `XAIClient.__init__`. |

## 6. Modificări pe fișiere

### 6.1 `src/medicina_naturista/config.py`

- Câmpurile noi din §5 pe `Settings`; `ai_provider` validat împotriva `{"xai", "huggingface", "ollama"}`.
- `api_key()` rămâne (întoarce `X_API_KEY`, folosit de testele existente). Se adaugă `hf_token()` și `ollama_api_key()` după același model (`os.getenv(...).strip()`).

### 6.2 `src/medicina_naturista/ai/providers.py` — nou

- `ProviderConfig` (dataclass frozen): `name`, `label` (pentru mesajele din UI, ex. „xAI”, „Hugging Face”, „Ollama”), `base_url`, `model`, `reasoning_effort | None`, `api_key: Callable[[], str]`, `api_key_env` (numele variabilei, pentru mesajul de eroare), `api_key_required`, `json_format` (`"text_format" | "response_format" | None`), `send_store`, `max_context_chars | None`, `max_output_tokens`, `read_timeout_seconds`.
- `provider_config(settings) -> ProviderConfig` — singurul loc unde `AI_PROVIDER` se transformă în configurare.

### 6.3 `src/medicina_naturista/ai/client.py`

- **`ResponsesClient(provider: ProviderConfig)`** primește corpul actual al `XAIClient`, cu trei puncte parametrizate:
  - `_post()`: URL `f"{provider.base_url}/responses"`; antetul `Authorization` doar dacă există cheie; cheie lipsă și obligatorie → `AIUnavailable(f"Lipsește {provider.api_key_env}. ...")`; mesajele de eroare folosesc `provider.label`; `ai_request_started` loghează și `provider=`.
  - `_build_payload(system, user, max_tokens)`: `model`, `input`, `max_output_tokens` întotdeauna; `reasoning` doar dacă e setat; `text.format` sau `response_format` după `json_format`; `store: False` doar dacă `send_store`.
  - `_extract_json(payload)`: logica actuală (`status == "completed"`, concatenarea `output_text` din itemii `message` — itemii `reasoning` ai DeepSeek sunt ignorați automat) + parsarea tolerantă (D7) + log dedicat pentru `status == "incomplete"` cu `incomplete_details.reason` (tipic `max_output_tokens` la modelele cu gândire).
- **`XAIClient(ResponsesClient)`**: `__init__(self, settings)` construiește configurarea xAI. Payload-ul rezultat trebuie să fie **identic byte cu byte** cu cel de azi (`model`, `reasoning.effort`, `input`, `text.format=json_object`, `max_output_tokens`, `store=false`).
- **`create_ai_client(settings) -> ResponsesClient`**: `XAIClient` pentru `xai`, `ResponsesClient(provider_config(settings))` pentru ceilalți.
- **`fit_evidence_to_context(evidence, limit: int | None = None)`**: `limit=None` păstrează comportamentul actual (`MAX_CONTEXT_CHARS`), deci testul existent care face `patch.object(ai_module, "MAX_CONTEXT_CHARS", ...)` rămâne valid. `ResponsesClient.context_budget()` întoarce `min(MAX_CONTEXT_CHARS, provider.max_context_chars)`, citit la apel.
- Logul `"xAI request user payload prepared"` devine `ai_request_payload_prepared provider=... chars=... approx_tokens=...`.

### 6.4 `src/medicina_naturista/web/main.py`

- `ai = create_ai_client(settings)` în loc de `XAIClient(settings)`.
- Linia 421: `fit_evidence_to_context(retriever.collect(session), ai.context_budget())`.
- `/healthz`: `ai.is_configured()` în loc de `settings.api_key()`; mesajul 503 numește variabila lipsă a furnizorului activ.
- `application_started` loghează `ai_provider` și `ai_model`.

### 6.5 `docker-compose.yaml`

- `X_API_KEY: ${X_API_KEY:?...}` → `${X_API_KEY:-}`: altfel stiva nu pornește cu `AI_PROVIDER=huggingface` fără cheie xAI. Verificarea cheii furnizorului activ se mută în aplicație (`/healthz` → 503, ca acum).
- Variabilele noi din §5, cu aceleași valori implicite.
- Pentru `ollama` cu daemon pe host: `extra_hosts: ["host.docker.internal:host-gateway"]`. Atenție: daemonul ascultă implicit doar pe `127.0.0.1`, deci ar trebui pornit cu `OLLAMA_HOST=0.0.0.0`, ceea ce îl expune în rețeaua locală (se restricționează din firewall). Dacă Faza 0 confirmă `/v1/responses` pe `https://ollama.com`, varianta cloud directă este mai simplă și mai sigură în Docker.

### 6.6 Documentație

- `README.md`: tabelul de variabile, secțiunea „Local vs. extern” (datele pot ajunge la xAI, la DeepInfra prin HF sau la Ollama Cloud, după `AI_PROVIDER`), nota despre `store=false` (se aplică doar la xAI; pentru HF și Ollama se trec politicile lor de retenție, după verificare).
- `architecture/final-report-generation.md`: secțiunea 9 („Cererea către furnizorul AI”) și pasul 3.5 (bugetul per furnizor). Se corectează și timeout-ul menționat (azi documentul spune 75 s, codul are 300 s).

### 6.7 Frontend

Nicio modificare: UI-ul consumă aceleași secțiuni și aceleași mesaje de eroare.

## 7. Faza 0 — verificare manuală, înainte de cod

Se rulează de utilizator, cu tokenurile proprii. Scop: fixarea D4, D6 și a variantei Ollama.

1. **HF, cerere minimă cu toate câmpurile pe care le trimite xAI azi:**
   ```bash
   curl https://router.huggingface.co/v1/responses \
     -H "Authorization: Bearer $HF_TOKEN" -H "Content-Type: application/json" \
     -d '{"model":"deepseek-ai/DeepSeek-V4-Flash:deepinfra",
          "input":[{"role":"system","content":"Răspunde doar cu un obiect JSON."},
                   {"role":"user","content":"Dă-mi {\"ok\": true}"}],
          "text":{"format":{"type":"json_object"}},
          "reasoning":{"effort":"medium"},
          "max_output_tokens":2000,"store":false}'
   ```
   De notat: dacă cererea e acceptată sau ce câmp respinge (`store`, `text.format`, `reasoning`); valoarea `status`; forma lui `output` (există item `reasoning` separat?); dacă JSON-ul vine curat sau între garduri Markdown. Dacă `text.format` e ignorat, se repetă cu `response_format`.
2. **HF, limita reală de context:** aceeași cerere cu un `user` de ~150k, apoi ~250k caractere de text românesc (de ex. un document din `data/documents/`). Eroarea HTTP sau câmpul `usage.input_tokens` dau raportul caractere/token și limita → valoarea finală `HF_MAX_CONTEXT_CHARS`.
3. **HF, cerere reală:** fragmentele unei căutări obișnuite (din logul `fragments_sent_to_ai`) + promptul de sistem real; se notează durata și `usage.output_tokens` (reasoning inclus) → valoarea `AI_MAX_OUTPUT_TOKENS` și `AI_READ_TIMEOUT_SECONDS` pentru HF.
4. **Ollama:** `ollama --version` (≥ 0.13.3), `ollama signin`, `ollama run deepseek-v4.1-flash:cloud "salut"`, apoi aceeași cerere ca la pasul 1 către `http://localhost:11434/v1/responses` (fără antet de autentificare). Separat, cu `OLLAMA_API_KEY`, către `https://ollama.com/v1/responses`, ca să aflăm dacă varianta cloud directă există.
5. **Confidențialitate:** politicile de retenție HF Inference Providers, DeepInfra și Ollama Cloud, pentru README.

## 8. Teste

Toate în `tests/unit/web/test_web.py` (sau un `tests/unit/ai/test_client_providers.py` nou), fără cereri reale, cu `FakeResponse`/`client.http.post` înlocuit ca în testele existente.

- **Regresie xAI:** toate testele actuale trec **nemodificate**; în plus, un test care fixează payload-ul xAI exact (dicționar complet) și URL-ul `https://api.x.ai/v1/responses`.
- **Selecția furnizorului:** `create_ai_client()` întoarce configurarea corectă pentru fiecare valoare a `AI_PROVIDER`; valoare necunoscută → `ValueError`.
- **Payload per furnizor:** HF — URL-ul routerului, `Bearer HF_TOKEN`, modelul cu `:deepinfra`, fără `reasoning` când `HF_REASONING_EFFORT` e gol; Ollama local — fără antet `Authorization`, fără `store`.
- **Cheie lipsă:** `AIUnavailable` cu numele variabilei corecte (`HF_TOKEN`, `OLLAMA_API_KEY`); Ollama local fără cheie nu aruncă.
- **Parsare:** JSON între garduri ```` ```json ````, JSON precedat de text, item `reasoning` înaintea itemului `message`, `status="incomplete"` → `AIUnavailable` și log cu motivul.
- **Buget:** `context_budget()` = minimul dintre global și furnizor; `fit_evidence_to_context(evidence, limit)` păstrează prefixul cel mai bine punctat; `limit=None` = comportamentul vechi.
- **`/healthz`:** 200/503 în funcție de cheia furnizorului activ.

Comandă: `.venv/Scripts/python.exe -m pytest tests/unit`.

## 9. Riscuri

- **Context HF de 64k:** cu bugetul redus, pacientul primește mult mai puține fragmente decât cu Grok, deci rețete bazate pe mai puține surse. Nu se poate compensa în cod; dacă limita contează, varianta `ollama` + `deepseek-v4.1-flash:cloud` (1M) sau Grok rămân opțiunile.
- **Reasoning consumă `max_output_tokens`:** în modul „think” răspunsul poate fi tăiat (`incomplete`) înainte de JSON. Atenuare: `AI_MAX_OUTPUT_TOKENS` per mediu, efort `low`/`medium`, log explicit.
- **Responses API la HF este beta:** câmpurile acceptate se pot schimba; testele cu payload fix vor semnala doar regresiile noastre, nu pe ale lor.
- **Disponibilitatea modelului:** V4-Flash a fost deja retras din Ollama (2026-09-25); poate fi retras și la DeepInfra. `HF_MODEL` / `OLLAMA_MODEL` se schimbă din `.env`, fără cod (ex. `deepseek-ai/DeepSeek-V4.1-Flash`).
- **Date medicale la terți:** fiecare furnizor nou este încă o destinație externă pentru fragmente și pentru descrierea problemei pacientului. Se documentează în README (§6.6) înainte de activare.
- **Docker + Ollama pe host:** `OLLAMA_HOST=0.0.0.0` expune daemonul; de preferat cloud direct sau firewall.

## 10. Ordinea de lucru

1. **Faza 0** (§7), rulată de utilizator; rezultatele fixează D4, D6 și varianta Ollama.
2. `config.py` + `providers.py` + testele de selecție.
3. Refactorul `client.py` (`ResponsesClient` + `XAIClient` subclasă) — **testele existente trebuie să treacă înainte de orice furnizor nou**.
4. Furnizorii `huggingface` și `ollama` + testele lor.
5. `web/main.py` (fabrică, buget, `/healthz`), apoi `docker-compose.yaml`.
6. Documentație (README, `final-report-generation.md`).
7. Probă reală cu `AI_PROVIDER=huggingface` pe o problemă cunoscută (ex. „gripă”), comparând raportul PDF cu cel generat de Grok pe aceleași fragmente.

## Surse

- [Hugging Face — Responses API (beta)](https://huggingface.co/docs/inference-providers/guides/responses-api)
- [Forum HF — limita de context DeepInfra / DeepSeek-V4 pe Hugging Face](https://discuss.huggingface.co/t/deepinfra-deepseek-v4-pro-context-size-wrong-on-huggingface/176578)
- [deepseek-ai/DeepSeek-V4-Flash pe Hugging Face](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash)
- [DeepInfra — DeepSeek V4 Flash](https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash)
- [Ollama — compatibilitate OpenAI (`/v1/responses`)](https://docs.ollama.com/api/openai-compatibility)
- [Ollama — modele cloud](https://docs.ollama.com/cloud)
- [Ollama — deepseek-v4-flash (retras)](https://ollama.com/library/deepseek-v4-flash)
- [Ollama — deepseek-v4.1-flash](https://ollama.com/library/deepseek-v4.1-flash)
