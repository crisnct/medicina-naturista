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

# The current scoring diagram is fragment-search-and-scoring.xmind;
# this historical text migration does not edit XMind workbooks.

# The current classification diagram is message-classification-plan.xmind;
# this historical text migration does not edit XMind workbooks.

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
