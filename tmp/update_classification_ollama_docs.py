from pathlib import Path

path = Path("README.md")
text = path.read_text(encoding="utf-8")
replacements = {
    "folosind conexiunea Hugging Face existentă": "folosind Ollama local cu modelul existent `gemma3:1b` (`CONDITION_AI_LOCAL_MODEL`)",
    "Clasificarea trimite către HF numai mesajul și context minimal de rutare, fără PDF sau corpus. `HF_TOKEN` este necesar pentru acest pas indiferent de `AI_PROVIDER`.": "Clasificarea trimite către Ollama local numai mesajul și context minimal de rutare, fără PDF sau corpus. Refolosește `CONDITION_AI_LOCAL_BASE` și `CONDITION_AI_LOCAL_MODEL`, cu temperatura 0, fără cheie API și fără fallback Hugging Face. Este independentă de `AI_PROVIDER`.",
    "Clasifică prin Hugging Face și rutează": "Clasifică prin Ollama local (`gemma3:1b`) și rutează",
    "necesar pentru clasificarea mesajelor și cu `AI_PROVIDER=huggingface`": "necesar cu `AI_PROVIDER=huggingface` sau pentru identificarea afecțiunii prin backendul `huggingface`",
    "Modelul Ollama local (descărcare:": "Modelul Ollama local pentru clasificarea mesajului și identificarea afecțiunii (descărcare:",
    "Adresa Ollama folosită pentru identificarea afecțiunii.": "Adresa Ollama folosită pentru clasificarea mesajului și identificarea afecțiunii.",
    "Timeout la clasificare prin HF": "Timeout la clasificare prin Ollama local",
    "Serviciul `ollama` rulează modelul local de identificare a afecțiunii": "Serviciul `ollama` rulează modelul local de clasificare a mesajului și identificare a afecțiunii",
}
for before, after in replacements.items():
    assert before in text, before
    text = text.replace(before, after)
path.write_text(text, encoding="utf-8")

path = Path("architecture/fragment-search-and-scoring.md")
text = path.read_text(encoding="utf-8").replace("(`/api/classify`, Hugging Face)", "(`/api/classify`, Ollama local `gemma3:1b`)")
path.write_text(text, encoding="utf-8")

path = Path("architecture/message-classification-plan.md")
text = path.read_text(encoding="utf-8")
text = text.replace("folosind conexiunea existentă Hugging Face", "folosind Ollama local cu modelul existent `gemma3:1b`")
text = text.replace("noul clasificator va folosi direct Hugging Face", "noul clasificator folosește direct Ollama local (`gemma3:1b`)")
text = text.replace('HF["Hugging Face · conexiunea existentă<br/>POST /responses"]', 'HF["Ollama local · gemma3:1b<br/>POST /responses"]')
text = text.replace("conectăm clasificatorul la Hugging Face", "conectăm clasificatorul la Ollama local")
text = text.replace("cu `HF_API_BASE`, `HF_TOKEN` și modelul Hugging Face deja configurat pentru identificare. În prima versiune nu adăugăm alt provider sau model implicit.", "cu `CONDITION_AI_LOCAL_BASE` și `CONDITION_AI_LOCAL_MODEL` (`gemma3:1b`), deja configurate pentru identificare. Temperatura este 0, fără cheie API și fără fallback Hugging Face. Timeoutul și bugetul de ieșire rămân independente.")
text = text.replace("apelează Hugging Face și validează", "apelează Ollama local și validează")
path.write_text(text, encoding="utf-8")

path = Path("architecture/message-classification-validation.md")
text = path.read_text(encoding="utf-8").replace("clasificatorul HF cu JSON validat", "clasificatorul Ollama local (`gemma3:1b`) cu JSON validat")
text = text.replace("## Limitarea verificării Hugging Face", "## Verificarea inițială Hugging Face (istoric; provider înlocuit)")
text = text.replace("Pentru activarea clasificării reale sunt necesare credite disponibile în contul Hugging Face. Până atunci, se aplică fallbackul documentat. După refacerea creditelor se poate relua verificarea live cu întrebările sintetice, fără documente medicale sau emailuri reale.", "Clasificarea folosește acum Ollama local (`gemma3:1b`), fără token și fără credite Hugging Face. Refolosește configurația locală de identificare a afecțiunii; indisponibilitatea Ollama păstrează fallbackul sigur spre remedii sau clarificarea cererii de email. Verificarea HF de mai sus descrie exclusiv prima implementare.")
path.write_text(text, encoding="utf-8")

path = Path("tmp/render_classification_diagram.py")
text = path.read_text(encoding="utf-8")
text = text.replace("Clasificare mesaj apelează Hugging Face prin", "Clasificare mesaj apelează Ollama local gemma3:1b prin")
text = text.replace('"Hugging Face · clasificare mesaj",["HF_API_BASE /responses · HF_TOKEN","Model CONDITION_AI_HF_MODEL · timeout separat"]', '"Ollama local · clasificare mesaj",["CONDITION_AI_LOCAL_BASE /responses · fără token","gemma3:1b · CONDITION_AI_LOCAL_MODEL · timeout separat"]')
path.write_text(text, encoding="utf-8")
