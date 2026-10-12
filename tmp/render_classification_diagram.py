from html import escape
from pathlib import Path
import xml.etree.ElementTree as ET

parts = ['''<svg xmlns="http://www.w3.org/2000/svg" width="1760" height="1810" viewBox="0 0 1760 1810" role="img" aria-labelledby="title description">
<title id="title">Chatbot medicina-naturista — clasificare și conexiuni</title>
<desc id="description">După POST /api/messages, Clasificare mesaj apelează Ollama local gemma3:1b prin POST /api/classify și validează rezultatul JSON pentru revizia curentă a sesiunii. Remedii continuă rezolvarea afecțiunilor și căutarea existentă; diverse caută după mesaj fără identificare AI a afecțiunii și fără cele două notificări despre afecțiuni necunoscute; planta citește afecțiunile asociate din aceeași bază PostgreSQL și afișează numărul rezultatelor DISTINCT. Numele ambigue și cererile neclare necesită clarificări. Dacă AI eșuează, fluxul implicit este remedii; cererile de email necesită clarificare, iar comanda existentă cu o adresă simplă se păstrează. Email raport trimite PDF-ul precedent al sesiunii prin Gmail numai la solicitarea utilizatorului. Reindexarea execută migrările SQL și publică fragmentele și asocierile herbs_benefits atomic în PostgreSQL.</desc>
<style>
text{font-family:"Segoe UI",Arial,sans-serif;fill:#343431}.title{font-size:26px;font-weight:650}.heading{font-size:18px;font-weight:600}.body{font-size:15px}.code{font:14px Consolas,monospace}.label{font-size:13px;fill:#5f5e5a}
.gray rect{fill:#f1efe8;stroke:#888780}.purple rect{fill:#eeedfe;stroke:#7971bb}.teal rect{fill:#e1f5ee;stroke:#4d9a83}.arr{stroke:#888780;stroke-width:1.6;fill:none}.dash{stroke-dasharray:5 4}
</style><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="#888780" stroke-width="1.5"/></marker></defs>
<rect width="1760" height="1810" fill="white"/>
<text x="880" y="42" text-anchor="middle" class="title">Chatbot · clasificarea mesajelor și conexiuni externe</text>
<rect x="430" y="260" width="600" height="1240" rx="12" fill="#fcfcfa" stroke="#b4b2a9" stroke-dasharray="6 5"/>
<text x="450" y="288" class="heading">FastAPI · app:7860 · src/backend</text>
''']


def box(x, y, w, h, title, lines=(), color="gray"):
    parts.append(f'<g class="{color}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>')
    for i, text in enumerate((title, *lines)):
        style = "heading" if i == 0 else "body"
        parts.append(f'<text x="{x+w/2}" y="{y+27+i*24}" text-anchor="middle" class="{style}">{escape(text)}</text>')
    parts.append('</g>')


def arrow(path, dashed=False, bidirectional=False):
    start = ' marker-start="url(#arrow)"' if bidirectional else ''
    parts.append(f'<path d="{path}" class="arr{" dash" if dashed else ""}"{start} marker-end="url(#arrow)"/>')


box(450,70,560,60,"Browser · React SPA",["API aceeași origine · prefix PUBLIC_ROOT_PATH"])
box(450,175,560,60,"Caddy · reverse proxy (Docker Compose)",["HTTP / HTTPS → app:7860"])
arrow("M730 130V175"); arrow("M730 235V305")
box(1120,70,580,130,"Tunel / proxy extern · opțional",["ngrok + proxy JobsHunter existent","PUBLIC_PROXY_NETWORK · implicit jobshunter-net","destinație medicina-caddy:80"])
arrow("M1010 100H1120",True); arrow("M1120 180H1065V205H1010",True)
arrow("M450 100H405V335H450")
parts.append('<text x="395" y="215" text-anchor="end" class="label">Local: direct / proxy Vite · 127.0.0.1:7860</text>')
box(450,305,560,60,"Mesaj · sesiune izolată · categorii și semnale",["POST /api/messages"])
arrow("M730 365V395")
box(450,395,560,65,"Clasificare mesaj",["POST /api/classify · JSON validat · revizie · clarificări"])
box(1120,365,580,95,"Ollama local · clasificare mesaj",["CONDITION_AI_LOCAL_BASE /responses · fără token","gemma3:1b · CONDITION_AI_LOCAL_MODEL · timeout separat"],"purple")
arrow("M1010 420H1120",bidirectional=True)
box(30,365,350,110,"Clasificare indisponibilă",["Fallback remedii + informare","Cerere email → clarificare","Adresă simplă: comandă păstrată"])
arrow("M450 420H380",True)
box(450,505,560,60,"remedii",["Fluxul existent pentru problema de sănătate"])
box(30,505,350,80,"diverse",["Mesaj original → căutare locală","Fără AI / notificări despre afecțiune"])
box(1120,505,580,60,"planta",["Nume / alias → catalog; clarificare dacă este ambiguu"])
arrow("M730 460V505"); arrow("M600 460V480H205V505"); arrow("M865 460V480H1410V505")
box(450,610,560,60,"Rezolvarea afecțiunilor și sinonimelor",["Dicționar PostgreSQL · reîncărcat la modificare"])
arrow("M730 565V610")
box(30,610,350,85,"Catalogul afecțiunilor",["medical_conditions · medical_condition_synonyms","PostgreSQL · nume + sinonime"],"teal")
arrow("M380 648H450")
box(1120,610,580,135,"SQL local · afecțiuni asociate plantei",["herbs → herbs_benefits → medical_conditions","WHERE h.ro ILIKE %s · parametru literal","SELECT DISTINCT mc.id, mc.name · ORDER BY mc.name","Catalog + generație index verificate în aceeași tranzacție"],"teal")
arrow("M1410 565V610")
box(1120,780,580,60,"Rezultat planta",["Total afecțiuni distincte în partea de sus → tabel ID / nume"])
arrow("M1410 745V780")
box(450,720,560,105,"Identificare AI · opțională, numai remedii",["POST /api/condition","Semnal A activ + nicio afecțiune în dicționar","CONDITION_AI_BACKENDS: local,huggingface"])
arrow("M730 670V720")
box(30,735,350,110,"Ollama · identificare locală",["Implicit gemma3:1b","http://ollama:11434/v1/responses","Primul backend implicit"],"purple")
arrow("M450 777H380")
box(1120,880,580,105,"Hugging Face · identificarea afecțiunii",["router.huggingface.co/v1/responses","CONDITION_AI_HF_MODEL · HF_TOKEN","Fallback la eșecul backendului local"],"purple")
arrow("M1010 777H1065V928H1120")
box(450,880,560,110,"Căutare hibridă · POST /api/search",["A: afecțiuni · B: lexical · C: semantic","Qwen3-Embedding-0.6B · ONNX CPU · 1024 dim.","Model din model_cache · întrebări offline"])
arrow("M730 825V880"); arrow("M450 645H415V935H450")
arrow("M380 545H395V907H450")
box(30,915,350,110,"PostgreSQL 16 · db:5432",["pgvector + FTS · documents / chunks","sync_metadata · asocieri herbs_benefits","Sesiuni owner · host 127.0.0.1:5432"],"teal")
arrow("M450 955H380",bidirectional=True)
arrow("M1700 690H1725V1515H20V975H30",bidirectional=True)
parts.append('<text x="1300" y="1505" text-anchor="middle" class="label">SQL plante · citire din aceeași bază PostgreSQL</text>')
box(450,1045,560,110,"Generarea raportului · proprietar autorizat",["POST /api/searches/{search_id}/generate","Profil + fragmente admise → JSON","Generare la cerere · scor minim și buget de context"])
arrow("M730 990V1045")
box(1120,1045,580,135,"LLM · selectat prin AI_PROVIDER",["xai → api.x.ai/v1 · deepseek → api.deepseek.com","huggingface → router.huggingface.co/v1","ollama → OLLAMA_API_BASE (local sau cloud)","Model configurabil · POST /responses"],"purple")
arrow("M1010 1100H1120",bidirectional=True)
box(450,1205,560,65,"Validare raport și citări → PDF local",["GET /api/reports/{tab_id}/{report_id}"])
arrow("M730 1155V1205")
box(30,1120,350,105,"email_raport · acțiune",["Raport precedent din aceeași sesiune","Adresă explicită, validată local","Fără căutare / generare nouă"])
arrow("M500 460V490H15V1170H30")
box(450,1330,560,105,"Email · PDF existent",["Raport selectat înainte de clasificare","Clarificare când lipsește destinatarul","Cereri duplicate fără reexpediere automată"])
arrow("M730 1270V1330",True)
parts.append('<text x="745" y="1300" class="label">Numai la cererea utilizatorului</text>')
arrow("M380 1170H410V1380H450")
box(1120,1305,580,60,"Google OAuth2 · refresh token",["oauth2.googleapis.com/token"])
box(1120,1410,580,60,"Gmail API · trimite email + PDF",["/gmail/v1/users/me/messages/send"])
arrow("M1010 1360H1080V1335H1120"); arrow("M1010 1400H1080V1440H1120"); arrow("M1410 1365V1410")
parts.append('<path d="M30 1530H1700" stroke="#d3d1c7"/><text x="30" y="1559" class="heading">Pregătire și sincronizare index · separat de cererile chatbotului</text>')
box(30,1590,350,120,"Surse și cataloage locale",["medicina-naturista-documente/data/","documents/ · Markdown","medical_conditions / herbs · PostgreSQL"],"teal")
box(450,1590,560,120,"src/scripts/build_hybrid_index.py",["Migrări SQL → fragmentare → embeddings","CPU / CUDA · sincronizare incrementală SHA-256","Fragmente + herbs_benefits: publicare atomică"])
box(1120,1590,580,120,"Hugging Face Hub",["Qwen/Qwen3-Embedding-0.6B → model_cache/","Descărcare la pregătire, dacă lipsește","Nicio conexiune Hub la căutarea în chat"],"purple")
arrow("M380 1650H450",True); arrow("M1120 1650H1010",True)
arrow("M450 1680H390V1005H380",True)
parts.append('<text x="375" y="1450" text-anchor="end" class="label">Publicare atomică în PostgreSQL</text>')
parts.append('<text x="30" y="1750" class="label">Mov: AI / modele · Verde: date locale · Gri: aplicație / rutare · Linie întreruptă: opțional / erori / sincronizare</text>')
parts.append('<text x="30" y="1780" class="label">Asocierile plantei reprezintă coapariții în corpus, inclusiv atenționări. Modelele și URL-urile sunt configurabile.</text></svg>')
# Keep the artifact compatible with SVG 1.1 renderers used by desktop editors.
# Resolve CSS locally so rendering never depends on a CSS parser or SVG 2 markers.
namespace = "http://www.w3.org/2000/svg"
ET.register_namespace("", namespace)
root = ET.fromstring("\n".join(parts))
root.set("version", "1.1")
root.attrib.pop("role", None)
root.attrib.pop("aria-labelledby", None)
root.remove(root.find(f"{{{namespace}}}style"))
text_styles = {
    "title": {"font-size": "26", "font-weight": "700"},
    "heading": {"font-size": "18", "font-weight": "600"},
    "body": {"font-size": "15"},
    "label": {"font-size": "13", "fill": "#5f5e5a"},
}
colors = {"gray": ("#f1efe8", "#888780"), "purple": ("#eeedfe", "#7971bb"), "teal": ("#e1f5ee", "#4d9a83")}
for group in root.findall(f"{{{namespace}}}g"):
    color = group.attrib.pop("class", "")
    if color in colors:
        fill, stroke = colors[color]
        for rectangle in group.findall(f"{{{namespace}}}rect"):
            rectangle.set("fill", fill)
            rectangle.set("stroke", stroke)
for element in root.iter():
    classes = element.attrib.pop("class", "").split()
    if element.tag == f"{{{namespace}}}text":
        element.set("font-family", "Segoe UI, Arial, sans-serif")
        element.set("fill", "#343431")
        for name in classes:
            element.attrib.update(text_styles.get(name, {}))
    if "arr" in classes:
        element.attrib.update({"stroke": "#888780", "stroke-width": "1.6", "fill": "none"})
    if "dash" in classes:
        element.set("stroke-dasharray", "5 4")
    if "marker-start" in element.attrib:
        element.set("marker-start", "url(#arrow-start)")
definitions = root.find(f"{{{namespace}}}defs")
end_marker = definitions.find(f"{{{namespace}}}marker")
end_marker.set("orient", "auto")
start_marker = ET.SubElement(definitions, f"{{{namespace}}}marker", dict(end_marker.attrib))
start_marker.set("id", "arrow-start")
start_marker.set("refX", "2")
ET.SubElement(start_marker, f"{{{namespace}}}path", {
    "d": "M8 1L2 5L8 9", "fill": "none", "stroke": "#888780", "stroke-width": "1.5",
})
ET.indent(root, space="  ")
ET.ElementTree(root).write("architecture/chatbot-external-connections.svg", encoding="utf-8", xml_declaration=True)
