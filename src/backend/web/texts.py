"""Bootstrap public copy in the original Vite HTML; assets retain normal static serving."""

from __future__ import annotations

import asyncio
import re
from html import escape
from pathlib import Path

from starlette.responses import FileResponse, HTMLResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from backend.core.texts import public_catalog, script_json, tr


def bootstrap_html(template: str) -> str:
    replacements = {
        "__APP_TEXTS__": script_json(
            {language: public_catalog(language) for language in ("ro", "en")}
        ),
        "__APP_TITLE__": escape(tr("interface.page_title"), quote=True),
        "__APP_DESCRIPTION__": escape(tr("interface.page_description"), quote=True),
    }
    if any(marker not in template for marker in replacements):
        raise RuntimeError("Frontend HTML lacks the text bootstrap; rebuild the frontend once")
    return re.sub(
        r"__APP_(?:TEXTS|TITLE|DESCRIPTION)__", lambda match: replacements[match[0]], template
    )


class TextStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        if path in (".", "", "index.html"):
            # Conditional static responses could retain copy from an older process.
            scope = {
                **scope,
                "headers": [
                    (name, value)
                    for name, value in scope["headers"]
                    if name.lower() not in (b"if-none-match", b"if-modified-since")
                ],
            }
        response = await super().get_response(path, scope)
        if isinstance(response, FileResponse) and Path(response.path).name == "index.html":
            template = await asyncio.to_thread(Path(response.path).read_text, encoding="utf-8")
            response = HTMLResponse(bootstrap_html(template), headers={"Cache-Control": "no-store"})
            if scope["method"] == "HEAD":
                response.body = b""
        return response
