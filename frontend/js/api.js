let csrf = null;
export const setCsrf = t => { csrf = t; };
let onAuthLost = () => {};
export const whenAuthLost = fn => { onAuthLost = fn; };

export async function api(method, url, body, opts = {}) {
  const init = { method, credentials: 'same-origin', headers: {} };
  if (csrf) init.headers['X-CSRF-Token'] = csrf;
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
  let r;
  try { r = await fetch('/api/v1' + url, init); }
  catch { const e = new Error('Cannot reach the server. Check your connection.'); e.code = 'network'; throw e; }
  const isJson = (r.headers.get('content-type') || '').includes('json');
  const data = isJson ? await r.json() : await r.text();
  if (!r.ok) {
    const e = new Error(data?.error?.message || 'Request failed');
    Object.assign(e, { status: r.status, code: data?.error?.code, details: data?.error?.details });
    if (r.status === 401 && !opts.quiet) onAuthLost();
    throw e;
  }
  return data;
}
export const get = (u, o) => api('GET', u, undefined, o);
export const post = (u, b) => api('POST', u, b ?? {});
export const patch = (u, b) => api('PATCH', u, b);
export const put = (u, b) => api('PUT', u, b);
export const del = (u, b) => api('DELETE', u, b);
export const qs = o => '?' + new URLSearchParams(Object.entries(o).filter(([, v]) => v !== '' && v != null)).toString();

export function detailsText(e) {
  return e.details ? Object.entries(e.details).map(([k, v]) => `${k}: ${v}`).join('; ') : e.message;
}
