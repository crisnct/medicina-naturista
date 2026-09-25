# 02 · Generarea raportului final cu recomandări naturiste

**Proiect:** medicina-naturista  
**Componente implicate:** `web/main.py`, `web/handlers.py`, `core/sessions.py`, `core/models.py`, `ai/retrieval.py`, `ai/search.py`, `ai/client.py`, `ai/prompts/generate_report_system.md`, `reporting/pdf.py`, `integrations/gmail.py`  
**Tip diagrame:** sequence diagram (Mermaid)

## Context

Fluxul pornește când utilizatorul trimite descrierea problemei de sănătate în interfața Gradio. Raportul se obține în patru etape, toate executate sincron în `on_report`, sub `session.lock`:

1. **retrieval** — căutare hibridă locală (semantic + FTS5) și asamblarea dovezilor `C<chunk_id>`;
2. **ai** — un singur request către xAI Responses API (`grok-4.3`, `reasoning.effort=low`, `json_object`, `max_output_tokens=20000`, `store=false`);
3. **pdf** — randare ReportLab în memorie (`bytes`), păstrată în sesiune;
4. **email** — trimitere best-effort prin Gmail API (OAuth2 refresh token).

Documentul are patru diagrame: orchestrarea completă (2.1), apoi detaliile pentru retrieval (2.2), requestul AI (2.3) și crearea PDF-ului cu livrarea lui (2.4).

## 2.1 Orchestrare end-to-end

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilizator
    participant BR as Browser<br/>(Gradio UI)
    participant MW as FastAPI middleware<br/>session_and_limits
    participant H as main.py<br/>on_message / on_auto_report / on_report
    participant SS as SessionStore
    participant RT as Retriever
    participant AI as XAIClient
    participant PDF as reporting.pdf<br/>create_pdf
    participant GM as integrations.gmail<br/>send_report

    U->>BR: descrie problema și apasă Trimite
    BR->>MW: POST /gradio_api/... (on_message)
    MW->>MW: verificare Origin, rate limit per IP (60/min), cookie naturist_sid
    MW->>H: on_message(message)
    H->>SS: get(cookie, tab_id)
    SS-->>H: SessionData
    H->>H: validare lungime (MAX_CHAT_CHARS)
    H->>H: sub session.lock: clear_report, replace_health_problem,<br/>auto_report_pending = true, mesaj "Pregătesc recomandările..."
    H-->>BR: istoric actualizat
    BR->>BR: auto-scroll, buton în starea "Se pregătește..."

    BR->>MW: POST (on_auto_report, lanț .then)
    MW->>H: on_auto_report()
    H->>H: sub session.lock: pending = false
    H->>H: on_report()
    alt lipsește health_problem
        H-->>BR: "Descrieți problema de sănătate..."
    end

    H->>RT: collect(session)  [stage=retrieval]
    RT-->>H: evidence {C123: {source, text}, ...}
    alt evidence gol
        H-->>BR: "Nu am găsit fragmente relevante în sursele locale."
    end

    H->>AI: generate(profile.as_dict(), evidence)  [stage=ai]
    AI-->>H: sections {uz_intern, nutritie, uz_extern,<br/>alte_recomandari, atentionari}

    H->>PDF: create_pdf(profile, sections, evidence)  [stage=pdf]
    PDF-->>H: bytes PDF
    H->>H: session.report_bytes = PDF,<br/>session.report_id = token_urlsafe(18)

    H->>GM: send_report(problemă, PDF, nume fișier)  [stage=email]
    alt OAuth incomplet
        GM-->>H: email_skipped
    else trimis
        GM-->>H: email_sent
    else eroare Google
        GM-->>H: excepție, logată, fluxul continuă
    end

    H->>H: _recommendation_text(sections, evidence) — text + bibliografie
    H-->>BR: istoric + panou "Descarcă PDF"
    BR->>BR: buton "Trimite" reactivat

    U->>BR: click "Descarcă PDF"
    BR->>MW: GET /api/reports/{tab_id}/{report_id}
    MW->>H: download()
    H->>SS: get(cookie, tab_id)
    alt sesiune sau report_id invalid
        H-->>BR: 404
    else valid
        H-->>BR: application/pdf, Content-Disposition attachment
    end
```

## 2.2 Retrieval hibrid și asamblarea dovezilor

```mermaid
sequenceDiagram
    autonumber
    participant H as on_report
    participant RT as Retriever.collect
    participant Q as consultation_queries
    participant S as search.rank
    participant FE as FastEmbed<br/>(query_embed)
    participant NP as embeddings.npy<br/>(mmap)
    participant DB as index.sqlite3
    participant FS as data/documents

    H->>RT: collect(session)
    RT->>Q: consultation_queries(profile)
    Q->>Q: problemă + perechi întrebare/răspuns + health_context,<br/>tăiate la 900 caractere, deduplicate
    Q-->>RT: interogări de bază
    RT->>RT: topic_words = cuvinte ≥ 4 litere minus generic_query_words.txt
    RT->>RT: prepend: problema brută + topic_words sortate
    RT->>RT: search_queries = interogări + aceleași interogări<br/>cu sufixul "contraindicații interacțiuni atenționări"

    loop pentru fiecare search_query (2 × interogări de bază)
        RT->>S: rank(query, limit=120, candidates=720)
        S->>NP: citește manifest + np.load(mmap)
        S->>FE: query_embed("query: ...")
        FE-->>S: vector 384
        S->>NP: produs scalar pe toată matricea
        S->>DB: FTS5 MATCH ... ORDER BY bm25 LIMIT 720
        S->>S: RRF (k = 60) → top 120
        S->>DB: SELECT chunks WHERE chunk_id IN (...)
        S-->>RT: candidați
        RT->>RT: acceptă dacă (lexical_rank există ȘI conține un cuvânt-cheie)<br/>SAU sursa este ATENTIONARI-SI-CONTRAINDICATII
    end

    RT->>DB: _topic_coverage_chunks — SELECT * FROM chunks (scanare completă)
    RT->>RT: filtrare Python: fraza exactă a problemei (fără diacritice),<br/>sortare: fișier dedicat, frecvență cuvinte, sursă, linie
    RT->>DB: _dedicated_document_chunks — fișiere al căror nume conține un topic_word
    DB-->>RT: toate fragmentele acelor fișiere

    Note over RT: Ordinea de prioritate în evidence (max MAX_EVIDENCE = 2000)
    RT->>RT: 1. fragmentele care conțin fraza exactă
    RT->>RT: 2. fragmentele din documentele dedicate
    RT->>RT: 3. round-robin între loturile acceptate per interogare, fără duplicate

    loop pentru fiecare fragment adăugat
        RT->>FS: _context — dacă textul are sub 600 caractere,<br/>citește ±5 linii din fișierul-sursă (max 1800)
        RT->>RT: "Secțiune: heading" + context, tăiat la EVIDENCE_CONTEXT_CHARS (3000)
    end
    RT-->>H: evidence {C<chunk_id>: {source: "documents/fișier:linie-linie", text}}
```

## 2.3 Requestul către xAI

```mermaid
sequenceDiagram
    autonumber
    participant H as on_report
    participant AI as XAIClient.generate
    participant EV as _evidence_entries
    participant LG as Logger
    participant CJ as complete_json / _post
    participant X as xAI Responses API<br/>POST /v1/responses

    H->>AI: generate(profile, evidence)
    AI->>LG: fragments_collected_for_ai (count, total_chars)
    AI->>EV: convertește în listă {id, source, text}
    EV->>EV: serialized_length = len(json.dumps(entries))
    alt serialized_length > MAX_CONTEXT_CHARS (2 400 000)
        EV->>LG: fragments_before_compaction (inventar complet)
        EV->>EV: scalare proporțională a textelor, minim 256 caractere per fragment
        loop cât timp JSON-ul depășește limita
            EV->>EV: taie uniform din fragmentele mai lungi de 256
        end
        EV->>LG: WARNING fragment_compaction_completed
        EV->>LG: fragments_sent_to_ai (cu original_text_chars)
    else în limită
        AI->>LG: fragments_sent_to_ai
    end
    Note over LG: textul fragmentelor ajunge în log dacă LOG_FRAGMENT_TEXT=true (implicit)

    AI->>AI: user = profil JSON + toate fragmentele JSON
    AI->>CJ: complete_json(system = generate_report_system.md, user, 20000)
    CJ->>CJ: api_key() din GROK_API_KEY_MED
    alt cheie lipsă
        CJ-->>H: AIUnavailable "Lipsește GROK_API_KEY_MED..."
    end
    CJ->>X: POST {model, reasoning.effort, input [system, user],<br/>text.format = json_object, max_output_tokens, store = false}<br/>timeout 75 s, connect 10 s
    alt HTTP 4xx / 5xx
        X-->>CJ: eroare + corp
        CJ->>LG: ai_request_failed (status, request_id, body)
        CJ-->>H: AIUnavailable "Serviciul AI a respins cererea..."
    else eroare de rețea / timeout
        CJ-->>H: AIUnavailable "Serviciul AI nu este disponibil..."
    else 200 OK
        X-->>CJ: {status, output[message.content[output_text]]}
    end
    CJ->>CJ: status == "completed", concatenează output_text, json.loads
    alt JSON invalid sau nu e obiect
        CJ-->>H: AIUnavailable "Răspunsul AI nu a putut fi validat..."
    end
    CJ-->>AI: dict

    loop pentru fiecare secțiune din SECTIONS
        alt nutritie este obiect
            AI->>AI: _normalize_nutrition_section — retete, recomandate,<br/>nerecomandate, interzise, alte → prefixe [RETETA], [RECOMANDAT] ...
        else listă
            AI->>AI: păstrează item-urile cu "text" string,<br/>evidence_ids filtrate la string-uri
        end
    end
    AI->>LG: ai_report_sections_completed (număr item-uri per secțiune)
    AI-->>H: sections
```

## 2.4 Crearea PDF-ului și livrarea

```mermaid
sequenceDiagram
    autonumber
    participant H as on_report
    participant P as create_pdf
    participant RL as ReportLab<br/>NatureReportDocTemplate
    participant SS as SessionData
    participant G as send_report
    participant OA as Google OAuth2<br/>oauth2.googleapis.com/token
    participant GA as Gmail API<br/>messages/send
    participant BR as Browser

    H->>P: create_pdf(profile, sections, evidence)
    P->>P: _register_fonts — Arial (Windows) / Liberation Sans (Docker)
    P->>P: stiluri paragraf (copertă, secțiuni, bibliografie)
    P->>P: report_title(profile) + CoverPanel (avertisment informativ-adjuvant)
    P->>P: sort_sections_by_source_count
    P->>P: build_reference_index — sursă → număr bibliografic
    loop pentru fiecare secțiune (uz_intern, nutritie, uz_extern, alte_recomandari, atentionari)
        alt secțiune goală
            P->>P: text "Nu au fost identificate informații suficient de relevante..."
        else nutritie
            P->>P: nutrition_display_groups — rețete, recomandate, nerecomandate ...
        end
        P->>P: item + ancoră + chip "→ Surse [n]" legat de bibliografie
        P->>P: RoundedSection (se poate împărți pe mai multe pagini)
    end
    P->>P: secțiunea Bibliografie grupată pe documente
    P->>RL: doc.build(story, onFirstPage, onLaterPages) în BytesIO
    RL->>RL: afterFlowable — bookmark-uri / outline
    RL-->>P: PDF
    P-->>H: bytes
    H->>SS: report_bytes, report_id

    H->>G: send_report(problemă, PDF, nume fișier)
    G->>G: load_mail_config() din .env
    alt configurație incompletă
        G-->>H: email_skipped
    else configurat
        G->>G: build_report_message (To = REPORT_RECIPIENT, atașament PDF)
        G->>OA: POST grant_type = refresh_token (timeout 20 s)
        OA-->>G: access_token
        G->>GA: POST {raw: base64url(MIME)} cu Bearer token
        GA-->>G: 200
        G-->>H: email_sent
    end

    H-->>BR: panou "Raportul complet este gata" + link download
    BR->>H: GET /api/reports/{tab_id}/{report_id}
    H->>SS: verifică cookie + tab + report_id
    H-->>BR: PDF (no-store, attachment, nume din titlul raportului)
```

## Observații de arhitectură

Punctele sunt ordonate după impact.

1. **Emailul trimite datele de sănătate ale fiecărui utilizator la o adresă fixă.** `REPORT_RECIPIENT` este hard-codat, iar utilizatorul nu primește raportul pe email și nu este informat că problema lui descrisă în subiect plus PDF-ul pleacă în altă căsuță. Pentru date medicale, asta cere cel puțin informare și consimțământ explicit (GDPR, art. 9). Tehnic, adresa trebuie mutată în configurație și operațiunea făcută opțională.
2. **`LOG_FRAGMENT_TEXT=true` este valoarea implicită.** La fiecare raport se loghează până la 2000 de fragmente întregi, la care se adaugă profilul utilizatorului în requestul AI. Logurile devin o copie a conversațiilor medicale. Valoarea implicită sigură este `false`, iar activarea să se facă explicit, doar pentru diagnostic.
3. **Trasabilitatea nu este impusă de cod.** `generate()` păstrează item-urile cu `evidence_ids` goale sau inexistente, iar PDF-ul le afișează fără sursă. Promptul cere dovezi, dar modelul nu e obligat. Recomandarea: item-urile din `uz_intern`, `uz_extern`, `alte_recomandari` și `atentionari` fără cel puțin un ID valid din `evidence` se elimină sau se marchează vizibil. Rețetele sunt singura excepție documentată în prompt.
4. **Retrieval-ul repetă I/O la fiecare interogare.** `rank()` citește `manifest.json`, redeschide `embeddings.npy` și deschide o conexiune SQLite nouă pentru fiecare dintre cele 2 × N interogări. În plus, `_topic_coverage_chunks` scanează în Python toată tabela `chunks` la fiecare raport. Soluții: un obiect `HybridIndex` încărcat o singură dată la startup (matrice în memorie, conexiune read-only reutilizată) și o interogare FTS5 pe frază (`"frază exactă"`) în locul scanării.
5. **Etapele lente rulează sincron, cu `queue=False` și sub lock.** Retrieval + un request xAI care poate dura zeci de secunde (timeout 75 s) ocupă un thread din pool pe toată durata. Nu există limitare a rapoartelor concurente, nici retry pentru 429/5xx. Pentru producție: coadă Gradio cu `concurrency_limit`, retry cu backoff exponențial pe erorile tranzitorii și un timeout total separat de cel de citire.
6. **Contextul trimis la AI poate fi foarte mare.** 2000 de fragmente × 3000 de caractere = până la 6 milioane de caractere înainte de compactare, apoi tăiate la 2,4 milioane (circa 600 000 de tokeni după estimarea din cod, `chars / 4`). Compactarea taie uniform din fiecare fragment, deci și din fragmentele de prioritate maximă (fraza exactă, documentul dedicat). Mai sigur: buget pe tokeni real și eliminarea fragmentelor de la coada priorităților în loc de trunchierea tuturor.
7. **Sesiunile și PDF-urile stau în memoria procesului.** Soluția e simplă și corectă pentru o singură instanță. Rezultatul: nu se poate scala orizontal și orice restart pierde conversațiile, lucru deja documentat în README.
