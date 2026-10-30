"""Export public copy and regenerate key/parameter metadata, never a second editable catalog."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from string import Formatter

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "backend/resources/texts.ro.toml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--public-json", action="store_true")
    parser.add_argument("--language", choices=("ro", "en"), default="ro")
    parser.add_argument("--all-public-json", action="store_true")
    args = parser.parse_args()
    with CATALOG.open("rb") as stream:
        sections = tomllib.load(stream)
    values = {
        f"{section}.{key}": value
        for section, items in sections.items()
        for key, value in items.items()
    }
    parameters = {
        key: tuple(sorted({field for _, field, _, _ in Formatter().parse(value) if field}))
        for key, value in values.items()
    }
    public = {
        key: value for key, value in values.items() if key.split(".")[0] in ("common", "interface")
    }
    if args.all_public_json:
        from backend.core.texts import public_catalog

        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps({lang: public_catalog(lang) for lang in ("ro", "en")}, ensure_ascii=False))
        return
    if args.public_json:
        from backend.core.texts import catalog, public_catalog

        public = public_catalog(args.language)
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(public, ensure_ascii=False))
        return
    if args.generate:
        lines = [
            '"""Generated key/parameter contract. Regenerate with scripts.manage_texts --generate."""',
            "",
            "from __future__ import annotations",
            "",
            "TEXT_PARAMETERS: dict[str, tuple[str, ...]] = {",
        ]
        for key, fields in parameters.items():
            items = ", ".join(json.dumps(field) for field in fields)
            entry = f"    {json.dumps(key)}: ({items}{',' if len(fields) == 1 else ''}),"
            if len(entry) <= 100:
                lines.append(entry)
            else:
                lines.append(f"    {json.dumps(key)}: (")
                lines.extend(f"        {json.dumps(field)}," for field in fields)
                lines.append("    ),")
        contract = "\n".join([*lines, "}", ""])
        (ROOT / "backend/core/text_contract.py").write_text(contract, encoding="utf-8")
        metadata = {key: parameters[key] for key in public}
        (ROOT / "frontend/lib/texts.generated.ts").write_text(
            "// Generated key/parameter metadata; contains no message values.\n"
            + "export const TEXT_PARAMETERS = "
            + json.dumps(metadata, ensure_ascii=True, indent=2)
            + " as const;\n",
            encoding="utf-8",
        )
    from backend.core.texts import catalog

    catalog("ro")
    catalog("en")
    print(f"Validated {len(values)} texts ({len(public)} public).")


if __name__ == "__main__":
    main()
