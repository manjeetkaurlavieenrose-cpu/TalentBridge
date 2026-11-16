// Tiny DOM helper. Text is always set via textContent/createTextNode, so API data can never inject markup.
export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') { for (const [n, x] of Object.entries(v)) n.startsWith('--') ? el.style.setProperty(n, x) : (el.style[n] = x); }   // CSSOM is allowed by our CSP; style="..." attributes are not
    else if (k === 'value') el.value = v;
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  add(el, kids);
  return el;
}
function add(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k.nodeType ? k : document.createTextNode(String(k)));
  }
}
export const $ = (s, r = document) => r.querySelector(s);
export const mount = (el, ...kids) => { el.replaceChildren(); add(el, kids); return el; };
let tt;
export function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('on');
  clearTimeout(tt); tt = setTimeout(() => t.classList.remove('on'), 3200);
}
export const fmt = d => d ? new Date(d).toLocaleString() : '';
export const tags = (arr, cls = '') => (arr || []).map(s => h('span', { class: 'tag ' + cls }, s));
export const field = (label, input) => h('label', {}, label, input);

// friendly empty state
export const empty = (title, text, ...more) => h('div', { class: 'empty' }, h('img', { src: '/img/empty.svg', alt: '' }), h('b', {}, title), text, more);
