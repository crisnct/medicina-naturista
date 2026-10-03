# Fluxul de generare a raportului final

**Intrare:** descrierea problemei de sănătate furnizată de utilizator și indexul hibrid local.

**Ieșire:** fragmentele găsite (afișate pacientului), recomandările afișate în chat, un raport PDF descărcabil și, la cerere, trimiterea PDF-ului pe e-mail către o adresă indicată în chat.

Documentul are două părți: **[Partea I — Rezumat](#partea-i--rezumat)** (cele 10 etape pe scurt) și **[Partea II — Detalii](#partea-ii--detalii)** (aceleași 10 etape, pas cu pas).

----------------------------------------------------------------------------------------------------

## Partea I — Rezumat

Aplicația este un server FastAPI (`web/main.py`) cu o interfață React (`frontend/`). Fluxul are două momente separate: **căutarea** (butonul „📨 Trimite”, fără AI) și **generarea rețetei** (butonul „💊 Generează rețeta”, cu AI).

1. **Sesiunea** (`GET /api/session`) — fiecare tab din browser are propria sesiune, ținută doar în memorie (cookie `naturist_sid` + antet `X-Tab-Id`); pacientul este întâmpinat cu întrebarea despre problema de sănătate.
2. **Mesajul pacientului** (`POST /api/messages`) — mesajul devine noua problemă de sănătate; în chat apar afecțiunea recunoscută și anunțul „🔍 Caut rapid…”.
3. **Căutarea** (`POST /api/search`) — `Retriever.collect()` găsește și notează fragmentele, în limita de text a furnizorului AI (vezi [fragment-search-and-scoring.md](fragment-search-and-scoring.md)).
4. **Afișarea fragmentelor** — pacientul vede fragmentele găsite și butonul „💊 Generează rețeta”; nimic nu a fost trimis încă la AI.
5. **Pornirea generării** (`POST /api/searches/{id}/generate`) — doar proprietarul aplicației (cookie `naturist_owner`, din `OWNER_KEY`) poate genera; ceilalți primesc o notificare.
6. **Cererea către AI** (`ResponsesClient.generate()`) — o singură cerere către furnizorul ales în `AI_PROVIDER` (xAI, DeepSeek, Hugging Face sau Ollama), cu exact fragmentele afișate; răspunsul JSON are 5 secțiuni de recomandări, fiecare cu dovezile citate.
7. **PDF-ul** (`create_pdf()`) — copertă, cele 5 secțiuni colorate, legături „→ Surse” și bibliografie, totul în memorie (ReportLab).
8. **Rezultatul în chat** — recomandările cu bibliografie, butonul „📄 Descarcă PDF” și oferta de trimitere pe e-mail.
9. **E-mail** — dacă pacientul scrie doar o adresă de e-mail, ultimul PDF este trimis prin Gmail API.
10. **Erori și protecții** — erorile AI apar ca mesaj în chat și generarea se poate relua; serverul limitează cererile (`MAX_REQUESTS_PER_MINUTE`) și verifică originea lor.

```text
„Trimite” → afecțiune recunoscută → fragmente notate (fără AI) → pacientul le vede
    → „Generează rețeta” (doar owner) → o cerere AI → PDF în memorie → chat + descărcare (+ e-mail)
```

----------------------------------------------------------------------------------------------------

## Partea II — Detalii

### 1. Sesiunea — `GET /api/session`

- **1.1.** La prima cerere, middleware-ul creează cookie-ul `naturist_sid` (aleator, `httponly`, `samesite=strict`, `secure` dacă `COOKIE_SECURE=true`).
- **1.2.** Frontend-ul generează un identificator de tab (`crypto.randomUUID()`, păstrat în `sessionStorage`) și îl trimite la fiecare cerere în antetul `X-Tab-Id`. Perechea cookie + tab identifică sesiunea (`SessionStore`), deci două taburi au conversații separate.
- **1.3.** Sesiunea stă doar în memoria procesului (`SessionData`): istoricul chatului, profilul (`HealthProfile`), căutările în așteptare și rapoartele generate. Nicio informație medicală nu se scrie în baza de date.
- **1.4.** Pentru o sesiune nouă, istoricul începe cu „Bună ziua! 👋” și întrebarea despre problema de sănătate.
- **1.5.** Istoricul păstrează ultimele 60 de mesaje. Fiecare mesaj are un tip (`kind`): `text`, `fragments`, `generate` sau `download`; frontend-ul afișează fiecare tip cu componenta lui.
- **1.6.** `GET /api/categories` întoarce arborele categoriilor (folderele din `data/documents`) pentru panoul „Setează sursele”; implicit sunt bifate toate.

### 2. Mesajul pacientului — `POST /api/messages`

- **2.1.** Mesajul este curățat de spații; un mesaj gol este ignorat. Peste `MAX_CHAT_CHARS` (implicit 4000) cererea este respinsă cu HTTP 422.
- **2.2.** Se obține blocarea sesiunii.
- **2.3.** Dacă există deja un raport generat și mesajul este **exclusiv o adresă de e-mail** (`EMAIL_PATTERN`), este tratat ca cerere de trimitere pe e-mail (secțiunea 9) și nu se face nicio căutare.
- **2.4.** Altfel, mesajul este adăugat în chat și înlocuiește problema de sănătate din profil (`replace_health_problem()`): contextul și transcriptul încep de la acest mesaj. Categoriile bifate de pacient sunt salvate în sesiune.
- **2.5.** Dacă nu există o problemă de sănătate: „Descrieți problema de sănătate înainte de căutare.” Dacă indexul are categorii și nu este bifată niciuna: „Nicio sursă selectată…”. În ambele cazuri căutarea nu pornește.
- **2.6.** Altfel se adaugă mesajul „✅ Am identificat afecțiunea: …” (când s-a recunoscut o afecțiune) și „🔍 Caut rapid în cele N documente interne disponibile. Vă rog să așteptați.”, unde N este numărul documentelor din categoriile bifate.
- **2.7.** Răspunsul revine imediat cu `startSearch: true`; frontend-ul afișează mesajele și abia apoi pornește căutarea (cererea separată de la secțiunea 3), ca pacientul să-și vadă imediat mesajul. Butonul devine „⏳ Caută...” cât durează.

### 3. Căutarea fragmentelor — `POST /api/search`

- **3.1.** Apelează `Retriever.collect(session, ai.context_budget())`. Bugetul este limita de context a furnizorului activ: `X_AI_MAX_CONTEXT_CHARS`, `DEEPSEEK_MAX_CONTEXT_CHARS`, `OLLAMA_MAX_CONTEXT_CHARS` (implicit 1.000.000 de caractere) sau `HF_MAX_CONTEXT_CHARS` (implicit 120.000); cu Hugging Face pacientul vede deci mai puține fragmente.
- **3.2.** Interogarea este **întreaga problemă de sănătate** (`consultation_query()`); istoricul conversației nu este folosit.
- **3.3.** `rank()` notează toate fragmentele (`score = 4·P1 + 2·P2 + L + V`) și întoarce, în ordinea scorului, doar fragmentele întregi care încap în buget. Detaliile sunt în [fragment-search-and-scoring.md](fragment-search-and-scoring.md).
- **3.4.** Fiecare fragment devine o dovadă `C<chunk_id>` cu `source` (`documents/<cale>:<linie_start>-<linie_end>`), `text` (prefixat cu `Secțiune: <titlu>`), `score`, `relevance_percent` și componentele scorului.
- **3.5.** Dacă nu există nicio dovadă: „Nu am găsit fragmente relevante în sursele locale.”
- **3.6.** Altfel, dovezile sunt păstrate în sesiune ca `PendingSearch` (împreună cu profilul de la acel moment), sub un `search_id` aleator. Se păstrează cel mult 12 căutări în așteptare, deci pacientul poate genera și pentru o căutare mai veche din chat.

### 4. Afișarea fragmentelor — `_fragments_message()` și `FragmentsPanel`

- **4.1.** În chat se adaugă mesajul `fragments`: „Am găsit N fragmente relevante în M documente locale”, cu lista fragmentelor ordonată după scor.
- **4.2.** Pentru fiecare fragment: textul complet, `Scor relevanță: X%`, scorul semantic și lexical, `Afecțiune în titlu` / `Afecțiune în text`, `Găsire Lexicală` și calea documentului.
- **4.3.** Panoul are filtre (scor minim, scor semantic, afecțiune, găsire lexicală, document) și un sumar cu numărul de fragmente, documente și caractere. Filtrele schimbă doar ce se vede, nu ce se trimite la AI.
- **4.4.** Sub panou apare mesajul `generate`: „Trimite-le la AI pentru a le combina și generează apoi documentul cu recomandări” și butonul „💊 Generează rețeta”.

### 5. Pornirea generării — `POST /api/searches/{search_id}/generate`

- **5.1.** La apăsare, butonul devine „⏳ Se generează rețeta...” și este dezactivat.
- **5.2.** Serverul verifică cookie-ul `naturist_owner` (HMAC-SHA256 din `OWNER_KEY`, `_is_owner()`). Fără `OWNER_KEY` configurat verificarea eșuează închis.
- **5.3.** Un vizitator care nu este owner primește notificarea „Generarea rețetei este disponibilă doar pentru autorul acestui chatbot.”, butonul revine la normal și nu se face niciun apel către AI. Cookie-ul owner (valabil 10 ani) se obține accesând `/owner?key=<OWNER_KEY>`.
- **5.4.** Pentru owner, `_generate_report()` ia blocarea sesiunii și citește `PendingSearch`-ul căutării apăsate: profilul și fragmentele deja afișate, fără a recalcula căutarea.
- **5.5.** Dacă acea căutare nu mai există (de exemplu, a ieșit din cele 12 păstrate): „Nu există fragmente pregătite. Descrieți din nou problema de sănătate.”

### 6. Cererea către furnizorul AI — `ResponsesClient.generate()`

- **6.1.** Furnizorul vine din `AI_PROVIDER` (`ai/providers.py`, implicit `xai`):

  | Furnizor | Cheie | Model implicit | JSON cerut prin |
  |---|---|---|---|
  | `xai` | `X_API_KEY` | `grok-4.3` (reasoning `medium`) | `text.format=json_object`, plus `store=false` |
  | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-flash` | `text.format=json_object` |
  | `huggingface` | `HF_TOKEN` | `deepseek-ai/DeepSeek-V4-Flash:deepinfra` | promptul de sistem |
  | `ollama` | `OLLAMA_API_KEY` (nu e necesară pe un host local) | `deepseek-v4.1-flash:cloud` | promptul de sistem |

- **6.2.** Dovezile sunt ordonate după `score`, descrescător, ca înregistrări `id`, `source`, `text`. **Toate** sunt trimise nemodificate; bugetul a fost deja aplicat la căutare.
- **6.3.** Se înregistrează în log inventarul fragmentelor trimise (textul doar dacă `LOG_FRAGMENT_TEXT` este activ, tăiat la `LOG_FRAGMENT_TEXT_MAX_CHARS`).
- **6.4.** Promptul utilizatorului conține profilul (JSON) și lista fragmentelor; promptul de sistem este `ai/prompts/generate_report_system.md`.
- **6.5.** `complete_json()` trimite o singură cerere `POST {base_url}/responses` (Responses API), cu `max_output_tokens=AI_MAX_OUTPUT_TOKENS` (implicit 20000) și timeout de citire `AI_READ_TIMEOUT_SECONDS` (implicit 300 s; conectare 10 s). Cu `AI_STREAM=true` răspunsul este citit ca flux de evenimente, iar timeout-ul se aplică între evenimente.
- **6.6.** Răspunsul trebuie să aibă `status == "completed"` (un `incomplete` se loghează cu motivul, de obicei limita de tokeni). Se concatenează blocurile `output_text` și se parsează JSON-ul, tolerant la garduri Markdown (se reîncearcă între primul `{` și ultimul `}`).
- **6.7.** Se normalizează cele cinci secțiuni: `uz_intern`, `nutritie`, `uz_extern`, `alte_recomandari`, `atentionari`. Fiecare element are `text` și `evidence_ids` (ID-urile dovezilor citate).
- **6.8.** Nutriția este un obiect cu `retete`, `recomandate`, `nerecomandate`, `interzise`, `alte`, convertit în elemente prefixate (`[RETETA]`, `[RECOMANDAT]`, `[NERECOMANDAT]`, `[INTERZIS]`, `[ALTE]`).

### 7. Generarea PDF-ului — `create_pdf()`

- **7.1.** Titlul (`report_title()`): „Remedii naturiste pentru <afecțiunile recunoscute>”, sau textul scris de pacient când nu s-a recunoscut nicio afecțiune. Același titlu dă și numele fișierului PDF.
- **7.2.** Copertă (`CoverPanel`): „GHID INFORMATIV”, titlul, „de la dr. Cuișor”, portretul medicului și avertismentul că ghidul este informativ.
- **7.3.** `sort_sections_by_relevance()` ordonează elementele fiecărei secțiuni după cel mai mare `relevance_percent` al fragmentelor citate, apoi după numărul de surse distincte, apoi după poziția inițială.
- **7.4.** `build_reference_index()` numerotează sursele citate în ordinea primei apariții.
- **7.5.** Cele cinci secțiuni colorate (`RoundedSection`); o secțiune goală afișează „Nu au fost identificate informații suficient de relevante în sursele disponibile.” Nutriția este grupată prin `nutrition_display_groups()`: rețetele sunt elemente separate, celelalte categorii sunt grupate.
- **7.6.** Fiecare recomandare cu dovezi primește legătura „→ Surse N” către bibliografie.
- **7.7.** Secțiunea „6. Bibliografie” grupează sursele pe fișier; fiecare intrare are legătura „← înapoi” către prima recomandare care o citează.
- **7.8.** Documentul este construit în memorie cu ReportLab (A4, semne de carte, subsol „Remedii naturiste de la Dr. Cuișor” și numărul paginii) și întors ca octeți.

### 8. Rezultatul în chat și descărcarea

- **8.1.** Raportul este păstrat în sesiune (`StoredReport`: octeții, numele fișierului, problema) sub un `report_id` aleator (`secrets.token_urlsafe(18)`); se păstrează ultimele 12 rapoarte, iar ultimul este cel trimis pe e-mail.
- **8.2.** Mesajul `generate` al căutării este înlocuit, chiar în locul lui din chat, cu: textul recomandărilor cu bibliografie (`_recommendation_text()`), panoul de descărcare („📄 Descarcă PDF”) și oferta: „Dacă doriți să trimiteți documentul pe mail la cineva, spuneți-mi la ce adresă să îl trimit.”
- **8.3.** Descărcarea: `GET /api/reports/{tab_id}/{report_id}` (cu prefixul `PUBLIC_ROOT_PATH` când aplicația rulează sub o subcale). Întoarce HTTP 404 dacă sesiunea sau raportul nu există; altfel PDF-ul ca atașament, cu `Cache-Control: no-store`.
- **8.4.** Rapoartele rămân în memorie până când sesiunea este închisă, expiră (inactivitate `SESSION_IDLE_SECONDS` = 3600 s, durată maximă `SESSION_MAX_SECONDS` = 14400 s, verificate la fiecare minut) sau aplicația este repornită. Închiderea sau reîncărcarea paginii (`pagehide`) trimite `POST /api/session/unload`, care șterge sesiunea.

### 9. Trimiterea pe e-mail — `_send_report_email()` și `send_report()`

- **9.1.** Declanșare: după generarea unui raport, pacientul scrie în chat **doar o adresă de e-mail** (pasul 2.3).
- **9.2.** Configurația vine din `GMAIL_USERNAME`, `MAIL_FROM`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`. Dacă lipsește ceva: „Trimiterea pe mail nu este configurată momentan.”
- **9.3.** Mesajul are subiectul „Raport recomandări naturiste pentru <problemă>”, un text scurt și ultimul PDF atașat.
- **9.4.** Se reînnoiește tokenul Google OAuth, apoi mesajul este trimis prin Gmail API (`users/me/messages/send`), fiecare cerere cu timeout de 20 s.
- **9.5.** La succes: „✅ Am trimis documentul la <adresa>.”; la orice eroare se loghează și se afișează „Nu am putut trimite documentul pe mail. Încercați din nou.” Raportul rămâne neafectat.

### 10. Erori și protecții

- **10.1.** `AIUnavailable` (cheie lipsă, eroare HTTP, conexiune eșuată sau răspuns invalid): mesajul erorii apare în chat. Pe server, căutarea rămâne în așteptare, deci generarea se poate relua.
- **10.2.** Altă excepție la generare: se loghează cu traceback, iar chatul afișează „Raportul nu a putut fi generat. Încercați din nou.”
- **10.3.** Dacă o cerere eșuează la nivel de rețea, frontend-ul afișează o notificare („Mesajul nu a putut fi trimis…” / „Rețeta nu a putut fi generată…”) și reactivează butonul.
- **10.4.** Sesiune expirată: HTTP 409 („Sesiunea a expirat. Reîncărcați pagina.”); cookie sau tab lipsă: 401 / 400.
- **10.5.** Protecții la toate cererile: cererile `POST`/`PUT`/`DELETE` cu `Origin` străin sunt respinse (403); cel mult `MAX_REQUESTS_PER_MINUTE` (implicit 60) cereri pe minut pe IP pentru `/api/` (cu `TRUST_PROXY=true` IP-ul vine din `X-Forwarded-For`); antetele `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- **10.6.** `GET /healthz` întoarce 503 dacă lipsește cheia furnizorului AI activ.
- **10.7.** La pornire, aplicația face o căutare de probă (`warm_up()`), ca prima căutare a unui pacient să fie rapidă.

---

Căutarea și scorul fragmentelor sunt descrise în [fragment-search-and-scoring.md](fragment-search-and-scoring.md), iar generarea indexului în [hybrid-index-generation.md](hybrid-index-generation.md).
