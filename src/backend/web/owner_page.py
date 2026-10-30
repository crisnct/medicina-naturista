"""Owner login/logout form. Credentials travel only in a CSRF-protected POST."""

from __future__ import annotations

import re
from html import escape

from backend.core.language import current_language
from backend.core.texts import script_json, tr


def owner_page(prefix: str, nonce: str) -> str:
    template = """<!doctype html>
<html lang="__LANGUAGE__"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>__COPY_TITLE__</title></head>
<body data-prefix="__PREFIX__"><main><h1>__COPY_TITLE__</h1>
<p>__COPY_DESCRIPTION__</p>
<form id="login"><label for="key">__COPY_KEY__</label>
<input id="key" type="password" autocomplete="off" required maxlength="4096">
<button id="submit" type="submit">__COPY_SUBMIT__</button></form>
<button id="logout" type="button" hidden>__COPY_LOGOUT__</button>
<p id="status" role="status" aria-live="polite"></p>
<p><a href="__PREFIX__/">__COPY_BACK__</a></p></main>
<script nonce="__NONCE__">
const labels = __LABELS__;
const prefix = document.body.dataset.prefix;
const language = '__LANGUAGE__';
const status = document.getElementById('status');
const logout = document.getElementById('logout');
const form = document.getElementById('login');
let csrf = '';
let busy = false;
async function refresh() {
  const response = await fetch(prefix + '/api/owner', {credentials: 'same-origin', cache: 'no-store', headers: {'X-App-Language': language}});
  if (!response.ok) throw new Error('status');
  const data = await response.json();
  csrf = data.csrfToken;
  logout.hidden = !data.authorized;
  status.textContent = data.authorized ? labels.authorized : labels.unauthorized;
}
async function action(path, body) {
  if (busy) return;
  busy = true;
  document.getElementById('submit').disabled = true;
  logout.disabled = true;
  try {
    if (!csrf) await refresh();
    const response = await fetch(prefix + path, {
      method: 'POST', credentials: 'same-origin',
      headers: {'X-App-Language': language, 'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error('authorization');
    await refresh();
  } catch (_) {
    status.textContent = labels.failed;
    csrf = '';
  } finally {
    document.getElementById('key').value = '';
    document.getElementById('submit').disabled = false;
    logout.disabled = false;
    busy = false;
  }
}
form.addEventListener('submit', event => {
  event.preventDefault();
  action('/api/owner/login', {key: document.getElementById('key').value});
});
logout.addEventListener('click', () => action('/api/owner/logout', {}));
refresh().catch(() => { status.textContent = labels.load_failed; });
</script></body></html>"""
    values = {
        "__LANGUAGE__": current_language(),
        "__PREFIX__": escape(prefix, quote=True),
        "__NONCE__": escape(nonce, quote=True),
        "__LABELS__": script_json(
            {
                name: tr("authorization." + name)
                for name in ["authorized", "unauthorized", "failed", "load_failed"]
            }
        ),
        **{
            "__COPY_" + name.upper() + "__": escape(tr("authorization." + name), quote=True)
            for name in ["title", "description", "key", "submit", "logout", "back"]
        },
    }
    return re.sub(
        r"__(?:LANGUAGE|PREFIX|NONCE|LABELS|COPY_[A-Z_]+)__",
        lambda match: values[match[0]],
        template,
    )
