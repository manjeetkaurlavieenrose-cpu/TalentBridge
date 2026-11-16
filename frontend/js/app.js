import { h, $, mount, toast } from './dom.js';
import { get, post, setCsrf, whenAuthLost, detailsText } from './api.js';
import * as cand from './candidate.js';
import * as rec from './recruiter.js';
import * as adm from './admin.js';

export const state = { me: null };
const root = $('#app');
let leave = [];
export const onLeave = fn => leave.push(fn);

const ROUTES = {
  candidate: [[/^#\/?$/, cand.dashboard], [/^#\/jobs$/, cand.jobs], [/^#\/applications$/, cand.applications], [/^#\/application\/(\w+)$/, cand.application],
              [/^#\/assessment\/(\w+)$/, cand.assessment], [/^#\/account$/, cand.account]],
  recruiter: [[/^#\/?$/, rec.jobs], [/^#\/job\/(\w+)$/, rec.job], [/^#\/application\/(\w+)$/, rec.application],
              [/^#\/compare\/(\w+)\/([\w,]+)$/, rec.compare], [/^#\/candidates$/, rec.candidates], [/^#\/candidate\/(\w+)$/, rec.candidate], [/^#\/team$/, rec.team]],
  admin: [[/^#\/?$/, adm.users], [/^#\/audit$/, adm.audit]],
};
const NAV = {
  candidate: [['#/', 'My CV and profile'], ['#/jobs', 'Openings'], ['#/applications', 'Applications'], ['#/account', 'Account']],
  recruiter: [['#/', 'Openings'], ['#/candidates', 'Candidates'], ['#/team', 'Team']],
  admin: [['#/', 'Users'], ['#/audit', 'Audit log']],
};

function nav() {
  const n = $('#nav');
  if (!state.me) return mount(n);
  const raw = location.hash || '#/';
  const cur = state.me.role === 'candidate' ? raw.replace(/^#\/(application|assessment)\/.*/, '#/applications')
    : raw.replace(/^#\/(job|application|compare)\/.*/, '#/').replace(/^#\/candidate\/.*/, '#/candidates');
  mount(n, NAV[state.me.role].map(([href, label]) => h('a', { href, 'aria-current': cur === href ? 'page' : null }, label)),
    h('span', { class: 'who' }, state.me.candidate?.full_name || state.me.recruiter?.full_name || state.me.email || state.me.role), h('button', { onclick: signOut }, 'Sign out'));
}

async function signOut() {
  try { await post('/auth/logout'); } catch {}
  setCsrf(null); state.me = null; location.hash = '#/'; render();
}

export async function render() {
  leave.forEach(f => f()); leave = [];
  nav();
  if (!state.me) return authView();
  const hash = location.hash || '#/';
  for (const [re, fn] of ROUTES[state.me.role]) {
    const m = hash.match(re);
    if (m) {
      mount(root, h('p', { class: 'm' }, 'Loading…'));
      try { await fn(root, ...m.slice(1)); }
      catch (e) { mount(root, h('div', { class: 'card' }, h('h2', {}, 'Something went wrong'), h('p', { class: 'err' }, e.message))); }
      root.focus({ preventScroll: true });
      return;
    }
  }
  mount(root, h('div', { class: 'card' }, h('h2', {}, 'Page not found'), h('a', { href: '#/' }, 'Go to start')));
}

function authView() {
  const err = h('div', { class: 'err', role: 'alert' });
  const email = h('input', { type: 'email', autocomplete: 'username', required: true });
  const pw = h('input', { type: 'password', autocomplete: 'current-password', required: true });
  const name = h('input', { autocomplete: 'name' });
  const org = h('input', { autocomplete: 'organization' });
  const mode = { v: 'login' };
  const body = h('div');
  const tabs = h('div', { class: 'seg', style: { marginBottom: '6px' } });
  const submit = h('button', { class: 'p', type: 'submit' }, 'Sign in');
  const extra = h('div'), demoBox = h('div'), hint = h('p', { class: 'm small' });
  function draw() {
    mount(tabs, [['login', 'Sign in'], ['candidate', 'I am a candidate'], ['recruiter', 'I am a recruiter']].map(([k, l]) =>
      h('button', { type: 'button', class: mode.v === k ? 'on' : '', onclick: () => { mode.v = k; err.textContent = ''; draw(); } }, l)));
    mount(extra, mode.v !== 'login' && h('label', {}, 'Full name', name), mode.v === 'recruiter' && h('label', {}, 'Organisation', org));
    pw.autocomplete = mode.v === 'login' ? 'current-password' : 'new-password';
    submit.textContent = mode.v === 'login' ? 'Sign in' : 'Create account';
    hint.textContent = mode.v === 'login' ? '' : mode.v === 'candidate' ? 'Choose a password of at least 10 characters. You are signed in straight away.' : 'Choose a password of at least 10 characters. An administrator approves new recruiter accounts.';
  }
  const form = h('form', { onsubmit: async ev => {
    ev.preventDefault(); err.textContent = ''; submit.disabled = true;
    try {
      if (mode.v === 'login') {
        const me = await post('/auth/login', { email: email.value, password: pw.value });
        setCsrf(me.csrf_token); state.me = me; location.hash = '#/'; return render();
      }
      const payload = { email: email.value, password: pw.value, full_name: name.value };
      if (mode.v === 'recruiter') payload.organization = org.value;
      const r = await post('/auth/register/' + mode.v, payload);
      if (mode.v === 'recruiter') { mode.v = 'login'; draw(); toast(r.message); }
      else { const me = await post('/auth/login', { email: email.value, password: pw.value }); setCsrf(me.csrf_token); state.me = me; render(); }
    } catch (e) { err.textContent = detailsText(e); }
    finally { submit.disabled = false; }
  } }, h('label', {}, 'Email', email), h('label', {}, 'Password', pw),
    h('label', { class: 'cb', style: { marginTop: '2px' } }, h('input', { type: 'checkbox', onchange: e => { pw.type = e.target.checked ? 'text' : 'password'; } }), 'Show password'),
    hint, extra, err, submit);
  draw();
  mount(root, h('div', { class: 'hero' },
      h('div', {}, h('div', { class: 'eyebrow' }, 'Candidate assessment and talent matching'),
        h('h1', {}, 'Hiring that shows its work, and leaves the ', h('em', {}, 'decision'), ' to people.'),
        h('p', { class: 'lead' }, 'TalentBridge reads CVs, writes a short skill test for each applicant and checks answers for copied work. Every result comes with the text it is based on, so a reviewer can agree, disagree and decide.')),
      h('div', { class: 'card', style: { borderColor: 'var(--line2)' } }, h('h2', {}, 'Come in'), tabs, form, demoBox)),
    h('div', { class: 'g3 how' },
      h('div', { class: 'card' }, h('h3', {}, 'Evidence, not verdicts'), h('p', { class: 'm' }, 'Each match, score and similarity finding quotes the CV or answer it comes from.')),
      h('div', { class: 'card' }, h('h3', {}, 'Fair to honest applicants'), h('p', { class: 'm' }, 'Template CVs sent in bulk and shared test answers are shown side by side.')),
      h('div', { class: 'card' }, h('h3', {}, 'A person signs off'), h('p', { class: 'm' }, 'Nothing is shortlisted or rejected until a reviewer says so, with a note.'))));
  get('/health', { quiet: true }).then(hl => {
    if (!hl.demo) return;
    const fill = (e, p) => h('button', { type: 'button', class: 's', onclick: () => { mode.v = 'login'; draw(); email.value = e; pw.value = p; err.textContent = ''; } }, 'Fill in');
    mount(demoBox, h('div', { class: 'info demo' }, h('b', {}, 'Demo mode. '), 'All people and companies here are fictional. Pick a login:',
      [['Recruiter', 'recruiter@talentbridge.demo', 'DemoRecruiter#2026'], ['Admin', 'admin@talentbridge.demo', 'DemoAdmin#2026'],
       ['Candidate (Priya)', 'priya.nair@talentbridge.demo', 'DemoCandidate#2026']].map(([l, e, p]) =>
        h('div', { class: 'chk' }, h('span', { class: 'grow' }, l + ': ', h('code', {}, e)), fill(e, p))),
      h('span', { class: 'm' }, 'Or register a new candidate and upload a CV from the sample_data folder.')));
  }).catch(() => {});
}

whenAuthLost(() => { state.me = null; setCsrf(null); render(); });
window.addEventListener('hashchange', render);
(async () => {
  get('/health', { quiet: true }).then(hl => {
    if (!hl.demo) return;
    $('header.top').after(h('div', { class: 'demo-strip', role: 'note' }, 'Demo mode: public demo logins are enabled. Use fictional test data only; do not upload real people\'s CVs here.'));
  }).catch(() => {});
  try { const me = await get('/auth/me', { quiet: true }); setCsrf(me.csrf_token); state.me = me; } catch {}
  render();
})();
