# Fluxul de generare a raportului final

**Intrare:** descrierea problemei de sănătate furnizată de utilizator și indexul hibrid local.

**Ieșire:** fragmentele găsite (afișate pacientului), recomandările afișate în chat, un raport PDF descărcabil și, la cerere, trimiterea PDF-ului pe e-mail către o adresă indicată în chat.

Documentul are două părți: **[Partea I — Rezumat](#partea-i--rezumat)** (cele 10 etape pe scurt) și **[Partea II — Detalii](#partea-ii--detalii)** (aceleași 10 etape, pas cu pas).

----------------------------------------------------------------------------------------------------

## Partea I — Rezumat

Aplicația este un server FastAPI (`src/backend/web/main.py`) cu o interfață React (`src/frontend/`); căile de mai jos fără prefix sunt relative la `src/backend/`. Fluxul are două momente separate: **căutarea** (butonul „📨 Trimite”, fără AI) și **generarea rețetei** (butonul „💊 Generează rețeta”, cu AI).

1. **Sesiunea** (`GET /api/session`) — fiecare tab din browser are propria sesiune, ținută doar în memorie (cookie `naturist_sid` + antet `X-Tab-Id`); pacientul este întâmpinat cu întrebarea despre problema de sănătate.
2. **Mesajul pacientului** (`POST /api/messages`, eventual `POST /api/condition`) — mesajul devine noua problemă de sănătate, împreună cu categoriile și tipurile de căutare bifate; dacă dicționarul nu recunoaște nicio afecțiune, un model AI mic încearcă să o identifice; în chat apar afecțiunea recunoscută și anunțul „🔍 Caut rapid…”.
3. **Căutarea** (`POST /api/search`) — `Retriever.collect()` găsește și notează fragmentele cu semnalele alese, în limita de text a furnizorului AI (vezi [fragment-search-and-scoring.md](fragment-search-and-scoring.md)).
4. **Afișarea fragmentelor** — pacientul vede fragmentele găsite și butonul „💊 Generează rețeta”; nimic nu a fost trimis încă la AI.
5. **Pornirea generării** (`POST /api/searches/{id}/generate`) — doar proprietarul aplicației (cookie `naturist_owner`, din `OWNER_KEY`) poate genera; ceilalți primesc o notificare.
6. **Cererea către AI** (`ResponsesClient.generate()`) — o singură cerere către furnizorul ales în `AI_PROVIDER` (xAI, DeepSeek, Hugging Face sau Ollama), cu exact fragmentele afișate; răspunsul JSON are 5 secțiuni de recomandări, fiecare cu dovezile citate.
7. **PDF-ul** (`create_pdf()`) — copertă, cele 5 secțiuni colorate, legături „→ Surse” și bibliografie, totul în memorie (ReportLab).
8. **Rezultatul în chat** — recomandările cu bibliografie, butonul „📄 Descarcă PDF” și oferta de trimitere pe e-mail.
9. **E-mail** — dacă pacientul scrie doar o adresă de e-mail, ultimul PDF este trimis prin Gmail API.
10. **Erori și protecții** — erorile AI apar ca mesaj în chat și generarea se poate relua; serverul limitează cererile (`MAX_REQUESTS_PER_MINUTE`) și verifică originea lor.

```text
„Trimite” → afecțiune recunoscută (dicționar sau AI mic) → fragmente notate (fără AI) → pacientul le vede
    → „Generează rețeta” (doar owner) → o cerere AI → PDF în memorie → chat + descărcare (+ e-mail)
```

----------------------------------------------------------------------------------------------------

## Partea II — Detalii

### 1. Sesiunea — `GET /api/session`

- **1.1.** La prima cerere, middleware-ul creează cookie-ul `naturist_sid` (aleator, `httponly`, `samesite=strict`, `secure` dacă `COOKIE_SECURE=true`).
- **1.2.** Frontend-ul generează un identificator de tab (`crypto.randomUUID()`, păstrat în `sessionStorage`) și îl trimite la fiecare cerere în antetul `X-Tab-Id`. Perechea cookie + tab identifică sesiunea (`SessionStore`), deci două taburi au conversații separate.
- **1.3.** Sesiunea stă doar în memoria procesului (`SessionData`): istoricul chatului, profilul (`HealthProfile`), căutările în așteptare și rapoartele generate. Nicio informație medicală nu se scrie în baza de date.
- **1.4.** Pentru o sesiune nouă, istoricul începe cu un singur mesaj: „Bună ziua! 👋” urmat de întrebarea despre problema de sănătate (`HEALTH_PROBLEM_QUESTION`).
- **1.5.** Istoricul păstrează ultimele 60 de mesaje. Fiecare mesaj are un tip (`kind`): `text`, `fragments`, `generate` sau `download`; frontend-ul afișează fiecare tip cu componenta lui.
- **1.6.** `GET /api/categories` întoarce arborele categoriilor (folderele din `data/documents`) pentru panoul „Căutare avansată”; implicit sunt bifate toate. Dacă indexul nu are încă categorii, `tree` este `null` și filtrarea pe categorii nu este disponibilă.
- **1.7.** În același panou, „Ce tip de căutare doriți să efectuez?” oferă trei semnale (`SearchSignals`): „Căutare afecțiuni” (A), „Căutare lexicală” (B) și „Căutare semantică” (C). Implicit sunt bifate toate; cel puțin unul rămâne mereu bifat, iar alegerea este ținută în `localStorage` (`naturist.searchSignals`).

### 2. Mesajul pacientului — `POST /api/messages` și `POST /api/condition`

- **2.1.** Mesajul este curățat de spații; un mesaj gol este ignorat. Peste `MAX_CHAT_CHARS` (implicit 4000) cererea este respinsă cu HTTP 422.
- **2.2.** Se obține blocarea sesiunii.
- **2.3.** Dacă există deja un raport generat și mesajul este **exclusiv o adresă de e-mail** (`EMAIL_PATTERN`), este tratat ca cerere de trimitere pe e-mail (secțiunea 9) și nu se face nicio căutare.
- **2.4.** Altfel, mesajul este adăugat în chat și înlocuiește problema de sănătate din profil (`replace_health_problem()`): contextul și transcriptul încep de la acest mesaj, iar afecțiunile identificate anterior de AI (`ai_conditions`) se șterg. Categoriile și semnalele bifate de pacient sunt salvate în sesiune (un corp cu toate semnalele debifate este respins cu HTTP 422).
- **2.5.** Dacă nu există o problemă de sănătate: „Descrieți problema de sănătate înainte de căutare.” Dacă indexul are categorii și nu este bifată niciuna: „Nicio sursă selectată…”. În ambele cazuri căutarea nu pornește.
- **2.6.** Dacă semnalul „afecțiuni” este bifat, `CONDITION_AI_BACKENDS` nu este gol și dicționarul (`resolve_query()`) nu recunoaște nicio afecțiune în mesaj, se adaugă „🤖 Nu am găsit afecțiunea în dicționarul meu. Încerc să o identific cu ajutorul AI. Vă rog să așteptați.” și răspunsul are `identifyCondition: true` (pasul 2.8).
- **2.7.** Altfel se adaugă câte un rând „✅ Am identificat afecțiunea: **…**.” pentru fiecare afecțiune recunoscută (cu semnalul lexical bifat, pentru o afecțiune care este o expresie întreagă din mesaj se adaugă „O caut și după denumirile: …”; fără semnalul „afecțiuni” se numesc doar acestea, iar fără niciunul din cele două nu se numește nimic) și „🔍 Caut rapid în cele N documente interne disponibile. Vă rog să așteptați.”, unde N este numărul documentelor din categoriile bifate.
- **2.8.** Identificarea cu AI (`POST /api/condition`, `identify_conditions()` din `ai/condition_ai.py`): segmentele mesajului (despărțite prin virgulă), numerotate, sunt trimise cu promptul de sistem `ai/prompts/condition_identification_system.md`, care cere un JSON `{"segments": [{"index", "name", "synonyms"}]}` (denumirea în română și 7 sinonime). Backend-urile din `CONDITION_AI_BACKENDS` (implicit `local,huggingface`) sunt încercate în ordine: `local` este un model Ollama (`CONDITION_AI_LOCAL_MODEL`, implicit `gemma3:1b`, la `CONDITION_AI_LOCAL_BASE`, implicit `http://localhost:11434/v1`, temperatură 0), `huggingface` folosește routerul HF cu `CONDITION_AI_HF_MODEL` (implicit `HF_MODEL`) și `HF_TOKEN`. Timeout `CONDITION_AI_TIMEOUT_SECONDS` (implicit 10 s), `CONDITION_AI_MAX_OUTPUT_TOKENS` (implicit 300). Doar o eroare trece la backend-ul următor; un răspuns fără afecțiune oprește încercările. Răspunsurile reușite sunt ținute în cache (128 de intrări); orice eșec înseamnă „neidentificat” și nu oprește căutarea. Cererea AI rulează în afara blocării sesiunii; dacă între timp pacientul a trimis alt mesaj, rezultatul este ignorat.
- **2.9.** Rezultatul se salvează în profil (`ai_conditions`) și completează rezolvarea mesajului (`resolved_for()`), folosită apoi de căutare, chat și PDF; când numele sau un sinonim este exact un termen din dicționar, afecțiunea primește denumirea canonică din dicționar. În chat apare „✅ Am identificat afecțiunea (cu ajutorul AI): **…**.”; dacă nu s-a identificat nimic, „⚠️ Nu am putut identifica afecțiunea din mesaj. Caut după textul mesajului.”, sau, când este bifat doar semnalul „afecțiuni”, „… Scrieți denumirea afecțiunii (ex. gripă, hipertensiune).” și căutarea nu mai pornește. Apoi urmează anunțul „🔍 Caut rapid…”.
- **2.10.** Răspunsul lui `POST /api/messages` revine imediat, cu `startSearch: true` când trebuie căutat; frontend-ul afișează mesajele, apelează `POST /api/condition` dacă `identifyCondition` este `true` și abia apoi pornește căutarea (cererea separată de la secțiunea 3, doar dacă și pasul 2.9 a întors `startSearch: true`), ca pacientul să-și vadă imediat mesajul. Butonul devine „⏳ Caută...” cât durează.

### 3. Căutarea fragmentelor — `POST /api/search`

- **3.1.** Dacă este bifat doar semnalul „afecțiuni” și mesajul nu are nicio afecțiune (nici din dicționar, nici de la AI), se afișează mesajul „… Scrieți denumirea afecțiunii …” și nu se caută. Altfel se apelează `Retriever.collect(session, ai.context_budget())`. Bugetul este limita de context a furnizorului activ: `X_AI_MAX_CONTEXT_CHARS`, `DEEPSEEK_MAX_CONTEXT_CHARS`, `OLLAMA_MAX_CONTEXT_CHARS` (implicit 1.000.000 de caractere) sau `HF_MAX_CONTEXT_CHARS` (implicit 120.000); cu Hugging Face pacientul vede deci mai puține fragmente.
- **3.2.** Interogarea este **întreaga problemă de sănătate** (`consultation_query()`); istoricul conversației nu este folosit. Afecțiunile vin din `resolved_for()` (dicționar plus cele identificate de AI), iar categoriile bifate restrâng căutarea (toate bifate = fără filtru).
- **3.3.** `rank()` notează toate fragmentele doar cu semnalele bifate (cu toate trei: `score = 4·P1 + 2·P2 + L + V`; ponderile depind de combinație, iar fără nicio afecțiune în mesaj semnalul „afecțiuni” este ignorat) și întoarce, în ordinea scorului, fragmentele cu scor > 0 care încap întregi în buget. `relevance_percent` este scorul raportat la scorul maxim al combinației folosite. Detaliile sunt în [fragment-search-and-scoring.md](fragment-search-and-scoring.md).
- **3.4.** Fiecare fragment devine o dovadă `C<chunk_id>` cu `source` (`documents/<cale>:<linie_start>-<linie_end>`), `text` (prefixat cu `Secțiune: <titlu>` când fragmentul are titlu), `score`, `relevance_percent` și componentele scorului (cele ale semnalelor debifate sunt `None`).
- **3.5.** Dacă nu există nicio dovadă: „Nu am găsit fragmente relevante în sursele locale. Încercați o căutare semantică sau introduceți altă denumire a afecțiunii.”
- **3.6.** Altfel, dovezile sunt păstrate în sesiune ca `PendingSearch` (împreună cu profilul de la acel moment, inclusiv `ai_conditions`, și semnalele folosite), sub un `search_id` aleator. Se păstrează cel mult 12 căutări în așteptare, deci pacientul poate genera și pentru o căutare mai veche din chat.

### 4. Afișarea fragmentelor — `_fragments_message()` și `FragmentsPanel`

- **4.1.** În chat se adaugă mesajul `fragments`: „Am găsit N fragmente relevante în M documente locale (le puteți vedea mai jos). Dacă vi se par potrivite, apăsați „Generează rețeta”.”, cu lista fragmentelor ordonată după scor și semnalele cu care a fost făcută căutarea.
- **4.2.** Pentru fiecare fragment: textul complet, `Scor relevanță: X%` și, doar pentru semnalele bifate la acea căutare, scorul semantic, scorul lexical, `Afecțiune în titlu` / `Afecțiune în text` și `Găsire Lexicală`; apoi calea documentului.
- **4.3.** Panoul are filtre (scor minim, document și, după semnalele căutării, scor semantic, afecțiune, găsire lexicală) și un sumar cu numărul de fragmente, documente și caractere. Filtrele din acest panou schimbă doar ce se vede, nu ce se trimite la AI.
- **4.4.** Sub panou apare mesajul `generate`: „Trimite-le la AI pentru a le combina și generează apoi documentul cu recomandări”, selectorul „Scor minim” (Toate, ≥ 25%, ≥ 50%, ≥ 75%, ≥ 90%; implicit Toate) și butonul „💊 Generează rețeta”. Selectorul este independent de filtrul cu același nume din panoul de fragmente și **decide ce fragmente se trimit la AI**: doar cele cu `relevance_percent` ≥ pragul ales (pragul este inclus). Dacă niciun fragment al căutării nu atinge pragul, butonul este dezactivat și apare „Niciun fragment nu atinge scorul minim selectat.”

### 5. Pornirea generării — `POST /api/searches/{search_id}/generate`

- **5.1.** La apăsare, butonul devine „⏳ Se generează rețeta...” și este dezactivat.
- **5.2.** Serverul verifică cookie-ul `naturist_owner` (HMAC-SHA256 din `OWNER_KEY`, `_is_owner()`). Fără `OWNER_KEY` configurat verificarea eșuează închis.
- **5.3.** Un vizitator care nu este owner primește notificarea „Generarea rețetei este disponibilă doar pentru autorul acestui chatbot.”, butonul revine la normal și nu se face niciun apel către AI. Cookie-ul owner (valabil 10 ani) se obține accesând `/owner?key=<OWNER_KEY>`.
- **5.4.** Pentru owner, `_generate_report()` ia blocarea sesiunii și citește `PendingSearch`-ul căutării apăsate: profilul și fragmentele deja afișate, fără a recalcula căutarea.
- **5.5.** Dacă acea căutare nu mai există (de exemplu, a ieșit din cele 12 păstrate): „Nu există fragmente pregătite. Descrieți din nou problema de sănătate.”
- **5.6.** Corpul cererii poate conține `{"minScore": N}` (0–100, implicit 0; altă valoare → HTTP 422). `_evidence_above()` păstrează, într-o copie, doar fragmentele cu `relevance_percent` ≥ N (un fragment fără procent contează ca 0). `PendingSearch` rămâne neschimbat, deci generarea se poate relua cu alt prag. Dacă nu rămâne niciun fragment (protecție pe server, interfața dezactivează deja butonul): „Niciun fragment nu atinge scorul minim selectat. Alegeți un prag mai mic.”, fără apel AI, iar căutarea rămâne în așteptare.

### 6. Cererea către furnizorul AI — `ResponsesClient.generate()`

- **6.1.** Furnizorul vine din `AI_PROVIDER` (`ai/providers.py`, implicit `xai`):

  | Furnizor | Cheie | Model implicit | JSON cerut prin |
  |---|---|---|---|
  | `xai` | `X_API_KEY` | `XAI_MODEL` = `grok-4.3` (reasoning `XAI_REASONING_EFFORT` = `medium`) | `text.format=json_object`, plus `store=false` |
  | `deepseek` | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` = `deepseek-flash` | `text.format=json_object` |
  | `huggingface` | `HF_TOKEN` | `HF_MODEL` = `deepseek-ai/DeepSeek-V4-Flash:deepinfra` | promptul de sistem |
  | `ollama` | `OLLAMA_API_KEY` (nu e necesară pe un host local) | `OLLAMA_MODEL` = `deepseek-v4.1-flash:cloud` | promptul de sistem |

  Adresele vin din `XAI_API_BASE`, `DEEPSEEK_API_BASE`, `HF_API_BASE`, `OLLAMA_API_BASE`; pentru ceilalți furnizori `reasoning.effort` se trimite doar dacă `DEEPSEEK_/HF_/OLLAMA_REASONING_EFFORT` este setat.

- **6.2.** Dovezile sunt ordonate după `score`, descrescător, ca înregistrări `id`, `source`, `text`. Sunt trimise nemodificate toate dovezile care au trecut de pragul „Scor minim” (pasul 5.6); bugetul a fost deja aplicat la căutare. Aceleași dovezi filtrate sunt folosite și pentru PDF și pentru bibliografia din chat.
- **6.3.** Se înregistrează în log inventarul fragmentelor trimise (textul doar dacă `LOG_FRAGMENT_TEXT` este activ, tăiat la `LOG_FRAGMENT_TEXT_MAX_CHARS`).
- **6.4.** Promptul utilizatorului conține „Problema pentru care se solicită recomandări naturiste:” cu profilul din `PendingSearch` (JSON: `health_problem`, `health_context`, `transcript`, `ai_conditions`) și „Toate fragmentele locale admise:” cu lista fragmentelor. Promptul de sistem este `ai/prompts/generate_report_system.md`: folosirea exclusivă a fragmentelor (cu excepția rețetelor culinare), parcurgerea tuturor fragmentelor, consolidarea recomandărilor repetate, contraindicațiile în `atentionari` și un singur obiect JSON cu exact cele cinci chei.
- **6.5.** `complete_json()` trimite o singură cerere `POST {base_url}/responses` (Responses API), cu `max_output_tokens=AI_MAX_OUTPUT_TOKENS` (implicit 20000) și timeout de citire `AI_READ_TIMEOUT_SECONDS` (implicit 300 s; conectare 10 s). Cu `AI_STREAM=true` răspunsul este citit ca flux de evenimente, iar timeout-ul se aplică între evenimente.
- **6.6.** Răspunsul trebuie să aibă `status == "completed"` (un `incomplete` se loghează cu motivul, de obicei limita de tokeni). Se concatenează blocurile `output_text` și se parsează JSON-ul, tolerant la garduri Markdown (se reîncearcă între primul `{` și ultimul `}`). Un text gol sau un JSON care nu este obiect este răspuns invalid; dacă `output_tokens` a atins limita, logul sugerează mărirea `AI_MAX_OUTPUT_TOKENS`. Textul brut al răspunsului se loghează doar cu `LOG_AI_RESPONSE_TEXT=true`.
- **6.7.** Se normalizează cele cinci secțiuni: `uz_intern`, `nutritie`, `uz_extern`, `alte_recomandari`, `atentionari`. Fiecare element are `text` și `evidence_ids` (ID-urile dovezilor citate); elementele fără `text` șir de caractere sunt ignorate, iar cheile lipsă devin secțiuni goale.
- **6.8.** Nutriția este un obiect cu `retete` (listă), `recomandate`, `nerecomandate`, `interzise` (șiruri separate prin virgulă) și `alte`, convertit în elemente prefixate (`[RETETA]`, `[RECOMANDAT]`, `[NERECOMANDAT]`, `[INTERZIS]`, `[ALTE]`). Promptul permite aici `evidence_ids` goale.

### 7. Generarea PDF-ului — `create_pdf()`

- **7.1.** Titlul (`report_title()`): „Remedii naturiste pentru <afecțiunile recunoscute>” (din dicționar sau, dacă acesta nu știe niciuna, cele identificate de AI), sau prima parte (până la virgulă) a textului scris de pacient când nu s-a recunoscut nicio afecțiune. Același titlu dă și numele fișierului PDF (caracterele interzise în nume de fișier sunt înlocuite cu `-`).
- **7.2.** Copertă (`CoverPanel`): „GHID INFORMATIV”, titlul, „de la dr. Cuișor”, portretul medicului și avertismentul că ghidul este informativ.
- **7.3.** `sort_sections_by_relevance()` ordonează elementele fiecărei secțiuni după cel mai mare `relevance_percent` al fragmentelor citate, apoi după numărul de surse distincte, apoi după poziția inițială.
- **7.4.** `build_reference_index()` numerotează sursele citate în ordinea primei apariții.
- **7.5.** Cele cinci secțiuni colorate (`RoundedSection`); o secțiune goală afișează „Nu au fost identificate informații suficient de relevante în sursele disponibile.” Nutriția este grupată prin `nutrition_display_groups()`: rețetele sunt elemente separate, celelalte categorii sunt grupate.
- **7.6.** Fiecare recomandare cu dovezi primește legătura „→ Surse N” către bibliografie.
- **7.7.** Secțiunea „6. Bibliografie” grupează sursele pe fișier; fiecare intrare are legătura „← înapoi” către prima recomandare care o citează. Fără surse citate apare „Nu există referințe bibliografice utilizate.”
- **7.8.** După bibliografie, `generation_summary_lines()` adaugă trei rânduri: „Număr total de fragmente folosite”, „Număr total de caractere trimise la AI” (suma caracterelor din textele fragmentelor trimise, fără promptul de sistem și profil) și „Scor minim selectat” („Toate” sau „≥ N%”), toate pentru fragmentele rămase după pragul de la pasul 5.6.
- **7.9.** Documentul este construit în memorie cu ReportLab (A4, semne de carte, subsol „Remedii naturiste de la Dr. Cuișor” și numărul paginii) și întors ca octeți.

### 8. Rezultatul în chat și descărcarea

- **8.1.** Raportul este păstrat în sesiune (`StoredReport`: octeții, numele fișierului, problema) sub un `report_id` aleator (`secrets.token_urlsafe(18)`); se păstrează ultimele 12 rapoarte, iar ultimul este cel trimis pe e-mail.
- **8.2.** Mesajul `generate` al căutării este înlocuit, chiar în locul lui din chat, cu: textul recomandărilor cu bibliografie (`_recommendation_text()`, care începe cu „✅ Raportul este gata. Recomandările susținute de surse:”), panoul de descărcare („📄 Descarcă PDF”) și oferta: „Dacă doriți să trimiteți documentul pe mail la cineva, spuneți-mi la ce adresă să îl trimit.” Căutarea este apoi scoasă din `PendingSearch`-urile sesiunii.
- **8.3.** Descărcarea: `GET /api/reports/{tab_id}/{report_id}` (cu prefixul `PUBLIC_ROOT_PATH`, sau vechiul `GRADIO_ROOT_PATH`, când aplicația rulează sub o subcale). Întoarce HTTP 404 dacă sesiunea sau raportul nu există; altfel PDF-ul ca atașament, cu `Cache-Control: no-store`.
- **8.4.** Rapoartele rămân în memorie până când sesiunea este închisă, expiră (inactivitate `SESSION_IDLE_SECONDS` = 3600 s, durată maximă `SESSION_MAX_SECONDS` = 14400 s, verificate la fiecare minut) sau aplicația este repornită. Închiderea sau reîncărcarea paginii (`pagehide`) trimite `POST /api/session/unload` (un `fetch` cu `keepalive`), care șterge sesiunea.

### 9. Trimiterea pe e-mail — `_send_report_email()` și `send_report()`

- **9.1.** Declanșare: după generarea unui raport, pacientul scrie în chat **doar o adresă de e-mail** (pasul 2.3).
- **9.2.** Configurația vine din `GMAIL_USERNAME`, `MAIL_FROM` (implicit `GMAIL_USERNAME`), `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`. Dacă lipsește ceva: „Trimiterea pe mail nu este configurată momentan.”
- **9.3.** Mesajul are subiectul „Raport recomandări naturiste pentru <problemă>” (problema raportului respectiv), un text scurt și ultimul PDF atașat, cu numele lui de fișier.
- **9.4.** Se reînnoiește tokenul Google OAuth, apoi mesajul este trimis prin Gmail API (`users/me/messages/send`), fiecare cerere cu timeout de 20 s.
- **9.5.** La succes: „✅ Am trimis documentul la <adresa>.”; la orice eroare se loghează și se afișează „Nu am putut trimite documentul pe mail. Încercați din nou.” Raportul rămâne neafectat.

### 10. Erori și protecții

- **10.1.** `AIUnavailable` (cheie lipsă, eroare HTTP, conexiune eșuată sau răspuns invalid): mesajul erorii apare în chat. Pe server, căutarea rămâne în așteptare, deci generarea se poate relua.
- **10.2.** Altă excepție la generare: se loghează cu traceback, iar chatul afișează „Raportul nu a putut fi generat. Încercați din nou.”
- **10.3.** Dacă o cerere eșuează (eroare de rețea sau răspuns HTTP de eroare), frontend-ul afișează o notificare („Mesajul nu a putut fi trimis…” / „Rețeta nu a putut fi generată…”) și reactivează butonul.
- **10.4.** Sesiune expirată: HTTP 409 („Sesiunea a expirat. Reîncărcați pagina.”); cookie sau tab lipsă: 401 / 400.
- **10.5.** Protecții la toate cererile: cererile `POST`/`PUT`/`DELETE` cu `Origin` străin sunt respinse (403); cel mult `MAX_REQUESTS_PER_MINUTE` (implicit 60) cereri `POST`/`PUT`/`DELETE` pe minut pe IP pentru `/api/`, peste limită HTTP 429 (cu `TRUST_PROXY=true` IP-ul vine din `X-Forwarded-For`); antetele `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- **10.6.** `GET /healthz` întoarce 503 dacă lipsește cheia furnizorului AI activ (când acesta cere una).
- **10.7.** La pornire, aplicația face o căutare de probă (`warm_up()` din `ai/search.py`: încarcă modelul de embedding și dicționarul de afecțiuni) și, dacă `local` este în `CONDITION_AI_BACKENDS`, o cerere de probă către modelul local de identificare a afecțiunii, ca prima căutare a unui pacient să fie rapidă. Un eșec aici doar se loghează.

---

Căutarea și scorul fragmentelor sunt descrise în [fragment-search-and-scoring.md](fragment-search-and-scoring.md), iar generarea indexului în [hybrid-index-generation.md](hybrid-index-generation.md).
