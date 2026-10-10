# Sesiuni, retenție și autorizare owner

Implementarea planului `aiPlans/01-sesiuni-limite-autorizare.md` (10 octombrie 2026).

## Pornire și migrări

Configurarea este construită explicit prin `Settings.from_env()`. `.env` este încărcat de startup/CLI; importul `backend.web.main` și `create_app()` nu conectează baza, nu șterge directoare și nu încarcă modele. Testele pot injecta `Dependencies` și `Settings()` fără `.env` sau infrastructură personală.

Înainte de prima pornire cu noua autorizare, din rădăcina proiectului:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m scripts.migrate_database
.\.venv\Scripts\python.exe -m uvicorn backend.web.main:app --host 127.0.0.1 --port 7860 --workers 1
```

CLI-ul aplică SQL versionat sub lock advisory, în tranzacție, cu ledger `schema_migrations`. `001_hybrid_index.sql` pregătește/adoptă schema existentă a indexului, fără rebuild; `002_owner_sessions.sql` creează autorizările. Conexiunile runtime nu execută DDL. Rebuildul și schimbarea dimensiunii embeddings rămân responsabilitatea CLI-ului de indexare.

Containerul aplicației include și `scripts.migrate_database`: migrarea poate fi executată din imaginea construită, după disponibilitatea bazei. Nu este executată implicit la pornirea serverului.

## Autorizare

Conform cererii utilizatorului din 10 octombrie 2026, autorizarea se face din nou prin `GET /owner?key=<OWNER_KEY>` (sau `<PUBLIC_ROOT_PATH>/owner?key=<OWNER_KEY>`), fără formular sau controale owner în UI. Cheia validă emite un token individual și redirecționează cu 303 către chat, fără cheia în URL-ul destinației. Cheia lipsă, greșită sau prea lungă produce 404. Filtrul access log Uvicorn redactează query-ul rutei; configurați aceeași redactare în orice access log de proxy activat separat.

`GET /api/owner` returnează starea browserului și un token CSRF semnat, asociat unui cookie HttpOnly. Endpointurile POST de login/logout cer tokenul în `X-CSRF-Token` și `Origin`/`Referer` de aceeași origine. Autorizarea directă GET folosește cheia din query și refuză navigările cross-site. Ambele căi de login emit un token aleator versionat și semnat; serverul păstrează doar digestul SHA-256, `created_at` și `revoked_at`. Nu există expirare server fixă. Cookie-ul are `HttpOnly`, `SameSite=Strict`, `Path` egal cu prefixul și `Secure` conform `COOKIE_SECURE`; Max-Age de 31536000 este reînnoit după verificarea autorizării serverului. Browserul poate șterge sau limita cookie-ul și atunci este necesar un nou login.

`POST /api/owner/logout` revocă autorizarea în bază înainte de confirmare și ștergerea cookie-ului. O copie extrasă a tokenului devine invalidă. Restartul cu aceeași bază și cheie păstrează autorizarea; rotația cheii și formatul vechi al cookie-ului o invalidează. Baza/tabela indisponibilă produce 503; nu există fallback de autorizare locală. Încercările GET și POST de login, inclusiv chei greșite și CSRF/origini invalide, folosesc aceeași fereastră separată de cinci încercări/minut/IP.

## Limite configurabile

KiB și MiB folosesc 1024. Variabilele în bytes primesc numere întregi, nu sufixe.

| Variabilă | Implicit | Scop |
|---|---:|---|
| `MAX_ACTIVE_SESSIONS` | 100 | Sesiuni active pe proces |
| `MAX_SESSIONS_PER_COOKIE` | 1 | Sesiuni active per browser |
| `MAX_SESSIONS_PER_IP` | 1 | Sesiuni active per IP |
| `NEW_SESSIONS_PER_IP_MINUTE` | 10 | Creări într-o fereastră de 60 secunde |
| `NEW_SESSIONS_PER_COOKIE_MINUTE` | 5 | Creări per cookie în 60 secunde |
| `MAX_HISTORY_BYTES` | 8388608 | 8 MiB istoric per sesiune |
| `MAX_EVIDENCE_BYTES` | 25165824 | 24 MiB căutări păstrate |
| `MAX_PDF_BYTES` | 16777216 | 16 MiB PDF-uri per sesiune |
| `MAX_SESSION_BYTES` | 67108864 | 64 MiB total per sesiune |
| `MAX_GLOBAL_BYTES` | 268435456 | 256 MiB total pe proces, inclusiv rezervări |
| `MAX_API_BODY_BYTES` | 262144 | 256 KiB, înaintea parsării, inclusiv streaming |
| `OWNER_LOGIN_PER_MINUTE` | 5 | Încercări login per IP în 60 secunde |
| `MAX_CONCURRENT_SEARCHES` | 2 | Identificări/căutări simultane pe proces |
| `MAX_CONCURRENT_GENERATIONS` | 1 | Generări simultane pe proces |
| `OPERATION_TIMEOUT_SECONDS` | 600 | Deadline monoton pentru acceptarea etapelor și publicare |
| `OPERATION_RESERVATION_BYTES` | 65536 | Rezervare minimă per operație; se adaugă snapshotul |

Rămân active limitele suplimentare de 12 căutări și 12 rapoarte. `SESSION_IDLE_SECONDS=3600`, `SESSION_MAX_SECONDS=14400` și `MAX_REQUESTS_PER_MINUTE=60` continuă să se aplice. Valorile sunt pozitive; durata idle nu poate depăși durata absolută, iar bugetele componentelor trebuie să încapă în bugetul sesiunii, care trebuie să încapă în bugetul global.

IP-ul provine exclusiv din `request.client` al serverului ASGI. Configurați allowlistul Uvicorn `FORWARDED_ALLOW_IPS` cu IP-urile/CIDR-urile proxy-urilor autorizate și mențineți antetele curățate de proxy. `TRUST_PROXY` și un `X-Forwarded-For` primit direct de aplicație nu modifică cheia de limitare. Nu configurați un wildcard pentru clienți necontrolați. Dacă mai multe persoane folosesc același NAT, limita implicită de o sesiune per IP se aplică tuturor; operatorul poate ajusta explicit valoarea.

Conform cererii utilizatorului din 10 octombrie 2026, un al doilea tab/browser de la același IP primește `429 SESSION_ALREADY_ACTIVE`, fără să închidă prima sesiune. UI-ul ascunde căutarea și oferă „Verifică din nou”, după închiderea paginii active. Taburile duplicate care moștenesc același `sessionStorage` sunt protejate și printr-un Web Lock exclusiv pentru identificatorul tabului în browserele compatibile. Numai o pagină admisă trimite notificarea de închidere. La revenirea din cache-ul de navigare, pagina cere din nou admiterea. Dacă notificarea de închidere nu ajunge la server, eliberarea rămâne supusă expirării idle/absolute.

Pentru deploymentul existent `ngrok → jobshunter-nginx → Caddy → aplicație`, configurația standard conectează direct Caddy la rețeaua proxy existentă `jobshunter-net` (nume configurabil prin `PUBLIC_PROXY_NETWORK`). Nu este necesar un fișier Compose suplimentar:

```powershell
docker compose up -d
```

Ruta `/medicina/` din `D:\Workspace\jobshunter\nginx.conf` acceptă IP-ul transmis numai de agentul `ngrok`, selectează ultima adresă adăugată de acesta și transmite o singură adresă către aliasul `medicina-caddy`. Caddy acceptă acel antet numai de la IP-ul Nginx configurat în `CADDY_TRUSTED_PROXY_IPS`, iar aplicația acceptă antetele proxy numai de la IP-ul intern Caddy configurat în `FORWARDED_ALLOW_IPS`. Valorile locale verificate sunt `CADDY_TRUSTED_PROXY_IPS=172.18.0.4` și `FORWARDED_ALLOW_IPS=127.0.0.1,172.20.0.2`. La recrearea rețelelor/containerelor, verificați și actualizați aceste adrese, apoi recreați serviciile și reîncărcați Nginx. Nu includeți gateway-ul hostului sau toate rețelele private în allowlist.

Pentru HTTPS terminat la ngrok înainte de un hop HTTP prin Caddy, setați `PUBLIC_ORIGIN=https://hostname-ul-public` în `.env` și recreați containerul aplicației. Valoarea reprezintă numai originea (schemă, hostname și port opțional), fără prefixul `/medicina`, query sau credențiale. API-ul, loginul și logoutul compară originea browserului cu această valoare explicită. Nu deduc originea acceptată din `X-Forwarded-Host` ori `X-Forwarded-Proto` furnizate de client. Dacă variabila este goală, se păstrează comparația cu originea cererii ASGI pentru rularea directă/Vite.

## Tranzacții și anulare

Ordinea lockurilor este registru → sesiune. Identificarea, retrieval-ul, AI-ul, PDF-ul și emailul lucrează pe snapshoturi independente, fără aceste lockuri. Fiecare sesiune are o identitate internă de viață; aceeași pereche cookie/tab recreată nu poate primi rezultatul unui worker vechi. Fiecare mesaj nou crește revizia și anulează identificarea/căutarea precedente. Frontendul propagă `contextRevision` prin `X-Context-Revision` între mesaj, identificare și căutare.

Generarea folosește exact profilul și dovezile căutării selectate, inclusiv pentru o căutare mai veche păstrată. Două generări ale aceleiași căutări primesc 409 înaintea unui al doilea apel AI. Limita globală de operații lente este verificată separat, fără coadă; excesul primește 429.

`commit_operation()` este unica cale runtime de publicare a profilului, mesajelor, căutărilor și rapoartelor. Verifică durata de viață, închiderea, anularea, deadline-ul, revizia/resursa și bugetele înainte de modificarea stării. Răspunsul conține numai mesajele operației, fără reconstrucție prin diferențe de lungime ale istoricului.

Close, unload, expirare și shutdown folosesc aceeași tranziție, curățând profilul, istoricul, căutările, rapoartele și rezervările. Nu se păstrează un cache global de identificare derivat din text medical. Startupul șterge doar subdirectoare cu markerul de proprietate `.naturist-session`, fără a traversa symlinkuri/junctions. Shutdownul oprește acceptarea, anulează, așteaptă workerii și apoi închide clienții și poolul.

Anularea exclude publicarea rezultatului. Un apel extern deja trimis poate continua până la finalizarea sa sau timeoutul clientului; Python nu îl oprește forțat. Verificările de deadline/anulare se fac înainte și după etapele lente. Sloturile de concurență rămân ocupate până la ieșirea workerului, chiar dacă rezervările de retenție au fost eliberate la închidere. Un email deja expediat nu poate fi retras; confirmarea tardivă este abandonată. Configurați separat timeouturile clienților AI și Gmail pentru a limita durata unui apel în curs.

## Contabilizare și retenție

Contabilizarea folosește o serializare JSON deterministă, UTF-8 fără escaparea diacriticelor, cu chei ordonate și separatori constanți, plus bytes PDF. Include profilul și metadata păstrate. Vizualizarea fragmentelor este contorizată prin resursa de dovezi; aliasul `report_bytes` al ultimului PDF nu este numărat din nou. Reprezentarea nu măsoară exact memoria Python, modelul de embeddings ori bufferele furnizorilor.

La începutul operației se rezervă atomic un minim configurabil plus dimensiunea datelor snapshotului. Commitul verifică rezultatul real. Resursele unei operații active sunt protejate de retenție. La presiune se propune eliminarea celor mai vechi interacțiuni complete, cu mesajele, căutările și rapoartele lor. Dacă rezultatul tot nu încape, propunerea este refuzată fără eliminări sau actualizări parțiale.

`evictedGroupIds`, `evictedSearchIds` și `evictedReportIds` permit frontendului să elimine mesaje și acțiuni invalide. La generare reușită, căutarea este consumată: panoul de fragmente și butonul ei dispar, fiind înlocuite de recomandare și PDF în aceeași interacțiune. Istoricul recuperat de la server conține numai resurse valabile.

| HTTP | Situație |
|---|---|
| 413 | Body API prea mare, inclusiv fără Content-Length sau cu lungime falsă |
| 429 | Rate limiting, plafon per client sau capacitate de operații lente |
| 409 | Sesiune/context/resursă invalidă, generare duplicată sau buget per sesiune insuficient |
| 503 | Plafon global, shutdown sau autorizare PostgreSQL indisponibilă |

Erorile controlate au `detail: {code, message}`. Frontendul acceptă și vechiul `detail` string și nu reîncearcă automat generările AI. Cheile inactive ale limitatoarelor sunt eliminate după 120 de secunde; cleanupul rulează și periodic. `SessionStore.metrics()` expune numere de sesiuni/bytes/rezervări/workeri, fără date medicale.

Aceste plafoane sunt garantate numai pentru un singur proces/worker cu registru în memorie. Mai mulți workeri ar necesita registru și limitatoare comune.

## Teste

Backendul folosește evenimente/bariere, ceas injectabil și dependențe sintetice pentru curse, praguri UTF-8/PDF, rollback, retenție și autentificare HTTP. Testele PostgreSQL folosesc implicit testcontainers cu bază efemeră. Pe Windows, dacă SDK-ul Docker nu poate accesa named pipe-ul, harnessul poate lansa un container separat prin CLI și poate transmite exclusiv URL-ul acelei baze temporare prin `TEST_POSTGRES_URL`. Nu transmiteți baza personală: fixture-urile de integrare șterg tabelele de test. `.env` și `DATABASE_URL` nu sunt folosite pentru acest override.

Testul istoric împotriva corpusului/indexului personal este în `src/tests/integration/test_local_corpus.py` și necesită opt-in explicit `RUN_LOCAL_CORPUS_TESTS=1`; nu face parte din verificarea sintetică implicită.
