# Fluxul de generare a raportului final

**Intrare:** descrierea problemei de sănătate furnizată de utilizator și indexul hibrid local.

**Ieșire:** fragmentele găsite (afișate pacientului), recomandările afișate în chat, un raport PDF descărcabil și, la cerere, trimiterea PDF-ului pe e-mail către o adresă indicată în chat.

Fluxul are **două etape separate**, declanșate de acțiuni diferite ale utilizatorului:

1. **Căutarea locală** (butonul „Trimite”) — fără niciun apel către AI; pacientul vede fragmentele găsite.
2. **Generarea raportului** (butonul „Generează rețeta”) — trimite către xAI exact fragmentele deja verificate de pacient.

## 1. Preluarea descrierii problemei de sănătate — `on_message()`

- **1.1.** Identifică sesiunea tabului curent folosind cookie-ul de sesiune `naturist_sid` și identificatorul de sesiune Gradio.
- **1.2.** Elimină spațiile inutile din mesaj; un mesaj gol este ignorat.
- **1.3.** Respinge mesajul dacă depășește `MAX_CHAT_CHARS` (implicit 4000).
- **1.4.** Obține blocarea exclusivă a sesiunii și resetează `email_request_handled=False`.
- **1.5.** Dacă există deja un raport generat și mesajul este **exclusiv o adresă de e-mail**, tratează cazul ca o cerere de trimitere pe e-mail (vezi secțiunea 10): marchează `email_request_handled=True`, adaugă răspunsul în chat și oprește fluxul, fără a reface căutarea.
- **1.6.** Altfel, adaugă mesajul utilizatorului în istoric și elimină din chat panourile de descărcare rămase de la raportul anterior.
- **1.7.** Șterge raportul anterior (`clear_report()`) și `pending_evidence`.
- **1.8.** Înlocuiește problema de sănătate din profil (`replace_health_problem()`): contextul și transcriptul sunt resetate la noul mesaj.
- **1.9.** Adaugă în chat mesajul „Caut rapid în cele N documente interne disponibile”.
- **1.10.** Ascunde panoul „Generează rețeta” și returnează istoricul actualizat.

## 2. Înlănțuirea evenimentelor Gradio

După `on_message()` (declanșat de „Trimite” sau de Enter), Gradio rulează în lanț, cu `queue=False`:

- **2.1.** Script JS care restrânge panourile de fragmente vechi, apoi derulare automată.
- **2.2.** Butonul „Trimite” devine „⏳ Caută...” și este dezactivat; zona de notificare owner este golită.
- **2.3.** `on_find_fragments()` — etapa de căutare locală (secțiunile 3–6).
- **2.4.** Butonul „Trimite” este reactivat și se derulează automat la ultimul mesaj.

## 3. Căutarea locală a fragmentelor — `on_find_fragments()`

- **3.1.** Identifică sesiunea și obține blocarea exclusivă.
- **3.2.** Dacă mesajul a fost o cerere de e-mail (`email_request_handled`), resetează indicatorul și se oprește fără căutare.
- **3.3.** Dacă profilul nu conține o problemă de sănătate, adaugă mesajul „Descrieți problema de sănătate înainte de căutare” și se oprește.
- **3.4.** Apelează `Retriever.collect(session)` (secțiunile 4–5).
- **3.5.** Aplică `fit_evidence_to_context()`: păstrează cel mai bine punctat prefix de fragmente care încape în `MAX_CONTEXT_CHARS` (2.400.000 de caractere). Aceasta este singura aplicare a limitei, astfel încât pacientul vede exact ce va primi AI-ul.
- **3.6.** Dacă nu rămâne niciun fragment: `pending_evidence=None`, mesaj „Nu am găsit fragmente relevante în sursele locale” și panoul „Generează rețeta” rămâne ascuns.
- **3.7.** Altfel, stochează fragmentele în `session.pending_evidence`, adaugă în chat panoul HTML al fragmentelor (`_fragments_panel_html()`) și afișează panoul cu butonul „💊 Generează rețeta”.

## 4. Construirea interogărilor și rularea retrieval-ului — `Retriever.collect()`

- **4.1.** `consultation_queries()` folosește **întreaga problemă de sănătate** ca interogare unică; istoricul conversației nu este folosit, pentru a nu devia căutarea de la subiect.
- **4.2.** Extrage cuvintele relevante ale problemei (minimum 4 caractere, fără cuvintele generice din `generic_query_words.txt`, comparate fără diacritice și fără diferențe de majuscule).
- **4.3.** Dacă există cuvinte relevante, adaugă o interogare cu acestea sortate alfabetic; textul problemei inserat în față se deduplică cu interogarea de bază.
- **4.4.** Deduplică interogările după forma normalizată (spații și majuscule); de regulă rămân două.
- **4.5.** Pentru fiecare interogare apelează `rank()` (secțiunea 5), care întoarce **toate** fragmentele indexului, fiecare cu `hybrid_score`.
- **4.6.** Însumează pentru fiecare fragment scorurile `hybrid_score` din toate interogările și reține dacă a fost găsit lexical de cel puțin o interogare.

## 5. Retrieval hibrid pentru o interogare — `search.rank()`

- **5.1.** Citește modelul de embedding și dimensiunea vectorilor din `sync_metadata` (Postgres).
- **5.2.** Încarcă modelul FastEmbed (ONNX) din `data/model_cache` (offline, în cache pe proces).
- **5.3.** Generează vectorul E5 al interogării cu prefixul `query: ` și îl normalizează L2.
- **5.4.** Calculează similaritatea semantică față de **toți** vectorii direct în Postgres (`pgvector`, operatorul `<#>`); fiecare fragment primește un rang semantic (fără limită top-N — niciun index aproximativ HNSW/ivfflat).
- **5.5.** Construiește interogarea `tsquery`: un segment fără virgulă devine o **frază exactă** (`phraseto_tsquery`); segmentele separate prin virgulă devin fraze combinate prin `||` (OR). Nu există revenire la potrivirea pe cuvinte individuale.
- **5.6.** Preia din Postgres fragmentele al căror `text_search` se potrivește, ordonate prin `ts_rank_cd` (fără `LIMIT`); acestea primesc un rang lexical.
- **5.7.** Calculează scorul prin Reciprocal Rank Fusion, `k=60`: `1/(60+rang_semantic)` plus, dacă există potrivire exactă, `1/(60+rang_lexical)`.
- **5.8.** Întoarce toate fragmentele sortate descrescător după `hybrid_score`, cu `found_by_lexical`, similaritatea semantică, calea sursei, intervalul de linii, titlul și textul.
- **5.9.** `RRF_MAX_SCORE = 2/(k+1)` este scorul maxim posibil și servește drept plafon pentru procentul de relevanță.

## 6. Selecția, îmbinarea și asamblarea dovezilor — `Retriever.collect()`

- **6.1.** Calculează `relevance_percent = suma_scorurilor / număr_interogări / RRF_MAX_SCORE × 100`.
- **6.2.** Nu se aplică niciun prag pe `relevance_percent` — toate fragmentele întoarse de `rank()`, pentru fiecare interogare, devin dovezi. Singura selecție rămasă e bugetul `MAX_CONTEXT_CHARS`, la pasul 7, comună panoului din UI și cererii către AI.
- **6.3.** Grupează fragmentele din același fișier ale căror intervale de linii se suprapun sau sunt la cel mult 5 linii distanță (`NEIGHBOR_LINE_GAP`), doar cât timp diferența dintre cel mai mare și cel mai mic procent din grup rămâne strict sub `MERGE_MAX_PERCENT_DIFF` (implicit 9).
- **6.4.** Ordonează grupurile după scorul celui mai bun membru, descrescător.
- **6.5.** Pentru un grup cu un singur fragment, construiește textul cu `_context()`: adaugă titlul secțiunii și, pentru fragmente sub 600 de caractere, liniile apropiate din fișierul sursă (limitat la 1800 de caractere).
- **6.6.** Pentru un grup cu mai multe fragmente, construiește textul cu `_group_context()`: liniile sursă ale intervalului unit; dacă fișierul nu este disponibil, textele membrilor în ordinea din fișier.
- **6.7.** Fiecare dovadă primește ID-ul `C<chunk_id>` al celui mai bun membru și conține `source` (`documents/<cale>:<linie_start>-<linie_end>`), `text`, `score`, `relevance_percent` și `found_by_lexical`.
- **6.8.** Înregistrează în log numărul de interogări, candidați, dovezi, caractere și surse unice.

## 7. Afișarea fragmentelor pacientului — `_fragments_panel_html()`

- **7.1.** Construiește un panou `<details>` cu banner: „Am găsit N fragmente relevante în M documente locale”.
- **7.2.** Sortează lista plată de fragmente după `score`, descrescător, indiferent de document sau interogare.
- **7.3.** Pentru fiecare fragment afișează textul complet (spații normalizate) și o linie cu „Scor relevanță: X%”, eticheta „Găsire Lexicală” (dacă este cazul) și documentul sursă. Nu sunt afișate ID-uri sau intervale de linii.
- **7.4.** Încheie cu totalul fragmentelor și documentelor.
- **7.5.** Panoul „Trimite-le la AI ... 💊 Generează rețeta” devine vizibil; pacientul decide dacă continuă.

## 8. Declanșarea generării — `on_generate_report()`

- **8.1.** Apăsarea butonului „Generează rețeta” îl dezactivează („⏳ Se generează rețeta...”), golește notificarea owner și restrânge panourile de fragmente.
- **8.2.** Verifică cookie-ul `naturist_owner` prin HMAC-SHA256 față de `OWNER_KEY` (`_is_owner()`). Fără `OWNER_KEY` configurat verificarea eșuează închis.
- **8.3.** Vizitatorii care nu sunt owner primesc o notificare roșie sub fragmente („Generarea rețetei nu este disponibilă momentan pentru acest cont”); panoul rămâne vizibil, nu se face niciun apel către AI. Cookie-ul owner se obține accesând `/owner?key=<OWNER_KEY>`.
- **8.4.** Pentru owner apelează `_generate_report()`.
- **8.5.** Obține blocarea sesiunii și citește `session.pending_evidence` (fragmentele deja afișate, nerecalculate).
- **8.6.** Dacă profilul nu este pregătit sau nu există dovezi pending, adaugă „Nu există fragmente pregătite. Descrieți din nou problema de sănătate.” și ascunde panoul.

## 9. Cererea către xAI și parsarea răspunsului — `XAIClient.generate()`

- **9.1.** Înregistrează în log numărul de dovezi și numărul de caractere.
- **9.2.** Ordonează dovezile după `score`, descrescător, în înregistrări `id`, `source`, `text`. **Toate** sunt trimise nemodificate (fără compactare sau trunchiere); bugetul de context a fost deja aplicat la secțiunea 3.5.
- **9.3.** Înregistrează inventarul fragmentelor trimise (textul este logat doar dacă `LOG_FRAGMENT_TEXT` este activ).
- **9.4.** Construiește promptul utilizatorului: profilul medical serializat JSON și lista completă a fragmentelor admise; promptul de sistem este `ai/prompts/generate_report_system.md`.
- **9.5.** `complete_json()` trimite o singură cerere către xAI Responses API (`{XAI_API_BASE}/responses`) cu `Authorization: Bearer GROK_API_KEY_MED`, modelul și nivelul de reasoning din configurare (implicit `grok-4.3`, `medium`), format `json_object`, `max_output_tokens=20000`, `store=false`, timeout 75 s (conectare 10 s).
- **9.6.** Lipsa cheii API sau erorile HTTP/conexiune/răspuns invalid devin `AIUnavailable` cu mesaj afișabil utilizatorului; se înregistrează statusul, durata, dimensiunea răspunsului și ID-ul cererii.
- **9.7.** Verifică `status == "completed"`, concatenează blocurile `output_text`, parsează JSON-ul și respinge un răspuns gol sau care nu este obiect.
- **9.8.** Normalizează cele cinci secțiuni: `uz_intern`, `nutritie`, `uz_extern`, `alte_recomandari`, `atentionari`.
- **9.9.** Nutriția este un obiect cu `retete`, `recomandate`, `nerecomandate`, `interzise`, `alte`, convertit în elemente prefixate (`[RETETA]`, `[RECOMANDAT]`, `[NERECOMANDAT]`, `[INTERZIS]`, `[ALTE]`).
- **9.10.** Textele își păstrează întreruperile de linie relevante; din `evidence_ids` sunt păstrate doar șirurile.

## 10. Generarea PDF-ului — `create_pdf()`

- **10.1.** Înregistrează fonturile și construiește stilurile.
- **10.2.** Copertă (`CoverPanel`): „GHID INFORMATIV”, titlul derivat din problema de sănătate, „de la dr. Cuișor”, portretul medicului și avertismentul informativ.
- **10.3.** `sort_sections_by_relevance()` ordonează elementele fiecărei secțiuni după cel mai mare `relevance_percent` al fragmentelor citate, apoi după numărul de surse distincte, apoi după poziția inițială.
- **10.4.** `build_reference_index()` numerotează sursele citate în ordinea primei apariții.
- **10.5.** Redă cele cinci secțiuni colorate (`RoundedSection`) în ordinea configurată; o secțiune goală afișează „Nu au fost identificate informații suficient de relevante în sursele disponibile.”
- **10.6.** Nutriția este grupată prin `nutrition_display_groups()`: rețetele sunt elemente separate, celelalte categorii sunt grupate.
- **10.7.** Fiecare recomandare cu dovezi primește o legătură „→ Surse N” către secțiunea de bibliografie.
- **10.8.** Secțiunea „6. Bibliografie” grupează sursele, iar fiecare intrare are legătură „← înapoi” către prima recomandare care o citează.
- **10.9.** Construiește documentul în memorie cu ReportLab (A4, semne de carte/outline, subsol) și returnează octeții PDF.

## 11. Stocarea și afișarea rezultatului

- **11.1.** Stochează octeții în `session.report_bytes` și un `report_id` aleatoriu (`secrets.token_urlsafe(18)`) în `session.report_id`.
- **11.2.** Adaugă în chat, în ordine: textul recomandărilor cu bibliografie (`_recommendation_text()`, maximum 14.000 de caractere), panoul de descărcare (`_download_html()`) și oferta de e-mail: „Dacă doriți să trimiteți documentul pe mail la cineva, spuneți-mi la ce adresă să îl trimit.”
- **11.3.** Golește `session.pending_evidence` și ascunde panoul „Generează rețeta”.
- **11.4.** Raportul rămâne în memoria procesului până când sesiunea este ștearsă, expiră (inactivitate `SESSION_IDLE_SECONDS` = 3600 s, durată maximă `SESSION_MAX_SECONDS` = 14400 s) sau aplicația este repornită.

## 12. Descărcarea PDF-ului — `GET /api/reports/{tab_id}/{report_id}`

- **12.1.** Identifică sesiunea din cookie-ul `naturist_sid` și `tab_id`.
- **12.2.** Returnează HTTP 404 dacă sesiunea lipsește, `report_id` nu coincide sau nu există PDF.
- **12.3.** Altfel returnează PDF-ul ca atașament (`Content-Disposition` cu numele derivat din titlu) și `Cache-Control: no-store`.

## 13. Trimiterea pe e-mail către altă persoană — `_send_report_email()` și `send_report()`

- **13.1.** Declanșare: după generarea raportului, utilizatorul scrie în chat **doar o adresă de e-mail** (potrivire completă cu `EMAIL_PATTERN`); vezi pasul 1.5.
- **13.2.** `load_mail_config()` citește din mediu `GMAIL_USERNAME`, `MAIL_FROM`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`.
- **13.3.** Dacă configurația este incompletă, returnează `email_skipped` și chatul afișează „Trimiterea pe mail nu este configurată momentan.”
- **13.4.** Construiește mesajul (subiect „Raport recomandări naturiste pentru …”) cu PDF-ul atașat.
- **13.5.** Reînnoiește tokenul de acces Google OAuth (refresh token), apoi trimite mesajul prin Gmail API (`users/me/messages/send`), fiecare cerere cu timeout de 20 s.
- **13.6.** La succes chatul afișează „✅ Am trimis documentul la <adresa>.”; la orice excepție se loghează și se afișează „Nu am putut trimite documentul pe mail. Încercați din nou.” Raportul PDF rămâne neafectat.

## 14. Tratarea erorilor

- **14.1.** Problemă lipsă: mesaj „Descrieți problema de sănătate înainte de căutare.”
- **14.2.** Niciun fragment peste prag: mesaj „Nu am găsit fragmente relevante în sursele locale.”
- **14.3.** `AIUnavailable`: se afișează mesajul erorii; panoul „Generează rețeta” rămâne vizibil și butonul este reactivat, astfel încât pacientul poate reîncerca fără a pierde fragmentele.
- **14.4.** Excepție neașteptată: se loghează tipul, mesajul și traceback-ul; chatul afișează „Raportul nu a putut fi generat. Încercați din nou.”, cu același comportament de reîncercare.
- **14.5.** Cerere non-owner: notificare dedicată, fără apel către AI (secțiunea 8.3).
- **14.6.** Protecții HTTP la toate cererile: verificare `Origin`, limită de `MAX_REQUESTS_PER_MINUTE` (implicit 60) pe IP pentru `/api/` și `/gradio_api/`, antete `Cache-Control: no-store`, `X-Content-Type-Options`, `Referrer-Policy`.

## Rezultatul final

```text
Mesajul utilizatorului („Trimite”)
    -> profilul sesiunii (problema înlocuiește contextul anterior)
    -> retrieval hibrid local (semantic E5 + lexical FTS5, RRF)
    -> îmbinarea fragmentelor vecine (fără filtrare pe relevanță)
    -> limitare la MAX_CONTEXT_CHARS (singurul filtru)
    -> panou cu fragmentele găsite, afișat pacientului (fără AI)
    -> „Generează rețeta” (doar owner)
    -> o singură cerere structurată către xAI, cu exact fragmentele afișate
    -> secțiuni normalizate de recomandări
    -> raport PDF în memorie
    -> răspuns în chat și link securizat de descărcare
    -> la cerere: adresă de e-mail scrisă în chat -> trimitere prin Gmail
```
