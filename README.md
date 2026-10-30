<div align="center">

# 🌿 Remedii Naturiste Adjuvante - de la Dr. Cuișor

### Asistent AI de medicină naturistă bazat pe surse locale

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![Hybrid retrieval](https://img.shields.io/badge/Retrieval-pgvector%20%2B%20tsvector-6A5ACD)](#-cum-funcționează)
[![License](https://img.shields.io/badge/License-Business%20Source%201.1-D22128)](LICENSE)

🟢 **surse locale** · 🔵 **căutare semantică** · 🟠 **căutare lexicală** · 🟣 **raport PDF**

</div>

> [!IMPORTANT]
> Aplicația oferă informații orientative și recomandări adjuvante. Nu înlocuiește diagnosticul, consultația, tratamentul prescris sau îngrijirea medicală de urgență.
> Conversațiile și rapoartele sunt păstrate temporar în memoria procesului. Descrierea problemei și fragmentele selectate pot fi trimise furnizorului AI configurat; identificarea afecțiunii poate folosi separat un serviciu extern. Nu introduceți nume, CNP, adrese sau alte date de identificare în chat.

## ✨ Despre proiect

Proiectul transformă o colecție locală de documente Markdown despre medicină naturistă și terapii complementare într-un index hibrid interogabil. Interfața web primește problema descrisă de utilizator și afișează fragmentele relevante găsite în arhiva locală. După verificarea fragmentelor, administratorul autorizat prin `/owner` alege modelul pentru fiecare raport, inclusiv modelele Ollama locale. Aplicația trimite dovezile către furnizorul ales pentru redactarea răspunsului structurat și generează un raport PDF cu trimiteri la surse. Generarea este rezervată administratorului pentru toate modelele.

| 🧩 Componentă | Rol |
|---|---|
| **Index semantic** | Identifică fragmente apropiate ca sens cu vectori Qwen3-Embedding de 1024 de dimensiuni, stocați în Postgres (`pgvector`). |
| **Index lexical** | Găsește expresii cu termenii în aceeași ordine, prin `tsvector` în Postgres; folosește prefixe pentru flexiuni și sinonime când expresia întreagă este o afecțiune recunoscută. |
| **Scor combinat** | Fiecare fragment primește un singur scor, din semnalele pe care pacientul le bifează în „Surse și opțiuni de căutare” (afecțiuni, lexical, semantic). Cu toate trei: `4·P1 + 2·P2 + L + V` (afecțiune în titlu › afecțiune în text › potrivire lexicală › potrivire semantică), calculat într-o singură interogare SQL. |
| **Fragmentare pe afecțiuni** | Împarte documentele în fragmente R1 (afecțiunea în titlul capitolului), R2 (afecțiunea în textul capitolului) și D1 (restul textului), folosind catalogul de afecțiuni și sinonime din PostgreSQL. |
| **Filtrare pe surse** | În același panou „Surse și opțiuni de căutare”, căutarea poate fi restrânsă la anumite foldere din `medicina-naturista-documente/data/documents/` (categoria unui document este folderul lui). |
| **Retriever medical** | Ordonează fragmentele după scorul combinat și păstrează, întregi, cele care încap în bugetul de context al furnizorului AI. În „Opțiuni de generare”, „Scor minim” (procent de relevanță) limitează fragmentele trimise către AI. |
| **Chat web** | Oferă sesiuni izolate pe tab și afișează recomandările structurate. |
| **Raport PDF** | Include recomandări, atenționări, citări și bibliografie navigabilă. |
| **Livrare e-mail** | După generare, poate trimite raportul prin Gmail API cu OAuth2 la adresa scrisă de utilizator în chat, dacă este configurat. |

Interfața folosește o coloană fluidă de maximum 640 px, un antet crem cu titlu lizibil,
portretul lui Dr. Cuișor și decor botanic discret. Pe mobil, portretul apare sub descriere.
Identitatea de asistent virtual AI și atenționarea medicală rămân vizibile. Același portret
este folosit în antet, avatarele conversației, pictograma aplicației și rapoartele PDF noi.

## 🎨 Cum funcționează

Fiecare mesaj trece prin **Clasificare mesaj**, cu scurtături deterministe pentru cererile explicite și Ollama local `gemma3:1b` (`MEDICAL_CONDITION_AI_LOCAL_MODEL`) când este necesar. `POST /api/messages` afișează rapid mesajul și salvează contextul, apoi `POST /api/classify` selectează:

- **Remedii:** rezolvarea afecțiunilor și căutarea existentă, cu identificare AI opțională.
- **Planta/produsul:** numele/aliasul este rezolvat în catalog, apoi răspunsul arată
  numele și denumirea latină disponibilă în antet, cu două liste distincte dedesubt.
  Numărul afecțiunilor apare în titlul secțiunii, fără repetare în antet.
  Titlurile secțiunilor și intrările topurilor folosesc același acord după
  denumirea românească: masculin → „util/interzis”, feminin sau neutru → „utilă/interzisă”,
  plural → „utile/interzise” și „sunt”. Determinarea folosește dicționarul românesc local,
  primul substantiv al denumirii și reguli pentru forme ambigue sau neregulate; „gutui”
  și „pătlăgele” sunt tratate ca plural. Pentru cuvinte nelistate se
  folosesc terminațiile; denumirile neobișnuite pot necesita reguli lexicale suplimentare.
  Nu sunt necesare cereri AI, migrare sau reindexare. Mesajele structurate noi includ
  `herbAgreement`, folosit de frontend; mesajele vechi fără câmp păstrează forma feminină.
  Numărul M al interdicțiilor apare numai în titlul secțiunii dedicate. Utilizările
  citesc aceleași perechi `positive` și aceeași rulare publicată ca topurile; numărul N
  coincide cu rankingul produsului. Interdicțiile citesc perechile `herb_caution_pairs`
  cu dovezi explicite `prohibition`, din rularea caution legată de acea rulare pozitivă;
  M coincide cu `herb_caution_rankings.prohibition_ranking`. Precauțiile sunt păstrate
  separat și nu sunt numărate ca interdicții. Interdicțiile cer o formulare explicită în
  text despre produsul și afecțiunea respectivă; eticheta AI sau istorică `caution` nu este
  suficientă. Recomandările singure nu apar în lista interdicțiilor. Clasificarea surselor
  nu reprezintă validare clinică. O rulare pozitivă lipsă/incompatibilă produce aceeași eroare
  ca topurile, fără revenire la coaparițiile istorice. Lipsa părții caution este afișată ca
  indisponibilitate, iar informația istorică nerecuperabilă este marcată explicit ca parțială.
  Pentru orice intrare din `herbs`, fiecare secțiune are numărul afecțiunilor în titlu.
  Poza produsului este încărcată local prin `GET /api/herb-images/{herb_id}`, după ID-ul
  din catalog. Căutarea încearcă numele latin, apoi numele românesc, în `HERB_IMAGES_DIR`
  (implicit `medicina-naturista-documente/data/images`), numai fișiere PNG. Ignoră
  majusculele/minusculele și aplică înlocuirea caracterelor nepermise din procesul de
  generare; potrivirile ambigue sunt omise. Folderul este montat read-only în Docker
  și exclus din imaginea de container. Endpointul nu expune registrul ori alte fișiere.
  După încărcarea cu succes, poza apare în stânga (maximum 280 × 280 px, fără decupare),
  iar listele scurte rămân în două coloane în dreapta. Când textul depășește spațiul
  de lângă imagine, lista afecțiunilor utile curge pe trei coloane: prima începe sub poză,
  celelalte două în dreapta ei și continuă aliniate până jos. Listele lungi folosesc
  astfel și spațiul de sub imagine. Ordinea alfabetică se citește de sus în jos
  în fiecare coloană, apoi în coloana următoare. Titlul și sursele rămân pe toată
  lățimea; interdicțiile și atenționările nu sunt rearanjate. Până la încărcare sau
  dacă poza lipsește/eșuează, rămâne afișarea existentă cu trei coloane pe desktop.
  La maximum 640 px poza apare deasupra listei cu două coloane; la maximum 420 px lista
  are o coloană. Lipsa produsului, folderului sau pozei produce `404`, fără placeholder.
  Imaginile noi sunt găsite la următoarea cerere, fără reindexare sau apeluri AI.
  Un click pe poză deschide imaginea într-un panou modal cât pagina, deasupra
  interfeței, cu proporțiile păstrate și fără decupare. Escape sau butonul X din
  partea de sus închid panoul și readuc focusul la poză. Imaginea se poate deschide
  și din tastatură, cu Enter/Space; pagina din spate rămâne inactivă cât panoul este deschis.
  Numele produsului are 24 px, iar titlurile secțiunilor au 20 px; întregul text din secțiunea interdicțiilor, inclusiv
  sursele, este portocaliu. Cele trei secțiuni sunt separate prin linii de 3 px;
  panourile surselor nu au borduri exterioare. Fiecare panou „Vezi fragmente sursă — N fragmente din M documente”
  este închis inițial. La deschidere se
  încarcă 20 de fragmente integrale, cu filtru după afecțiune și „Încarcă mai multe”.
  Filtrele și paginarea sunt independente. Secțiunile goale păstrează panoul cu zero surse,
  fără cereri HTTP. Fiecare fragment apare o singură dată în secțiunea sa, cu toate
  afecțiunile eligibile, titlul, documentul și liniile sursă. Produsul/aliasurile sunt
  evidențiate cu verde; afecțiunile și sinonimele lor, cu galben. Textul original este păstrat.
  `GET /api/herb-evidence/{groupId}?evidenceKind=positive|contraindication&conditionId=…&offset=…`
  selectează sursele secțiunii cerute (`positive` implicit) și este limitat la sesiunea
  și tabul care dețin mesajul. Filtrul trebuie să aparțină secțiunii. Nu apelează AI și
  nu execută o nouă căutare hibridă.
  Schimbarea rulării produce `HERB_EVIDENCE_STALE`; un răspuns expirat/evacuat produce
  `HERB_EVIDENCE_UNAVAILABLE`. Interfața cere repetarea întrebării, fără combinarea
  generațiilor. Fragmentele încărcate sunt păstrate numai temporar în interfață.

  Migrarea aditivă `028_herb_caution_rankings.sql` creează `herb_caution_runs`,
  `herb_caution_evidence`, `herb_caution_pairs`, `herb_caution_rankings` și
  `herb_caution_cache`. Proiecția caution reutilizează regulile locale și valorile
  `recommendation`/`prohibition` din răspunsurile pe care clasificarea pozitivă le cere deja.
  Proiecția caution nu adaugă cereri AI și păstrează regulile clasificării. Informațiile
  lipsă din cache-ul caution vechi sunt recuperate numai local sau marcate `unknown`.
  Secțiunea de atenționări despre produs folosește separat mecanismul descris mai jos.
  Proiecția caution versiunea 2 verifică și listele explicite de alimente de evitat,
  inclusiv rândurile OCR întrerupte. Un avertisment despre alt produs sau procedură din
  același fragment nu validează o interdicție pentru produsul întrebat.
  Pregătirea pozitivă pregătește și caution; publicarea prin CLI activează atomic cele două
  rulări compatibile. Marcajul activ caution rămâne în `herb_caution_runs.is_active`,
  în afara metadatelor care intră în amprenta indexului pozitiv.

  După aplicarea explicită a migrărilor de către operator, popularea pentru clasamentul
  pozitiv deja activ se poate face separat, fără inferență sau reindexare:

  ```powershell
  $env:PYTHONPATH = 'src'
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-caution-ranking
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-caution-ranking RUN_ID
  ```

  Prima comandă returnează ID-ul noii rulări caution și numărul dovezilor istorice necunoscute.
  A doua acceptă acel ID numai dacă indexul, rularea pozitivă și activarea observată la
  pregătire sunt încă compatibile. Ambele raportează `ai_requests_sent_total=0` și nu
  apelează nici providerul, nici endpointul de verificare a modelului. Aplicarea migrării
  singure nu populează și nu activează aceste date. Aplicația nu migrează la startup.

  La actualizarea de la proiecția caution 1 la 2, se pregătește și se publică numai o
  rulare caution nouă prin comenzile de mai sus, folosind codul actualizat. Nu se șterg
  cache-urile sau tabelele și nu se reindexează documentele/embeddingurile. O rulare
  caution cu versiunea veche este afișată ca învechită până la publicarea celei noi.

  **Atenționări și interacțiuni:** secțiunea folosește exclusiv cunoștințele modelului
  local Ollama despre fiecare produs din `herbs`, indiferent de categorie și de existența
  unor documente sau asocieri produs–afecțiune. La reindexare se trimite o singură cerere
  pentru fiecare produs fără rezultat compatibil în cache. Cererea conține numai
  identitatea produsului: ID, denumirea română, denumirea latină când există, denumirile
  englezești, categoria, familia și aliasurile. Nu conține fragmente, afecțiuni ori citate.
  Specia latină trebuie respectată; o specie lipsă nu este inventată.

  Răspunsul este JSON strict cu `herb_id`, `status=complete|uncertain` și `messages`.
  Fiecare element are exact `message_type=warning|contraindication|interaction` și
  `problem`. Mesajele sunt în română, preferabil 10–25 de cuvinte, maximum 240 de
  caractere și 40 de cuvinte, fără tăiere automată. Interacțiunile iau în considerare
  medicamente, clase medicamentoase, suplimente, alte produse naturiste, fructe,
  legume, alimente și băuturi. Identitatea incertă ori cunoștințele insuficiente sunt
  marcate `uncertain`; o listă goală nu confirmă absența riscurilor.

  Migrarea aditivă `031_herb_product_safety_knowledge.sql` creează tabela
  `herb_safety_messages`: `herb_id`, `message_type`, `problem`, plus `run_id` și
  `message_id` pentru publicare și deduplicare. Un produs are mai multe rânduri.
  `herb_product_safety_results` păstrează explicit și produsele cu listă goală,
  `herb_product_safety_cache` păstrează răspunsurile validate, iar
  `herb_product_safety_runs` gestionează pregătirea și activarea atomică.
  Pentru mesajele curente, `herb_safety_messages` se filtrează prin generația cu
  `herb_product_safety_runs.is_active=true`; celelalte generații rămân istorice.
  Tabelele și algoritmul istoric `herb_safety_*` bazat pe fragmente nu mai alimentează
  secțiunea; datele istorice sunt păstrate. Migrarea se aplică prin comanda normală
  de indexare sau prin operatorul de migrări, niciodată la pornirea aplicației.

  Cheia cache-ului depinde de identitatea și aliasurile acelui produs, prompt,
  versiunea regulilor JSON, model și digestul său. Modificarea altui produs, a
  documentelor ori a afecțiunilor nu invalidează răspunsurile produselor neschimbate.
  Sunt reutilizate și rezultatele valide goale sau incerte. Rezultatul fiecărui produs
  se salvează imediat; un eșec nu pierde produsele deja procesate. Rularea normală
  fără parametri creează o generație nouă și reutilizează cache-ul compatibil.
  O schimbare de produs, prompt ori model cere un răspuns nou pentru produsul afectat.
  Cache-ul vechi de extragere din documente nu poate substitui această analiză.

  Nu se mai adaugă warnings la cererile produs–afecțiune și nu se mai planifică cereri
  pe produs/fragment. Lista existentă **Afecțiuni în care este interzisă** rămâne din
  `herb_caution_*`, cu aceleași surse și reguli; noua secțiune afișează separat
  Atenționări, Contraindicații și Interacțiuni din cunoștințele modelului. Interfața
  indică această proveniență și nu afișează citate sau „Vezi sursa” pentru ele.
  Întreaga secțiune de atenționări este roșie, cu titlul principal de 20 px. Nota
  de proveniență ocupă lățimea ambelor coloane și are aceeași dimensiune ca mesajele
  despre date parțiale. Fiecare
  problemă începe cu numele categoriei scris cu bold, urmat de punct: „Atenționări. …”,
  „Contraindicații. …” sau „Interacțiuni. …”; nu există subtitluri separate.
  Întregul conținut al secțiunii este împărțit pe două coloane. Pe ecrane de maximum 580 px se folosește
  o singură coloană. Nu se afișează contorul „Afișate N din M atenționări”; încărcarea
  următoarelor mesaje rămâne disponibilă când există pagini suplimentare.
  JSON valid și identitatea corectă nu reprezintă validare clinică.

  `GET /api/herb-safety/{groupId}` citește numai generația publicată, în pagini de 20.
  Referințele rămân legate de mesaj, sesiune și tab; o generație sau un catalog schimbat
  produce `HERB_SAFETY_STALE`. Nu există inferență în chat. Ruta veche de evidence nu
  inventează surse pentru răspunsurile modelului și răspunde indisponibil.

  Prima populare cere câte un request pentru fiecare produs din catalog; următoarele
  reindexări cer numai produsele fără cache compatibil. Pregătirea pozitivă normală
  pregătește și această generație, iar publicarea o activează după verificări.
  `--skip-positive-ranking` păstrează comportamentul de a omite și etapa AI safety.
  Se poate pregăti/publica și separat, după aplicarea migrării 031:

  ```powershell
  $env:PYTHONPATH = 'src'
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --analyze-safety-warnings
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-safety-warnings
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-safety-warnings --resume-safety-warnings RUN_ID
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-safety-warnings RUN_ID
  ```

  Analiza nu face inferență; publicarea verifică numai baza și digestul modelului.
  `RUN_ID` trebuie să aparțină noului algoritm; rulările istorice pe fragmente nu sunt
  compatibile. La întrerupere se așteaptă revenirea promptului înainte de relansare.
  Produsul în curs fără rezultat valid poate fi retrimis; nu există retry automat.
  Digestul modelului se verifică și înaintea salvării fiecărui răspuns; aceste citiri
  de metadate Ollama nu execută inferență și nu adaugă cereri AI pentru produs.
  Un răspuns invalid oprește pregătirea și păstrează generația publicată anterior.
  Mesajele nu sunt reparate euristic, scurtate sau înlocuite cu rezultate goale.

  Progresul folosește `progress_stage=product_safety`, `safety_products_total`,
  `safety_products_completed`, `safety_cache_hits`, `product_safety_ai_requests`,
  `safety_batches` și `safety_batches_completed`; un lot este acum un singur produs.
  `warnings_only_ai_requests` este păstrat ca alias de compatibilitate al numărului
  cererilor noi safety. ETA se măsoară după primul produs AI validat și salvat;
  rămâne `null` înainte de prima măsurătoare și este zero la `ready`/`published`.
  Metricele cererii includ `herb_id`, `safety_source=model_knowledge`, timpi/tokeni,
  contextul, outputul și timeoutul. Nu includ denumiri, probleme sau text generat.

  Parametrii safety impliciți sunt `HERB_SAFETY_AI_MAX_REQUESTS=10000`,
  `HERB_SAFETY_BUILD_TIMEOUT_SECONDS=86400`, `HERB_SAFETY_AI_CONTEXT_TOKENS=65536`
  și `HERB_SAFETY_AI_MAX_OUTPUT_TOKENS=25000`. Bugetele de cereri și timp au crescut
  deoarece limita se aplică acum produselor, nu loturilor de fragmente. Bugetul
  comenzii combinate acoperă timpul pentru asocieri plus timpul safety; safety are și
  propriul deadline. Timeoutul per request rămâne 900 secunde, `think=false`,
  temperatură zero și streaming local, fără cloud ori cereri AI de reparare.

  Potrivirea numelor românești acceptă flexiuni din dicționarul Hunspell inclus (articol, plural, genitiv), cu sau fără diacritice, inclusiv în denumiri din mai multe cuvinte. Regulile generale pentru intrările incomplete sunt validate cu același dicționar, fără liste de excepții pe plante. Forma exactă are prioritate; numele comune mai multor specii cer alegerea speciei.
- **Top plante/produse:** clasament pozitiv din `herb_positive_rankings`, filtrat exact după categoria cerută înainte de sortare și limitare. Interfața oferă exemplele „Top 100 produse naturiste” și „Top 10 produse naturiste pentru gripa”; un click completează câmpul și îi dă focus, apoi utilizatorul trimite mesajul. „Top X produse naturiste” fără afecțiune afișează cele 11 categorii, fiecare pe un rând numerotat; utilizatorul răspunde cu numărul categoriei și primește până la X produse din acea categorie. O alegere invalidă repetă lista fără a schimba X. Comenzile directe precum „Top 20 suplimente”, „Top 10 plante medicinale”, „Primele 20 vitamine” și „Top 100 semințe” rămân disponibile. „Top 100”, „Top 100 plante”, „top general” și „toate categoriile” includ toate categoriile. Fără cantitate se folosesc 100 de intrări; categoriile necunoscute sau multiple cer alegerea unei singure categorii, iar un număr invalid cere o cantitate între 1 și 10000. Clarificările păstrează categoria/numărul cerut. Răspunsul arată numărul efectiv returnat, asocierile și aliasurile regionale; fără căutare hibridă sau generare AI pentru comenzile explicite.
- **Top pentru o afecțiune:** „Top 10 produse naturiste pentru gripa” selectează direct, din toate categoriile, numai produsele cu pereche `positive` pentru afecțiunea din catalog. „Top 5 suplimente contra gripa” adaugă filtrul exact de categorie; „pentru”, „contra” și „împotriva” sunt echivalente. Eligibilitatea din `herb_positive_pairs` și rankingul din `herb_positive_rankings` folosesc aceeași rulare publicată compatibilă, într-o singură tranzacție. Ordinea este ranking global descrescător, apoi ID crescător, cu filtrele aplicate înainte de limita N. Rankingul rămâne numărul total de afecțiuni pozitive ale produsului; nu măsoară frecvența recomandărilor pentru gripa. Sinonimele și formele cu/fără diacritice se rezolvă local; o afecțiune necunoscută cere reformulare, iar denumirile ambigue, aproximările și cererile cu mai multe afecțiuni cer alegerea unei singure afecțiuni, păstrând N și categoria. Calificativele nerecunoscute nu sunt eliminate pentru a lărgi filtrul. Rezultatele pot fi mai puține decât N sau zero; indisponibilitatea rankingului produce eroarea existentă, fără revenire la asocierile istorice. Fluxul nu generează raport, PDF sau email și nu reprezintă validare clinică.
- **Diverse:** căutare după mesajul original, fără identificarea afecțiunii prin AI și fără notificările despre afecțiunea necunoscută. Generarea raportului naturist rămâne ca în fluxul de remedii.
- **Email raport:** adresă validată local și PDF-ul precedent din aceeași sesiune; fără căutare nouă. Mesajul poate fi o adresă singură sau o cerere precum „Trimite raportul la nume@example.com”.

Clasificarea trimite către Ollama local numai mesajul și context minimal de rutare, fără PDF sau corpus. Refolosește `CONDITION_AI_LOCAL_BASE` și `MEDICAL_CONDITION_AI_LOCAL_MODEL`, cu temperatura 0, fără cheie API și fără fallback Hugging Face. Schema JSON impune una dintre cele cinci intenții și câmpurile permise; validarea strictă se repetă în aplicație. Numele și aliasurile plantelor sunt recunoscute și în catalogul local, fără diferențe de diacritice sau cratime. Un nume explicit completează clarificarea. Dacă numele corespunde mai multor plante, aplicația afișează numele românești și latine și cere alegerea utilizatorului; aceasta selectează o singură specie și asocierile ei. Este independentă de `REPORT_GENERATION_MODELS`. La eșec se continuă cu fluxul existent, cu o notificare; cererile explicite de email cer clarificare, iar o adresă singură păstrează comanda deterministă existentă. Cererile neclare solicită planta sau destinatarul. Clasificarea și expedierea nu sunt reîncercate automat; identificatorul mesajului și revizia previn repetarea aceleiași expediții.

Diagrama actualizată: [chatbot-external-connections.xmind](architecture/chatbot-external-connections.xmind). Clasificarea și rutarea mesajelor (XMind 8): [message-classification-plan.xmind](architecture/message-classification-plan.xmind).

```text
📚 documente Markdown
        ↓
✂️ fragmente R1 / R2 / D1, cu afecțiuni, sursă și interval de linii
        ↓
🧠 embeddings Qwen3  +  🔎 tsvector, în Postgres/pgvector
        ↓
⚖️ scor combinat din semnalele alese (P1 › P2 › lexical › semantic) și bugetul de context
        ↓
👁️ utilizatorul verifică fragmentele găsite
        ↓
🤖 model ales: Ollama pentru toți utilizatorii / DeepSeek doar pentru admin
        ↓
💬 recomandări în chat  +  📄 raport PDF  +  ✉️ e-mail opțional
```

> **Local vs. extern:** documentele, fragmentarea, indexarea și retrieval-ul rulează local. Generarea trimite profilul consultației și fragmentele selectate către modelul ales în UI: modelele locale prin `OLLAMA_API_BASE`, `deepseek-flash` prin API-ul DeepSeek, `DeepSeek-V4-Flash` prin routerul Hugging Face/DeepInfra sau `grok-4.3` prin API-ul xAI. Generarea cu orice model necesită autorizarea de admin. Selecția se aplică doar raportului curent, fără modificarea variabilelor de mediu sau fallback la alt furnizor. Identificarea unei afecțiuni necunoscute trimite numai mesajul către Ollama de pe host. La timeout, eroare de comunicare sau răspuns invalid, afecțiunea rămâne neidentificată; nu se apelează alt furnizor AI. Livrarea prin Gmail este opțională.

## 🛠️ Tehnologii folosite

| Zonă | Tehnologii |
|---|---|
| **Limbaj și runtime** | Python ≥ 3.11 (mediu local documentat: 3.11), PowerShell, Node.js 22 pentru frontend |
| **Interfață și API** | React 19, TypeScript, Vite, TanStack Query, FastAPI, Uvicorn |
| **Embeddings locale** | FastEmbed, ONNX Runtime, `Qwen/Qwen3-Embedding-0.6B` (indexare opțională pe GPU, PyTorch fp16) |
| **Stocare index** | PostgreSQL, `pgvector` (similaritate cosinus), `unaccent` + `tsvector` (căutare lexicală) |
| **Scorul fragmentelor** | `4·P1 + 2·P2 + L + V` cu toate semnalele, cu prioritate pentru afecțiunea din titlu, apoi din text; pacientul poate alege oricare combinație de semnale |
| **Generare AI** | Ollama `/api/chat` nativ sau DeepSeek Responses API (doar admin), ales pentru fiecare raport, răspuns JSON structurat |
| **Documente** | ReportLab pentru PDF, pypdf pentru procesare și verificare |
| **E-mail** | Gmail API, OAuth2 cu refresh token |
| **Configurare** | python-dotenv, variabile de mediu |
| **Rulare și publicare** | Docker, Docker Compose, Tailscale Funnel, PostgreSQL (`pgvector/pgvector`) |
| **Testare** | `unittest`, `pytest` + `testcontainers` (Postgres efemer) pentru backend, Vitest pentru frontend |

## 🗺️ Documentație de arhitectură

| Document | Ce explică |
|---|---|
| 🧠 [Fluxul de generare a indexului hibrid (XMind 8)](architecture/hybrid-index-generation.xmind) | Fluxul complet: documente → sincronizare incrementală (SHA-256) → fragmente R1/R2/D1 → embeddings → Postgres (`pgvector` + `tsvector`). |
| 📄 [Fluxul de generare a raportului final (XMind 8)](architecture/final-report-generation.xmind) | Fluxul complet: mesaj → retrieval hibrid → fragmente afișate pacientului → „Generează raportul” → furnizorul AI → PDF → download și trimitere pe e-mail către altă persoană. |
| 🔎 [Căutarea și scoringul fragmentelor (XMind 8)](architecture/fragment-search-and-scoring.xmind) | Fluxul complet: mesaj → afecțiuni recunoscute → scor (`4·P1 + 2·P2 + L + V` cu toate semnalele alese) pentru toate fragmentele → procent de relevanță → limitarea contextului. |

## 📁 Structura proiectului

```text
medicina-naturista/
├── architecture/                 # diagramele fluxurilor principale în format XMind
├── medicina-naturista-documente/
│   └── data/
│       └── documents/                # corpusul Markdown local
├── model_cache/                  # modelele locale; ignorat de Git
├── src/
│   ├── backend/
│   │   ├── ai/                       # fragmentare, afecțiuni, căutare, retrieval, clienți AI și prompturi
│   │   ├── core/                     # modele și sesiuni izolate
│   │   ├── migrations/               # schema PostgreSQL și cataloagele inițiale de afecțiuni/plante
│   │   ├── integrations/             # integrarea Gmail
│   │   ├── reporting/                # generarea raportului PDF
│   │   └── web/                      # API JSON FastAPI (servește și build-ul React)
│   ├── frontend/                 # aplicația React/TypeScript (Vite)
│   ├── scripts/
│   │   ├── build_hybrid_index.py     # sincronizarea incrementală a indexului în Postgres
│   │   ├── bootstrap_database.py     # creează baza lipsă înainte de indexare
│   │   ├── migrate_database.py       # aplică migrările SQL versionate
│   │   ├── condition_sql.py          # generează SQL pentru afecțiuni noi
│   │   ├── manage_dependencies.py    # generează și verifică lockurile
│   │   ├── search_index.ps1          # căutare locală din terminal
│   │   ├── clean_documents.py        # curățare și corectare OCR/de scriere cu dicționarul inclus
│   │   ├── fragment_report.py        # simularea fragmentării; citește catalogul din DB, fără embeddings
│   │   ├── audit_conditions.py       # audit read-only al dicționarului de afecțiuni
│   │   ├── audit_near_dupes.py       # afecțiuni canonice aproape duplicate (read-only)
│   │   ├── audit_herbs.py            # raport read-only despre plantele din PostgreSQL (în tmp/herbs_review.md)
│   │   ├── icd10_work/               # scripturi one-off pentru completarea dicționarului după ICD-10
│   │   ├── evaluate_retrieval.py     # măsurarea calității căutării (P@10, MRR, nDCG)
│   │   ├── google_oauth_setup.py     # autorizare Gmail OAuth2
│   │   ├── extract_pdf_markdown.py   # extragerea structurată în Markdown
│   │   └── merge_book_pdfs.py        # combinarea părților de carte PDF
│   └── tests/                    # teste unitare și de integrare
├── docker-compose.yaml
├── Dockerfile
├── pyproject.toml
├── requirements-runtime*.lock    # dependențe runtime fixate, cu hashuri
├── requirements-dev*.lock        # runtime + unelte de dezvoltare/testare
└── requirements-web.txt          # alias compatibil pentru Windows/Python 3.11
```

## 🚀 Pornire rapidă

### 1. Pregătirea mediului

Comenzile PowerShell se execută din rădăcina proiectului. Instalați Python 3.11 și Node.js 22/npm; PostgreSQL cu `pgvector` trebuie să fie accesibil înainte de indexare. Corpusul `medicina-naturista-documente/data/documents/` este furnizat separat. Cataloagele de afecțiuni și plante se reconstruiesc din migrările SQL livrate.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-runtime.lock
```

Plasați documentele românești în `medicina-naturista-documente/data/documents/ro/` și documentele englezești în `medicina-naturista-documente/data/documents/en/`. Mutarea surselor vechi din rădăcina `documents` în `documents/ro` se face manual. Curățarea de mai jos parcurge recursiv ambele directoare, RO și EN. Nu publicați corpusul dacă include materiale private sau protejate. Opțional, curățați-le înainte de indexare (metadate de extragere PDF, linkuri, marcaje de pagină, trimiteri „Vezi și”, diacritice românești transcrise în litere ASCII: `ă/â → a`, `î → i`, `ș → s`, `ț → t`):

```powershell
.\.venv\Scripts\python.exe src\scripts\clean_documents.py --dry-run
.\.venv\Scripts\python.exe src\scripts\clean_documents.py
```

Înlocuirea diacriticelor este activă implicit; opțiunea `--no-fold-diacritics` le păstrează. Corectarea cuvintelor folosește fișierele Hunspell `ro_RO.dic` și `ro_RO.aff` din `src/scripts/dictionaires/ro/` pentru sursele RO, respectiv `en_GB.dic` și `en_GB.aff` din `src/scripts/dictionaires/en/` pentru sursele EN, localizate relativ la script. Limba este stabilită din directorul `documents/ro` sau `documents/en`, inclusiv când `--source` indică un subdirector al acestuia. Pentru a prelucra numai sursele englezești, adăugați `--source medicina-naturista-documente/data/documents/en`.

Corectarea rulează după curățare pentru sursele RO și EN: unește două fragmente OCR nerecunoscute, separă cuvinte lipite și corectează greșeli rare neambigue. Modernizarea ortografiei vechi se aplică numai limbii române. Frecvențele și cuvintele funcționale sunt separate pe limbi, astfel încât corpusul RO nu influențează corecturile EN și invers. Pentru fișierele din afara directoarelor de limbă, se păstrează tratarea anterioară: numai textele detectate ca românești primesc corecturi ortografice; cele englezești sau mixte primesc doar curățarea generală. Unirea protejează cuvintele din dicționar, cuvintele funcționale precum `la`, `de`, `si` și fragmentele de o singură literă; expresii precum `tumora la san` și `pieptul e` rămân separate. Întreaga prelucrare este planificată în memorie: frecvențele se recalculează după fiecare trecere, până când o trecere completă nu mai schimbă nimic. Abia apoi se rescriu fișierele. Cu același corpus, dicționar și aceleași opțiuni, o nouă rulare reușită nu mai modifică documentele sau datele lor de modificare. Un ciclu ori depășirea limitei de 16 treceri oprește execuția înainte de orice rescriere a surselor. `--dry-run` calculează același rezultat stabil, fără modificarea documentelor.

Documentele din `documents/ro` detectate clar ca englezești folosesc dicționarul EN la
curățare, fără mutarea fișierelor. Suprascrierea limbii folderului cere minimum 20 de
cuvinte, cel puțin patru cuvinte funcționale distincte specifice limbii engleze și
rezultatul EN al detectorului combinat. Textele scurte sau clasificate ca mixte/incerte păstrează limba folderului.
Detecția combină frecvența cuvintelor funcționale cu vocabularul distinct găsit exclusiv
într-unul dintre dicționare. Cuvintele comune și cele necunoscute sunt neutre. Votul
vocabularului cere cel puțin cinci cuvinte distincte exclusive, acoperire de minimum 20%
și un raport de cel puțin 2:1; un conflict cu metoda bazată pe cuvinte funcționale produce
rezultatul mixt. Ambele dicționare se încarcă o singură dată, înaintea selecției limbii,
și se reutilizează la detecție și corectare. Expansiunea Hunspell combină cel mult un
prefix cu un sufix compatibil, fără acumularea arbitrară de prefixe.
Selecția este anunțată în consolă prin `Dictionary override ro -> en`, inclusiv la
`--dry-run`. Această selecție privește doar corectarea ortografică; limba fragmentelor
la indexare rămâne cea a folderului sursă.

Raportul `var/spelling_changes.tsv` conține fișierul, linia din textul curățat la trecerea respectivă, regula, formele înainte/după și coloana `pass` cu numărul trecerii. El înregistrează pașii corectării; trecerile ulterioare pot elimina linii și schimba numerotarea. Se generează și la `--dry-run`. Folosiți `--spelling-report` pentru altă destinație. Lipsa dicționarului oprește execuția înainte de modificarea documentelor. Protecția dozelor și numerelor verifică rezultatul fiecărei treceri; fișierele care o încalcă sunt păstrate intacte și execuția se încheie cu eroare. `--no-fold-diacritics` păstrează diacriticele și folosește formele din dicționar pentru înlocuiri. Corectarea rămâne euristică; nu poate garanta sensul medical al textului și nu repară automat unirile greșite produse de versiuni anterioare.

Aveți nevoie de un Postgres cu extensia `pgvector` pornit și accesibil la `DATABASE_URL` (implicit `postgresql://medicina:medicina@127.0.0.1:5432/medicina`); cel mai simplu e `docker compose up -d db`, care cere `POSTGRES_PASSWORD` în `.env` (utilizatorul și baza sunt implicit `medicina`), deci `DATABASE_URL` trebuie să folosească aceeași parolă.

### 2. Sincronizarea indexului

Reindexarea implicită citește ambele rădăcini, `DOCUMENTS_DIR` (implicit
`data/documents/ro`) și `DOCUMENTS_EN_DIR` (implicit `data/documents/en`), și publică
un singur index atomic. `--source-ro` (alias `--source`) și `--source-en` înlocuiesc
explicit rădăcinile. Un folder lipsă, gol sau suprapus celuilalt oprește buildul înainte
de publicare. Identitățile surselor sunt `ro/<cale>` și `en/<cale>`; prefixul nu este
categorie. Fragmentele, statisticile de scor, sursele și topurile sunt filtrate după limbă.
După indexare, pregătirea/publicarea implicită a recomandărilor și a avertizărilor rulează
pentru fiecare limbă cu promptul ei. Comenzile dedicate de analiză, pregătire, reluare sau
publicare acceptă `--language ro|en`; RUN_ID trebuie folosit în limba în care a fost creat.
CLI-ul de căutare acceptă `-Language en`, iar `fragment_report.py` și
`evaluate_retrieval.py` acceptă `--language en`. Schimbarea versiunii reprezentării la
`11` necesită reindexare; aplicația nu aplică migrări și nu pornește reindexarea la startup.


```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe src\scripts\build_hybrid_index.py
```

Scriptul importă pachetul `backend`, deci are nevoie de `PYTHONPATH=src`. Baza vine din `DATABASE_URL` (`.env`); `--model` și `--source` sunt opționale. Scriptul pornește cu pythonul din care îl rulezi (pe CPU, fără alt mediu); pe GPU vezi mai jos.

`TEXT_REPR_VERSION` este definită o singură dată în `src/backend/ai/index_constants.py`, cu valoarea `"11"`. Scriptul de indexare și backendul citesc aceeași constantă; nu este o variabilă de mediu. Schimbarea valorii face ca următoarea rulare a scriptului să reproceseze toate documentele; până la sincronizare, backendul refuză indexul cu versiunea veche. Modificarea constantei nu pornește automat reindexarea. Reporniți backendul după schimbarea codului.

Modelul de embedding este `Qwen/Qwen3-Embedding-0.6B` (vectori de 1024 de dimensiuni); alt model nu este cunoscut de cod. Căutarea citește modelul din `sync_metadata` și scrie întrebările după profilul lui (`ai/embedding_model.py`: instrucțiunea Qwen la întrebare, fără prefix la pasaje). **Dacă baza conține un index făcut cu alt model sau cu altă dimensiune, următorul build reîncorporează toate documentele**, iar coloana `chunks.embedding` este recreată în aceeași tranzacție cu documentele și metadata noi. Orice eroare păstrează generația și dimensiunea anterioare. Durata depinde de corpus și hardware. Indexarea pe GPU necesită un mediu separat `.venv-gpu`, cu dependențele aplicației, `torch` cu suport CUDA și `sentence-transformers` deja instalate:

```powershell
$env:PYTHONPATH = "src"
$env:EMBEDDING_DEVICE = 'cuda'
.\.venv-gpu\Scripts\python.exe src\scripts\build_hybrid_index.py
```

Actualizați dependențele runtime în fiecare mediu Python folosit pentru indexare. Pachetul `pyahocorasick` se importă ca `ahocorasick`; instalarea în `.venv` nu îl face disponibil în `.venv-gpu` sau în Pythonul global. Pentru un mediu GPU existent căruia îi lipsește această dependență:

```powershell
.\.venv-gpu\Scripts\python.exe -m pip install --no-deps --only-binary=:all: pyahocorasick==2.3.1
```

Builderul verifică disponibilitatea pachetului înainte de pornirea workerilor și indică interpreterul și comanda de instalare dacă importul eșuează.

La prima sincronizare, modelul este descărcat în `model_cache/` dacă lipsește. Apoi căutarea funcționează offline. Căutarea pe CPU necesită modelul FastEmbed/ONNX, chiar dacă indexarea a fost făcută pe GPU cu PyTorch.

La următoarele sincronizări, se procesează doar documentele noi sau modificate, iar cele șterse sunt eliminate din index. Schimbarea catalogului de afecțiuni, a modelului sau a modului de pregătire a textului impune refacerea completă a indexului. Progresul și timpul estimat rămas sunt afișate în terminal.

**Reindexarea creează baza dacă lipsește și aplică automat migrările SQL.** Sunt necesare permisiuni pentru crearea bazei, a schemei și a extensiilor; opțional, `DATABASE_BOOTSTRAP_URL` poate furniza un cont separat pentru creare. Aplicația web nu execută migrări la pornire. Afecțiunile, plantele și sinonimele sunt citite din PostgreSQL; completările se fac prin migrări noi în `src/backend/migrations/`, fără modificarea celor deja aplicate.

În timpul sincronizării, căutarea și lista surselor sunt temporar indisponibile (`503`). Generarea din fragmente deja găsite și descărcarea PDF-urilor pot continua. Indexul nou este publicat numai după calcularea și validarea tuturor vectorilor; un eșec păstrează indexul anterior. Dacă între timp s-a schimbat catalogul, căutarea necesită finalizarea reindexării. Un catalog lipsă sau invalid blochează căutarea, iar un index incompatibil cere resincronizare (`INDEX_RESYNC_REQUIRED`).

Pentru reconstruirea indexului, păstrați documentele sursă, migrările SQL, modelul și configurația. Autorizările owner necesită backup separat.

Căutarea folosește numai sursele selectate. O selecție goală nu caută nicăieri; dacă toate sursele selectate au dispărut, aplicația cere reselecția. Dacă au dispărut doar unele, le păstrează pe cele valide și afișează un avertisment.

În generarea pe loturi, o trimitere la un fragment inexistent sau din alt lot invalidează răspunsul și oprește întregul raport; elementele de nutriție fără citări rămân exceptate. Validatorul reutilizabil păstrează modul compatibil de raport parțial pentru alți consumatori, dar fluxul nou de generare îl apelează strict și nu publică PDF parțial. La eșec, căutarea se păstrează pentru o reîncercare manuală. Verificarea citărilor nu reprezintă validare medicală. Logurile clientului AI conțin doar diagnostic tehnic, fără textul fragmentelor sau al răspunsului.

Pentru a vedea ce fragmente ar rezulta, fără scriere în index și fără embeddings (necesită catalogul migrat din PostgreSQL):

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe src\scripts\fragment_report.py
```

### 3. Căutarea locală

```powershell
.\src\scripts\search_index.ps1 "plante și măsuri pentru tuse"
```

Pentru rezultate ușor de procesat programatic:

```powershell
.\src\scripts\search_index.ps1 "plante și măsuri pentru tuse" -Json
```

Căutarea din terminal întoarce toate fragmentele cu scor pozitiv (fără limita de context a furnizorului AI). Fiecare rezultat păstrează documentul sursă, intervalul de linii și componentele scorului (`P1`, `P2`, `L`, `V`), astfel încât pasajul să poată fi verificat în fișierul original. `--signals` alege semnalele scorului (orice combinație de `A` afecțiuni, `B` lexical, `C` semantic; implicit `ABC`), de exemplu `python -m backend.ai.search "gripa" --signals AB`.

Calitatea căutării se măsoară pe interogările etichetate din `src/tests/eval/retrieval_queries.json`:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe src\scripts\evaluate_retrieval.py --output after.json
```

### 4. Pornirea aplicației în dezvoltare

Pentru rapoarte, instalați modelul `gemma4:12b` în Ollama pe host. Pentru opțiunea DeepSeek a adminului, adăugați cheia DeepSeek și cheia de owner în fișierul local `.env`:

```dotenv
REPORT_GENERATION_MODELS=ollama-gemma3:1b,ollama-gemma4:12b,ollama-ministral-3:8b,ollama-qwen3.5:9b,ollama-qwen3.5:4b,ollama-deepseek-r1:8b,deepseek-flash,huggingface-deepseek-v4-flash,grok-4.3
DEEPSEEK_API_KEY=...
OWNER_KEY=o-cheie-secreta-lunga
COOKIE_SECURE=false
```

Construiți interfața React (FastAPI servește `src/frontend/dist`):

```powershell
cd src/frontend
npm ci
npm run build
cd ..\..
```

Apoi porniți aplicația:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn backend.web.main:app --host 127.0.0.1 --port 7860
```

Dacă ați sincronizat indexul la pasul 2, migrările sunt deja aplicate. Pentru mentenanța unei baze existente, le puteți executa separat cu `.\.venv\Scripts\python.exe -m scripts.migrate_database` (cu `PYTHONPATH=src`). Deschideți chatul la `http://127.0.0.1:7860/`, respectiv `http://127.0.0.1:7860/owner` pentru login/logout. Formularul trimite cheia prin `POST /api/owner/login`, cu CSRF; logoutul revocă tokenul prin `POST /api/owner/logout`. Cu prefixul public, formularul este `/medicina/owner` pe originea HTTPS configurată. Cheia nu trebuie pusă în URL sau în istoricul terminalului. Autorizarea rămâne valabilă peste restart până la logout sau rotația cheii. Ruta veche cu cheia în query rămâne doar pentru compatibilitate. `/healthz` verifică inclusiv configurarea furnizorului AI; `/readyz` adaugă verificarea disponibilității și compatibilității indexului.

Pentru clasificarea mesajelor și identificarea locală a afecțiunilor, porniți Ollama pe `CONDITION_AI_LOCAL_BASE` (implicit `http://localhost:11434/v1`) și descărcați modelul o dată cu `ollama pull gemma3:1b`. Acest model este separat de furnizorul ales pentru generarea raportului.

Pentru dezvoltarea interfeței cu reîncărcare automată, rulați `npm run dev` în `src/frontend/`. Vite servește interfața local la `http://localhost:5173/medicina/` și trimite cererile API, verificările de stare și formularul owner către backend-ul de producție `https://cristiantone.taila68086.ts.net/medicina/`. Mesajele, căutările și rapoartele folosesc acest backend. Fișierele TypeScript ale interfeței sunt servite local, fără a fi trimise prin proxy. Backend-ul trebuie să fie disponibil; `npm run dev` nu îl pornește. `DEV_BACKEND_URL` poate suprascrie adresa backend-ului.

Pentru a folosi în schimb un backend pornit local, setați adresa înainte de lansarea Vite:

```powershell
$env:DEV_BACKEND_URL = "http://127.0.0.1:7860/"
npm run dev
```

În această variantă, interfața locală este la `http://localhost:5173/`. Pentru a reveni la backend-ul de producție implicit, eliminați variabila cu `Remove-Item Env:DEV_BACKEND_URL -ErrorAction SilentlyContinue` și reporniți Vite. `PUBLIC_BASE_PATH` continuă să configureze calea pentru build-ul de producție.

API-ul JSON (`src/backend/web/main.py`) este folosit de interfața React; documentația OpenAPI (`/docs`) este dezactivată. Cererile `/api/...` cu sesiune trimit antetul `X-Tab-Id` (identificatorul tabului).

| Endpoint | Rol |
|---|---|
| `GET /healthz` | Starea aplicației și configurarea cheii AI; independent de mentenanța sau compatibilitatea indexului. Folosit de healthcheck-ul Docker. |
| `GET /readyz` | Verifică și indexul; 503 cu `INDEX_MAINTENANCE`, `INDEX_RESYNC_REQUIRED` sau `INDEX_UNAVAILABLE` și `Retry-After: 60`. |
| `GET /owner` | Formularul de autentificare/deconectare owner. Varianta veche cu `?key=...` este încă acceptată, dar nu este recomandată: expune cheia în URL. |
| `GET /api/owner` | Starea autorizării și tokenul CSRF pentru browser. |
| `POST /api/owner/login`, `POST /api/owner/logout` | Emit, respectiv revocă autorizarea individuală; necesită origine validă și token CSRF. |
| `GET /api/session` | Creează sesiunea tabului și întoarce istoricul conversației. |
| `GET /api/categories` | Arborele categoriilor (folderele surselor) și selecția implicită (toate). |
| `POST /api/messages` | Salvează mesajul, categoriile și semnalele; întoarce `classifyMessage` și `contextRevision`. `messageId` opțional previne dublarea cererii. |
| `POST /api/classify` | Aplică scurtăturile deterministe sau clasifică prin Ollama local; rutează spre `remedii`, `planta`, `top_plante`, `diverse` sau `email_raport`. Necesită `X-Context-Revision`. |
| `POST /api/condition` | Identifică prin AI afecțiunea pe care dicționarul nu o cunoaște (Ollama local, fără fallback). |
| `POST /api/search` | Rulează căutarea și întoarce fragmentele găsite și secțiunea „Generează raportul”. |
| `GET /api/report-models` | Toate modelele configurate în ordinea env, `defaultModel` (primul model) și `allowedModels` (cele permise utilizatorului curent). Lista vizibilă este aceeași pentru public și autor; drepturile sunt verificate separat. |
| `GET /api/report-duration-estimate?model=...&characters=...` | Durata estimată în secunde și numărul măsurătorilor, folosind toate rândurile modelului din `report_generation_metrics`. Numai agregate, fără afecțiuni sau texte medicale. |
| `POST /api/searches/{search_id}/generate` | Primește `minScore` și `model` din catalog; fără model folosește `REPORT_GENERATION_MODELS`. Orice model fără autorizare admin → HTTP 403; model necunoscut → HTTP 422. Aplică pragul selectat și procesează loturile în paralel conform `REPORT_BATCH_WORKERS` (implicit 2), în cadrul unui singur raport activ. Generează un singur PDF după validarea tuturor loturilor. |
| `GET /api/reports/{tab_id}/{report_id}` | Descarcă PDF-ul generat în sesiunea tabului. |
| `POST /api/session/end`, `POST /api/session/unload` | Închid sesiunea tabului (la cerere, respectiv la închiderea paginii). |

## Sesiuni, retenție și autorizare owner

- **Sesiuni:** aplicația poate fi deschisă simultan în mai multe taburi sau browsere de pe același PC/IP. Fiecare încărcare completă a paginii, inclusiv refresh, Shift+F5 sau duplicarea tabului, începe o conversație nouă. Identificatorul este păstrat doar în memoria paginii; reîncercările și reconectările din aceeași pagină continuă conversația curentă. Rămân active limita globală de sesiuni și limitele de creare a sesiunilor pe minut.
- **Retenție:** istoricul, fragmentele și PDF-urile rămân în memoria procesului. Sesiunea expiră după o oră de inactivitate sau cel mult patru ore (`SESSION_IDLE_SECONDS`, `SESSION_MAX_SECONDS`). Închiderea paginii încearcă să închidă sesiunea; dacă notificarea nu ajunge la server, expirarea eliberează datele. Repornirea aplicației le elimină. Se păstrează cel mult 12 căutări și 12 rapoarte per sesiune, în limitele bugetelor de memorie.
- **Owner / admin:** setați `OWNER_KEY` și autentificați browserul prin formularul `/owner` pentru a folosi modelele externe `deepseek-flash`, `huggingface-deepseek-v4-flash` și `grok-4.3`. Cele patru modele Ollama sunt disponibile și fără autorizare. Selectorul „Model AI” urmează câmpului „Scor minim”; lista se actualizează la revenirea în pagină după autentificare. API-ul verifică autorizarea la fiecare generare cu un model extern și la citirea/anularea jobului său. PostgreSQL păstrează hashul tokenului și date tehnice, fără conversații sau PDF-uri. Autorizarea supraviețuiește restartului; logoutul o revocă, iar schimbarea cheii invalidează tokenurile existente.

## Catalogul de plante și produse

Fiecare top nevid afișează imediat sub titlu instrucțiunea de selectare prin numărul produsului, cu exemplul `1` pentru primul produs, înaintea explicației scorului și a listei.

După afișarea unui top de plante sau produse (general, pe categorie sau pentru o afecțiune), următorul mesaj poate fi doar numărul poziției din listă: `1` deschide aceleași detalii ca întrebarea „la ce e bun Ulei de măsline”, dacă acesta este primul produs afișat. Se folosește ordinea exactă a topului afișat, fără o nouă clasificare AI. Un număr în afara listei cere o alegere validă și păstrează lista pentru reîncercare. O altă solicitare încheie această selecție; meniurile pentru categorie, numărul de intrări sau afecțiune își păstrează regulile proprii.

Catalogul de plante și produse și aliasurile sunt citite din PostgreSQL. Căutarea unei plante ignoră diferențele de caz, diacritice și cratime; un nume comun mai multor specii cere alegerea utilizatorului. Cererile „Top N plante” afișează clasamentul plantelor și produselor după numărul de afecțiuni distincte cu recomandări pozitive identificate în surse și denumirile regionale, fără generarea unui raport. Fiecare intrare folosește formularea „util/utilă/utile în X afecțiuni”, cu acordul denumirii românești; nota precizează că atenționările, contraindicațiile și relațiile mixte sunt excluse din scor și că această clasificare nu reprezintă validare clinică. Listele generale de afecțiuni ale unui produs păstrează asocierile istorice, inclusiv avertismentele.

Topurile pe afecțiune reutilizează acest ranking global după filtrarea perechilor pozitive pentru afecțiunea cerută. Un produs cu ranking mai mare care nu are asociere pozitivă cu afecțiunea este exclus. Filtrul nu cere migrare sau reindexare; necesită o rulare pozitivă deja publicată și compatibilă. Codul local nou și exemplele din catalogul de texte devin disponibile în aplicația care rulează numai după livrarea explicită a versiunii compatibile și reîncărcarea paginii.

Categoriile de produse acceptate sunt `seminte`, `suplimente`, `uleiuri esentiale`, `uleiuri`, `aminoacizi`, `vitamine` și `minerale`. Produsele apicole, fibrele, probioticele și prebioticele aparțin categoriei `suplimente`. Categoria `medicamente` și intrarea `aspirina` sunt eliminate prin migrarea 026. Sunt grupări tehnice de catalog, fără a stabili statutul medical sau eficacitatea produsului. Intenția API `planta` și rutele existente acoperă și produsele, recunoscute după `ro` și `en`, fără diferențe de caz sau diacritice. Produsele fără specie returnează `species=[]` și se afișează fără paranteze goale.

Migrările `014`/`015` adaugă 391 de produse (inclusiv cele 12 denumiri comerciale confirmate la `suplimente`), reutilizează înregistrările pentru psyllium, ashwagandha, drojdie de bere, spirulina și chlorella și adaugă numai plantei Thuja aliasurile `arborele vietii` și `thuya occidentalis`. Denumirile vitaminice istorice și cele trei etichete de uleiuri de iasomie, vanilie și lotus alb sunt păstrate conform cerinței de catalog, fără afirmații despre identitate chimică sau extracție. „Ulei sau extract de afin” este exclus. Totalul inițial după migrare este 1.579 intrări: 1.188 botanice și 391 produse. Catalogul nu introduce automat sinonime precum `NAC`: numele canonic disponibil este `N-acetilcisteina`.

Pentru migrările `014`/`015`, codul compatibil trebuie livrat înainte de migrare; după migrare se rulează `scripts.build_hybrid_index --rebuild-herbs` pentru asocieri, ranking și fingerprinturi. Între aceste etape, rezultatele despre catalog pot cere resincronizare. Documentele neschimbate își păstrează embeddings dacă profilul lor nu s-a schimbat.

Migrarea `016_separate_herb_category.sql` separă categoria de familia botanică și reconstruiește numai tabela `herbs` pentru ordinea fizică `id, category, family, latin, ro, en, ranking`. Pentru upgrade de la 015: pregătiți imaginea compatibilă, verificați backupul și snapshoturile datelor, opriți scurt aplicația, rulați explicit `python -m scripts.migrate_database` cu `PYTHONPATH=src` și configurația bazei țintă, apoi porniți imaginea nouă și verificați `/healthz` și `/readyz`. Migrarea este tranzacțională, păstrează ID-urile, numele, aliasurile, asocierile și rankingul; refuză configurații sau dependențe suplimentare neacoperite. **Pentru 016 nu se rulează reindexarea, `--rebuild-herbs` sau embeddings**: fingerprintul de matching și toate valorile `sync_metadata` rămân neschimbate. SQL NULL pentru familie/latin se normalizează la șir gol numai în obiectele runtime; parserul surselor JSONL istorice rămâne botanic. Fingerprintul catalogului runtime este versionat separat și include categoria și familia.

Migrarea `017_food_categories_in_herbs.sql` introduce 12 categorii: `plante medicinale`, `fructe`, `legume`, `cereale`, `seminte`, `uleiuri esentiale`, `suplimente`, `aminoacizi`, `vitamine`, `minerale`, `produse apicole`, `fibre, probiotice, prebiotice`. Cele patru grupe botanice păstrează latinul și familia. Clasificarea alimentară pune roșiile la fructe, nucile/alunele la fructe, leguminoasele alimentare la legume și hrișca/quinoa/amarantul alimentar la cereale. Nu se mută genuri sau familii întregi. Speciile-sursă și semințele consumate separat sunt intrări distincte: cele patru produse-semințe (floarea-soarelui, dovleac, struguri, in) au `latin` și `family` SQL NULL. Un ulei din semințe rămâne în categoria sa. Categoriile nu devin nume sau aliasuri de matching.

017 reclasifică explicit 161 de rânduri existente și adaugă cele patru semințe plus `chenopodium quinoa` (`amaranthaceae`): totalul seedului este **1.584**, cu toate ID-urile/numele/familiile/aliasurile vechi păstrate. Noile rânduri primesc ID-uri identity și ranking inițial 0. Formele cu/fără cratimă sunt deja echivalente în matching și nu necesită aliasuri duplicate. Definițiile comune se află în `core/herb_categories.py`; parserul surselor istorice rămâne botanic.

Migrarea `018_reclassify_oils_medicines_and_beta_carotene.sql`, aplicată după 017, extinde catalogul la **14 categorii** și mută numai trei intrări: `beta-caroten` → `vitamine`, `ulei de masline` → categoria nouă `uleiuri`, `aspirina` → categoria nouă `medicamente`. Păstrează ID-urile, numele, aliasurile, rankingul, asocierile și totalul de 1.584 de intrări. „Top N uleiuri” și „Top N medicamente” folosesc noile filtre; „uleiuri esențiale” rămâne o categorie distinctă. Pentru 018 singură nu se refac asocierile, fragmentele sau embeddings. Dacă 017 este încă neaplicată, cerințele de rollout pentru 017 de mai jos rămân valabile. Migrarea refuză identități sau categorii-sursă neașteptate și nu este aplicată automat la pornirea aplicației.

Migrarea `019_reclassify_additional_oils.sql` mută explicit din `suplimente` în `uleiuri` cele șapte produse existente: ulei de primula, avocado, krill, peste, catina, in și cocos. Nu schimbă ID-uri, nume, rankinguri, aliasuri sau asocieri; păstrează totalul de 1.584 de intrări și fingerprintul de matching. Pentru această reclasificare singură nu se refac asocierile, fragmentele sau embeddings.

Migrarea `020_reclassify_remaining_requested_oils.sql` mută încă 13 produse existente din `suplimente` în `uleiuri`: ulei de argan, bame - seminte, caise - samburi, castraveti - seminte, cirese - samburi, coacaze negre - seminte, fistic, macadamia, macese, neem, papaya - seminte, tamanu și tarate de orez. Păstrează toate celelalte date, inclusiv rankingurile 0, și nu cere refacerea asocierilor, fragmentelor sau embeddings. Împreună cu 018 și 019, categoria `uleiuri` conține 21 de produse; totalul catalogului rămâne 1.584. Fiecare migrare verifică explicit identitățile și categoria-sursă și refuză orice abatere.

Migrarea `021_reclassify_probiotic_products.sql` mută `Biogaia Prodendis`, `Biothin Probiotic`, `Digestive Advantage` și `Mood Probiotic` în categoria `fibre, probiotice, prebiotice`, păstrând ID-urile, numele, rankingurile și asocierile. Nu cere refacerea asocierilor sau embeddings.

Migrarea `022_add_sunflower_and_pumpkin_oils.sql` adaugă numai `ulei de floarea-soarelui` și `ulei de dovleac`, cu nume englezești `sunflower oil` și `pumpkin seed oil`, în categoria `uleiuri`. Ambele au familie/latin SQL NULL, ID identity nou și ranking inițial 0. Nu se adaugă ulei de luminita-noptii sau aliasuri pentru acesta. Auditul verifică numele românești, englezești, latine și aliasurile pentru a refuza dubluri. Totalul seedului devine **1.586** de intrări, dintre care **23 de uleiuri**. Fiind produse noi, după 022 se rulează separat `--rebuild-herbs-only`, conform procedurii pentru 017 de mai jos: numai asocieri/rankinguri din fragmentele existente, fără refacerea documentelor sau embeddings. Aplicarea migrărilor și refacerea asocierilor nu fac parte din modificările locale de cod.

**Aplicarea 017 se face separat de implementare.** Pregătiți imaginea compatibilă și un backup verificat prin restaurare; salvați înainte amprentele complete și xmin pentru `documents`/`chunks`, catalog, asocieri și metadate. Opriți scurt aplicația, aplicați explicit migrarea și executați apoi numai refacerea asocierilor:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.migrate_database
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --rebuild-herbs-only
```

Acest mod cere un index existent și compatibil, nu scanează corpusul, nu fragmentează și nu încarcă modelul de embeddings. Publică diferențial asocierile și rankingul în aceeași tranzacție și actualizează exclusiv cele cinci chei `herbs_benefits_*`, folosind generația existentă. Verifică fingerprintul catalogului anterior: permite completări cu ID-uri noi după cele deja indexate; modificarea/ștergerea numelor vechi sau orice schimbare a perechilor/rankingurilor vechi oprește publicarea. `--rebuild-herbs` este în continuare fluxul general și poate sincroniza documente modificate; nu îl folosiți pentru această aplicare.

Comparați amprentele după operație: documentele/chunks (inclusiv xmin), embeddings, generația și metadatele de bază trebuie să fie identice. Porniți aplicația compatibilă numai după aceste verificări; verificați `/healthz`, `/readyz` și topurile. Dacă refacerea asocierilor eșuează după commitul migrării, remediați operația sau restaurați backupul înainte de pornire. **Nu rulați reindexarea completă.**

În cererile despre plante, numele complet sau aliasul complet are prioritate. Dacă acesta nu există, începutul unei denumiri românești, pe cuvinte întregi, oferă speciile candidate: „plop” cere alegerea între plop alb, plop negru, plop tremurător și plop tremurător american. Sunt acceptate și flexiunile românești și formulările cu părți de plantă, precum „muguri de plop” sau „mugurii de plop”. După alegere, rezultatul include numai specia selectată. Această potrivire parțială nu se aplică mențiunilor din corpus sau citărilor din rapoarte.

`build_hybrid_index.py` reconstruiește automat asocierile `herbs_benefits` și clasamentul `herbs.ranking`. O asociere înseamnă că titlul fragmentului numește afecțiunea (`primary_medical_conditions`), iar textul menționează planta sau un alias. Mențiunile negative și contraindicațiile sunt incluse: asocierea nu dovedește un beneficiu terapeutic.

Asocierile se publică în aceeași tranzacție cu indexul. Extinderea catalogului de plante/produse sau schimbarea aliasurilor reconstruiește asocierile fără recalcularea embeddings pentru documentele neschimbate. Pentru refacere explicită sau audit:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --rebuild-herbs
.\.venv\Scripts\python.exe -m scripts.audit_herbs
```

Completările și corecțiile cataloagelor se fac prin migrări SQL noi în `src/backend/migrations/`, păstrând ID-urile existente. Catalogul lipsă sau invalid și asocierile nesincronizate blochează rezultatele despre plante cu o eroare explicită (`503`).

### Comasarea fibrelor, probioticelor și prebioticelor în suplimente

Migrarea append-only `024_merge_fibre_probiotics_into_supplements.sql` mută toate intrările
din vechea grupă în `suplimente` și elimină vechea valoare din constrângerile/indexul de
categorii. După 024, catalogul avea **13 categorii**. Pe seed-ul complet sunt 11 intrări mutate,
61 de suplimente și 1.586 de intrări în total. ID-urile, numele, aliasurile, familia, specia,
asocierile și scorurile istorice sunt păstrate. Referințele de mai sus la categoriile
migrărilor 014–021 descriu etapele istorice, înlocuite în acest punct de migrarea 024.

„Top 100 probiotice”, „Top 100 prebiotice”, „Top 100 fibre” și vechea denumire
completă cer acum topul `suplimente`, fără clasificare AI suplimentară pentru comenzile
explicite. Numărul și regulile topului strict pozitiv rămân aceleași.

Aplicarea pe baza activă se face separat, după backup și verificarea versiunilor pending;
comanda obișnuită de migrare aplică toate migrările restante, inclusiv 023 dacă lipsește.
Nu este necesară refacerea coaparițiilor, fragmentelor sau embeddings. Amprenta catalogului
se schimbă: un clasament pozitiv deja publicat cere o nouă pregătire/publicare, cu reutilizarea
cache-ului neafectat. Nu se pornește aplicația cu definiția nouă peste catalogul vechi nemigrat.

### Eliminarea medicamentelor și comasarea produselor apicole

Migrarea append-only `026_remove_medicines_and_merge_bee_products.sql` elimină aspirina
(ID 1212) din catalog, împreună cu aliasurile, asocierile și dovezile sale de clasament prin
cheile externe cu ștergere în cascadă. Verifică identitatea înainte de ștergere și refuză
alte medicamente neașteptate. Mută toate produsele apicole la `suplimente`: pe seed-ul
complet, propolis, miere, polen, păstură și lăptișor de matcă. Aceste produse își păstrează
ID-urile, numele, aliasurile, asocierile și scorurile.

Catalogul curent are **11 categorii**, **1.585 de intrări** și **66 de suplimente** pe seed-ul
complet. Constrângerile SQL interzic categoriile eliminate. Meniul păstrează pozițiile 1–8,
apoi continuă cu `9. aminoacizi`, `10. vitamine`, `11. minerale`. Cererile „Top N produse
apicole” selectează `suplimente`; „Top N medicamente” cere alegerea unei categorii valide.
Schema JSON a clasificatorului și promptul folosesc aceeași listă de 11 categorii.

Aplicarea pe baza activă rămâne un pas separat, împreună cu versiunea nouă a aplicației.
Nu se refac documentele, fragmentele sau embeddings. Eliminarea aspirinei schimbă amprenta
de matching: asocierile se resincronizează controlat cu `--rebuild-herbs-only`, apoi topurile
pozitive se pregătesc și se publică din nou, reutilizând cache-ul compatibil. Migrarea singură
nu publică un clasament pozitiv nou.

## Topuri cu recomandări pozitive

### Recunoașterea uleiurilor esențiale

Migrarea `027_essential_oil_source_aliases.sql` adaugă 183 de aliasuri pentru formele
mixte română/engleză din surse, precum `ulei esential de peppermint`, folosind denumirea
engleză completă a produsului existent. Nu creează produse noi și nu atribuie un nume
generic tuturor speciilor, variantelor sau chemotipurilor. Aliasurile sunt în `en_alt`,
nu în denumirile regionale afișate în top.

În `Uleiuri esentiale.md`, cele 55 de liste confirmate de operator drept recomandări
sunt etichetate explicit `Uleiuri recomandate` și au câte un produs pe rând. Cele 309
mențiuni și titlurile sunt păstrate. Regulile recunosc introducerile explicite de liste
pentru uleiuri, fără a transforma o simplă mențiune sau un titlu de boală în recomandare.
Sursele fără afecțiuni primare recunoscute și denumirile neidentificate rămân în afara
scorului. La următoarea indexare executată de operator se aplică migrarea, se actualizează
documentul schimbat și se pregătește/publică noua rulare; rularea anterioară nu se modifică.

`herbs_benefits` și `herbs.ranking` păstrează coaparițiile istorice. Topurile citesc separat
`herb_positive_rankings.ranking`: numărul de afecțiuni **primare** distincte cu cel puțin o
recomandare pozitivă și nicio mențiune negativă. Pozitiv + negativ, inclusiv în documente
diferite, înseamnă `mixed` și scor zero pentru pereche. `unclear` nu adaugă puncte și nu
anulează o dovadă pozitivă explicită. Repetările nu multiplică scorul.

La pregătirea clasamentului, o denumire românească principală unică are prioritate față
de aliasurile exclusiv regionale ale altor produse. De exemplu, `par` identifică implicit
`Pyrus communis`, nu scorușul (`Cormus domestica`), care are același alias regional.
O denumire explicită în paranteză sau în titlul local poate indica însă specia regională;
indiciile contradictorii și coliziunile între denumiri principale rămân ambigue.
Pentru omonimul `par`, lipsa unui context botanic explicit păstrează clasificarea `unclear`,
pentru a nu atribui pomului mențiuni despre părul de pe corp sau verbul „a părea”.
Identificarea produsului nu îl declară automat util: recomandarea și afecțiunea trebuie
clasificate în continuare din surse. Modificarea regulilor necesită o nouă pregătire și
publicare la reindexarea pornită de operator; scorurile active nu sunt rescrise direct.
În interfață, `Pyrus communis` este afișat „Păr”, inclusiv în topuri și în fișa produsului;
denumirea `par` și ID-ul său rămân neschimbate în baza de date.

Migrarea aditivă `023_positive_herb_rankings.sql` creează rulări, dovezi cu poziții în text,
perechi, scoruri și cache. Nu clasifică și nu activează nimic. **Aplicarea în baza activă
necesită autorizare separată**, backup verificat prin restaurare și evaluarea descrisă mai jos.
Aplicația nu aplică migrări la startup.

După aplicarea explicită a migrării într-un mediu pregătit, comanda obișnuită actualizează
implicit și topurile la final:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index
```

După încheierea tranzacției de indexare, CLI-ul execută secvențial analiza, pregătirea unei
rulări noi și publicarea ei atomică. Același flux rulează după `--rebuild-herbs` sau
`--rebuild-herbs-only`. Nu sunt necesare opțiunile separate de topuri pentru fluxul complet.
`herb_positive_runs` primește noua rulare; `herb_positive_evidence`, `herb_positive_pairs`
și `herb_positive_rankings` sunt populate pentru aceasta. `herb_positive_cache` reutilizează
deciziile compatibile și salvează deciziile noi validate. Tabelele nu sunt golite și
istoricul rulărilor este păstrat. Chiar și când indexul nu se schimbă, comanda creează o
rulare nouă, cu reutilizarea cache-ului. Nu este necesară o migrare suplimentară.

La execuția nativă pe Windows, CLI-ul traduce adresa Ollama `host.docker.internal`
moștenită din configurația Docker în `127.0.0.1`, păstrând protocolul, portul și calea.
În container adresa Docker rămâne neschimbată; o adresă locală configurată explicit
este de asemenea păstrată. Nu există retry sau schimbare de model/furnizor.

`--skip-positive-ranking` dezactivează explicit această etapă. Un eșec al indexării nu
lansează clasificarea; un eșec ulterior al pregătirii sau publicării topurilor returnează
cod de ieșire 1, fără activarea rezultatelor parțiale. Indexul deja publicat nu este anulat.

Pentru operații separate, modurile explicite rămân disponibile:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --analyze-positive-ranking
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-positive-ranking
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-positive-ranking --resume-positive-ranking RUN_ID
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-positive-ranking RUN_ID
```

Modurile sunt mutual exclusive cu reconstruirea asocierilor. Analiza nu cheamă Ollama și
nu scrie: raportează unitățile, deciziile prin reguli, cazurile ambigue, cache hits și loturile
calculate. Digestul folosit pentru analiza cache-ului este cel al ultimei pregătiri cu aceeași
configurație, dacă există; este marcat neverificat. Pregătirea verifică modelul instalat prin
`/api/tags`, înainte și după procesare, și publică numai o rulare neactivă `ready`. Modelul
nu este descărcat automat. Publicarea reverifică digestul modelului, inputul, acoperirea, agregatele și pointerul
observat la pregătire, sub lock, apoi activează într-un singur commit. O publicare concurentă
nu poate fi suprascrisă de o rulare veche. Repetarea publicării aceleiași rulări este idempotentă.

Regulile lucrează pe textul **indexat**, fără să modifice fragmentele sau embeddings.
Unitățile se separă la limitele paragrafelor, elementelor de listă și rândurilor de tabel,
cu titlurile relevante. Paragrafele păstrează contextul dintre propoziții, inclusiv referințele
indirecte la produse. Aceste unități sunt folosite numai pentru regulile locale. Cazurile
nerezolvate se grupează pe fragment indexat și pereche produs–afecțiune; Ollama primește
întregul `chunks.text`, cu toate paragrafele și titlurile din acel fragment. Mențiunile și
citatele se raportează la fragmentul complet, inclusiv în dovezile persistate.
`cache_semantics=6` separă deciziile obținute cu fragmentul integral și schema curentă de
deciziile salvate după protocoalele anterioare.
Un fragment care depășește bugetele tehnice oprește explicit pregătirea, fără trunchiere.
Fiecare fragment indexat ajunge la Ollama într-un singur câmp `units[].text`, cu întregul
`chunks.text` exact, fără împărțire, selecții de paragrafe sau trunchiere. Delimitările scurte
folosite pentru dovezile persistate se calculează local după răspuns; nu apar în payload.
Introducerile listelor și antetele tabelelor sunt preluate numai din textul indexat;
coloanele fără antet disponibil nu primesc un sens presupus. Un simplu titlu de boală
nu justifică o clasificare pozitivă. Regulile v3 tratează listele explicite și coliziunile
gramaticale clare ale aliasurilor, vehiculele alcoolice, ingredientele adăugate numai pentru
gust și unele descrieri strict nutritive. Interdicțiile explicite complet interpretate
(`interzis`, `contraindicat`, `contraindicată`, `contraindicate`, `nu este permis a se consuma`)
primesc local eticheta `caution` pentru produsul numit și afecțiunea primară verificată,
fără cerere AI pentru o unitate astfel rezolvată. Sunt recunoscute și listele negative
explicite. Negațiile interdicției, condițiile secundare, limitele de doză și formulările
incomplete rămân la AI. O interdicție certă dintr-un pasaj complex se păstrează separat
și se combină cu răspunsul modelului/cache-ului; nu elimină evaluarea celorlalte mențiuni.
Numai în matcherul produselor, aliasul neambiguu `rosie` acoperă și formele explicite
`rosii`, `rosiile`, `rosia`, `rosiei`, `rosiilor`, păstrând ID-ul catalogului; aliasurile
existente au prioritate, iar adjectivele de culoare nu identifică leguma. Antetul OCR
al unui tabel este moștenit numai din
textul indexat anterior aceleiași secțiuni; o nouă secțiune întrerupe moștenirea. Clasificarea
locală pozitivă verifică domeniul afecțiunii, nu doar existența unei instrucțiuni. Cazurile
nesigure păstrează întregul context pentru AI.
Regulile v4 elimină clasificarea directă `ingredient_quantity_only_v3`: o enumerare de
ingrediente sau cantități continuă prin celelalte reguli și, dacă acestea nu decid,
este evaluată de modelul local. Nu devine automat recomandare pozitivă. Schimbarea regulilor
cere o nouă pregătire/publicare a topurilor, dar permite reutilizarea deciziilor modelului
pentru text, context, prompt și model compatibile. Modificarea promptului schimbă cheia
cache-ului modelului; clasamentul deja publicat nu este modificat automat.
Prompturile de clasificare permit stabilirea afecțiunii din titlul secțiunii, fără repetarea
bolii pentru fiecare ingredient sau instrucțiune. Administrarea nu reprezintă singură o
precauție; `caution` cere o restricție efectivă pentru perechea evaluată.
Matcherul folosește numele și aliasurile existente, fără aliasuri de uleiuri deduse automat.
Contextul local limitează afecțiunile candidate; avertismentele despre alte afecțiuni,
excepțiile și relațiile nesigure merg la clasificatorul local.

Numele comune care indică mai multe identități de catalog și mențiunile din bibliografie
rămân neclare și nu adaugă puncte. Clasificatorul primește fiecare fragment integral într-un
singur câmp `units[].text`, fără segmente. Deciziile produs–afecțiune nu cer ID-uri de citat;
componenta separată `warnings` folosește catalogul de referințe descris mai sus.
Schema JSON impune toți
identificatorii relațiilor și doar trei răspunsuri factuale: `local_condition`,
`recommendation`, `prohibition`. Pozițiile mențiunilor și textul complet rămân în sursa locală;
validatorul găsește local dovada pentru persistență după răspuns.
Fiecare candidat include numele canonic în `condition` și toate sinonimele din catalog
în `condition_synonyms`, în ordinea lor din catalog, fără limitarea listei. Sinonimele
sunt denumiri echivalente ale țintei și sunt incluse atât în bugetul cererii, cât și în
cheia cache-ului; modificarea listei cere reevaluarea deciziei modelului.
Mențiunile repetate ale aceleiași perechi
produs–afecțiune dintr-o unitate primesc o singură evaluare, distribuită apoi tuturor
mențiunilor originale. Agregarea între unități rămâne separată; nicio mențiune nu este
omisă după găsirea unei contraindicații.
Atenționările locale certe se combină cu decizia modelului după evaluarea tuturor
mențiunilor, inclusiv când răspunsul provine din cache. Consultarea medicului înainte de
utilizarea unui produs impune precauție numai când aceeași afirmație numește explicit
produsul și afecțiunea candidat; negațiile și condițiile concurente rămân la AI.

Protocolul v8 cere trei fapte pentru fiecare relație: `local_condition`, `recommendation` și
`prohibition`. Ollama primește fragmentul integral într-un singur câmp, iar răspunsul nu
conține trimiteri la citate. Codul verifică numele local prin catalogul complet (inclusiv
sinonime și flexiuni, fără potrivire fuzzy), caută toate aparițiile lui în text și confirmă
mențiunea candidatului în sursă. Sinonimele formate dintr-o abreviere alfabetică scrisă cu
majuscule se verifică separat, păstrând majusculele: prepoziția „pe” nu identifică sinonimul
„PE”. Denumirile complete continuă să fie recunoscute fără diferențierea majusculelor.
Un titlu sau o introducere locală poate stabili afecțiunea
și când modelul omite numele. Un nume care identifică altă afecțiune este respins. Titlurile
Markdown, titlurile clinice scurte și formulările explicite „În tratarea X” delimitează
contextul; sunt recunoscute și titlurile clinice cu majuscule precedate de unul sau două
cuvinte OCR reziduale. Un context străin produce `unclear`. Recomandarea are prioritate față de interdicția
pentru aceeași relație în același fragment. Etichetele finale rămân `unclear`, `positive`,
`caution`; `mixed` se păstrează numai intern pentru contradicții între fragmente distincte.
`cache_semantics=6` separă deciziile validate după acest protocol de cele anterioare.
Promptul permite recomandarea unei plante ca ingredient indicat într-o rețetă terapeutică.
O enumerare botanică a speciilor dintr-un material natural nu transferă automat indicațiile
materialului asupra fiecărei specii.
Regulile v6 recunosc ca descriptive enumerările de plante întâlnite într-un habitat,
în lipsa unei afirmații terapeutice în aceeași propoziție; rețetele și listele administrate
pentru tratament continuă prin regulile existente sau model.
Listele de alternative preiau indicația tratamentului pe care îl continuă. Promptul cere
urmărirea schimbărilor de subiect din fragmentele OCR cu mai multe secțiuni; primul titlu
nu stabilește automat indicația tuturor produselor din fragment.
Listele explicite de produse recomandate, cu identitate neambiguă și afecțiune locală
confirmată, se păstrează ca dovezi pozitive și când modelul omite recomandarea. Dovada
locală se combină cu decizia brută a modelului, care este păstrată separat în cache.
Promptul de clasificare și contractul de transport sunt documente Markdown separate, scrise
în română fără diacritice. Primul stabilește regulile de decizie și legarea afecțiunii locale;
al doilea definește câmpurile JSON și transmiterea fragmentului integral. Deciziile
produs–afecțiune nu folosesc ID-uri de citat; referințele safety sunt independente.
Identitatea semantică include textul, contextul complet transmis, numele, mențiunile grupate,
politica de clasificare și digestul modelului. Versiunile regulilor și transportului sunt
separate: un transport schimbat nu invalidează aceleași decizii semantice. Cache-ul vechi
rămâne păstrat, fără declararea artificială a compatibilității cu noua politică.
Profilul rulării include și amprenta implementării regulilor; o modificare a acestora
cere o generație compatibilă nouă. Cache-ul deciziilor brute ale modelului rămâne separat
de această amprentă, iar regulile curente sunt reaplicate înaintea agregării finale.
Profilul verifică și politica extragerii metadatelor de catalog. Un alias complet și
neambiguu al afecțiunii poate verifica titlul; o potrivire parțială nu este suficientă.
Analizele pe unitate păstrează separat rolul produsului în tabel, administrarea explicită
și restricțiile. Un avertisment colectiv pentru suplimente se leagă de categoriile
corespunzătoare și de afecțiunea numită, apoi se combină cu rezultatul AI. Limitele de
doză recunoscute nu devin automat contraindicații pentru afecțiune.
Construcția loturilor serializează fiecare unitate o singură dată și caută binar cel
mai mare prefix care respectă toate bugetele, folosind anvelopa completă reală.

Loturile pot grupa fragmente complete scurte pentru aceeași afecțiune primară. Fragmentele
lungi, tabelele, condițiile multiple și excepțiile complexe se procesează separat. În loturile
obișnuite pot fi cel mult șase fragmente indexate. Fiecare fragment apare o singură dată,
întreg, în `units[].text`, indiferent de numărul relațiilor. Un fragment lung este trimis
integral, singur în cerere. Instrucțiunile, contextul și schema intră în plafonul configurabil
de 100.000 de caractere pentru cererea completă. Se păstrează maximum 20 de relații distincte.
Prompturile sunt înghețate și reverificate înainte de finalizare. Publicarea verifică din nou
profilul compatibil.

| Variabilă | Implicit | Rol |
|---|---|---|
| `HERB_ASSOCIATION_AI_BASE` | `CONDITION_AI_LOCAL_BASE`, altfel `http://localhost:11434/v1` | Numai localhost sau hostul Docker; Compose folosește implicit `host.docker.internal`. |
| `HERB_ASSOCIATION_AI_MODEL` | `qwen3.5:9b` | Independent de clasificarea conversațională și modelul raportului. |
| `HERB_ASSOCIATION_AI_MAX_UNITS` / `HERB_ASSOCIATION_AI_MAX_PAIRS` | `6` / `20` | Maximum șase fragmente integrale pentru loturile obișnuite; fragmentele prea mari se trimit izolat. Maximum 20 de relații distincte per cerere, indiferent de repetări. |
| `HERB_ASSOCIATION_AI_MAX_PASSAGE_CHARS` | `1000` | Prag pentru gruparea fragmentelor simple și limita dovezii scurte salvate local; nu împarte textul trimis la Ollama. |
| `HERB_ASSOCIATION_AI_MAX_INPUT_CHARS` | `100000` | Plafon tehnic pentru întregul request serializat, inclusiv promptul, contextul și schema. Depășirea oprește pregătirea; nu scurtează fragmentul. |
| `HERB_ASSOCIATION_AI_CONTEXT_TOKENS` / `HERB_ASSOCIATION_AI_MAX_OUTPUT_TOKENS` | `32768` / `2048` | Context și rezervă de răspuns. |
| `HERB_SAFETY_AI_CONTEXT_TOKENS` | `65536` | Fereastra pentru cererea de cunoștințe AI a unui singur produs; independentă de contextul clasificării. |
| `HERB_SAFETY_AI_MAX_OUTPUT_TOKENS` | `25000` | Plafon de ieșire pentru toate mesajele scurte ale produsului. |
| `HERB_SAFETY_AI_MAX_REQUESTS` | `10000` | Plafon de încercări per generație, inclusiv reluările. O cerere pentru fiecare produs fără cache. |
| `HERB_SAFETY_BUILD_TIMEOUT_SECONDS` | `86400` | Deadline al pregătirii safety; prima populare poate procesa întregul catalog. |
| `HERB_ASSOCIATION_AI_TIMEOUT_SECONDS` / `HERB_ASSOCIATION_BUILD_TIMEOUT_SECONDS` | `900` / `7200` | Buget per lot AI și limită de așteptare I/O, respectiv deadline per comandă. Timpul rămas al comenzii limitează fiecare lot. |
| `HERB_ASSOCIATION_AI_KEEP_ALIVE_SECONDS` | `3600` | Numai pentru reindexare: păstrează modelul Ollama până la 60 de minute de inactivitate între cereri, inclusiv cele pentru safety. `0` descarcă după fiecare cerere; `-1` păstrează nelimitat între cereri. La încheierea fluxului, CLI-ul solicită oricum descărcarea imediată. |
| `HERB_ASSOCIATION_AI_MAX_REQUESTS` | `1000` | Plafon de încercări pentru RUN_ID, inclusiv la reluare. |

Toate variabilele sunt validate de `Settings` și propagate prin Compose. Se folosește un
singur request în zbor, temperatură zero și JSON cu schemă strictă, fără retry/fallback.
Clasificările și cererile separate de cunoștințe despre produse folosesc streaming
nativ Ollama în același POST. Bucățile sunt reunite intern; validarea JSON și salvarea
în cache au loc după primirea marcajului final. Un flux întrerupt ori un timeout nu
salvează un rezultat incomplet. Bugetul de 900 de secunde este verificat între bucăți
și la ieșirea din lot, împreună cu deadline-ul comenzii; I/O păstrează limita de așteptare.

Fiecare cerere produce în stdout evenimente JSON cu `stage=herb_ai_batch`,
`event=started` și `event=completed`/`failed`. Sunt incluse:

- Rularea, tipul (`associations` sau `product_safety`), numărul lotului, modelul,
  contextul, limita de ieșire și limitele de timp configurată/efectivă.
- Numărul fragmentelor/țintelor și lungimile sursei, payloadului și system promptului.
- `herb_id` și `safety_source=model_knowledge` pentru noua analiză per produs;
  `warning_items_max_total` este un câmp istoric al extracției pe fragmente, zero aici.
- Durata lotului, timpul până la prima bucată și primul text, ultima activitate,
  numărul evenimentelor și numărul de caractere primite, fără conținutul lor.
- Timpii Ollama de încărcare, procesare a promptului și generare, tokenii de intrare,
  tokenii de prompt din cache, tokenii generați și viteza generării.
- Tipul erorii și un motiv tehnic controlat, fără mesaje brute de la furnizor.

Valorile native care lipsesc, inclusiv la întreruperea fluxului, sunt `null`. Duratele
native sunt convertite din nanosecunde în milisecunde; `duration_ms` măsoară lotul complet,
inclusiv validarea/salvarea. Evenimentele de lot și heartbeat-urile sunt serializate pe
linii JSON distincte. Streamingul și metricele păstrează loturile, numărul cererilor și
amprentele cache-urilor semantice; nu se adaugă cereri pentru diagnostic ori retry automat.

Conform ajustării din 23 octombrie, procesarea și controlerul operatorului nu verifică
temperatura GPU, nu opresc la 82°C și nu introduc pauze termice sau preventive.
Frecvența GPU este administrată de utilizator.
Se verifică setul exact de candidați și citatele exacte; rezultatele incomplete sunt respinse.
Citatele valide dovedesc proveniența, nu corectitudinea semantică. Numărul de caractere nu
măsoară tokenii. Plafonul cererii limitează memoria, iar Ollama verifică fereastra reală de
tokeni cu `truncate=false` și `shift=false`; depășirea este o eroare explicită, fără
reîncercare cu un fragment scurtat. Calibrarea pe modelul real rămâne necesară.

Cache-ul păstrează numai etichete și poziții relative validate, inclusiv `unclear`, fără
text integral sau răspunsuri brute. Cheia include pasajul/contextul, candidatul și numele
sale, politica promptului, configurația semantică și digestul modelului. Versiunea regulilor
și forma transportului nu schimbă singure cheia unei decizii brute. Timeouturile
nu schimbă cheia. Loturile reușite sunt salvate în tranzacții scurte, fără conexiuni DB sau
lockuri ținute în timpul inferenței. O reluare explicită recuperează numai lipsurile;
același input și digest produc zero cereri noi de clasificare. După un input schimbat,
se începe o rulare nouă care poate reutiliza intrările de cache neafectate.

Topurile nu cheamă clasificatorul și funcționează cu Ollama oprit dacă rularea publicată
este validă. Returnează până la X intrări cu scor strict pozitiv; nu completează cu zerouri.
Categoria fără rezultate este un rezultat valid. Lipsa unei rulări valide dă 503
`POSITIVE_RANKING_NOT_READY`, iar schimbarea inputului/configurației dă
`POSITIVE_RANKING_STALE`; nu există revenire la scorul istoric. Codurile indexului de bază
rămân aplicabile. Comanda normală de indexare actualizează automat topurile la final,
cu excepția folosirii `--skip-positive-ranking`. Până la publicarea noii rulări, un top
vechi incompatibil rămâne indisponibil; nu se afișează rezultate parțiale sau istorice.

Evaluarea offline folosește loturi reprezentative, inclusiv fructe/cereale, și un eșantion
independent de 80 de unități și minimum 100 de relații. Pentru activarea din 23 octombrie,
utilizatorul a acceptat precizia măsurată de 89,33% pe eșantioanele deja revizuite și
accelerarea existentă, fără un prag minim suplimentar de viteză. Aceasta nu certifică o
evaluare independentă a profilului final sau o accelerare de 2×. Evaluările de precizie
și viteză nu sunt executate automat de fiecare indexare; publicarea automată verifică
integritatea, acoperirea completă și compatibilitatea surselor, profilului și modelului.
Pentru comparațiile de viteză, folosiți două rulări fără cache pentru fiecare variantă,
pe același snapshot și model; excludeți eventualele pauze din `classification_seconds`.
Păstrați rularea anterioară și comparați hashurile/xmin ale indexului, coaparițiilor și
scorurilor istorice în evaluările care nu modifică indexul.
Revenirea la un pointer anterior necesită o operație explicită, cu același manifest încă
valid; o rulare veche nu poate fi republicată peste una nouă prin comanda obișnuită.
Progresul clasificării afișează la circa 60 de secunde numai ID-uri și agregate, durată,
rată și câmpurile `elapsed(hh:mm:ss)` și `ETA(hh:mm:ss)`, de exemplu
`"elapsed(hh:mm:ss)": "00:10:00"` și `"ETA(hh:mm:ss)": "02:10:05"`.
Până când poate fi estimat timpul rămas, `ETA(hh:mm:ss)` este `null`. Tranzițiile și finalizarea
sunt raportate imediat.
`ai_requests_sent_total` arată numărul cererilor de clasificare lansate în execuția curentă,
inclusiv cele care eșuează; `requests` păstrează același contor. Rezultatele din cache,
regulile locale și verificările digestului modelului nu sunt cereri de clasificare.
`batches` este numărul planificat de cereri. După publicare, linia
`"stage": "positive_ranking_summary"` reia totalul trimis în etapa de pregătire.
La o reluare, contorul afișat include numai cererile noi din acea execuție; limita cumulată
pentru `RUN_ID` continuă să fie verificată separat în baza de date.

## 📦 Schema indexului hibrid (Postgres)

Tabelele principale ale indexului, catalogului și migrărilor sunt:

| Tabel | Conținut |
|---|---|
| `documents` | Un rând per fișier sursă: cale, SHA-256, codificare, număr de linii; categoria (folderul) este o coloană generată din cale. Folosit și pentru a decide ce fișiere sar la sincronizarea următoare. |
| `medical_conditions` | `id`, `name` (numele canonic românesc) și `en` (echivalentul englezesc, completat prin SQL); identitatea afecțiunii este comună ambelor limbi. |
| `medical_condition_synonyms` | Numai `id`, `medical_condition_id` și `synonym`: sinonimele legate prin FK de afecțiune. |
| `herbs` | Coloane fizice `id, category, family, latin, ro, en, ranking`; ID numeric identity. Plantele păstrează denumirile/familiile lowercase și un nume latin unic; produsele au `latin = NULL` și păstrează capitalizarea cerută pentru `ro`/`en`. Unicitatea numelui produsului (`lower(btrim(ro))`) este comună tuturor celor zece categorii de produse, inclusiv `seminte`. Intrările botanice folosesc `plante medicinale`, `fructe`, `legume` sau `cereale`; `family` păstrează familia botanică originală. Pentru produse, categoria tehnică se află numai în `category`, iar `family` este SQL NULL. `ranking` numără afecțiunile distincte asociate din titlurile fragmentelor. Numele populare pot fi comune mai multor specii. |
| `herb_aliases` | Coloane `id, herb_id, name, kind`; aliasuri lowercase, FK cu ștergere în cascadă, tipuri `ro_regional`, `latin_synonyms`, `en_alt`. |
| `herbs_benefits` | Asocieri derivate din coapariția în corpus: `id, herb_id, medical_condition_id, language`; pereche unică per limbă, FK cu ștergere în cascadă și indecși individuali. Publicate atomic la finalul reindexării. |
| `schema_migrations` | Ledgerul migrărilor SQL aplicate o singură dată. |
| `owner_sessions` | Autorizări owner persistente: hashuri și metadata tehnică; fără conversații sau rapoarte. |
| `chunks` | Un rând per fragment, cu `language` (`ro`/`en`, RO pentru rândurile existente): text, interval de linii, calea titlurilor (`heading`), categoria generată din cale (`category_id`, folosită de filtrarea pe surse), `business_category` (`R1`/`R2`/`D1`), `primary_medical_conditions`, `secondary_medical_conditions`, vectorul semantic (`embedding vector(1024)`) și coloana lexicală (`text_search tsvector`). |
| `sync_metadata` | Modelul, dimensiunea, profilul pasajelor, versiunea textului, fingerprintul SHA-256 al dicționarului, generația indexului, data sincronizării și cele cinci marcaje `herbs_benefits_*`. |

Dacă profilul indexului și fingerprintul catalogului sunt neschimbate, un document cu același SHA-256 este ignorat la sincronizare; un document nou sau modificat își înlocuiește fragmentele într-o singură tranzacție.

Fragmentarea (`src/backend/ai/fragmenter.py`) citește afecțiunile din `medical_conditions` și sinonimele din `medical_condition_synonyms`, în ordinea ID-urilor de inserare. Python adaugă numele canonic în lista termenilor de potrivire, fără să-l dubleze în tabela sinonimelor. Apoi aplică pe rând:

| Categorie | Criteriu |
|---|---|
| **R1** | Titlul unui capitol Markdown numește o afecțiune → titlul și tot subarborele lui rămas liber (subcapitolele cu afecțiune proprie devin fragmente separate). |
| **R2** | Textul propriu al unui capitol rămas (până la următorul titlu) menționează o afecțiune → titlul și acel text. |
| **D1** | Restul textului (inclusiv documentele fără titluri) → bucăți de ~1800 de caractere (1500–2100), tăiate la sfârșit de paragraf sau propoziție, cu suprapunere de cel mult 270 de caractere. |

Afecțiunile se caută pe cuvinte întregi, fără diacritice și majuscule, cu toleranță la terminațiile românești (`gripa`/`gripei`). Numele fișierului și al folderelor nu se compară cu afecțiunile. Fragmentele R1 și R2 primesc `primary_medical_conditions` (afecțiunile din titlu) și `secondary_medical_conditions` (afecțiunile din text); D1 nu are afecțiuni. R1 și R2 nu au limită de lungime.

La căutare, fiecare fragment primește scorul `4·P1 + 2·P2 + L + V` (maximum 8, cu toate semnalele bifate): P1 = afecțiunea căutată este în `primary_medical_conditions`, P2 = este în `secondary_medical_conditions`, L = fracțiunea de expresii (separate prin virgulă) regăsite în fragment, V = similaritatea semantică rescalată între mediana și maximul căutării. Pacientul poate debifa semnale în panoul „Surse și opțiuni de căutare”, iar formula se adaptează (de exemplu `L + V` sau doar `2·P1 + P2`). Scorul nu se stochează în DB; detaliile sunt în [fragment-search-and-scoring.xmind](architecture/fragment-search-and-scoring.xmind).

Pentru embeddings, un fragment mai lung de 1400 de caractere este împărțit în ferestre care se suprapun cu 240, iar vectorii lor se mediază (valorile, dimensiunea vectorilor și prefixele de text ale fiecărui model sunt în profilul lui din `ai/embedding_model.py`). Diacriticele sunt păstrate prin normalizare Unicode NFC.

## 🐳 Rulare cu Docker Compose

Înainte de build/pornire, trebuie să existe `medicina-naturista-documente/data/documents/`, `model_cache/` (cu modelul de embeddings deja descărcat: containerul rulează offline) și fișierul local `.env` cu cheia furnizorului AI ales (`X_API_KEY`, `DEEPSEEK_API_KEY`, `HF_TOKEN` sau `OLLAMA_API_KEY`), `POSTGRES_PASSWORD` și `OWNER_KEY`. Stiva are două servicii: `db` și `app`. Serviciul `db` (Postgres 16 + `pgvector`, cu `shared_buffers=512MB`) este expus doar pe `127.0.0.1:5432` (`DB_HOST_PORT`), astfel încât indexul se sincronizează de pe host cu `python src/scripts/build_hybrid_index.py` (cu `PYTHONPATH=src` și un `DATABASE_URL` spre `127.0.0.1` cu parola `POSTGRES_PASSWORD`).

**Ollama rulează separat, pe host (Windows), și trebuie pornit înaintea aplicației.** Containerul `app` îl accesează prin `http://host.docker.internal:11434/v1`, atât pentru clasificarea mesajelor și identificarea afecțiunilor (`CONDITION_AI_LOCAL_BASE`), cât și pentru rapoartele cu `ollama-gemma4:12b` (`OLLAMA_API_BASE`). Descărcați modelul de raport cu `ollama pull gemma4:12b` și modelul ales în `MEDICAL_CONDITION_AI_LOCAL_MODEL` (implicit `gemma3:1b`). Modelele sunt administrate de instalarea Ollama de pe host.

Pentru rapoartele Ollama, clientul derivă `/api/chat` din `OLLAMA_API_BASE` eliminând sufixul `/v1`. Folosește format JSON nativ, `truncate=false` și `shift=false`: intrarea nu este scurtată automat și nu sunt eliminate porțiuni din context pentru a continua generarea. O depășire a contextului este raportată ca `AI_CONTEXT_LIMIT_EXCEEDED`, cu mesajul de a selecta mai puține fragmente sau de a crește scorul minim. R1 8B are context explicit per cerere; pentru celelalte modele, dacă nu există un override, se păstrează configurația serverului Ollama. Loturile folosesc bugete conservative de tokeni de intrare; acestea nu înlocuiesc contextul real verificat de Ollama. Intrarea, instrucțiunile și ieșirea trebuie să încapă împreună în context. Clasificarea mesajelor și identificarea afecțiunilor folosesc și ele clientul nativ `/api/chat`, cu `think=false`, pentru a trimite durata de păstrare în aceeași cerere.

Aplicația trimite `keep_alive=60` pentru fiecare cerere Ollama: modelul este eliberat după
60 de secunde de inactivitate, fără preîncărcare la pornirea aplicației. Reindexarea folosește
separat `keep_alive=3600`. La încheierea reindexării sau a unei pregătiri explicite de ranking/safety,
`build_hybrid_index.py` trimite o cerere de control fără prompt, cu `keep_alive=0`, pentru modelul
de indexare configurat. Descărcarea este solicitată și la eroare sau Ctrl+C; o oprire forțată a
procesului poate sări peste cleanup. Analiza, publicarea separată, proiecția caution fără AI și
`--skip-positive-ranking` nu descarcă modelul. Evenimentul `index_model_release` confirmă
`released` numai după răspunsul Ollama; la eșec afișează `warning` fără să schimbe rezultatul
indexării. Cererea de control nu generează text și nu intră în numărul de cereri de inferență.

Pentru `gemma4:12b` cu contextul maxim de 262.144 tokeni, configurația de performanță măsurată pe GPU-ul local folosește următoarele variabile **pe Windows**, în PowerShell:

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q4_0", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "2", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "262144", "User")
```

Închideți complet Ollama din zona de notificări și porniți-l din nou din Start. Verificați în jurnalul `%LOCALAPPDATA%\Ollama\server.log` valorile efective și `offloaded …/49`; aplicația desktop poate avea setări proprii. Aceste variabile configurează serverul Ollama, nu clientul Python: adăugarea lor în `.env` sau în mediul serviciului Compose `app` nu schimbă Ollama de pe host.

`q4_0` reduce precizia cache-ului KV; măsurarea vitezei nu validează calitatea rapoartelor la intrări lungi. Pentru procesarea efectiv simultană a loturilor, serverul Ollama trebuie să permită cel puțin numărul de cereri per model configurat prin `REPORT_BATCH_WORKERS` (implicit `OLLAMA_NUM_PARALLEL>=2`). Dacă permite una singură, cererile trimise de aplicație pot fi procesate succesiv. Contextele simultane necesită mai multă memorie; nu este garantată accelerarea și nu se modifică automat configurația serverului. Aplicația păstrează separat `MAX_CONCURRENT_GENERATIONS=1`. Rezultatele locale istorice și limitele măsurării sunt în [investigația Ollama](aiPlans/2026-10-15-investigare-performanta-ollama.md).

```dotenv
CONDITION_AI_LOCAL_BASE=http://host.docker.internal:11434/v1
MEDICAL_CONDITION_AI_LOCAL_MODEL=gemma4:12b
CONDITION_AI_TIMEOUT_SECONDS=30
MESSAGE_CLASSIFICATION_TIMEOUT_SECONDS=30
```

Cele două timeouturi din exemplu sunt de 30 de secunde. Clasificarea și identificarea locală cer `reasoning.effort=none`, astfel încât modelele cu „thinking” să folosească bugetul de răspuns pentru JSON-ul final.

Pentru verificarea conexiunii din container:

```powershell
docker compose exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/version', timeout=5).read().decode())"
```

După schimbarea configurației din `.env`, recreați aplicația cu `docker compose up -d --no-deps --force-recreate app`. Dacă migrați de la vechiul serviciu Ollama, opriți și eliminați numai containerul vechi cu `docker stop medicina-ollama` și `docker rm medicina-ollama`; volumul său cu modele poate fi păstrat pentru recuperare. Modelele necesare trebuie descărcate separat în Ollama de pe host.

Sincronizați indexul după pornirea serviciului `db`, înainte de a folosi căutarea.

```powershell
docker compose up -d --build
docker compose ps
Invoke-WebRequest http://localhost:8760/healthz
```

Aplicația este publicată pe host la `127.0.0.1:8760` (`APP_HOST_PORT`; în container rămâne portul 7860, iar 8760 evită intervalul de porturi rezervat de Windows) și publicat prin Tailscale Funnel, care gestionează HTTPS. Rulează într-un container read-only, fără capabilități Linux suplimentare, ca utilizator non-root. Documentele sunt montate read-only, iar directoarele temporare folosesc `tmpfs`. Indexul locuiește în Postgres (volum named `pg_data`), nu mai e nevoie de bind-mount sau de oprirea aplicației la resincronizare.

Oprire fără ștergerea volumelor:

```powershell
docker compose down
```

> [!WARNING]
> `docker compose down -v` șterge volumele named declarate în Compose: indexul din Postgres (`pg_data`). Modelele Ollama de pe host sunt administrate separat.

### Publicare prin Tailscale Funnel

Pe Windows, Tailscale Funnel trimite cererile direct către portul local al aplicației, fără Nginx sau Caddy pe această cale. Prefixul `/medicina` permite publicarea ulterioară a altor aplicații pe același hostname. Portul `8760` rămâne legat exclusiv de `127.0.0.1`.

În `.env`, setați `PUBLIC_ORIGIN=https://cristiantone.taila68086.ts.net` (originea exactă a dispozitivului Tailscale) și păstrați `COOKIE_SECURE=true`. `PUBLIC_ROOT_PATH` rămâne `/medicina`, valoarea implicită din Compose. Adăugați în `FORWARDED_ALLOW_IPS` numai adresa gateway-ului Docker prin care ajung cererile proxy-ului de pe host; la această instalare este `172.20.0.1`, verificată în jurnalul cererilor. Nu folosiți `*` sau întreaga subrețea: Tailscale înlocuiește headerele forwarded, iar Uvicorn trebuie să le accepte numai de la proxy-ul cunoscut. Adresele gateway-ului se pot schimba dacă rețeaua Docker este recreată.

După schimbarea `.env`, recreați numai aplicația:

```powershell
docker compose up -d --no-deps --force-recreate app
```

Cu Tailscale instalat și conectat la cont, porniți Funnel din PowerShell:

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" funnel --bg --set-path=/medicina http://127.0.0.1:8760
& "C:\Program Files\Tailscale\tailscale.exe" funnel status
```

La prima utilizare, urmați linkul de activare afișat de Tailscale. Aplicația va fi disponibilă la `https://cristiantone.taila68086.ts.net/medicina/`, iar verificarea de disponibilitate la `/medicina/readyz`. Hostname-ul exact poate fi aflat din `tailscale status --json`, câmpul `Self.DNSName`. Pentru alt hostname, actualizați și `PUBLIC_ORIGIN` și adresa de dezvoltare `DEV_BACKEND_URL`.

`--bg` păstrează configurația Funnel după restart. Pentru acces înainte de autentificarea în Windows, activați `Preferences → Run unattended` în Tailscale; Docker și containerul aplicației trebuie să fie pornite separat. Verificați și expirarea cheii dispozitivului în consola Tailscale pentru funcționare continuă. Pentru a opri numai ruta acestei aplicații:

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" funnel --bg --set-path=/medicina http://127.0.0.1:8760 off
```

Migrarea acestei aplicații nu necesită modificarea proxy-ului Nginx comun sau oprirea ngrok pentru celelalte proiecte. Serviciul și configurația Caddy au fost eliminate; HTTPS este administrat de Tailscale. Accesul vechi la Medicina Naturistă prin ngrok nu mai este originea autorizată pentru cererile de modificare după schimbarea `PUBLIC_ORIGIN`.

## Limba aplicației și textele fixe

Selectorul „Română / English” din antet schimbă limba interfeței și a operațiunilor
următoare. Prima vizită folosește RO; preferința este salvată în `localStorage` pentru
taburile noi. Taburile deja deschise își păstrează limba. Schimbarea este blocată cât timp
există o operațiune activă în acel tab și nu recreează sesiunea sau istoricul.

Fiecare mesaj, căutare și raport păstrează limba originală. Acțiunile asupra rezultatelor
istorice folosesc acea limbă: un raport generat dintr-o căutare RO rămâne RO chiar dacă
interfața a trecut la EN, inclusiv PDF-ul și emailul. Pentru un raport EN este necesară o
căutare EN nouă. Căutarea EN nu folosește fragmente RO când lipsesc rezultate EN.

Textele sunt în două cataloage UTF-8 independente:
`src/backend/resources/texts.ro.toml` și `src/backend/resources/texts.en.toml`.
Catalogul RO a fost păstrat neschimbat la introducerea limbii EN. Ambele au exact aceleași
468 de chei și aceiași parametri numiți. Secțiunile `common` și `interface` sunt publice;
`conversation`, `errors`, `authorization`, `report` și `email` rămân pe backend.
Cheile lipsă, necunoscute, parametrii incompatibili sau HTML-ul opresc validarea;
nu există fallback al textelor EN către RO.

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe -m scripts.manage_texts
.venv/Scripts/python.exe -m scripts.manage_texts --public-json --language en
```

Bootstrapul HTML transmite ambele cataloage publice înainte de pornirea React.
`GET /api/texts?language=en` expune catalogul public EN; fără limbă, răspunsul compatibil
este RO. Cererile UI trimit `X-App-Language: ro|en`; navigarea către autorizare folosește
un parametru de limbă validat. `POST /api/language` schimbă preferința sesiunii fără a
șterge conversația. HTML-ul și textele publice sunt `no-store`.

Backendul și fiecare worker folosesc un context izolat de limbă derivat din snapshotul
operațiunii, fără modificarea unui client AI global. Prompturile RO rămân în
`ai/prompts/`; variantele EN sunt în `ai/prompts/en/`, cu aceleași chei JSON și reguli de
citare. Clasificarea și identificarea afecțiunilor rămân exclusiv locale. Avertizările
produselor sunt pregătite la reindexare pentru ambele limbi, cu cache și generații active
separate; consultarea din UI nu inițiază apeluri AI.

`medical_conditions.en` este populat prin migrare SQL din aliasurile bilingve ale
catalogului, fără schimbarea ID-urilor și fără traducere AI la runtime. Produsele folosesc
`herbs.en`; când nu există un nume comun EN, se păstrează numele științific. Completările
ulterioare de afecțiuni prin `scripts.condition_sql.additions_sql` trebuie să furnizeze
explicit `Condition.english`. Clasificarea surselor și verificarea citărilor nu reprezintă
validare medicală a traducerilor sau a recomandărilor.

În UI, denumirile produselor folosesc dicționarul limbii operației: `ro_RO` pentru RO
și `src/scripts/dictionaires/en/en_GB.dic` / `en_GB.aff` pentru EN. La recunoașterea
denumirilor EN se acceptă pluralurile validate de regulile nominale ale dicționarului,
inclusiv în numele alternative și expresiile cu mai multe cuvinte. Numele latine rămân
exacte; prefixele și derivările care schimbă sensul nu extind potrivirile. Afișarea
păstrează formele ambigue sau necunoscute. Cache-urile cataloagelor sunt separate pe
limbă; mesajele introduse și documentele nu sunt corectate automat de această integrare.
Catalogul afecțiunilor din PostgreSQL rămâne separat de dicționarul ortografic Hunspell.

La modificări de chei/parametri, `python -m scripts.manage_texts --generate` regenerează
numai metadatele comune Python/TypeScript. Nu dublează mesajele în frontend. Compose
montează ambele cataloage read-only. Activarea codului nou cere reconstruirea aplicației;
editarea ulterioară numai a valorilor cere repornirea procesului și reîncărcarea paginii.
Vite în dezvoltare trebuie conectat la un backend care include contractul bilingv.

## ⚙️ Configurare

Fișierul `.env` este ignorat de Git. Valorile principale recunoscute de aplicație sunt:

| Variabilă | Implicit | Rol |
|---|---:|---|
| `X_API_KEY` | — | Cheia xAI (necesară la utilizarea modelului `grok-4.3`). |
| `XAI_REASONING_EFFORT` | `medium` (direct) / `low` (Docker Compose) | Nivelul de reasoning solicitat. |
| `XAI_API_BASE` | `https://api.x.ai/v1` | URL-ul de bază al API-ului xAI. |
| `HF_TOKEN` | — | Token Hugging Face cu permisiunea „Make calls to Inference Providers”; necesar la utilizarea modelului `huggingface-deepseek-v4-flash`. |
| `HF_API_BASE` | `https://router.huggingface.co/v1` | URL-ul de bază al routerului HF; clientul apelează ruta `/responses`. |
| `HF_REASONING_EFFORT` | _(gol)_ | `low`/`medium`/`high`; se trimite doar dacă este setat. |
| `HF_MAX_CONTENT_TOKENS` | `120000` | Buget conservator pentru totalul fragmentelor selectate pentru `huggingface-deepseek-v4-flash`, inclusiv ID-urile și sursele serializate. Un token bugetat per octet UTF-8; separat de limita cererii pe lot și de ieșire. |
| `DEEPSEEK_API_KEY` | — | Cheia API de pe platform.deepseek.com, necesară când adminul alege `deepseek-flash`. Lipsa ei nu blochează rapoartele Ollama. |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | URL-ul de bază al API-ului DeepSeek. |
| `DEEPSEEK_REASONING_EFFORT` | _(gol)_ | Se trimite doar dacă este setat. |
| `DEEPSEEK_MAX_CONTENT_TOKENS` | `1000000` | Buget conservator pentru totalul fragmentelor selectate pentru `deepseek-flash`, inclusiv ID-urile și sursele serializate. Un token bugetat per octet UTF-8; separat de limita cererii pe lot și de ieșire. |
| `OLLAMA_API_BASE` | `http://localhost:11434/v1` | Baza Ollama; în Docker Compose `http://host.docker.internal:11434/v1`. |
| `OLLAMA_KEEP_ALIVE_SECONDS` | `60` | Durata de păstrare după ultima cerere Ollama din aplicație (raport, clasificare sau identificare). `0` descarcă după fiecare cerere. Nu modifică dimensiunea contextului și nu controlează reindexarea. |
| `OLLAMA_API_KEY` | — | Necesară doar când `OLLAMA_API_BASE` nu este local (ex. `https://ollama.com/v1`). |
| `OLLAMA_REASONING_EFFORT` | _(gol)_ | Pentru Gemma4 și Qwen3.5, controlează `think`: `none` îl dezactivează, celelalte valori îl activează. Pentru Gemma3 și Ministral este omis. |
| `OLLAMA_MAX_CONTENT_TOKENS` | `1000000` | Buget conservator pentru totalul fragmentelor selectate pentru Ollama, inclusiv ID-urile și sursele serializate. Un token bugetat per octet UTF-8. Limitează conținutul total înainte de împărțirea în loturi; nu setează contextul Ollama și nu include promptul sau ieșirea. |
| `OLLAMA_NUM_CTX_BY_MODEL` | `{"ollama-deepseek-r1:8b":32768}` | Obiect JSON cu contextul în tokeni per model Ollama din catalog. Cheile omise păstrează valorile implicite; celelalte modele nu trimit `num_ctx` dacă nu sunt configurate explicit. |
| `OLLAMA_MAX_OUTPUT_TOKENS_BY_MODEL` | `{"ollama-deepseek-r1:8b":8192}` | Obiect JSON cu limita de ieșire per model Ollama. Pentru celelalte modele se păstrează limita globală. Valorile trebuie să fie întregi pozitive, iar ieșirea trebuie să fie mai mică decât contextul explicit. Cheile necunoscute, modelele externe și duplicatele sunt respinse. |
| `MEDICAL_CONDITION_AI_LOCAL_MODEL` | `gemma3:1b` | Modelul Ollama local pentru clasificarea mesajului și identificarea afecțiunii; se descarcă pe host cu `ollama pull <model>`, inclusiv când aplicația rulează în Docker. |
| `REPORT_GENERATION_MODELS` | cele 9 modele în ordinea catalogului de mai jos | Listă CSV ordonată a modelelor disponibile. Primul este implicit. Ordinea din UI este aceeași; drepturile controlează generarea, nu vizibilitatea opțiunilor. Listele goale, elementele goale, modelele necunoscute și duplicatele sunt respinse la pornire. Alegerea din UI se aplică numai jobului respectiv. |
| `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL` | `24000` pentru R1 8B, `25000` pentru celelalte | Obiect JSON cu bugete conservative de tokeni de intrare per lot și model. Include cererea serializată completă și o rezervă de 256 tokeni; numărare locală la un token bugetat per octet UTF-8. Lipsă/valoare goală → valorile implicite; un obiect explicit trebuie să includă fiecare model activat. |
| `REPORT_BATCH_WORKERS` | `2` | Întreg pozitiv: numărul maxim de loturi procesate simultan în raportul activ. `1` procesează succesiv. Nu modifică limita de un singur raport activ. Este transmis explicit aplicației prin Docker Compose. |
| `CONDITION_AI_LOCAL_BASE` | `http://localhost:11434/v1` (direct) / `http://host.docker.internal:11434/v1` (Compose) | Adresa Ollama de pe host, folosită pentru clasificarea mesajului și identificarea afecțiunii. |
| `CONDITION_AI_TIMEOUT_SECONDS` | `10` | Timeout pentru identificarea afecțiunii prin Ollama local. |
| `MESSAGE_CLASSIFICATION_TIMEOUT_SECONDS` | `10` | Timeout la clasificare prin Ollama local, independent de identificarea afecțiunii. |
| `MESSAGE_CLASSIFICATION_MAX_OUTPUT_TOKENS` | `300` | Bugetul JSON de clasificare. |
| `CONDITION_AI_MAX_OUTPUT_TOKENS` | `300` | Limita răspunsului (un JSON mic) la identificarea afecțiunii. |
| `REPORT_GENERATION_AI_STREAM` | `false` | Cere răspunsul ca flux de evenimente (`stream: true`). Timeoutul de citire se aplică între evenimente, deci evită tăierea cererilor lungi de un proxy (ex. 504 după 60 s la routerul HF). Dacă furnizorul nu suportă streaming, lăsați `false`. |
| `REPORT_GENERATION_MAX_OUTPUT_TOKENS` | `20000` | `max_output_tokens` al cererii, pentru toți furnizorii (la modelele cu gândire, reasoning-ul consumă din el). |
| `REPORT_GENERATION_READ_TIMEOUT_SECONDS` | `300` | Timeoutul de citire al cererii către furnizorul AI. |
| `DOCUMENTS_DIR` | `medicina-naturista-documente/data/documents` | Directorul documentelor locale. |
| `HERB_IMAGES_DIR` | `medicina-naturista-documente/data/images` | Directorul opțional cu pozele PNG ale produselor; montat doar pentru citire în Docker. |
| `DATABASE_URL` | `postgresql:// medicina:medicina @127.0.0.1:5432/medicina` | Conexiunea Postgres a indexului hibrid (`pgvector` + `tsvector`). |
| `DATABASE_BOOTSTRAP_URL` | gol | Conexiune de mentenanță opțională pentru crearea unei baze lipsă, pe același server ca `DATABASE_URL`; folosită numai de reindexare. Implicit se folosesc credențialele țintei pe baza `postgres`. |
| `MODEL_CACHE_DIR` | `model_cache` | Directorul cache-ului local al modelului ONNX. |
| `EMBEDDING_THREADS` | `8` (cel mult numărul de nuclee) | Firele de execuție ale modelului de embedding (ONNX Runtime), la indexare și la căutare. Pe procesoare hibride P/E-core, mai puține fire sunt de obicei mai rapide decât toate nucleele. |
| `EMBEDDING_DEVICE` | `cpu` | Dispozitivul modelului de embedding la **construirea** indexului: `cpu` (FastEmbed/ONNX) sau `cuda` (PyTorch fp16, doar din mediul GPU `.venv-gpu`; fără CUDA build-ul se oprește, nu trece pe CPU). Întrebările din aplicație rulează mereu pe CPU. |
| `SESSION_TEMP_DIR` | `var/sessions` (Windows) / `/tmp/naturist-sessions` | Directorul fișierelor temporare ale sesiunilor. |
| `MAX_CHAT_CHARS` | `4000` | Lungimea maximă a mesajului utilizatorului. |
| `X_AI_MAX_CONTENT_TOKENS` | `1000000` | Buget conservator pentru totalul fragmentelor selectate pentru `grok-4.3`, inclusiv ID-urile și sursele serializate. Un token bugetat per octet UTF-8. Toate fragmentele primesc scor și se păstrează prefixul în ordinea scorului, fără trunchiere. Separat de limita cererii pe lot și de ieșire. |
| `MAX_REQUESTS_PER_MINUTE` | `60` | Limita de cereri `POST`/`PUT`/`PATCH`/`DELETE` către `/api/`, pe minut și IP; loginul owner are o limită separată. |
| `SESSION_IDLE_SECONDS` | `3600` | Expirarea unei sesiuni inactive. |
| `SESSION_MAX_SECONDS` | `14400` | Durata maximă a unei sesiuni. |
| `MAX_ACTIVE_SESSIONS` | `100` | Numărul maxim de sesiuni în proces. |
| `NEW_SESSIONS_PER_COOKIE_MINUTE` | `5` | Numărul de conversații noi pe minut pentru același cookie de browser; reîncărcarea paginii deschide o conversație nouă. Instalarea locală folosește `60`, prin `.env`. |
| `NEW_SESSIONS_PER_IP_MINUTE` | `10` | Numărul de conversații noi pe minut pentru același IP. Instalarea locală folosește `120`, prin `.env`. La depășire, răspunsul `429` include `Retry-After` cu timpul rămas până la eliberarea cotei. |
| `MAX_API_BODY_BYTES` | `262144` | Dimensiunea maximă a corpului unei cereri API. |
| `MAX_CONCURRENT_SEARCHES` / `MAX_CONCURRENT_GENERATIONS` | `2` / `1` | Două căutări simultane; generarea rapoartelor este serială (valoarea 1 este obligatorie). |
| `MAX_QUEUED_GENERATIONS` | `20` | Numărul maxim de rapoarte în așteptare, pe lângă raportul în execuție. |
| `OPERATION_TIMEOUT_SECONDS` | `600` | Durata totală acceptată pentru o operație. |
| `DEPLOYMENT_PROFILE` | `local` | `public` validează HTTPS, cookie-uri securizate și dezactivarea logării de conținut; trebuie transmis explicit în Compose. |
| `COOKIE_SECURE` | `false` (direct) / `true` (Compose) | Impune transmiterea cookie-ului numai prin HTTPS. |
| `OWNER_KEY` | _(gol)_ | Cheie secretă lungă, introdusă în formularul `/owner` și trimisă prin `POST /api/owner/login`. Autorizările individuale persistă în PostgreSQL până la logout; rotația cheii le invalidează. Cookie-ul este reînnoit cu Max-Age de 365 de zile la activitate autorizată. |
| `LOG_LEVEL` | `INFO` | Nivelul minim al logurilor. |
| `LOG_FRAGMENT_TEXT` | `false` (direct) / `true` (Compose) | Opțiune de compatibilitate; clientul AI actual loghează numai metadata tehnică, fără textul fragmentelor. Profilul `public` cere `false`. |
| `LOG_FRAGMENT_TEXT_MAX_CHARS` | `4000` | Opțiune de compatibilitate; clientul AI actual nu loghează textul fragmentelor. |
| `LOG_AI_RESPONSE_TEXT` | `false` | Opțiune de compatibilitate; clientul AI actual nu loghează corpul răspunsului nici dacă este activată. Profilul `public` cere `false`. |
| `APP_HOST_PORT` | `8760` (Docker Compose) | Portul de pe host la care Compose publică aplicația. |
| `POSTGRES_PASSWORD` | — (obligatoriu în Docker Compose) | Parola Postgres a serviciului `db`; Compose construiește din ea `DATABASE_URL` pentru aplicație. |
| `POSTGRES_USER` / `POSTGRES_DB` | `medicina` / `medicina` (Docker Compose) | Utilizatorul și baza serviciului `db`. |
| `DB_HOST_PORT` | `5432` (Docker Compose) | Portul de pe host (doar `127.0.0.1`) la care Compose publică Postgres. |
| `PUBLIC_ROOT_PATH` | gol (direct) / `/medicina` (Docker Compose) | Prefixul căii publice, necesar când aplicația este expusă de un reverse proxy sub `/medicina`: intră în linkul de descărcare a PDF-ului și, la build-ul imaginii, devine `PUBLIC_BASE_PATH` pentru frontend. |
| `PUBLIC_ORIGIN` | gol | Originea publică exactă (`https://hostname`, fără `/medicina`), pentru validarea originii când TLS se termină la ngrok/proxy și backendul primește HTTP. Dacă este gol, se compară cu originea cererii ASGI. |
| `FRONTEND_DIST_DIR` | `src/frontend/dist` | Directorul cu build-ul React servit ca fișiere statice de FastAPI. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Allowlist Uvicorn pentru IP-urile/CIDR-urile proxy-urilor autorizate; aplicația nu interpretează direct `X-Forwarded-For`. |

Creșterea bugetului de conținut (`OLLAMA_MAX_CONTENT_TOKENS`, `X_AI_MAX_CONTENT_TOKENS`, `DEEPSEEK_MAX_CONTENT_TOKENS`, `HF_MAX_CONTENT_TOKENS`) mărește numărul de fragmente afișate, timpul de procesare și volumul total trimis către furnizorul AI. Limita per lot controlează separat dimensiunea fiecărei cereri. În medii în care logurile nu au acces controlat, setați `LOG_FRAGMENT_TEXT=false`.

La pornirea directă, aplicația citește valorile din `.env`; valorile implicite diferă unde este indicat. Docker Compose transmite variabilele enumerate în secțiunea `environment`; `COOKIE_SECURE` este implicit `false` la pornire directă și `true` în Compose. `OWNER_KEY` este opțional, dar fără el generarea raportului este dezactivată; setați o cheie secretă și autorizați browserul prin formularul `/owner`. IP-ul pentru limite este furnizat de serverul ASGI; aplicația nu interpretează `X-Forwarded-For`. În deploymentul cu proxy, configurați allowlistul explicit `FORWARDED_ALLOW_IPS` al Uvicorn pentru proxy-urile autorizate; vechiul `TRUST_PROXY` nu mai acordă încredere antetelor.

### ✉️ Gmail OAuth2 — opțional

```dotenv
GMAIL_USERNAME=adresa-ta@gmail.com
MAIL_FROM=adresa-ta@gmail.com
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
```

Autorizarea inițială se face o singură dată:

```powershell
.\.venv\Scripts\python.exe src\scripts\google_oauth_setup.py
```

Este solicitat numai scope-ul `gmail.send`. Tokenul nu este afișat și nu trebuie publicat. Dacă integrarea nu este complet configurată, raportul rămâne disponibil în aplicație, iar livrarea e-mail este omisă.

Dacă Google respinge reîmprospătarea cu `invalid_grant`, verificați mai întâi dacă tokenul valid din `.env` a fost încărcat în container. Pentru Docker, aplicați configurația curentă cu `docker compose up -d --no-deps --force-recreate app`; simpla repornire nu actualizează variabilele de mediu ale containerului. Recrearea închide sesiunile active și elimină rapoartele din memorie, deci salvați PDF-urile înainte. Dacă și tokenul local este respins, reautorizați contul cu același script. Acesta înlocuiește tokenul în `.env`. Reautorizarea nu expediază automat un raport.

## 🔐 Confidențialitate și siguranță

- 🔒 `.env` și cache-ul modelului sunt ignorate de Git; indexul locuiește în Postgres, nu în fișiere din repo.
- 🧭 fiecare fragment rămâne legat de fișierul și liniile sursă;
- 🧹 conversațiile și PDF-urile stau doar în memoria procesului, separate pe tab; închiderea notificată serverului, expirarea sau repornirea le elimină. Nicio informație medicală a pacientului nu se scrie în baza de date;
- 🚫 requesturile xAI folosesc `store=false` (pentru DeepSeek, Hugging Face și Ollama parametrul nu se trimite; se aplică politicile lor de retenție);
- 🩺 răspunsurile sunt informative și trebuie verificate medical înainte de utilizare.

## 🧪 Testare

Comenzile se execută din rădăcina proiectului.

Instalați uneltele de dezvoltare în mediul CPU (nu în `.venv-gpu`):

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s src/tests/unit -t src -v
.\.venv\Scripts\python.exe -m pytest src/tests/unit/ai/test_report_validation.py src/tests/unit/web/test_report_integrity.py -q
```

Unitarele folosesc dependențe simulate și nu necesită Docker, PostgreSQL, `.env` sau corpusul personal. Testele de integrare folosesc implicit un PostgreSQL/pgvector efemer și corpus sintetic:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s src/tests/integration -t src -v
.\.venv\Scripts\python.exe -m pytest src/tests/integration/test_index_integrity.py -q
```

Docker trebuie să fie disponibil pentru integrare. Alternativ, `TEST_POSTGRES_URL` poate indica **exclusiv o bază de test dispensabilă**: fixture-urile îi modifică schema și datele. Nu folosiți baza aplicației. Testele corpusului și cataloagelor personale necesită separat `RUN_LOCAL_CORPUS_TESTS=1`; nu sunt activate în CI.

Verificările statice și frontend:

```powershell
.\.venv\Scripts\python.exe -m ruff check src
.\.venv\Scripts\python.exe -m ruff format --check src
.\.venv\Scripts\python.exe -m mypy
npm --prefix src/frontend ci
npm --prefix src/frontend run test
npm --prefix src/frontend run typecheck
npm --prefix src/frontend run build
```

Ruff nu rescrie fișiere în CI. Mypy verifică gradual configurația, contractele, modelele, serviciul conversației, bugetul operațiilor și evaluatorul de conținut. Dicționarele third-party din `src/scripts/dictionaires` și scripturile experimentale `icd10_work` sunt excluse din formatarea/lintul aplicației.

### Dependențe și CI

`pyproject.toml` este sursa declarațiilor. Lockurile sunt generate cu pip-tools, includ dependențele tranzitive și hashurile distribuțiilor și păstrează versiunile existente fără upgrade implicit:

| Mediu | Runtime | Dezvoltare |
|---|---|---|
| Windows, Python 3.11 | `requirements-runtime.lock` | `requirements-dev.lock` |
| Linux, Python 3.11 | `requirements-runtime-py311-linux.lock` | `requirements-dev-py311-linux.lock` |

Generați fiecare pereche pe sistemul și versiunea Python corespunzătoare:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m scripts.manage_dependencies --generate
.\.venv\Scripts\python.exe -m scripts.manage_dependencies --check
```

`requirements-locks.json` înregistrează hashul declarațiilor și al fiecărui lock. CI refuză declarații schimbate fără regenerare. `requirements-web.txt` și `requirements-lock.txt` sunt aliasuri pentru lockul Windows/Python 3.11; pe Linux folosiți perechea Linux. Mediul GPU existent și modelul `Qwen/Qwen3-Embedding-0.6B` sunt păstrate.

Workflow-ul `.github/workflows/ci.yml` separă verificările statice, unitarele Python 3.11, integrarea pgvector, frontendul și buildul Docker. Folosește date sintetice și nu publică corpusul personal.

### Evaluarea retrieval-ului la nivel de conținut

Evaluatorul structural existent rămâne disponibil. Noul mod `--content` folosește exact 30 de cazuri din `src/tests/eval/content_cases.json`, acoperind afecțiuni, sinonime, exprimări libere și atenționări. Fiecare fragment este identificat prin cale relativă și SHA-256 al textului, independent de ID-ul PostgreSQL.

Cazurile livrate sunt etichetate pentru corpusul sintetic din `src/tests/eval/synthetic_corpus`. Clasamentele din `synthetic_rankings.json` și baseline-ul analitic ideal verifică mecanismul metricilor; **nu măsoară calitatea modelului pe corpusul personal**:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval --content --rankings src/tests/eval/synthetic_rankings.json --baseline src/tests/eval/synthetic_baseline.json --output var/output/synthetic-metrics.json
```

Pentru un index real, pregătiți local 30 de cazuri cu hashuri din acel corpus, apoi măsurați baseline-ul înaintea schimbării scoringului. Datele personale și etichetele locale rămân în `var/output`:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval --content --dotenv --cases var/output/content-cases-local.json --output var/output/retrieval-before.json
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval --content --dotenv --cases var/output/content-cases-local.json --baseline var/output/retrieval-before.json --output var/output/retrieval-after.json
```

Raportul include Recall@50 din fragmentele relevante etichetate, nDCG@10 cu grade 0–3, numărul rezultatelor etichetate ca irelevante în top 10, fragmentele fără etichetă în top 10 și acoperirea atenționărilor așteptate în top 50. Comparația refuză corpusuri/cazuri/configurații diferite și raportează regresii pe fiecare caz, cu exit code 2. O nouă generație a aceluiași conținut poate fi comparată. Aceste metrici nu validează clinic sursele.

## Operare și limite

Rulați aplicația cu **un singur worker Uvicorn**: sesiunile și limitele sunt gestionate în memoria procesului. Implicit sunt permise două căutări și o generare simultană (`MAX_CONCURRENT_SEARCHES=2`, `MAX_CONCURRENT_GENERATIONS=1`). Rapoartele suplimentare primesc `202` și așteaptă într-o coadă FIFO în memoria procesului; următorul pornește după oprirea efectivă a workerului anterior. Sunt admise cel mult `MAX_QUEUED_GENERATIONS=20` cereri în așteptare, în limitele bugetelor de memorie. Depășirea capacității cozii produce `429 GENERATION_QUEUE_FULL`; o operație cu alte opțiuni deja în curs pe aceeași căutare poate produce `409`.

Operațiile au un buget total de 600 de secunde (`OPERATION_TIMEOUT_SECONDS`), fără reîncercare automată. După expirare sau închiderea sesiunii, rezultatele tardive sunt abandonate; un apel deja pornit poate continua, ocupând capacitatea până la terminare.

Folosiți `/healthz` pentru configurația AI și `/readyz` pentru disponibilitatea indexului. Reindexarea creează baza lipsă și aplică migrările; aplicația web nu le execută la pornire. În timpul sincronizării indexului, căutarea poate răspunde `503`; un eșec păstrează generația anterioară.

Pentru expunere publică, setați `DEPLOYMENT_PROFILE=public`, `PUBLIC_ORIGIN=https://...`, `COOKIE_SECURE=true`, `LOG_FRAGMENT_TEXT=false` și `LOG_AI_RESPONSE_TEXT=false`. În Compose, adăugați explicit `DEPLOYMENT_PROFILE` în `app.environment`; simpla adăugare în `.env` nu îl transmite containerului. Configurați proxy-urile autorizate prin `FORWARDED_ALLOW_IPS` (Uvicorn); pentru Funnel pe host și Docker sunt autorizate loopback-ul și gateway-ul rețelei interne a aplicației.

## Extragerea PDF în Markdown

`src/scripts/extract_pdf_markdown.py` convertește local PDF-uri în Markdown, deduce titlurile și ordinea de citire și păstrează reperele `<!-- Pagina PDF N -->`. Instalați dependențele opționale, apoi rulați conversia:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[pdf]"
.\.venv\Scripts\python.exe src\scripts\extract_pdf_markdown.py "carte.pdf"
```

Implicit, pentru `carte.pdf`, scriptul creează folderul `medicina-naturista-documente/data/documents/Surse sigure/carte/` și salvează acolo `carte.pdf.md`. Folderul primește numele PDF-ului fără extensie, iar fișierul Markdown păstrează numele complet al PDF-ului, la care se adaugă `.md`. Destinația este relativă la rădăcina proiectului, calculată din locația scriptului, indiferent de directorul de lansare. `-o` / `--output` permite alegerea explicită a altui fișier de ieșire.

PyMuPDF extrage caracterele și informațiile despre fonturi și randează paginile. Implicit, fiecare pagină este îndreptată separat înainte de extragere, textul existent este păstrat, OCR se aplică numai paginilor fără text, iar coloanele sunt detectate automat. OCR rulează în memorie prin `Page.get_textpage_ocr`, fără pornirea executabilului Tesseract și fără imagini sau fișiere TSV intermediare. API-ul folosește motorul Tesseract integrat și necesită fișierele de limbă `ron.traineddata` și `eng.traineddata`. Directorul lor se indică prin `--tessdata` sau `TESSDATA_PREFIX`; pe Windows se detectează implicit `C:\Program Files\Tesseract-OCR\tessdata`. Opțiunea `--tesseract-cmd` a fost înlocuită cu `--tessdata`.

Opțiuni utile:

- `--start-page N --end-page N`: conversia unui interval de pagini.
- `--ocr always|never`: forțarea sau dezactivarea OCR.
- `--columns 1|2|3` și `--deskew off`: control manual pentru documente ambigue.
- `--debug`: logarea intrării în fiecare funcție/metodă explicită, cu numele parametrilor; parolele sunt mascate, iar colecțiile și obiectele mari sunt rezumate. Implicit se afișează progresul la nivel `INFO`.
- `--help`: lista completă a opțiunilor.

Raportul JSON descrie extragerea și avertismentele pe pagină. Markdown-ul și raportul sunt pregătite înainte de înlocuirea rezultatelor; dacă publicarea eșuează, scriptul încearcă restaurarea versiunilor anterioare și păstrează copiile de recuperare dacă restaurarea este blocată. Destinațiile care coincid cu sursa, inclusiv hardlinkurile, sunt respinse. Randarea OCR este limitată la 64 megapixeli pe pagină; reduceți `--dpi` pentru paginile foarte mari. Verificați titlurile, tabelele și scanările degradate: structura este dedusă euristic, iar erorile OCR nu sunt corectate semantic.

`src/scripts/merge_book_pdfs.py` unește fragmentele `pag<prima>-<ultima>.pdf` și îndreaptă fiecare pagină în memorie, folosind PyMuPDF pentru toate operațiile PDF. Fiecare fragment este deschis o singură dată; numărul de pagini este verificat în timpul unirii, iar nepotrivirile și intervalele lipsă produc avertismente. Intervalele suprapuse sunt respinse, inclusiv la apelarea directă din Python. Nu execută OCR și nu generează imagini intermediare. Implicit, PDF-ul final este salvat în rădăcina proiectului (`D:\Workspace\medicina-naturista` în checkout-ul curent), cu numele folderului sursă și extensia `.pdf`; destinația este calculată din locația scriptului, indiferent de directorul din care este lansat. `--output-dir` schimbă destinația, iar `--deskew off` dezactivează îndreptarea. `--debug` activează logarea intrării în fiecare funcție/metodă explicită, cu parametri numiți și obiecte mari rezumate. Progresul este afișat la nivel `INFO`. PDF-ul final este verificat înainte de înlocuirea atomică a destinației; sursele, inclusiv aliasurile/hardlinkurile, sunt protejate împotriva suprascrierii.

## 📜 Licență

Codul proiectului este distribuit sub [Business Source License 1.1](LICENSE) ([versiunea în română](LICENSE.ro.md)). Utilizarea în medii non-producție este gratuită; utilizarea în producție necesită un acord comercial separat cu licențiatorul. Apache 2.0 este licența prevăzută după schimbare, conform termenilor din `LICENSE`, nu licența inițială a proiectului.

---

<div align="center">

🌱 **Surse verificabile · retrieval local · recomandări adjuvante**

</div>


## Generarea rapoartelor în fundal

Modelele suportate sunt definite într-un singur catalog backend. `REPORT_GENERATION_MODELS` este lista CSV a modelelor activate, în ordinea din UI; primul model este implicit. `/api/report-models` returnează toate modelele configurate în `models`, primul în `defaultModel` și separat modelele permise utilizatorului curent în `allowedModels`. Toate opțiunile rămân vizibile și selectabile pentru public. Generarea rețetei/raportului este rezervată administratorului pentru toate modelele, inclusiv Ollama local. Un utilizator neautorizat vede mesajul „Generarea rețetei este disponibilă doar administratorului platformei.” și butonul de generare dezactivat pentru orice model. `allowedModels` este gol pentru public și conține modelele configurate pentru administrator; lipsa metadatelor de permisiuni dezactivează generarea în UI. Administratorul autentificat poate genera cu toate modelele configurate. Aceeași protecție se aplică pe backend pentru toate modelele: cererea primește HTTP 403 cu `MODEL_FORBIDDEN`, înainte de admiterea jobului sau apelul AI, dacă sesiunea de autor nu este validă. Cererile fără model folosesc primul model configurat și aceeași verificare, fără schimbare automată către alt model. Modelul explicit neconfigurat este respins cu HTTP 422 și `MODEL_NOT_CONFIGURED`. Statusul și anularea unui job cer de asemenea o sesiune de administrator validă. Se construiesc clienți numai pentru modelele configurate. Variabila singulară anterioară a fost eliminată.

În chat, confirmarea „Raportul este gata și a fost generat în …” include și `folosind modelul AI **<model>**`, cu identificatorul efectiv al modelului afișat cu bold. Informația este păstrată în mesajul raportului din istoricul sesiunii, independent de selecțiile ulterioare din UI.

La finalul PDF-ului, după bibliografie și sumarul generării, apare `Model AI folosit: <model>`. Se afișează identificatorul efectiv trimis furnizorului, fixat din clientul ales pentru raport; o schimbare ulterioară a implicitului nu modifică această informație pentru cererile deja admise în coadă.

| Opțiune UI / env | Furnizor | Model trimis în request |
| --- | --- | --- |
| `ollama-gemma3:1b` | Ollama local | `gemma3:1b` |
| `ollama-gemma4:12b` | Ollama local | `gemma4:12b` |
| `ollama-ministral-3:8b` | Ollama local | `ministral-3:8b` |
| `ollama-qwen3.5:9b` | Ollama local | `qwen3.5:9b` |
| `ollama-qwen3.5:4b` | Ollama local | `qwen3.5:4b` |
| `ollama-deepseek-r1:8b` | Ollama local | `deepseek-r1:8b` |
| `deepseek-flash` | DeepSeek | `deepseek-flash` |
| `huggingface-deepseek-v4-flash` | Hugging Face / DeepInfra | `deepseek-ai/DeepSeek-V4-Flash:deepinfra` |
| `grok-4.3` | xAI | `grok-4.3` |

Toate modelele Ollama pentru rapoarte folosesc ruta nativă `/api/chat`. Parametrul de thinking este activat conform configurării pentru Gemma4 și Qwen3.5; pentru Gemma3 și Ministral este omis. R1 8B folosește explicit `think=true`, independent de `OLLAMA_REASONING_EFFORT`. Instalați pe host modelul local ales înainte de utilizare; opțiunea `ollama-ministral-3:8b` folosește tagul Ollama `ministral-3:8b`.

Pentru rapoartele `ollama-gemma3:1b`, profilul din catalog trimite `temperature=0`, `repeat_penalty=1.1` și `repeat_last_n=256`, pentru a reduce buclele de repetare în răspunsurile JSON. Aceste opțiuni se aplică numai generării rapoartelor cu acest model; schema, fragmentele întregi, contextul și limita de ieșire sunt păstrate. Profilul reduce riscul repetițiilor, fără a garanta eliminarea lor sau calitatea semantică a recomandărilor.

Dacă Ollama întrerupe fluxul cu `prediction aborted, token repeat limit reached`, aplicația îl recunoaște drept `repetition_limit`, îl loghează fără textul generat și încheie jobul cu `AI_REPETITION_LIMIT_EXCEEDED`. Mesajul explică bucla de repetiție, în loc să raporteze o eroare generică de validare JSON. Celelalte loturi active sunt anulate; nu există retry automat, trunchiere sau publicare de PDF incomplet. Excepția de la bugetul local pentru requesturile cu un singur fragment rămâne valabilă.

Pentru `ollama-deepseek-r1:8b`, instalați modelul cu `ollama pull deepseek-r1:8b`. Tagul actual este DeepSeek-R1-0528-Qwen3-8B, Q4_K_M, care acceptă promptul `system` existent. Profilul implicit trimite `num_ctx=32768`, `num_predict=8192` și folosește un buget conservator de 24.000 tokeni de intrare per lot, inclusiv instrucțiunile, profilul și schema JSON. Contextul a fost mărit pentru ca estimarea conservatoare a instrucțiunilor să lase loc și fragmentelor. Limita globală de ieșire nu înlocuiește limita specifică R1. Un fragment care nu încape în bugetul conservator este trimis întreg într-un request separat; limita reală de context rămâne verificată de Ollama, fără trunchiere sau fallback. Creșterea contextului poate mări consumul de memorie al Ollama.

Ollama rulează pe GPU-ul hostului; containerul FastAPI nu necesită acces CUDA pentru rapoarte. Contextul R1 explicit înlocuiește pentru această cerere valoarea globală `OLLAMA_CONTEXT_LENGTH`. Verificați în timpul generării `ollama ps`: `100% GPU` indică încărcarea integrală a modelului pe GPU. Configurarea singură nu garantează încadrarea în VRAM. Nu sunt adăugate apeluri de warm-up la pornire. R1 14B nu este integrat.

Dacă Ollama răspunde că modelul cerut nu este găsit, jobul primește `AI_MODEL_NOT_FOUND`, iar interfața afișează că modelul selectat nu este instalat sau nu este disponibil.



Generarea pornește prin `POST /api/searches/{searchId}/generate` și răspunde cu `202`, `jobId` și `Location`. Clientul trimite un `requestId` stabil pentru fiecare încercare. `GET /api/report-generations/{jobId}` citește starea, iar `POST /api/report-generations/{jobId}/cancel` solicită anularea. Verificarea periodică nu lansează apeluri AI suplimentare. Aceeași execuție funcționează cu toți clienții AI suportați; modelul ales este fixat la admitere. Restricțiile existente de acces pentru modelul ales se aplică și citirii/anulării operației.

Frontendul reconciliază statusul jobului cu snapshotul din sesiune: la revenirea într-un tab, o stare veche „în coadă” din cache nu poate înlocui un status final primit odată cu raportul. Aceeași stare reconciliată controlează mesajul, indicatorul de generare și pollingul; oprirea workerului nu este inversată de un snapshot vechi.

În PDF, item-urile din `uz_intern`, `uz_extern`, `alte_recomandari` și `atentionari` se ordonează descrescător după **numărul fragmentelor citate**. Fiecare ID de fragment valid se numără o singură dată pentru un item; două fragmente diferite din același document sunt două surse. **X** rămâne afișat și calculat ca înainte: `● (57) Tinctura de fructe de soc: descriere...`. Plantele sunt identificate doar în denumire, inclusiv prin sinonimele din catalog; pentru fiecare plantă se numără rândurile din `herbs_benefits`, fără filtrare după afecțiunea raportului. Dacă denumirea conține mai multe plante, X este maximul numărătorilor; dacă nu se identifică nicio plantă sau nu există asocieri, X este zero și nu se afișează nici numărul, nici parantezele. La egalitate de număr de fragmente se folosesc relevanța maximă a fragmentelor citate, numărul referințelor distincte și poziția inițială. X reflectă asocierile indexate, nu o măsură a eficacității clinice, și nu influențează sortarea. Nutriția și textul raportului din chat păstrează ordonarea existentă. Regula se aplică PDF-urilor nou generate.

Cronometrul raportului rămâne la `00:00` cât cererea așteaptă admiterea sau este în coadă. Pornește când workerul preia raportul, folosind `startedAt`, fără a include așteptarea. Schimbările de etapă și actualizările statusului nu îl resetează; o nouă încercare primește un cronometru nou.

Dacă furnizorul marchează răspunsul drept incomplet cu motivul `max_output_tokens`, jobul primește `AI_OUTPUT_LIMIT_EXCEEDED` și un mesaj care explică atingerea limitei de tokeni înainte de finalizarea raportului. Aceasta este distinctă de timeout și de un JSON invalid. Textul primit rămâne în panou; un răspuns incomplet nu este publicat ca raport/PDF și nu este reîncercat automat.

După publicarea cu succes a PDF-ului complet, aplicația inserează o singură măsurătoare în tabela PostgreSQL `report_generation_metrics`: `id`, `medical_condition`, `min_score`, `characters`, `ai_model`, `ai_effort`, `duration`. Afecțiunea este identificată din snapshotul căutării și salvată cu numele exact din `medical_conditions.name`: pentru „Remedii naturiste pentru gripă” se stochează `Gripa`. Pentru mai multe afecțiuni, numele canonice se păstrează în ordinea identificării, separate prin virgulă. Răspunsurile AI sunt acceptate aici numai dacă sunt mapate la catalog; dacă nu există nicio afecțiune din catalog, măsurătoarea nu se inserează, iar PDF-ul rămâne disponibil. `characters` numără caracterele Unicode din fragmentele efectiv furnizate AI, după filtrarea prin scor și buget. `ai_model` păstrează alegerea din catalog (de exemplu `ollama-gemma4:12b`), iar `ai_effort` păstrează efortul configurat pentru clientul selectat, cu `NULL` dacă nu este specificat. Efortul înregistrat nu garantează că furnizorul îl aplică. API-ul acceptă `minScore` doar ca întreg între 0 și 100.

`duration` este un `BIGINT` în **milisecunde**, măsurat cu ceas monoton până după publicarea în sesiune; exclude coada, inserarea statisticii și emailul. Anulările, eșecurile și cererile repetate pentru același job nu adaugă măsurători. Inserarea folosește pool-ul existent, cu așteptare de maximum 1 s pentru conexiune, `statement_timeout` de 2 s și `lock_timeout` de 500 ms în tranzacție. Dacă inserarea eșuează, PDF-ul rămâne disponibil, iar logul `report_metrics_persistence_failed` identifică operația fără conținut medical. Nu există retry automat sau garanție de înregistrare dacă baza este indisponibilă ori procesul se oprește între publicare și INSERT.

Sub „Număr total caractere”, UI afișează „Durată estimată: mm:ss (min:sec)” pentru numărul de caractere eligibile și modelul ales. Calculul folosește toate rândurile modelului, fără filtre după afecțiune, scor sau efort: regresie liniară prin origine, `durata_ms = caractere_selectate × SUM(characters × duration) / SUM(characters²)`. Duratele din tabel sunt în milisecunde; rezultatul este rotunjit în sus la secunde. Când modelul sau caracterele se schimbă, estimarea este recerută, iar răspunsurile selecțiilor anterioare nu pot suprascrie selecția curentă. După terminarea unui job se reîmprospătează estimarea pentru a include istoricul nou. Fără date utilizabile, UI afișează „indisponibilă”; indisponibilitatea DB/rețelei nu blochează generarea. Ruta returnează numai modelul, caracterele, `estimatedSeconds` și `sampleCount`; estimarea nu lansează cereri AI și nu modifică drepturile de generare.

Migrările `011_report_generation_metrics.sql` și `012_seed_report_generation_metrics.sql` creează tabela și inserează cele șase măsurători istorice furnizate (53.924 de caractere fiecare). Aplicați-le înainte de activarea codului, prin `python -m scripts.migrate_database` cu `PYTHONPATH=src` și configurația bazei țintă; registrul migrărilor previne reaplicarea seedului. Nu este necesară reindexarea. Rularea manuală repetată a INSERT-ului din migrarea 012 adaugă alte șase rânduri.

Migrarea `013_canonical_report_metric_conditions.sql` corectează etichetele istorice care corespund exact unui nume din catalog, inclusiv forma „Remedii naturiste pentru <afecțiune>”. Celelalte valori ale măsurătorii se păstrează; textele fără potrivire rămân pentru verificare manuală.

`REPORT_GENERATION_TIMEOUT_SECONDS` limitează întregul raport, inclusiv toate loturile și construirea PDF-ului (implicit 600 s; poate fi configurat). `OPERATION_TIMEOUT_SECONDS` rămâne separat pentru celelalte operații, iar `REPORT_GENERATION_READ_TIMEOUT_SECONDS` limitează I/O. Așteptarea în coada aplicației nu pornește timerul raportului.

### Un singur raport activ, cu loturi paralele configurabile

Workerul FIFO unic (`REPORT_GENERATION_WORKERS = 1`) păstrează un singur raport activ.
În interiorul său, un executor separat folosește `REPORT_BATCH_WORKERS` din `.env`
(implicit `2`) drept limită de cereri AI simultane, exclusiv pentru loturile acelui
raport. `1` dezactivează paralelismul; valorile neîntregi sau nepozitive sunt respinse
la pornire. Docker Compose transmite setarea prin `app.environment`.
După încheierea unui
lot se poate admite următorul, fără a aștepta celelalte loturi active. Contextul operației,
deadline-ul și ID-ul lotului sunt propagate explicit în fiecare fir. Nu există retry
automat sau request AI de consolidare. Fiecare request primește același system prompt
din `ai/prompts/generate_report_system.md`, profilul consultației și fragmentele întregi
ale lotului său.

`REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL` permite bugete de intrare diferite per model și lot. În `.env`, exemplu cu valorile implicite:

```dotenv
REPORT_BATCH_WORKERS=2
REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL='{"ollama-gemma3:1b":25000,"ollama-gemma4:12b":25000,"ollama-ministral-3:8b":25000,"ollama-qwen3.5:9b":25000,"ollama-qwen3.5:4b":25000,"ollama-deepseek-r1:8b":24000,"deepseek-flash":25000,"huggingface-deepseek-v4-flash":25000,"grok-4.3":25000}'
```

Numărarea este locală și conservatoare: fiecare octet UTF-8 al payloadului JSON complet consumă un token din buget, plus o rezervă fixă de 256 tokeni pentru încadrarea mesajelor. Sunt incluse promptul de sistem, profilul, fragmentele, sursele, ID-urile, schema JSON și câmpurile cererii. Nu se folosește raportul de patru caractere per token, nu se descarcă tokenizatoare și nu se apelează furnizorii pentru numărare. Aceasta este o estimare conservatoare, nu numărul exact produs de tokenizerul modelului; poate produce loturi mai mici, iar furnizorul rămâne autoritatea pentru contextul real.

Pentru Ollama cu `num_ctx` explicit, bugetul efectiv de intrare este minimul dintre limita configurată și `num_ctx - num_predict`, astfel încât ieșirea să aibă spațiu rezervat. Fără context explicit, rămâne configurația serverului Ollama; bugetul de intrare trebuie ales împreună cu limita de ieșire și contextul serverului. `REPORT_GENERATION_MAX_OUTPUT_TOKENS` și override-urile de ieșire rămân limite per lot, independente de bugetul de intrare.

Fragmentele sunt păstrate întregi și ordonate după scor. Dacă un singur fragment cu întregul overhead depășește bugetul conservator, este izolat într-un lot și trimis întreg. Limita locală per lot este ignorată numai pentru requesturi cu exact un fragment, inclusiv dacă bugetul efectiv este redus de rezervarea ieșirii din contextul explicit. Loturile cu mai multe fragmente respectă în continuare limita. Nu se scurtează conținutul și nu se schimbă contextul sau limita de ieșire trimise furnizorului. Furnizorul poate respinge în continuare un request care depășește contextul real; eroarea rămâne `AI_CONTEXT_LIMIT_EXCEEDED`. Logurile folosesc `input_tokens_upper_bound` și `counting=utf8_bytes`, iar excepția locală este marcată prin `report_batch_token_limit_bypassed` cu `fragments=1`.

`OLLAMA_MAX_CONTENT_TOKENS`, `X_AI_MAX_CONTENT_TOKENS`, `DEEPSEEK_MAX_CONTENT_TOKENS` și `HF_MAX_CONTENT_TOKENS` limitează separat totalul conținutului selectat pentru furnizorul respectiv înainte de lotizare. Se numără conservator octeții UTF-8 ai fragmentelor cu ID-uri, surse, titluri și serializare; se păstrează prefixul în ordinea scorului, fără scurtarea fragmentelor. Promptul, profilul, schema și ieșirea sunt bugetate separat per request. SQL folosește aceeași valoare ca prefiltru în caractere, apoi retrieval-ul verifică explicit octeții UTF-8: astfel, limita în tokeni nu este tratată ca o limită în caractere. Aceste estimări locale nu reprezintă numărul exact de tokeni calculat de furnizori.

Vechea variabilă `REPORT_GENERATION_BATCH_MAX_CHARS_BY_MODEL` trebuie eliminată și înlocuită cu valori alese în noua unitate; dacă ajunge în mediul aplicației, pornirea o respinge explicit, pentru a evita reinterpretarea silențioasă a caracterelor drept tokeni. După modificarea `.env` și a codului, configurația și imaginea serviciului trebuie actualizate de operator.

Aceeași migrare explicită se aplică pentru `OLLAMA_MAX_CONTEXT_CHARS` → `OLLAMA_MAX_CONTENT_TOKENS`, `X_AI_MAX_CONTEXT_CHARS` → `X_AI_MAX_CONTENT_TOKENS`, `DEEPSEEK_MAX_CONTEXT_CHARS` → `DEEPSEEK_MAX_CONTENT_TOKENS` și `HF_MAX_CONTEXT_CHARS` → `HF_MAX_CONTENT_TOKENS`. Numele vechi sunt respinse la pornire dacă ajung în mediul aplicației.

Fiecare răspuns este validat strict față de ID-urile lotului său; un lot valid fără recomandări este permis. Rezultatele sunt combinate prin cod: se elimină numai textele identice din aceeași secțiune și se reunesc sursele lor. Variantele diferite, dozele și atenționările sunt păstrate. Listele alimentare elimină numai elementele identice din aceeași subcategorie; rețetele culinare distincte din toate loturile sunt păstrate, fără plafon global suplimentar. Combinarea nu face reconciliere semantică sau validare clinică globală.

În forma structurată a secțiunii Nutriție, câmpurile text goale sau alcătuite numai din spații, liniuțe ASCII și marcaje `•` sunt normalizate ca lipsă de conținut; de exemplu, `"interzise": "-"` nu creează o recomandare goală și nu invalidează lotul. Obiectele-recomandare fără text util, citările invalide, câmpurile obligatorii lipsă și celelalte abateri continuă să fie respinse de validarea strictă.

Pentru rapoartele Ollama, `format` primește schema JSON a celor cinci secțiuni,
inclusiv structura Nutriție și ID-urile permise din lotul curent. Recomandările din
afara Nutriției cer cel puțin o citare. Schema ghidează generarea; validatorul local
rămâne obligatoriu și respinge răspunsurile invalide, fără reparare sau retry automat.

Problemele integrării Ollama sunt logate cu modelul, etapa și tipul eșecului:
HTTP/rețea/timeout, model absent, încărcare sau memorie insuficientă, limită de context
sau ieșire, protocol/stream întrerupt, JSON invalid și validarea rezultatului.
`ai_report_validation_failed` include lotul, numărul problemelor per cod și cel mult
20 de poziții afectate (secțiune/index), de exemplu `UNKNOWN_EVIDENCE`,
`MISSING_EVIDENCE`, `INVALID_ITEM` sau `MISSING_NUTRITION_FIELD`.
Clasificarea mesajelor, identificarea afecțiunilor, inventarul modelelor și indexarea
folosesc același diagnostic de transport; indexarea include și codurile cunoscute de
validare. Erorile neașteptate sunt logate prin tip, fără argumentele excepției.
Logurile nu includ promptul, fragmentele, răspunsul brut, thinking sau chei API;
mesajele arbitrare ale furnizorului sunt înlocuite cu motive tehnice cunoscute.
Pentru diagnostic în runtime: `docker compose logs --since 30m app`.

Zona „Previzualizare raport” afișează câte un panou separat „Lotul N din T” pentru
fiecare lot planificat, în ordinea procesării. Fiecare panou păstrează exclusiv
recomandările și bibliografia lotului său, cu derulare proprie; previzualizările nu
se cumulează. Loturile în așteptare, active, validate, eșuate, anulate sau expirate
au stări distincte. În timpul procesării, detaliile lotului afișează analiza
transmisă de furnizor și răspunsul brut, inclusiv JSON incomplet. După validare,
detaliile brute sunt restrânse; după succes rămân previzualizările validate ale
tuturor loturilor. La eșec/anulare se păstrează și detaliile lotului întrerupt,
iar cele neîncepute sunt marcate ca neprocesate. Textele brute sunt nevalidate
și nu intră direct în raport sau PDF.

API expune `batchPreviews`, cu `index`, `state`, `reportPreview`, `streamPreview`
și `thinkingPreview` pentru fiecare lot, plus `previewVersion`, `batchesCompleted`
și `batchesTotal`. Câmpul compatibil `reportPreview` conține ultimul lot validat.
Fiecare lot deține propriile fragmente de răspuns/analiză și propria `aiActivity`,
astfel încât textul simultan nu se amestecă. Câmpurile agregate de compatibilitate
sunt construite la citire, în ordinea loturilor, fără copii brute suplimentare
reținute în sesiune. Snapshoturile formatate, textul și metadatele loturilor (inclusiv
o rezervă de 2 KiB per lot pentru activitate) sunt contabilizate în bugetele existente.
Contorul loturilor finalizate numără loturile validate, chiar dacă lotul 2 se termină
înaintea lotului 1; versiunile cresc monoton. El nu este procent
de progres. Raportul final și PDF-ul continuă să combine toate loturile în backend,
cu aceleași reguli de validare și deduplicare.

Prima eroare de request sau validare oprește admiterea loturilor următoare și solicită
anularea cooperativă a celorlalte loturi active. Eroarea inițială este păstrată chiar dacă
anularea altui fir este observată prima de coordonator. Anularea utilizatorului
și timeoutul raportului se propagă tuturor loturilor active. Apelurile I/O deja blocate nu pot
fi ucise ca fire Python: capacitatea raportului rămâne ocupată până la ieșirea efectivă
a tuturor firelor, în limitele timeouturilor I/O. Nu se publică PDF parțial.
Previzualizările validate și datele loturilor întrerupte rămân în sesiune. Thinking și
răspunsul brut nu intră în PDF sau loguri; thinking este eliberat după succes. O nouă
generare înlocuiește previzualizarea anterioară. La succes, rezultatele sunt combinate
în ordinea inițială a loturilor, indiferent de ordinea sosirii lor.

PDF-ul, mesajul „Raportul este gata” și o singură măsurătoare `report_generation_metrics` sunt publicate numai după încheierea tuturor loturilor. Durata este timpul real al raportului, nu suma unor durate fictive per lot. Estimarea existentă continuă să folosească toate observațiile modelului; istoricul cu o singură cerere poate avea performanțe diferite de fluxul în loturi.

Starea `aiActivity` (`waiting`, `processing`, `thinking`, `answering`) și „Ultima activitate primită” se actualizează din evenimentele reale ale requestului curent, fără ca pollingul să reseteze timpul. Viteza rămâne aproximată la 4 caractere/token, separat pentru thinking și answer, fără separatoarele de diagnostic; nu reprezintă tokenii facturați de furnizor. Erorile de conexiune, anularea și etapele de validare/PDF au prioritate. Nu se afișează bară procentuală de progres.

`report_ai_timing` înregistrează timpii locali până la primul eveniment, prima analiză și primul text al răspunsului, plus durata apelului AI. Pentru Ollama include duratele finale de încărcare, procesare a promptului și generare, convertite în milisecunde; pentru DeepSeek, usage-ul disponibil, inclusiv tokenii de reasoning. Valorile necunoscute rămân absente sau `null`. `report_ai_phase_changed` înregistrează doar schimbările de fază, fără conținutul analizei sau răspunsului.

Interfața HTTP pornește fără a aștepta pregătirea căutării locale. În fundal se execută o singură căutare de probă pentru încărcarea embeddings-urilor, dicționarului și indexului, cu timpi `warm_up_started` / `warm_up_finished` pentru etapa `search`. La pornire nu se fac apeluri de încălzire către Ollama, DeepSeek sau Grok. `/api/startup` returnează `initializing`, `ready` sau `degraded`; UI verifică starea la o secundă și afișează inițializarea. Cât timp pregătirea rulează, trimiterea întrebărilor este dezactivată, iar operațiile de căutare/AI și `/readyz` răspund cu `APP_INITIALIZING` (503). `/healthz`, interfața și sesiunea rămân accesibile. Dacă pregătirea căutării eșuează, aplicația semnalează modul degradat și permite încercarea unei căutări. Taskul de pregătire este urmărit și așteptat limitat la oprire; resursele încă folosite nu sunt închise prematur.

`MAX_CONCURRENT_GENERATIONS` trebuie să fie 1. Cererile acceptate au inițial etapa `queued`; interogarea stării returnează `queuePosition` (de la 1), afișată în interfață. Anularea unei cereri din coadă o elimină fără apel AI. Cererile duplicate sunt reconciliate prin `requestId`, fără dublarea generării. Timpul de așteptare nu consumă bugetul `REPORT_GENERATION_TIMEOUT_SECONDS`, care începe la preluare; durata maximă a sesiunii rămâne aplicabilă. Coada nu persistă la repornirea procesului. Slotul rămâne ocupat până la oprirea efectivă a workerului, inclusiv după anularea sau expirarea logică. Stările terminale și codurile de eroare se pot citi independent de conexiunea de pornire. Metadatele sunt limitate la 32 de operații per sesiune și sunt incluse în bugetul ei de memorie.

Refreshul aceleiași file recuperează operația dacă se reconectează în `SESSION_RECONNECT_GRACE_SECONDS` (implicit 30 s). Închiderea explicită anulează imediat; fără reconectare, unloadul închide sesiunea după această fereastră. Sesiunile și operațiile rămân în memorie, într-un singur proces: restartul containerului pierde rezultatele și nu relansează automat cereri AI. Shutdownul așteaptă cel mult `REPORT_SHUTDOWN_TIMEOUT_SECONDS` (implicit 20 s), cu o perioadă Docker de 30 s; un apel sincron blocat poate necesita oprirea procesului.

Pentru activarea modificărilor de cod/configurare: `docker compose up -d --build app`, apoi reîncărcați pagina. Detalii de arhitectură: [generarea asincronă](architecture/report-generation-background.xmind).
