# Implementarea planului 04

Validarea automată a fost reluată la cererea utilizatorului pe 11 octombrie 2026.
Rezultatele de mai jos provin din execuții locale; workflow-ul GitHub nu a fost rulat.

| Cerință | Implementare |
|---|---|
| R01 | `backend.core.conversation.ConversationService` coordonează mesajele, identificarea, căutarea, generarea, emailul și închiderea. FastAPI rămâne frontiera HTTP. |
| R02 | Contracte comune pentru profil, dovezi, identificare, snapshoturi, rezultate, AI, retrieval, email și PDF. Schema raportului din planul 02 este reutilizată. |
| R03 | `Settings.from_env()` citește explicit mediul, validează opțiunile și păstrează separat secretele injectate. Profilul public cere HTTPS, cookies Secure și loguri fără conținut. |
| R04 | Registrul existent limitează per proces căutările/identificările la 2 și generările la 1; duplicatele sunt refuzate înaintea limitei globale. Capacitatea rămâne ocupată până la ieșirea workerului. |
| R05 | Bugetul de 600 secunde al operației este transmis prin context către AI, streaming, PDF și email. Timeouturile cererilor sunt limitate de bugetul rămas, iar rezultatele tardive nu se publică. |
| R06 | Lockuri runtime/dev complete, cu hashuri, pentru Windows/Python 3.11 și Linux/Python 3.11/3.14. Docker folosește lockul Linux și `npm ci`. Mediul GPU nu este reinstalat. |
| R07 | Ruff/mypy configurate gradual; CI separat pentru static, unit, integrare PostgreSQL, frontend și build Docker. Unitarele cu infrastructură au fost separate de cele pure. |
| R08 | 30 de cazuri etichetate explicit pentru un corpus sintetic, identificatori cale/hash, Recall@50, nDCG@10 cu grade, false positives și atenționări. CLI-ul poate captura rezultate reale și compara un baseline compatibil. |
| F14 | README descrie comenzile implementate, instalarea din lockuri, testarea separată, operațiile și formularul owner cu login/logout prin POST și CSRF. |

## Verificarea manuală

Reporniți backendul local după modificări. Modelul Qwen și indexul existent nu se
schimbă prin acest refactor. Nu este necesară reindexarea pentru aceste modificări.

1. Deschideți `http://127.0.0.1:8000/owner`, introduceți cheia în formular și reveniți în conversație.
2. Trimiteți o problemă de sănătate, selectați sursele și verificați mesajele de identificare și fragmentele găsite.
3. Generați raportul, deschideți PDF-ul și verificați că informațiile corespund fragmentelor selectate.
4. Verificați emailul dacă integrarea locală este configurată; un eșec nu trebuie să elimine PDF-ul.
5. Faceți logout din `/owner` și verificați că generarea este din nou restricționată.

Comanda pentru backendul local, din rădăcină:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn backend.web.main:app --host 127.0.0.1 --port 8000 --workers 1
```

## Rezultate ale validării

- Ruff, verificarea formatării celor 118 fișiere incluse și mypy pentru cele 7 module: trecute.
- Windows/Python 3.11: 420 teste unittest unitare, 9 omise pentru dependențe PDF opționale; 80 teste de integrare, 6 omise pentru corpusul personal; 33 teste pytest trecute. Integrarea a folosit numai PostgreSQL temporar.
- Linux/Python 3.11 și 3.14: instalări curate din lockurile dev cu hashuri și `pip check`, apoi aceeași matrice 420/80/33, cu aceleași omisiuni: trecute pe ambele versiuni. Fonturile Unicode sunt instalate explicit în CI.
- Frontend: 45 teste, TypeScript și build Vite trecute. Build Docker cu prefix `/medicina` și cataloage sintetice: trecut, fără deployment.
- Manifestul lockurilor: verificat pe Windows și pe ambele versiuni Linux.
- Teste noi: timeouturi HTTP limitate de deadline, respingerea răspunsurilor tardive, heartbeat-uri după deadline, restaurarea contextului, capacitate păstrată până la ieșirea workerului, PDF tardiv, formular owner/CSP și formulele metricilor RAG.
- Regresie corectată: selecția de categorii învechite este verificată înainte de ieșirea anticipată a unei căutări numai cu semnalul A; răspunsul rămâne `409 CATEGORY_SELECTION_STALE`.
- Qwen a indexat 20 de documente sintetice într-o bază temporară. Pe 30 de cazuri, două execuții reale identice: Recall@50 = 1, nDCG@10 = 0,97086, acoperirea atenționărilor = 1, false positives@10 = 8, fără fragmente neetichetate. Corpusul are două fragmente pozitive per caz; evaluarea nu introduce un prag de eliminare a celorlalte rezultate din top 10. Baseline-ul măsurat, captura și comparația fără regresii sunt păstrate local în `var/output/plan04-qwen-synthetic-*.json`.

## Verificări rămase

- Instalarea curată Windows din lock a fost întreruptă pentru a limita durata; testele Windows au folosit mediul de dezvoltare existent. Nu o considerați validată.
- Cele 9 teste pentru extragerea PDF necesită dependențele opționale; cele 6 teste de corpus personal necesită activare explicită.
- Baseline măsurat pe corpusul personal, cu 30 de cazuri etichetate pentru acesta. Baseline-ul Qwen sintetic și `synthetic_baseline.json` analitic nu îl înlocuiesc.
- Smoke testul public prin Caddy/HTTPS după configurarea profilului și contractelor
  din planul 03. CI nu publică un site și nu certifică infrastructura publică.

Rapoartele bazate pe corpusul personal se păstrează în `var/output` și nu sunt
încărcate în CI. Evaluarea retrieval-ului nu reprezintă validarea clinică a surselor.
