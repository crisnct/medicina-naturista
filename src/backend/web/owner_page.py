"""Owner login/logout form. Credentials travel only in a CSRF-protected POST."""

from html import escape


def owner_page(prefix: str, nonce: str) -> str:
    return """<!doctype html>
<html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Autorizare owner</title></head>
<body data-prefix="__PREFIX__"><main><h1>Autorizare owner</h1>
<p>Introduceți cheia pentru a permite generarea rapoartelor în acest browser.</p>
<form id="login"><label for="key">Cheia owner</label>
<input id="key" type="password" autocomplete="off" required maxlength="4096">
<button id="submit" type="submit">Autorizare</button></form>
<button id="logout" type="button" hidden>Logout</button>
<p id="status" role="status" aria-live="polite"></p>
<p><a href="__PREFIX__/">Înapoi la conversație</a></p></main>
<script nonce="__NONCE__">
const prefix = document.body.dataset.prefix;
const status = document.getElementById('status');
const logout = document.getElementById('logout');
const form = document.getElementById('login');
let csrf = '';
let busy = false;
async function refresh() {
  const response = await fetch(prefix + '/api/owner', {credentials: 'same-origin', cache: 'no-store'});
  if (!response.ok) throw new Error('status');
  const data = await response.json();
  csrf = data.csrfToken;
  logout.hidden = !data.authorized;
  status.textContent = data.authorized ? 'Browserul este autorizat până la logout.' : 'Browserul nu este autorizat.';
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
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error('authorization');
    await refresh();
  } catch (_) {
    status.textContent = 'Operația nu a reușit. Verificați cheia și reîncărcați formularul.';
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
refresh().catch(() => { status.textContent = 'Nu am putut încărca starea autorizării. Reîncărcați pagina.'; });
</script></body></html>""".replace("__PREFIX__", escape(prefix, quote=True)).replace(
        "__NONCE__", escape(nonce, quote=True)
    )
