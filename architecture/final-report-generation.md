# Fluxul de generare a raportului final

**Intrare:** descrierea problemei de sănătate furnizată de utilizator și indexul hibrid local.

**Ieșire:** recomandările afișate în chat și un raport PDF descărcabil, cu livrare opțională prin e-mail.

## 1. Preluarea descrierii problemei de sănătate — `on_message()`

- **1.1.** Identifică sesiunea tabului curent folosind cookie-ul de sesiune și identificatorul de sesiune Gradio.
- **1.2.** Elimină spațiile inutile din mesajul trimis.
- **1.3.** Ignoră mesajul dacă este gol.
- **1.4.** Respinge mesajul dacă depășește lungimea maximă configurată.
- **1.5.** Obține blocarea exclusivă a sesiunii.
- **1.6.** Adaugă mesajul utilizatorului în istoricul conversației.
- **1.7.** Elimină din sesiune orice raport generat anterior.
- **1.8.** Înlocuiește problema de sănătate curentă din profilul utilizatorului cu noul mesaj.
- **1.9.** Setează `auto_report_pending=True`.
- **1.10.** Adaugă în chat mesajul de stare „Se pregătesc recomandările”.
- **1.11.** Returnează către browser istoricul actualizat al conversației.

## 2. Declanșarea generării raportului — `on_auto_report()` și `on_report()`

- **2.1.** Gradio apelează `on_auto_report()` după finalizarea handlerului care procesează mesajul.
- **2.2.** Identifică din nou sesiunea curentă.
- **2.3.** Obține blocarea exclusivă a sesiunii.
- **2.4.** Se oprește dacă nu există un raport automat în așteptare.
- **2.5.** Setează `auto_report_pending=False`, astfel încât aceeași trimitere să fie procesată o singură dată.
- **2.6.** Apelează `on_report()`.
- **2.7.** Verifică dacă profilul conține o problemă de sănătate.
- **2.8.** Se oprește cu un mesaj pentru utilizator dacă profilul nu este pregătit pentru generarea raportului.

## 3. Construirea setului de interogări — `Retriever.collect()`

- **3.1.** Generează interogări de consultare din profilul medical curent.
- **3.2.** Oprește căutarea dacă nu poate fi generată nicio interogare utilizabilă.
- **3.3.** Extrage cuvintele relevante din textul complet al problemei de sănătate.
- **3.4.** Adaugă textul exact al problemei de sănătate ca interogare prioritară.
- **3.5.** Adaugă o interogare formată din cuvintele relevante ale subiectului.
- **3.6.** Adaugă celelalte interogări de consultare derivate din profil.
- **3.7.** Creează variante de siguranță prin adăugarea termenilor despre contraindicații, interacțiuni și atenționări la fiecare interogare de bază.

## 4. Rularea retrieval-ului hibrid pentru fiecare interogare — `search.rank()`

- **4.1.** Citește modelul de embedding și dimensiunea vectorilor din `data/hybrid_index/manifest.json`.
- **4.2.** Încarcă prin mapare în memorie `data/hybrid_index/embeddings.npy`.
- **4.3.** Generează vectorul E5 al interogării folosind prefixul `query: `.
- **4.4.** Normalizează vectorul interogării.
- **4.5.** Calculează similaritatea semantică față de toți vectorii documentelor.
- **4.6.** Păstrează numărul configurat de candidați semantici cu cele mai bune scoruri.
- **4.7.** Convertește interogarea într-o expresie SQLite FTS5.
- **4.8.** Preia candidații lexicali din `index.sqlite3`, ordonați prin BM25.
- **4.9.** Combină clasamentele semantic și lexical prin Reciprocal Rank Fusion, folosind `k=60`.
- **4.10.** Păstrează numărul configurat de rezultate hibride cu cele mai bune scoruri.
- **4.11.** Încarcă din SQLite textul fragmentului, calea sursei, titlul și intervalul de linii.
- **4.12.** Returnează scorul hibrid, similaritatea semantică, poziția lexicală și metadatele de trasabilitate.

## 5. Filtrarea, prioritizarea și asamblarea dovezilor — `Retriever.collect()`

- **5.1.** Pentru fiecare interogare, păstrează rezultatele care au o poziție lexicală și conțin un cuvânt relevant din interogare.
- **5.2.** Păstrează rezultatele din documentele de siguranță chiar dacă nu îndeplinesc condiția lexicală obișnuită.
- **5.3.** Găsește fragmente suplimentare care tratează direct întreaga problemă de sănătate.
- **5.4.** Găsește fragmente din documente dedicate cuvintelor-cheie detectate.
- **5.5.** Adaugă mai întâi la dovezi fragmentele care corespund exact subiectului.
- **5.6.** Adaugă apoi fragmentele din documentele dedicate.
- **5.7.** Adaugă celelalte rezultate acceptate prin alternare între loturile de interogări.
- **5.8.** Deduplică fragmentele după identificatorul de dovadă `C<chunk_id>`.
- **5.9.** Se oprește după atingerea numărului maxim configurat de dovezi.
- **5.10.** Extinde fiecare fragment cu titlul semantic și contextul apropiat din sursă.
- **5.11.** Limitează textul fiecărei dovezi la dimensiunea configurată pentru context.
- **5.12.** Stochează fiecare dovadă sub forma unui ID, a unei căi-sursă cu interval de linii și a textului.
- **5.13.** Returnează inventarul ordonat al dovezilor către `on_report()`.
- **5.14.** Oprește generarea raportului cu un mesaj pentru utilizator dacă nu este găsită nicio dovadă.

## 6. Pregătirea payloadului cu dovezi — `XAIClient.generate()`

- **6.1.** Înregistrează în log numărul total al dovezilor și numărul total de caractere.
- **6.2.** Convertește dicționarul de dovezi în înregistrări ordonate care conțin `id`, `source` și `text`.
- **6.3.** Serializează înregistrările pentru a estima dimensiunea contextului cererii.
- **6.4.** Păstrează fiecare dovadă neschimbată dacă textul serializat are cel mult 2.400.000 de caractere.
- **6.5.** Dacă limita este depășită, înregistrează în log inventarul complet de dinaintea compactării.
- **6.6.** Calculează bugetul de text rămas după includerea metadatelor JSON.
- **6.7.** Reduce proporțional textele fragmentelor, păstrând inițial cel puțin 256 de caractere pentru fiecare înregistrare.
- **6.8.** Continuă să reducă uniform înregistrările lungi până când dovezile serializate respectă limita strictă.
- **6.9.** Păstrează ID-ul și sursa fiecărei dovezi în timpul compactării.
- **6.10.** Înregistrează în log inventarul exact trimis către AI și numărul de caractere eliminate din fiecare fragment.
- **6.11.** Construiește promptul utilizatorului din profilul medical și toate dovezile acceptate.
- **6.12.** Încarcă promptul de sistem pentru generarea raportului din `ai/prompts/generate_report_system.md`.

## 7. Solicitarea raportului structurat de la xAI

- **7.1.** Citește `GROK_API_KEY_MED` din configurația aplicației.
- **7.2.** Se oprește cu `AIUnavailable` dacă lipsește cheia API.
- **7.3.** Creează o singură cerere către xAI Responses API.
- **7.4.** Folosește modelul xAI și nivelul de reasoning configurate.
- **7.5.** Trimite promptul de sistem și payloadul utilizatorului ca mesaje de intrare separate.
- **7.6.** Solicită un răspuns de tip obiect JSON.
- **7.7.** Setează `max_output_tokens=20000`.
- **7.8.** Setează `store=false`.
- **7.9.** Trimite cererea către endpointul `/responses` configurat.
- **7.10.** Înregistrează în log statusul HTTP, durata, dimensiunea răspunsului și ID-ul cererii.
- **7.11.** Convertește erorile HTTP sau de conexiune într-o eroare `AIUnavailable` afișabilă utilizatorului.

## 8. Parsarea și normalizarea răspunsului AI

- **8.1.** Parsează răspunsul HTTP ca JSON.
- **8.2.** Verifică dacă starea răspunsului xAI este `completed`.
- **8.3.** Extrage fiecare bloc `output_text` din mesajele de ieșire.
- **8.4.** Concatenează blocurile de text extrase.
- **8.5.** Parsează conținutul rezultat ca obiect JSON.
- **8.6.** Respinge un răspuns gol, incomplet sau care nu este un obiect.
- **8.7.** Inițializează cele cinci secțiuni ale raportului:
  - **8.7.1.** `uz_intern` — uz intern.
  - **8.7.2.** `nutritie` — nutriție.
  - **8.7.3.** `uz_extern` — uz extern.
  - **8.7.4.** `alte_recomandari` — alte recomandări.
  - **8.7.5.** `atentionari` — atenționări.
- **8.8.** Normalizează nutriția în rețete și alimente recomandate, nerecomandate, interzise sau din alte categorii.
- **8.9.** Normalizează textul recomandărilor, păstrând întreruperile de linie relevante.
- **8.10.** Păstrează numai ID-urile de dovezi de tip șir atașate fiecărei recomandări.
- **8.11.** Returnează dicționarul normalizat al secțiunilor către `on_report()`.

## 9. Generarea PDF-ului — `create_pdf()`

- **9.1.** Înregistrează fonturile disponibile pentru raport.
- **9.2.** Construiește titlul raportului și panoul informativ de început.
- **9.3.** Sortează secțiunile de recomandări folosind acoperirea surselor.
- **9.4.** Construiește un index stabil al numerelor surselor din ID-urile dovezilor asociate recomandărilor.
- **9.5.** Redă cele cinci secțiuni de recomandări în ordinea configurată.
- **9.6.** Afișează un mesaj explicit că nu există informații suficient de relevante pentru o secțiune goală.
- **9.7.** Redă secțiunea de nutriție folosind formatul dedicat rețetelor și categoriilor alimentare.
- **9.8.** Adaugă legături inline către surse pentru recomandările care au ID-uri de dovezi valide.
- **9.9.** Construiește bibliografia din căile surselor citate și intervalele de linii.
- **9.10.** Adaugă legături de la recomandări la intrările bibliografice și legături de întoarcere de la bibliografie.
- **9.11.** Adaugă notificarea privind caracterul informativ medical și stilizarea vizuală configurată.
- **9.12.** Construiește documentul în memorie folosind ReportLab.
- **9.13.** Returnează PDF-ul final sub formă de octeți.

## 10. Stocarea raportului în sesiunea curentă

- **10.1.** Stochează octeții PDF în `session.report_bytes`.
- **10.2.** Generează un `report_id` aleatoriu și sigur criptografic.
- **10.3.** Asociază ID-ul raportului cu sesiunea tabului curent.
- **10.4.** Păstrează raportul în memoria procesului până când sesiunea este eliminată, expiră sau aplicația este repornită.

## 11. Încercarea de livrare prin e-mail — `send_report()`

- **11.1.** Încarcă configurația Gmail OAuth.
- **11.2.** Returnează `email_skipped` dacă livrarea prin e-mail nu este configurată.
- **11.3.** Construiește mesajul e-mail și atașează PDF-ul generat.
- **11.4.** Reînnoiește tokenul de acces Google OAuth.
- **11.5.** Trimite mesajul prin Gmail API.
- **11.6.** Returnează `email_sent` după livrarea reușită.
- **11.7.** Înregistrează în log o eroare de e-mail fără a șterge PDF-ul deja generat.
- **11.8.** Continuă fluxul raportului chiar dacă livrarea prin e-mail eșuează.

## 12. Afișarea și descărcarea rezultatului

- **12.1.** Convertește secțiunile normalizate ale raportului într-un text de recomandări potrivit pentru chat.
- **12.2.** Adaugă textul recomandărilor în istoricul conversației asistentului.
- **12.3.** Construiește un URL de descărcare care conține `tab_id` și `report_id` curente.
- **12.4.** Returnează către browser istoricul actualizat al conversației și controlul de descărcare.
- **12.5.** Când utilizatorul solicită PDF-ul, identifică sesiunea folosind cookie-ul browserului.
- **12.6.** Verifică dacă ID-urile tabului și raportului solicitate aparțin sesiunii respective.
- **12.7.** Returnează HTTP 404 dacă raportul nu aparține sesiunii curente sau nu mai este disponibil.
- **12.8.** Returnează PDF-ul ca atașament cu `Cache-Control: no-store` dacă validarea reușește.

## 13. Tratarea erorilor de generare a raportului

- **13.1.** Afișează un mesaj specific dacă lipsește problema de sănătate.
- **13.2.** Afișează un mesaj specific dacă retrieval-ul local nu găsește dovezi.
- **13.3.** Afișează mesajul `AIUnavailable` dacă serviciul AI sau răspunsul acestuia nu este disponibil.
- **13.4.** Înregistrează în log tipul excepției, mesajul și traceback-ul pentru erorile neașteptate.
- **13.5.** Afișează un mesaj generic de eroare la generarea raportului pentru situațiile neașteptate.
- **13.6.** Tratează livrarea prin e-mail ca operație best-effort, astfel încât o eroare de e-mail să nu invalideze raportul.

## Rezultatul final

```text
Mesajul utilizatorului
    -> profilul sesiunii
    -> retrieval hibrid local
    -> inventarul prioritizat al dovezilor
    -> o singură cerere structurată către xAI
    -> secțiuni normalizate de recomandări
    -> raport PDF în memorie
    -> răspuns în chat și link securizat de descărcare
    -> livrare opțională prin Gmail
```

Acest document completează diagrama tehnică detaliată din `02-generare-raport-final.md` și explică fluxul fără sintaxă Mermaid sau complexitatea unei diagrame de secvență.
