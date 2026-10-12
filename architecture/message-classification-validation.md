# Validarea clasificării mesajelor

Data: 2026-10-12.

Implementarea include `/api/classify`, clasificatorul Ollama local (`gemma3:1b`) cu JSON validat, ramurile remedii/planta/diverse, trimiterea raportului precedent, clarificările, anularea operațiilor și identificatori pentru cereri repetate. Diagrama conexiunilor și documentația au fost actualizate.

## Verificări automate

- `pytest src/tests/unit src/tests/integration/test_herb_conditions.py`: **521 teste trecute**, plus **149 subteste**. Cele 13 teste SQL folosesc un PostgreSQL temporar, separat de baza aplicației. Cele două avertismente sunt deprecări existente din Starlette/httpx și importul testcontainers.
- `npm test`: **51 teste trecute**, în 11 fișiere.
- `npm run build`: TypeScript și Vite trecute.
- Ruff: trecut pentru backend și scriptul de indexare modificat.
- Mypy: trecut pentru cele 7 module configurate și separat pentru cele 2 module AI noi.
- Nu s-au trimis emailuri reale; testele folosesc un sender injectat și PDF-uri sintetice. Baza aplicației și indexul corpusului nu au fost modificate.

SQL-ul a fost verificat pentru DISTINCT între specii cu același nume românesc, aliasuri, diacritice, ordonare, total 0, plantă absentă, caractere LIKE literale, index lipsă și metadate învechite. Testele HTTP verifică mesajul inițial rapid, clasificarea repetată, revizii învechite, operații concurente, ramura diverse, completarea clarificărilor, selectarea raportului înainte de clasificare, adrese inventate/multiple/invalide, eșecul Gmail și evitarea reexpedierii la cereri duplicate.

Identificatorii de mesaje sunt păstrați într-o fereastră de 32 de cereri a sesiunii, inclusă în contabilizarea memoriei. În această fereastră, un mesaj repetat nu creează un context nou, iar repetarea unei clasificări nu reexpediază emailul. Frontendul nu face retry automat pentru aceste operații. Un mesaj nou cu un identificator nou reprezintă o nouă solicitare explicită.

## Verificare vizuală

Buildul real React a fost servit pe un port local separat, cu infrastructură sintetică. S-au verificat indicatorul „Clasificare mesaj…”, totalul deasupra tabelului plantei, ID-urile, numele speciilor și continuarea `diverse` spre fragmente fără cele două notificări medicale. SVG-ul a fost deschis în browser și inspectat integral pentru etichete și conexiuni.

Capturi locale: [interfață](../tmp/message-classification-ui.png), [diagramă](../tmp/message-classification-diagram.png). Datele din captura interfeței sunt sintetice.

## Verificarea inițială Hugging Face (istoric; provider înlocuit)

Apelul real prin conexiunea existentă `router.huggingface.co/v1/responses`, cu modelul configurat `deepseek-ai/DeepSeek-V4-Flash:deepinfra` și o întrebare sintetică, a ajuns la provider. Providerul a returnat `status: failed`, `error.code: server_error`, cu cauza **402 — no remaining credits**. Nu există un răspuns de clasificare reușit de la modelul live, deci calitatea lui nu este confirmată prin acest test.

Prima verificare a expirat cu timeoutul configurat de 10 secunde. O verificare diagnostică cu 30 de secunde a permis identificarea cauzei de credit. Implicitul aplicației rămâne 10 secunde, configurabil prin `MESSAGE_CLASSIFICATION_TIMEOUT_SECONDS`; modelul, tokenul și providerul existent nu au fost schimbate. Lipsa creditelor este acum identificată distinct în parser și testată, fără înregistrarea tokenului sau a corpului răspunsului în log.

Clasificarea folosește acum Ollama local (`gemma3:1b`), fără token și fără credite Hugging Face. Refolosește configurația locală de identificare a afecțiunii; indisponibilitatea Ollama păstrează fallbackul sigur spre remedii sau clarificarea cererii de email. Verificarea HF de mai sus descrie exclusiv prima implementare.

## Verificarea clasificatorului Ollama local

Clasificatorul nou a fost executat într-un proces temporar în containerul existent, prin stdin, fără modificarea aplicației pornite sau a bazei de date. Modelul `gemma3:1b` era deja disponibil. Temperatura este 0, timeoutul 10 secunde și bugetul 300 tokenuri. Requestul `/v1/responses` include `text.format.type=json_schema`, cu o ramură pentru fiecare intenție și câmpurile nerelevante obligatoriu null; validarea Pydantic rămâne strictă.

Șase mesaje sintetice au trecut verificarea live: remedii pentru gripă; informații despre mușețel; întrebare despre căutare semantică; trimiterea raportului la o adresă sintetică; interdicția de a trimite raportul; plante care ajută pentru gastrită. Interdicția a revenit ca `diverse`, cu clarificare, iar întrebarea despre plante pentru gastrită a revenit ca `remedii`. Nu s-a trimis niciun email. Aceste exemple confirmă conectivitatea și comportamentul verificat, nu acuratețea pentru toate mesajele posibile.

Testele clasificatorului, furnizorilor, identificării și rutării: 109 trecute, plus 11 subteste. Întreaga suită unit backend: 508 teste și 149 subteste trecute. Ruff și Mypy pentru modulele modificate au trecut. Activarea în containerul aplicației necesită reconstruirea și recrearea serviciului `app`; Ollama și indexul nu necesită reconstruire sau reindexare.

Schimbarea a fost activată prin `docker compose up -d --build --no-deps app`. Containerul aplicației a ajuns `healthy`; `/healthz` răspunde 200. O clasificare sintetică executată cu codul din noul container a confirmat `provider=ollama`, `model=gemma3:1b` și intenția `diverse`. Serviciile Ollama și PostgreSQL nu au fost repornite.

## Rezolvarea clarificărilor repetate pentru plante

În proba reală, `gemma3:1b` extrăgea numele plantei din răspunsul scurt, dar întorcea `needs_clarification=true`. Clasificatorul primește acum și numele recunoscute în catalogul local. Un nume recunoscut în mesaj și neambiguu completează cererea de plantă; un răspuns alcătuit numai dintr-un nume de catalog completează clarificarea în așteptare. Cererile pentru mai multe plante păstrează clarificarea, iar cererile de remedii nu sunt convertite doar fiindcă menționează o plantă.

Catalogul real are `musetel` drept nume canonic și drept alias pentru `musetel roman`. Numele comune cu mai multe interpretări afișează fiecare plantă ca „nume românesc (nume latin)” și cer alegerea utilizatorului, inclusiv atunci când mai multe specii au același nume românesc. Răspunsul se verifică în opțiunile oferite și selectează o singură specie; SQL-ul este parametrizat după nume și ID, fără reuniunea asocierilor altor specii.

Probe reale cu Ollama și catalogul PostgreSQL, fără modificarea datelor: „spune-mi tot ce stii despre coada-soricelului”, „coada-soricelului”, „musetel” și „papadie” au revenit cu intenția `planta` și un nume recunoscut, fără întrebarea generică repetată. „musetel” continuă prin alegerea uneia dintre plantele asociate numelui. Teste specifice: 66 trecute și 26 subteste; teste SQL într-o bază PostgreSQL temporară: 15 trecute, inclusiv separarea asocierilor speciei alese. Suitei unit complete i-au trecut 521 teste și 149 subteste înaintea ajustării finale a alegerii; ajustarea este acoperită de verificările specifice și SQL ulterioare. Ruff și Mypy au trecut.

În codul activ, proba reală a oferit „musetel (matricaria chamomilla)” și „musetel roman (chamaemelum nobile)”; răspunsul „musetel roman” a selectat `chamaemelum nobile`, fără altă clarificare.

Citirea rezultatelor a fost blocată de `INDEX_HERBS_RESYNC_REQUIRED`: fingerprinturile cataloagelor sunt diferite de cele publicate în asocieri. Rularea incrementală a aplicat migrarea restantă `009_add_premenopauza.sql`, apoi a detectat toate cele 383 de documente ca modificate din cauza noului dicționar. Procesul a fost oprit la încărcarea modelului CPU, înainte de embeddings și de publicarea fragmentelor/asocierilor. Migrarea SQL este aplicată; indexul vechi și asocierile vechi sunt păstrate. Utilizatorul a ales să păstreze doar corecția clasificării și a refuzat reindexarea completă; aceasta rămâne oprită. Afișarea asocierilor necesită ulterior sincronizarea indexului.

## Corecția verificării amprentelor după reindexare

După reindexarea completă și deploy, clasificarea reală pentru „spune-mi ce stii despre coada-soricelului” a revenit corect ca `planta`, dar citirea asocierilor răspundea 503. Diagnosticul read-only a confirmat versiunea textului `10`, generații identice, 105.943 de asocieri publicate și același număr real de rânduri. Verificarea indexului de embeddings trecea.

Cauza era în cititor: compara amprentele generice ale cataloagelor cu amprentele specifice asocierilor, calculate de indexer din ID-uri, sinonime deduplicate și nume de plante normalizate. Aceste formate diferă chiar pentru același catalog. Diagnosticul anterior bazat numai pe această diferență nu demonstra că asocierile necesitau reconstruire.

Calculul existent al indexerului este acum comun în `backend.ai.herb_index_catalog`; indexerul și cititorul folosesc `read_index_catalogs` pe conexiunea și tranzacția proprii. Formatul metadatelor publicate rămâne compatibil. Nu este necesară o nouă reindexare pentru această corecție. Testul de regresie publică asocierile prin indexerul real, le citește prin `lookup_herb_conditions`, apoi verifică respingerea lor dacă se schimbă catalogul. Cele 25 de teste SQL pentru citire și indexare au trecut, plus 4 subteste, într-o bază temporară separată.

Corecția a fost activată prin reconstruirea și recrearea numai a serviciului `app`, fără reindexare sau modificări în baza aplicației. Citirea directă din container a întors 435 de asocieri pentru `achillea millefolium` și 438 pentru `chamaemelum nobile`. Fluxul HTTP real, într-o sesiune sintetică închisă la final, a trecut pentru cererea despre coada-șoricelului, afișarea opțiunilor pentru `musetel` și selectarea `musetel roman` cu panoul limitat la `chamaemelum nobile`. Cele 47 de regresii unit/backend au trecut, plus 8 subteste; Ruff și Mypy au trecut.

## Activare

Reporniți backendul pentru încărcarea clasificatorului și reîncărcați pagina pentru buildul React nou. Nu este necesară o migrare nouă pentru această funcționalitate. Ramura plantei folosește asocierile `herbs_benefits` deja publicate de reindexare; un index absent sau învechit produce o eroare explicită, nu un total 0 fals.
