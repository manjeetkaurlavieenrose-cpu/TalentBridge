import { h, mount, toast, fmt } from './dom.js';
import { get, post, qs } from './api.js';

const pager = (p, go) => h('div', { class: 'pager' }, h('span', { class: 'm' }, `Page ${p.page} of ${Math.max(p.pages, 1)} · ${p.total} total`),
  h('button', { class: 's', disabled: p.page <= 1, onclick: () => go(p.page - 1) }, 'Previous'), h('button', { class: 's', disabled: p.page >= p.pages, onclick: () => go(p.page + 1) }, 'Next'));

export async function users(root) {
  const st = { page: 1, status: 'pending', role: '' }, tbody = h('tbody'), pg = h('div');
  async function load() {
    const r = await get('/admin/users' + qs({ ...st, limit: 25 }));
    mount(tbody, r.data.map(u => h('tr', {}, h('td', {}, u.email), h('td', {}, u.role), h('td', {}, u.organization || ''), h('td', {}, u.status), h('td', {}, fmt(u.last_login_at) || 'never'),
      h('td', {}, u.role === 'admin' ? null : u.status === 'active' ? h('button', { class: 's d', onclick: () => set(u, 'suspended') }, 'Suspend') : h('button', { class: 's p', onclick: () => set(u, 'active') }, u.status === 'pending' ? 'Approve' : 'Reactivate')))));
    if (!r.data.length) mount(tbody, h('tr', {}, h('td', { colspan: 6, class: 'm' }, 'Nobody here.')));
    mount(pg, pager(r, n => { st.page = n; load(); }));
  }
  async function set(u, status) { await post(`/admin/users/${u.id}/status`, { status }); toast(`${u.email}: ${status}`); load(); }
  mount(root, h('h1', {}, 'Users'), h('div', { class: 'row' },
    h('select', { 'aria-label': 'Status', onchange: e => { st.status = e.target.value; st.page = 1; load(); } }, [['pending', 'Waiting for approval'], ['active', 'Active'], ['suspended', 'Suspended'], ['', 'All']].map(([k, v]) => h('option', { value: k }, v))),
    h('select', { 'aria-label': 'Role', onchange: e => { st.role = e.target.value; st.page = 1; load(); } }, [['', 'All roles'], ['recruiter', 'Recruiters'], ['candidate', 'Candidates']].map(([k, v]) => h('option', { value: k }, v)))),
    h('div', { class: 'card tbl' }, h('table', {}, h('thead', {}, h('tr', {}, ['Email', 'Role', 'Organisation', 'Status', 'Last sign-in', ''].map(x => h('th', {}, x)))), tbody)), pg);
  await load();
}

export async function audit(root) {
  const st = { page: 1, action: '' }, tbody = h('tbody'), pg = h('div');
  async function load() {
    const r = await get('/admin/audit-logs' + qs({ ...st, limit: 50 }));
    mount(tbody, r.data.map(l => h('tr', {}, h('td', {}, fmt(l.created_at)), h('td', {}, l.actor_role), h('td', {}, l.action), h('td', {}, `${l.entity_type || ''} ${(l.entity_id || '').slice(0, 8)}`), h('td', { class: 'hide-sm' }, l.ip || ''))));
    mount(pg, pager(r, n => { st.page = n; load(); }));
  }
  mount(root, h('h1', {}, 'Audit log'), h('input', { type: 'search', placeholder: 'Filter by exact action, e.g. auth.login_failed', 'aria-label': 'Action filter',
    onchange: e => { st.action = e.target.value; st.page = 1; load(); } }), h('div', { class: 'card tbl' }, h('table', {}, h('thead', {}, h('tr', {}, ['When', 'Who', 'Action', 'Record', 'IP'].map((x, i) => h('th', { class: i === 4 ? 'hide-sm' : '' }, x)))), tbody)), pg);
  await load();
}
