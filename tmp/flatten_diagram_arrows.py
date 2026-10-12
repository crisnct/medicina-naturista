import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
root = ET.parse("tmp/diagram-vector.svg").getroot()
for node in list(root):
    if node.tag == f"{{{NS}}}defs":
        root.remove(node)
for parent in list(root.iter()):
    for node in list(parent):
        if node.tag == f"{{{NS}}}path":
            node.set("d", re.sub(r"-?\d+\.\d+", lambda match: format(float(match.group()), ".1f").rstrip("0").rstrip("."), node.get("d")))
        start = node.attrib.pop("marker-start", None)
        end = node.attrib.pop("marker-end", None)
        if not (start or end):
            continue
        points = []
        x = y = 0.0
        for command, value in re.findall(r"([MHV])([^MHV]+)", node.get("d")):
            numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", value)]
            if command == "M":
                x, y = numbers
            elif command == "H":
                x = numbers[0]
            elif command == "V":
                y = numbers[0]
            points.append((x, y))
        for enabled, tip, previous in [(start, points[0], points[1]), (end, points[-1], points[-2])]:
            if not enabled:
                continue
            dx, dy = tip[0] - previous[0], tip[1] - previous[1]
            length = math.hypot(dx, dy)
            dx, dy = dx / length, dy / length
            bx, by = tip[0] - dx * 6.72, tip[1] - dy * 6.72
            ET.SubElement(parent, f"{{{NS}}}path", {
                "d": f"M{bx-dy*4.48:.3f} {by+dx*4.48:.3f} L{tip[0]:.3f} {tip[1]:.3f} L{bx+dy*4.48:.3f} {by-dx*4.48:.3f}",
                "fill": "none", "stroke": "#888780", "stroke-width": "1.68",
            })
root.set("width", "1760px")
root.set("height", "1810px")
ET.indent(root, space="  ")
ET.ElementTree(root).write("architecture/chatbot-external-connections.svg", encoding="utf-8", xml_declaration=True)
assert not any(key.startswith("marker-") for node in root.iter() for key in node.attrib)
assert not root.findall(f".//{{{NS}}}text")
assert not root.findall(f".//{{{NS}}}style")
assert len(root.findall(f".//{{{NS}}}title")) == 103
print("Standalone vector SVG:", Path("architecture/chatbot-external-connections.svg").stat().st_size, "bytes")
