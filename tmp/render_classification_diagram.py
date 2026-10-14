"""Export the current XMind workbook's embedded vector diagram for local preview."""

from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


def export_preview() -> Path:
    root = Path(__file__).resolve().parents[1]
    with ZipFile(root / "architecture/chatbot-external-connections.xmind") as workbook:
        diagram = workbook.read("attachments/runtime-connections.svg")
    ElementTree.fromstring(diagram)
    destination = root / "tmp/chatbot-connections-preview.svg"
    destination.write_bytes(diagram)
    return destination


if __name__ == "__main__":
    print(export_preview())
