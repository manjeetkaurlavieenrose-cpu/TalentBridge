import { h, mount, toast, tags, field, fmt, empty } from './dom.js';
import { get, post, put, patch, del, api, qs, detailsText } from './api.js';
import { onLeave } from './app.js';
import { matchView, evalView, stepper, stateBadge, identityBadge, meter, pct, badge, engineText } from './views.js';

const MAX = 5 * 1024 * 1024;
const PCT = { uploaded: 15, extracting: 40, analysing: 70, ready: 100, failed: 100 };

function pager(p, onGo) {
  return h('div', { class: 'pager' }, h('span', { class: 'm' }, `Page ${p.page} of ${Math.max(p.pages, 1)} · ${p.total} total`),
    h('button', { class: 's', disabled: p.page <= 1, onclick: () => onGo(p.page - 1) }, 'Previous'),
    h('button', { class: 's', disabled: p.page >= p.pages, onclick: () => onGo(p.page + 1) }, 'Next'));
}

export async function dashboard(root) {
  const cvBox = h('div'), profBox = h('div'), err = h('div', { class: 'err', role: 'alert' }), stepBox = h('div');
  const drawSteps = p => {
    const hasCv = p.cvs.some(c => c.stage === 'ready' && c.active), ok = p.profile_status === 'confirmed', applied = p.applications > 0;
    const at = !hasCv ? 0 : !ok ? 1 : !applied ? 2 : 3;
    const S = [['Upload your CV', 'PDF or Word, your own.'], ['Check what we read', 'Fix anything, then confirm.'], ['Apply to an opening', 'See how you match first.'], ['Take the skill test', 'Short, written, in your own words.']];
    mount(stepBox, h('div', { class: 'steps' }, S.map(([t, d], i) => h('div', { class: 'step ' + (i < at ? 'done' : i === at ? 'now' : '') }, h('b', {}, t), d,
      i === 2 && at === 2 ? h('div', {}, h('a', { href: '#/jobs' }, 'Browse openings →')) : i === 3 && at === 3 ? h('div', {}, h('a', { href: '#/applications' }, 'Your applications →')) : null))));
  };
  let timer = null;
  onLeave(() => clearTimeout(timer));
  let lastReady = '';

  async function refresh() {
    const p = await get('/me/profile');
    drawSteps(p);
    mount(cvBox, p.cvs.length ? p.cvs.slice(0, 8).map(cv => cvRow(cv, refresh)) : empty('No CV yet', 'Choose your file above to begin.'));
    const sig = p.cvs.map(c => c.id + c.stage + c.identity_status + c.active).join() + p.profile_status;
    if (sig !== lastReady) { lastReady = sig; drawProfile(p); }
    if (p.cvs.some(c => ['uploaded', 'extracting', 'analysing'].includes(c.stage))) timer = setTimeout(refresh, 1500);
  }

  function cvRow(cv, after) {
    const busy = ['uploaded', 'extracting', 'analysing'].includes(cv.stage);
    const act = fn => async ev => { ev.target.disabled = true; try { await fn(); toast('Done'); lastReady = ''; await after(); } catch (e) { toast(detailsText(e)); ev.target.disabled = false; } };
    return h('div', { class: 'chk' },
      h('div', { class: 'grow' }, h('div', {}, h('b', { style: { width: 'auto' } }, cv.original_name), ' ', cv.active ? badge('Used for your profile', 'ok') : null,
        cv.stage === 'ready' ? identityBadge(cv.identity_status) : null),
        h('div', { class: cv.stage === 'failed' ? 'err' : 'm' }, cv.stage === 'failed' ? cv.error_message : cv.message, ' · ', fmt(cv.created_at)),
        cv.identity_status === 'mismatch' ? h('div', { class: 'alert' }, cv.identity?.reason,
          ' If this really is your CV (for example after a change of name), you can confirm it. Otherwise remove it: each person should apply from their own account.') : null,
        busy ? h('progress', { max: 100, value: PCT[cv.stage] }) : null),
      h('div', { class: 'row' },
        cv.stage === 'ready' && !cv.active && cv.identity_status !== 'mismatch' ? h('button', { class: 's', onclick: act(() => post(`/me/cvs/${cv.id}/use`, {})) }, 'Use for my profile') : null,
        cv.identity_status === 'mismatch' ? h('button', { class: 's', onclick: act(() => post(`/me/cvs/${cv.id}/use`, { confirm_mine: true })) }, 'This is my CV') : null,
        !cv.used_in_application && !busy ? h('button', { class: 's d', onclick: act(() => del(`/me/cvs/${cv.id}`)) }, 'Remove') : null));
  }

  const input = h('input', { type: 'file', accept: '.pdf,.docx', multiple: true, 'aria-label': 'Choose CV files' });
  const up = h('button', { class: 'p', onclick: async () => {
    err.textContent = '';
    const files = [...input.files];
    if (!files.length) return err.textContent = 'Choose a PDF or DOCX first.';
    if (files.length > 3) return err.textContent = 'Upload at most 3 files at a time.';
    const big = files.find(f => f.size > MAX);
    if (big) return err.textContent = `${big.name} is larger than 5 MB.`;
    const fd = new FormData(); files.forEach(f => fd.append('file', f));
    up.disabled = true;
    try {
      const r = await api('POST', '/me/cvs', fd);
      r.files.filter(f => !f.ok).forEach(f => toast(`${f.name}: ${f.error.message}`));
      r.files.filter(f => f.duplicate).forEach(f => toast(`${f.name} was already uploaded.`));
    } catch (e) { err.textContent = e.message; }
    finally { up.disabled = false; input.value = ''; }
    clearTimeout(timer); refresh();
  } }, 'Upload');

  mount(root, h('div', { class: 'page-head' }, h('div', {}, h('div', { class: 'eyebrow' }, 'Welcome'), h('h1', {}, 'Your CV and ', ('profile')), h('p', { class: 'lead' }, 'Four small steps. You can see everything that is read from your CV, and a person reviews every application.'))),
    stepBox,
    h('div', { class: 'card' }, h('h2', {}, 'CV files'),
      h('div', { class: 'drop' }, h('p', { class: 'm' }, 'PDF or DOCX, up to 5 MB. Password-protected files cannot be read.'), input, h('div', { class: 'row' }, up)), err, cvBox),
    profBox);
  await refresh();

  function drawProfile(p) {
    if (!p.profile) return mount(profBox, h('div', { class: 'card' }, h('h2', {}, 'Your profile'), h('p', { class: 'm' }, 'Upload a CV and the extracted profile appears here for you to check.')));
    const d = structuredClone(p.profile);
    for (const k of ['education', 'work_history', 'skills', 'projects', 'certifications']) d[k] ||= [];
    const name = h('input', { value: p.full_name }), phone = h('input', { value: p.phone || '' });
    const email = h('input', { type: 'email', value: d.email || '' });
    const boxes = { education: h('div'), work_history: h('div'), skills: h('div'), projects: h('div'), certifications: h('div') };
    const msg = h('div', { class: 'err', role: 'alert' });
    const NUM = new Set(['graduation_year', 'year']);
    const editor = (key, cols, blank, label) => {
      const draw = () => mount(boxes[key], d[key].map((item, i) => h('div', { class: 'editrow' },
        cols.map(([k, ph]) => k === 'level' ? h('select', { 'aria-label': ph, onchange: e => { item.level = e.target.value; } },
          [['demonstrated', 'Used in work or projects'], ['listed', 'Listed only']].map(([v, l]) => h('option', { value: v, selected: item.level === v }, l))) :
          h('input', { value: item[k] ?? '', placeholder: ph, 'aria-label': ph, type: NUM.has(k) ? 'number' : 'text',
            oninput: e => { const v = e.target.value; item[k] = NUM.has(k) ? (v === '' ? null : +v) : (v || (['end', 'field', 'issuer', 'context'].includes(k) ? null : '')); } })),
        h('button', { class: 's d', type: 'button', onclick: () => { d[key].splice(i, 1); draw(); } }, 'Remove'))),
        h('button', { class: 's', type: 'button', onclick: () => { d[key].push(structuredClone(blank)); draw(); } }, label));
      draw();
    };
    editor('education', [['degree', 'Degree'], ['field', 'Field'], ['institution', 'Institution'], ['graduation_year', 'Year']], { degree: '', institution: '' }, 'Add education');
    editor('work_history', [['title', 'Job title'], ['company', 'Company'], ['start', 'Start YYYY-MM'], ['end', 'End (blank = current)'], ['description', 'What you did']],
      { title: '', company: '', start: '', description: '', achievements: [] }, 'Add role');
    editor('skills', [['name', 'Skill'], ['level', 'Evidence'], ['context', 'Where you used it']], { name: '', level: 'listed' }, 'Add skill');
    editor('projects', [['name', 'Project'], ['description', 'What it was']], { name: '', description: '', skills: [] }, 'Add project');
    editor('certifications', [['name', 'Certification'], ['issuer', 'Issuer'], ['year', 'Year']], { name: '' }, 'Add certification');

    async function save(confirm) {
      msg.textContent = '';
      d.email = email.value || null;
      d.education = d.education.filter(e => e.degree || e.institution);
      d.work_history = d.work_history.filter(w => w.title || w.company).map(w => ({ ...w, start: w.start || 'unknown', company: w.company || 'Company not stated', title: w.title || 'Role not stated' }));
      d.skills = d.skills.filter(s => (s.name || '').trim());
      d.projects = d.projects.filter(x => (x.name || '').trim());
      d.certifications = d.certifications.filter(x => (x.name || '').trim());
      try {
        const body = { full_name: name.value, phone: phone.value || null, profile: d };
        if (confirm) body.confirm = true;
        await patch('/me/profile', body);
        toast(confirm ? 'Profile confirmed' : 'Changes saved'); lastReady = ''; refresh();
      } catch (e) { msg.textContent = detailsText(e); }
    }
    const warn = (d.gaps || []);
    const active = p.cvs.find(x => x.active), textBox = h('pre', {}, ''), textDet = h('details', {}, h('summary', {}, 'Show the text we read from your CV'), textBox);
    let loaded = false;
    textDet.addEventListener('toggle', async () => {
      if (!textDet.open || loaded || !active) return; loaded = true; textBox.textContent = 'Loading…';
      try { const t = await get('/cvs/' + active.id + '/text'); textBox.textContent = t.text + (t.truncated ? '\n… (shortened)' : ''); } catch (e) { loaded = false; textBox.textContent = e.message; }
    });
    const years = p.total_years == null ? (d.work_history.length ? 'not verifiable (roles without dates)' : 'none found') : `${p.total_years} years`;
    mount(profBox, h('div', { class: 'card' },
      h('div', { class: 'row sp' }, h('h2', {}, 'Check your profile'), badge(p.profile_status === 'confirmed' ? 'Confirmed' : 'Needs your confirmation', p.profile_status === 'confirmed' ? 'ok' : 'warn')),
      h('dl', { class: 'kv' }, h('dt', {}, 'Read from'), h('dd', {}, active ? active.original_name : '–'), h('dt', {}, 'Dated experience'), h('dd', {}, years),
        d.extracted_by ? [h('dt', {}, 'Read by'), h('dd', {}, engineText(d.extracted_by) + (d.text_source?.startsWith('ocr') ? ' · scanned CV read with OCR' : ''))] : null),
      warn.length ? h('div', { class: 'note' }, h('b', {}, 'Please check: '), h('ul', {}, warn.map(w => h('li', {}, w)))) : null,
      p.applications ? h('div', { class: 'info' }, 'Applications you have already made keep the profile you applied with. Changes here apply to new applications.') : null,
      textDet,
      h('div', { class: 'g2' }, field('Full name', name), field('Phone', phone), field('Email on CV', email)),
      h('h3', {}, 'Work history'), boxes.work_history, h('h3', {}, 'Education'), boxes.education, h('h3', {}, 'Skills'), boxes.skills,
      h('h3', {}, 'Projects'), boxes.projects, h('h3', {}, 'Certifications'), boxes.certifications,
      msg, h('div', { class: 'row' }, h('button', { onclick: () => save(false) }, 'Save changes'),
        h('button', { class: 'p', onclick: () => save(true) }, p.profile_status === 'confirmed' ? 'Save and keep confirmed' : 'Confirm profile'))));
  }
}

export async function jobs(root) {
  const list = h('div'), pg = h('div'), q = h('input', { type: 'search', placeholder: 'Search openings', 'aria-label': 'Search openings' });
  const me = await get('/me/profile');
  const mine = new Map((await get('/me/applications')).data.map(a => [a.job_id, a]));
  const state = { page: 1, kind: '' };
  const tabs = h('div', { class: 'seg', role: 'tablist', 'aria-label': 'Opening type', style: { margin: '8px 0 14px' } });
  const drawTabs = () => mount(tabs, [['', 'All'], ['job', 'Jobs'], ['competition', 'Competitions']].map(([k, l]) =>
    h('button', { class: state.kind === k ? 'on' : '', role: 'tab', 'aria-selected': state.kind === k ? 'true' : 'false', onclick: () => { state.kind = k; state.page = 1; drawTabs(); load(); } }, l)));
  drawTabs();
  async function load() {
    const r = await get('/jobs' + qs({ page: state.page, limit: 10, q: q.value, kind: state.kind }));
    mount(list, r.data.map(j => { const fit = h('div'); const applied = mine.get(j.id);
      return h('div', { class: 'card' }, h('div', { class: 'row sp' }, h('h2', {}, j.title), h('span', {}, j.kind === 'competition' ? badge('Competition', 'info') : null, applied ? badge('Applied', 'ok') : null)),
      h('p', {}, j.description), h('dl', { class: 'kv' }, h('dt', {}, 'Experience'), h('dd', {}, `${j.min_years}+ years`), h('dt', {}, 'Education'), h('dd', {}, j.education_level.replace('_', ' ')),
        h('dt', {}, 'Required'), h('dd', {}, tags(j.required_skills)), j.preferred_skills.length ? h('dt', {}, 'Preferred') : null, j.preferred_skills.length ? h('dd', {}, tags(j.preferred_skills)) : null),
      h('div', { class: 'row' },
        h('button', { onclick: async ev => {
          const b = ev.target; b.disabled = true; mount(fit, h('p', { class: 'm' }, h('span', { class: 'spin' }), 'Comparing your profile with this opening…'));
          try { const m = await get('/me/match/' + j.id);
            mount(fit, h('div', { class: 'info' }, 'Preview from your current profile. It uses the same calculation the hiring team sees; nothing is sent until you apply.'), matchView({ ...m }, { who: 'candidate' }));
          } catch (e) { mount(fit, h('div', { class: 'err', role: 'alert' }, e.message)); }
          b.disabled = false;
        } }, 'Check my fit'),
        applied ? h('a', { href: '#/application/' + applied.id }, h('button', {}, 'View application')) :
        h('button', { class: 'p', disabled: me.profile_status !== 'confirmed', onclick: async ev => {
          ev.target.disabled = true;
          try { const a = await post(`/jobs/${j.id}/apply`); toast('Application sent'); location.hash = '#/application/' + a.id; }
          catch (e) { toast(e.message); ev.target.disabled = false; }
        } }, 'Apply'), !applied && me.profile_status !== 'confirmed' ? h('span', { class: 'm' }, 'Confirm your profile first to apply') : null), fit); }));
    if (!r.data.length) mount(list, h('div', { class: 'card' }, empty(state.kind === 'competition' ? 'No competitions open right now' : 'No openings match', 'Check back soon, or clear the search.')));
    mount(pg, pager(r, n => { state.page = n; load(); }));
  }
  q.addEventListener('input', debounce(() => { state.page = 1; load(); }));
  mount(root, h('div', { class: 'page-head' }, h('div', {}, h('div', { class: 'eyebrow' }, 'Openings'), h('h1', {}, 'Jobs and ', ('competitions')))), q, tabs, list, pg); await load();
}

export async function applications(root) {
  const r = await get('/me/applications');
  mount(root, h('div', { class: 'page-head' }, h('h1', {}, 'Your ', ('applications'))), r.data.length ? h('div', { class: 'card tbl' }, h('table', {},
    h('thead', {}, h('tr', {}, ['Opening', 'Status', 'Match', 'Assessment', 'Applied', ''].map((x, i) => h('th', { class: i === 4 ? 'hide-sm' : i === 2 || i === 3 ? 'r' : '' }, x)))),
    h('tbody', {}, r.data.map(a => h('tr', { class: 'link', onclick: () => { location.hash = '#/application/' + a.id; } },
      h('td', {}, h('a', { href: '#/application/' + a.id }, a.title)), h('td', {}, a.status_label), h('td', { class: 'r num' }, pct(a.match_score)),
      h('td', { class: 'r num' }, a.assessment_score != null ? Math.round(a.assessment_score) + '/100' : '–'), h('td', { class: 'hide-sm m' }, fmt(a.created_at)),
      h('td', { onclick: e => e.stopPropagation() }, a.open_assessment_id ? h('a', { href: '#/assessment/' + a.open_assessment_id }, h('button', { class: 'p s' }, 'Open assessment')) : null))))))
    : h('div', { class: 'card' }, empty('No applications yet', 'When you apply, each application and its next step show up here. ', h('a', { href: '#/jobs' }, 'Browse openings'))));
}

export async function application(root, id) {
  let timer = null; onLeave(() => clearTimeout(timer));
  async function draw() {
    const d = await get('/me/applications/' + id);
    const st = d.assessment?.state?.code;
    const busy = d.status === 'applied' || st === 'preparing' || st === 'processing';
    clearTimeout(timer); if (busy) timer = setTimeout(draw, 1500);
    let next;
    if (d.status === 'applied') next = h('p', {}, h('span', { class: 'spin' }), 'Analysing your CV against this opening…');
    else if (st === 'preparing') next = h('p', {}, h('span', { class: 'spin' }), 'Preparing your assessment from the job requirements and your CV…');
    else if (d.assessment?.available) next = h('div', {}, h('p', {}, d.attempt > 1 ? `The hiring team has offered you another attempt at the skill test (about ${d.assessment.minutes} minutes once you start).` : `Your skill test is ready (about ${d.assessment.minutes} minutes once you start). Your answers are saved as you go.`),
      h('a', { href: '#/assessment/' + d.assessment.id }, h('button', { class: 'p' }, d.assessment.status === 'started' ? 'Continue assessment' : 'Start assessment')));
    else if (st === 'processing') next = h('p', {}, h('span', { class: 'spin' }), 'Your answers are saved and being scored…');
    else if (st === 'needs_review') next = h('p', {}, 'Your answers are saved. A member of the hiring team will read them.');
    else if (d.evaluation) next = h('p', {}, 'Your assessment has been scored. A member of the hiring team will now review your application.');
    else next = h('p', { class: 'm' }, 'There is nothing for you to do right now. The hiring team will contact you.');
    mount(root, h('a', { class: 'back', href: '#/applications' }, '← Your applications'),
      h('div', { class: 'card' }, h('div', { class: 'row sp top-al' }, h('div', {}, h('h1', {}, d.job.title), h('p', { class: 'm' }, 'Applied ' + fmt(d.created_at) + (d.cv ? ` with ${d.cv.original_name}` : ''))),
        h('div', {}, badge(d.status_label, 'info'), d.assessment?.state ? stateBadge(d.assessment.state) : null)),
        h('div', { class: 'section' }, h('div', { class: 'eyebrow' }, 'Next step'), next),
        h('p', { class: 'm small' }, 'Scores are guidance only. A person reviews every application and makes every decision.')),
      (d.messages || []).length ? h('div', { class: 'card', style: { borderColor: 'var(--line2)' } }, h('h2', {}, 'Messages from the hiring team'),
        d.messages.map(m => h('div', { class: 'section' }, h('div', { class: 'row sp' }, h('b', {}, m.subject), h('span', { class: 'm small' }, `${m.sender} · ${fmt(m.created_at)}`)),
          h('p', { style: { whiteSpace: 'pre-wrap', marginTop: '6px' } }, m.body)))) : null,
      d.match ? h('div', { class: 'card' }, h('h2', {}, 'How your CV matches this opening'), matchView(d.match, { who: 'candidate' })) : null,
      d.evaluation ? h('div', { class: 'card' }, h('h2', {}, 'Your assessment results'), evalView(d.evaluation, { who: 'candidate' })) : null);
  }
  await draw();
}

export async function assessment(root, id) {
  const a = await get('/assessments/' + id);
  let timer = null; onLeave(() => { clearInterval(timer); clearTimeout(timer); });
  if (a.status === 'sent') {
    return mount(root, h('div', { class: 'card' }, h('h1', {}, a.task.title), h('p', {}, `For ${a.job_title}. You have ${a.minutes} minutes once you start. Your answers are saved automatically and when you leave the page.`),
      h('ul', { class: 'signals' }, h('li', {}, 'The timer starts when you press Start. You can leave and come back; your draft is kept.'),
        h('li', {}, 'Answer in your own words, with concrete steps and examples from your own experience.'),
        h('li', {}, 'To be fair to everyone, answers are compared with other candidates’ answers. Close matches are shown to the reviewer, who reads them before deciding anything.'),
        h('li', {}, 'While the test is open, the page notes when you leave it or move the pointer away, and how much text you paste instead of typing. Only counts and times are kept, never what you do elsewhere, and there is no camera or screen recording. You are told on screen whenever something is noted. A person decides what, if anything, it means.'),
        h('li', {}, 'A person reads your answers. No score accepts or rejects you automatically.')),
      h('button', { class: 'p', onclick: async () => { try { await post(`/assessments/${id}/start`); assessment(root, id); } catch (e) { toast(e.message); } } }, 'Start assessment')));
  }
  if (a.status !== 'started') { if (a.application_id) { location.hash = '#/application/' + a.application_id; return; }
    return mount(root, h('div', { class: 'card' }, h('h1', {}, 'Assessment submitted'), h('p', {}, 'Thank you. The hiring team will review your work and get in touch.'), h('a', { href: '#/applications' }, 'Back to applications'))); }
  const answers = { ...a.answers }; let dirty = false, saving = null, done = false;
  const left = h('span', { class: 'timer', role: 'timer' }), saved = h('span', { class: 'm', 'aria-live': 'polite' }, a.answers && Object.keys(a.answers).length ? 'Draft restored' : ''), err = h('div', { class: 'err', role: 'alert' });
  const end = new Date(a.started_at).getTime() + a.minutes * 60000;
  const tick = () => { const s = Math.max(0, Math.round((end - Date.now()) / 1000)); left.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')} left`; };
  tick(); timer = setInterval(tick, 1000);
  // one save at a time; the server refuses a draft that arrives after the submission, so nothing can overwrite submitted answers
  const save = async () => {
    if (!dirty || done) return saving; if (saving) await saving;
    dirty = false;
    saving = put(`/assessments/${id}/draft`, { answers: { ...answers } })
      .then(r => { saved.textContent = 'Draft saved ' + new Date(r.saved_at).toLocaleTimeString(); })
      .catch(e => { dirty = true; saved.textContent = 'Not saved: ' + e.message; })
      .finally(() => { saving = null; });
    return saving;
  };
  const auto = setInterval(save, 8000);

  // ---- how the test is taken: counts and times only (see backend/app/integrity.py). The candidate is warned, never blocked.
  const queue = [], typed = {}; let awayAt = null, ptrAt = null, ptrTimer = null, leftTimes = 0;
  const notice = h('div', { class: 'watch', role: 'status', 'aria-live': 'polite' }, 'Stay on this page while you answer. Leaving it, moving the pointer away or pasting text is noted for the reviewer.');
  const say = (msg, tone = 'noted') => { notice.textContent = msg; notice.className = 'watch ' + tone; };
  const note = e => queue.push(e);
  const flush = async () => {
    for (const [qid, n] of Object.entries(typed)) if (n) { note({ kind: 'typed', question_id: qid, chars: n }); typed[qid] = 0; }
    while (queue.length && !done) {
      const batch = queue.splice(0, 60);
      try { await post(`/assessments/${id}/activity`, { events: batch }); } catch { queue.unshift(...batch); break; }
    }
  };
  const goAway = () => { if (awayAt == null && !done) awayAt = Date.now(); };
  const comeBack = () => {
    if (awayAt == null) return; const secs = Math.round((Date.now() - awayAt) / 1000); awayAt = null;
    if (secs < 2) return; leftTimes++; note({ kind: 'left_page', seconds: secs });
    say(leftTimes >= 3 ? `You have now left the test page ${leftTimes} times. The reviewer sees this next to your answers. Please stay on this page.`
      : `You were away from the test for ${secs} second${secs === 1 ? '' : 's'}. This is noted for the reviewer. If it was accidental, there is nothing you need to do.`, leftTimes >= 3 ? 'firm' : 'noted');
    flush();
  };
  const onVis = () => document.visibilityState === 'hidden' ? goAway() : comeBack();
  const onPtrOut = () => {
    if (ptrAt != null) return; ptrAt = Date.now();
    ptrTimer = setTimeout(() => say('Your pointer has been outside the test area for a few seconds. Please keep it on this page; this is noted for the reviewer.', 'noted'), 5000);
  };
  const onPtrIn = () => {
    clearTimeout(ptrTimer); if (ptrAt == null) return; const secs = Math.round((Date.now() - ptrAt) / 1000); ptrAt = null;
    if (secs >= 5) note({ kind: 'pointer_out', seconds: secs });
  };
  document.addEventListener('visibilitychange', onVis); window.addEventListener('blur', goAway); window.addEventListener('focus', comeBack);
  document.documentElement.addEventListener('mouseleave', onPtrOut); document.documentElement.addEventListener('mouseenter', onPtrIn);
  const tick2 = setInterval(flush, 10000);
  onLeave(() => { clearInterval(tick2); document.removeEventListener('visibilitychange', onVis); window.removeEventListener('blur', goAway); window.removeEventListener('focus', comeBack);
    document.documentElement.removeEventListener('mouseleave', onPtrOut); document.documentElement.removeEventListener('mouseenter', onPtrIn); clearTimeout(ptrTimer); flush(); });
  const unload = e => { if (dirty && !done) { e.preventDefault(); e.returnValue = ''; } };     // browser asks before closing with unsaved text
  const hidden = () => { if (document.visibilityState === 'hidden') save(); };                  // tab switched or laptop closed: save now
  window.addEventListener('beforeunload', unload); document.addEventListener('visibilitychange', hidden);
  onLeave(() => { clearInterval(auto); window.removeEventListener('beforeunload', unload); document.removeEventListener('visibilitychange', hidden); save(); });
  const sub = h('button', { class: 'p', onclick: async () => {
    const empty = a.task.questions.filter(q => !(answers[q.id] || '').trim()).length;
    if (empty && !confirm(`${empty} question(s) are blank. Submit anyway? You cannot change your answers afterwards.`)) return;
    sub.disabled = true; err.textContent = '';
    try { await save(); await flush(); done = true; await post(`/assessments/${id}/submit`, { answers }); toast('Submitted. Your answers are saved.'); location.hash = '#/application/' + a.application_id; }
    catch (e) { done = false; err.textContent = e.message; sub.disabled = false; }
  } }, 'Submit answers');
  const wc = t => (t.trim().match(/\S+/g) || []).length;
  const progress = h('span', { class: 'm' });
  const counts = {};
  const sync = () => { const n = a.task.questions.filter(q => wc(answers[q.id] || '') >= 5).length; progress.textContent = `${n} of ${a.task.questions.length} answered`;
    left.classList.toggle('low', end - Date.now() < 5 * 60000); };
  mount(root, h('div', { class: 'sticky-bar' }, h('div', {}, h('b', { style: { font: '640 17px var(--serif)' } }, a.task.title), h('div', { class: 'row', style: { gap: '4px 14px' } }, progress, saved), notice), left),
    h('div', { class: 'card' }, h('div', { class: 'eyebrow' }, 'The situation'), h('p', {}, a.task.scenario)),
    a.task.questions.map((q, i) => { const c = counts[q.id] = h('div', { class: 'count' }, `${wc(answers[q.id] || '')} words`);
      return h('div', { class: 'q' }, h('div', { class: 'qn' }, h('span', {}, `Question ${i + 1} of ${a.task.questions.length}`), h('span', {}, `${Math.round(q.max_points)} points`)),
        h('label', { for: 'q' + q.id }, q.prompt),
        h('textarea', { id: 'q' + q.id, value: answers[q.id] || '', placeholder: 'Write your answer here…', style: { minHeight: '150px' },
          oninput: e => { answers[q.id] = e.target.value; dirty = true; c.textContent = `${wc(e.target.value)} words`; sync();
            if ((e.inputType || '').startsWith('insert') && e.inputType !== 'insertFromPaste' && e.inputType !== 'insertFromDrop') typed[q.id] = (typed[q.id] || 0) + (e.data ? e.data.length : 1); },
          onpaste: e => { const n = (e.clipboardData?.getData('text') || '').length; if (n) { note({ kind: 'paste', question_id: q.id, chars: n });
            say(`You pasted ${n} characters. This is noted for the reviewer. The test asks for your own words, so please write the answer yourself.`, 'noted'); flush(); } },
          onblur: save }), c); }),
    h('div', { class: 'card' }, err, h('div', { class: 'row' }, sub, h('button', { onclick: save }, 'Save draft')),
      h('p', { class: 'm small', style: { marginTop: '8px' } }, 'Once submitted, answers cannot be changed. A person reads them.')));
  sync(); const syncT = setInterval(sync, 15000); onLeave(() => clearInterval(syncT));
}

export async function account(root) {
  const pw = h('input', { type: 'password', autocomplete: 'current-password' }), err = h('div', { class: 'err', role: 'alert' });
  mount(root, h('div', { class: 'card' }, h('h1', {}, 'Account'), h('h3', {}, 'Delete my data'),
    h('p', { class: 'm' }, 'This permanently removes your account, CV files, profile, applications and assessments.'),
    field('Confirm your password', pw), err,
    h('button', { class: 'd', onclick: async () => { try { await del('/me', { password: pw.value }); location.reload(); } catch (e) { err.textContent = e.message; } } }, 'Delete everything')));
}

function debounce(fn, ms = 300) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
