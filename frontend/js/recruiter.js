import { h, mount, toast, tags, field, fmt, empty } from './dom.js';
import { get, post, patch, del, api, qs, detailsText } from './api.js';
import { onLeave } from './app.js';
import { matchView, evalView, STAGE, meter, pct, bars, badge, stepper, stateBadge, identityBadge, engineText, ring, origBadge, originalityView, ORIG, ORIG_SHORT } from './views.js';

const EDU = ['none', 'high_school', 'diploma', 'bachelor', 'master', 'phd'];
const csv = s => s.split(',').map(x => x.trim()).filter(Boolean);
const debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const JOB_TONE = { open: 'ok', draft: 'warn', closed: '' };
const JOB_LABEL = { open: 'Open', draft: 'Draft', closed: 'Closed' };
const years = y => y == null ? 'not verifiable' : `${y} yrs`;

function pager(p, onGo) {
  return h('div', { class: 'pager' }, h('span', { class: 'm' }, `Page ${p.page} of ${Math.max(p.pages, 1)} · ${p.total.toLocaleString()} total`),
    h('button', { class: 's', disabled: p.page <= 1, onclick: () => onGo(p.page - 1) }, 'Previous'),
    h('button', { class: 's', disabled: p.page >= p.pages, onclick: () => onGo(p.page + 1) }, 'Next'));
}

export async function jobs(root) {
  const list = h('div'), pg = h('div'), err = h('div', { class: 'err', role: 'alert' }), st = { page: 1 }, overview = h('div');
  (async () => {
    try {
      const o = await get('/dashboard/summary'), a = o.applications;
      const stat = (n, label, title, cls = '') => h('div', { class: 'stat ' + cls, title }, h('b', {}, n), h('span', {}, label));
      mount(overview, h('div', { class: 'stats' }, stat(o.jobs.open, 'open positions', '', 'c1'), stat(a.total, 'applications', `${a.candidates} distinct candidates`, 'c2'),
        stat(a.in_assessment, 'taking a skill test', 'Test sent, started or submitted', 'c4'),
        stat(a.awaiting_review, 'waiting for your review', 'Scored or in human review, plus submissions whose automatic scoring failed', 'c3'),
        stat(a.similarity_flags || 0, 'similarity findings to read', 'Applications whose CV or answers closely match another applicant and that no reviewer has cleared yet', a.similarity_flags ? 'alertish' : 'c1'),
        stat(a.avg_match == null ? '–' : Math.round(a.avg_match) + '%', 'average match', '', 'c2')),
        a.scoring_failed ? h('div', { class: 'alert' }, `${a.scoring_failed} submitted assessment(s) could not be scored automatically. The answers are safe; open the application to read them or retry scoring.`) : null,
        o.top.length ? h('div', { class: 'card' }, h('div', { class: 'eyebrow' }, 'Closest matches on paper'), o.top.map(t => h('div', { class: 'chk', style: { alignItems: 'center' } }, ring(t.match_score, { small: true }),
          h('span', { class: 'grow' }, h('a', { href: '#/application/' + t.id, style: { fontWeight: 650 } }, t.full_name), h('div', { class: 'm' }, t.job_title + ' · ' + STAGE[t.status])))),
          h('p', { class: 'm small' }, 'A starting point for reading, not a ranking. Open each file to see the evidence.')) : null);
    } catch { /* overview is a convenience; the list below still works */ }
  })();
  const f = { title: h('input'), kind: h('select', {}, h('option', { value: 'job' }, 'Job'), h('option', { value: 'competition' }, 'Competition')),
    req: h('input', { placeholder: 'sql, excel, data analysis' }), pref: h('input', { placeholder: 'power bi' }),
    years: h('input', { type: 'number', min: 0, max: 50, value: 0 }), edu: h('select', {}, EDU.map(e => h('option', { value: e }, e.replace('_', ' ')))),
    custom: h('input', { placeholder: 'e.g. dashboard experience, published research' }), desc: h('textarea'), brief: h('input', { placeholder: 'optional scenario for the assessment' }),
    auto: h('input', { type: 'checkbox', checked: true, id: 'auto-new' }),
    size: h('select', {}, [3, 4, 5, 6].map(n => h('option', { value: n, selected: n === 4 }, `${n} questions (about ${Math.max(20, 8 * n + 5)} minutes)`))) };
  const suggest = h('button', { type: 'button', class: 's', onclick: async ev => {
    err.textContent = ''; ev.target.disabled = true;
    try { const r = await post('/jobs/suggest-skills', { description: f.desc.value });
      if (!r.skills.length) err.textContent = 'No known skills found in the description. Type them in manually.';
      else { f.req.value = r.skills.map(x => x.name).join(', '); toast(`${r.skills.length} skills found. Edit the list if needed.`); } }
    catch (e) { err.textContent = detailsText(e); } ev.target.disabled = false;
  } }, 'Suggest skills from description');
  async function load() {
    const r = await get('/jobs' + qs({ page: st.page, limit: 20 }));
    mount(list, r.data.length ? h('div', { class: 'card tbl' }, h('table', {}, h('thead', {}, h('tr', {}, ['Opening', 'Type', 'Status', 'Applicants', 'Required skills'].map((x, i) => h('th', { class: i === 3 ? 'r' : i === 4 ? 'hide-sm' : '' }, x)))),
      h('tbody', {}, r.data.map(j => h('tr', { class: 'link', onclick: () => { location.hash = '#/job/' + j.id; } },
        h('td', {}, h('a', { href: '#/job/' + j.id }, j.title)), h('td', { class: 'm' }, j.kind === 'competition' ? 'Competition' : 'Job'), h('td', {}, badge(JOB_LABEL[j.status], JOB_TONE[j.status])), h('td', { class: 'r num' }, j.applicants),
        h('td', { class: 'hide-sm' }, tags(j.required_skills.slice(0, 4)))))))) :
      h('div', { class: 'card' }, empty('No openings yet', 'Create your first one above and applicants will appear here.')));
    mount(pg, pager(r, n => { st.page = n; load(); }));
  }
  const create = status => async () => {
    err.textContent = '';
    try { await post('/jobs', { title: f.title.value, kind: f.kind.value, description: f.desc.value, required_skills: csv(f.req.value), preferred_skills: csv(f.pref.value),
      custom_requirements: csv(f.custom.value), min_years: +f.years.value || 0, education_level: f.edu.value, task_brief: f.brief.value || null, auto_assessment: f.auto.checked, test_questions: +f.size.value, status });
      toast(status === 'open' ? 'Opening published' : 'Saved as draft'); load(); } catch (e) { err.textContent = detailsText(e); }
  };
  mount(root, h('div', { class: 'page-head' }, h('div', {}, h('div', { class: 'eyebrow' }, "Reviewer's desk"), h('h1', {}, 'Your ', ('openings')))), overview, h('details', { class: 'card' }, h('summary', {}, 'Create an opening'),
    h('div', { class: 'g2' }, h('div', {}, field('Title', f.title), field('Type', f.kind), field('Minimum years of experience', f.years), field('Minimum education', f.edu)),
      h('div', {}, field('Required skills (comma-separated)', f.req), suggest, field('Preferred skills', f.pref), field('Other requirements', f.custom), field('Skill-test scenario', f.brief), field('Skill-test length', f.size))),
    field('Description (paste the job ad here)', f.desc),
    h('label', { class: 'cb', for: 'auto-new' }, f.auto, "Write and send each candidate's skill test automatically when they apply"),
    err, h('div', { class: 'row' }, h('button', { class: 'p', onclick: create('open') }, 'Publish'), h('button', { onclick: create('draft') }, 'Save as draft'))), list, pg);
  await load();
}

export async function job(root, id) {
  const j = await get('/jobs/' + id);
  const st = { page: 1, stage: '', q: '', sort: 'match', flagged: '' }, tbody = h('tbody'), pg = h('div'), pickBox = h('div'), origBox = h('div'), testBox = h('div');
  async function loadOrig() {
    let o; try { o = await get(`/jobs/${id}/originality`); } catch { return; }
    const n = o.flagged.cv + o.flagged.answers;
    const KIND = { cv: 'CV text or template', answers: 'Test answers' };
    mount(origBox, h('div', { class: 'card exhibit ' + (n ? 'concern' : 'fine') }, h('span', { class: 'tab' }, 'Originality'),
      h('div', { class: 'row sp' }, h('h2', { style: { margin: 0 } }, n ? `${o.groups.length} similarity finding${o.groups.length === 1 ? '' : 's'} to read` : 'No similar CVs or answers found'),
        h('button', { class: 's', onclick: async ev => { ev.target.disabled = true; try { const r = await post(`/jobs/${id}/originality/scan`); toast(`Comparing ${r.queued} application(s) again…`); setTimeout(() => { loadOrig(); load(); }, 2500); } catch (e) { toast(e.message); } ev.target.disabled = false; } }, 'Compare everyone again')),
      h('p', { class: 'm' }, `${o.checked.cv} CV(s) and ${o.checked.answers} set(s) of answers compared across your applicants. Mass-produced CVs and shared answers show up as groups.`),
      o.groups.map(g => h('div', { class: 'group' }, h('div', { style: { minWidth: '150px' } }, badge(...ORIG[g.level]), g.three_or_more && g.kind === 'answers' ? badge(`${g.members.length} candidates, same answer`, 'bad') : null,
          h('div', { class: 'm small' }, KIND[g.kind] + (g.members.length > 1 ? ` · up to ${Math.round(g.score)}% in common` : ''))),
        h('div', { class: 'grow' }, h('div', { class: 'people' }, g.members.flatMap((m, i) => [i ? h('span', { class: 'link' }, '↔') : null, h('a', { href: '#/application/' + m.application_id, title: m.job_title }, m.candidate)])),
          g.sample ? h('p', { style: { marginTop: '7px' } }, h('span', { class: 'passage' }, g.sample)) : null,
          g.other_openings ? h('p', { class: 'm small' }, 'Includes an application to another of your openings.') : null))),
      h('div', { class: 'human' }, 'These are leads to read, not verdicts. Open a file to see every matching passage and record what you conclude; nothing is rejected or re-scored by this check.')));
  }
  function skillTest() {
    const out = h('div'), size = h('select', { 'aria-label': 'Number of questions' }, [3, 4, 5, 6].map(n => h('option', { value: n, selected: n === (j.test_questions || 4) }, `${n} questions`)));
    mount(testBox, h('details', { class: 'card' }, h('summary', {}, 'Skill test for this opening'),
      h('p', { class: 'm' }, 'Each applicant gets a test written for them from this opening’s requirements and their own CV. Preview what it looks like, change its length, or send one to everyone who is still waiting.'),
      h('div', { class: 'row' }, h('div', { style: { width: '170px' } }, size),
        h('button', { onclick: async ev => { ev.target.disabled = true; mount(out, h('p', { class: 'm' }, h('span', { class: 'spin' }), 'Writing a sample test…'));
          try { const r = await post(`/jobs/${id}/skill-test/preview`, { test_questions: +size.value });
            mount(out, h('div', { class: 'section' }, h('div', { class: 'row sp' }, h('h3', { style: { margin: 0 } }, r.task.title), badge(`${r.task.minutes} minutes`, 'info')),
              h('p', { class: 'm small' }, `Written by: ${engineText(r.engine)}. ${r.note}`), h('p', {}, r.task.scenario),
              r.task.questions.map((q, i) => h('div', { class: 'qa' }, h('div', { class: 'qh' }, h('span', { class: 'qp' }, `${i + 1}. ${q.prompt}`), h('b', { class: 'num' }, `${Math.round(q.max_points)} pts`)),
                h('details', {}, h('summary', { class: 'small' }, 'Marking guide (never shown to candidates)'), h('p', { class: 'm' }, q.rubric))))));
          } catch (e) { mount(out, h('div', { class: 'err' }, detailsText(e))); } ev.target.disabled = false; } }, 'Preview a test'),
        +size.value !== (j.test_questions || 4) || true ? h('button', { onclick: async ev => { try { await patch('/jobs/' + id, { test_questions: +size.value }); j.test_questions = +size.value; toast(`New tests will have ${size.value} questions`); } catch (e) { toast(detailsText(e)); } } }, 'Use this length') : null,
        h('button', { class: 'p', onclick: async ev => { ev.target.disabled = true; try { const r = await post(`/jobs/${id}/skill-test/send`); toast(r.queued ? `Writing and sending ${r.queued} test(s)…` : 'Everyone already has a test'); setTimeout(load, 2000); } catch (e) { toast(detailsText(e)); } ev.target.disabled = false; } }, 'Send to everyone waiting')), out));
  }
  const chosen = new Set(), cmp = h('button', { disabled: true, onclick: () => { location.hash = `#/compare/${id}/${[...chosen].join(',')}`; } }, 'Compare selected');
  const syncCmp = () => { cmp.disabled = chosen.size < 2 || chosen.size > 5; cmp.textContent = chosen.size ? `Compare selected (${chosen.size})` : 'Compare selected'; };
  async function load() {
    const r = await get(`/jobs/${id}/applications` + qs({ ...st, limit: 25 }));
    mount(tbody, r.data.map(a => h('tr', { class: 'link', onclick: () => { location.hash = '#/application/' + a.id; } },
      h('td', { onclick: e => e.stopPropagation() }, h('input', { type: 'checkbox', 'aria-label': 'Select ' + a.full_name, checked: chosen.has(a.id), style: { margin: 0 },
        onchange: e => { e.target.checked ? chosen.add(a.id) : chosen.delete(a.id); syncCmp(); } })),
      h('td', {}, h('a', { href: '#/application/' + a.id }, a.full_name), ' ', origBadge(a.originality), h('div', { class: 'm small hide-sm' }, a.email)),
      h('td', {}, a.status_label, a.eval_status === 'failed' ? [' ', badge('scoring failed', 'bad')] : null),
      h('td', { class: 'r num' }, pct(a.cv_match_score)), h('td', { class: 'r num' }, h('b', {}, pct(a.match_score))),
      h('td', { class: 'r num' }, a.assessment_score == null ? '–' : Math.round(a.assessment_score)),
      h('td', { class: 'r num hide-sm' }, a.total_years == null ? '–' : a.total_years), h('td', { class: 'hide-sm' }, tags((a.top_skills || []).slice(0, 3)))))
      .concat(r.data.length ? [] : [h('tr', {}, h('td', { colspan: 8 }, empty('Nobody here yet', st.q || st.stage || st.flagged ? 'No application matches these filters.' : 'Applications appear here as candidates apply.')))]));
    mount(pg, pager(r, n => { st.page = n; load(); }));
  }
  const q = h('input', { type: 'search', placeholder: 'Search name or email', 'aria-label': 'Search applications', oninput: debounce(e => { st.q = e.target.value; st.page = 1; load(); }) });
  const stage = h('select', { 'aria-label': 'Filter by stage', onchange: e => { st.stage = e.target.value; st.page = 1; load(); } }, h('option', { value: '' }, 'All stages'), Object.entries(STAGE).map(([k, v]) => h('option', { value: k }, v)));
  const sort = h('select', { 'aria-label': 'Sort', onchange: e => { st.sort = e.target.value; load(); } }, [['match', 'Best overall match'], ['newest', 'Newest'], ['name', 'Name']].map(([k, v]) => h('option', { value: k }, v)));
  const flagOnly = h('label', { class: 'cb', style: { margin: 0, whiteSpace: 'nowrap' } }, h('input', { type: 'checkbox', onchange: e => { st.flagged = e.target.checked ? '1' : ''; st.page = 1; load(); } }), 'Similarity findings only');
  const pickQ = h('input', { type: 'search', placeholder: 'Find a candidate to add', 'aria-label': 'Find candidate', oninput: debounce(async e => {
    if (e.target.value.length < 2) return mount(pickBox);
    const r = await get('/candidates' + qs({ q: e.target.value, limit: 5 }));
    mount(pickBox, r.data.map(c => h('div', { class: 'chk' }, h('span', { class: 'grow' }, `${c.full_name} · ${c.email}`),
      h('button', { class: 's', onclick: async () => { try { await post(`/jobs/${id}/applications`, { candidate_id: c.id }); toast('Added'); mount(pickBox); load(); } catch (er) { toast(er.message); } } }, 'Add'))));
  }) });
  const setStatus = to => async ev => { ev.target.disabled = true; try { await patch('/jobs/' + id, { status: to }); toast(`Opening ${JOB_LABEL[to].toLowerCase()}`); job(root, id); } catch (e) { toast(e.message); ev.target.disabled = false; } };
  const statusActions = { draft: [['open', 'Publish', 'p']], open: [['closed', 'Close to new applications', '']], closed: [['open', 'Reopen', 'p'], ['draft', 'Move to draft', '']] }[j.status];
  mount(root, h('a', { class: 'back', href: '#/' }, '← Openings'),
    h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, j.title, ' ', badge(JOB_LABEL[j.status], JOB_TONE[j.status])),
      h('p', { class: 'm' }, `${j.min_years}+ years · ${j.education_level.replace('_', ' ')} · ${j.test_questions || 4}-question skill test, ${j.auto_assessment ? 'sent automatically' : 'sent by you'}`)),
      h('div', { class: 'row' }, statusActions.map(([to, label, cls]) => h('button', { class: cls, onclick: setStatus(to) }, label)))),
    h('div', { class: 'card' }, h('dl', { class: 'kv' }, h('dt', {}, 'Required'), h('dd', {}, tags(j.required_skills)), h('dt', {}, 'Preferred'), h('dd', {}, j.preferred_skills.length ? tags(j.preferred_skills) : '–'),
      h('dt', {}, 'Other'), h('dd', {}, j.custom_requirements.join(' · ') || '–'), h('dt', {}, 'Scenario'), h('dd', {}, j.task_brief || '–')),
      j.description ? h('p', { class: 'm', style: { marginTop: '8px' } }, j.description) : null),
    origBox, testBox, editPanel(j, id),
    h('details', { class: 'card' }, h('summary', {}, 'Add a candidate from your pool'), pickQ, pickBox),
    h('h2', { style: { marginTop: '22px' } }, 'Applicants'),
    h('div', { class: 'row', style: { marginBottom: '10px' } }, h('div', { class: 'grow', style: { minWidth: '200px' } }, q), h('div', { style: { width: '170px' } }, stage), h('div', { style: { width: '190px' } }, sort), flagOnly, cmp, h('a', { href: `/api/v1/applications/export.csv?job_id=${id}` }, 'Export CSV')),
    h('div', { class: 'card tbl' }, h('table', {}, h('thead', {}, h('tr', {}, [['', ''], ['Candidate', ''], ['Stage', ''], ['CV match', 'r'], ['Overall', 'r'], ['Assessment', 'r'], ['Years', 'r hide-sm'], ['Skills', 'hide-sm']].map(([x, c]) => h('th', { class: c }, x)))), tbody)),
    h('p', { class: 'm small' }, 'Overall = CV match until an assessment is scored, then 0.8 × CV match + 0.2 × assessment. Years and skills are from the profile each person applied with.'), pg);
  skillTest(); loadOrig();
  await load();
}

export async function application(root, id) {
  let timer = null; onLeave(() => clearTimeout(timer));
  async function draw() {
    const d = await get('/applications/' + id);
    const busy = d.assessments.some(a => ['preparing', 'processing'].includes(a.state?.code));
    clearTimeout(timer); if (busy) timer = setTimeout(draw, 2000);
    const err = h('div', { class: 'err', role: 'alert' });
    const act = fn => async ev => { ev.target.disabled = true; err.textContent = ''; try { await fn(); await draw(); } catch (e) { err.textContent = detailsText(e); ev.target.disabled = false; } };
    const cand = d.candidate, p = d.profile || {}, m = d.match;
    const cvBox = h('pre', { hidden: true }); let got = false;
    const ai = m?.ai_analysis;

    const identity = h('div', { class: 'card' }, h('div', { class: 'eyebrow' }, 'Candidate'),
      h('dl', { class: 'kv' }, h('dt', {}, 'Email'), h('dd', {}, cand.email), h('dt', {}, 'Phone'), h('dd', {}, cand.phone || 'not given'),
        h('dt', {}, 'Applied'), h('dd', {}, fmt(d.created_at)),
        h('dt', {}, 'CV used'), h('dd', {}, d.cv ? [d.cv.original_name, ' ', identityBadge(d.cv.identity_status), ' ',
          h('a', { href: `/api/v1/cvs/${d.cv.id}/file` }, 'Download'), ' · ',
          h('button', { class: 'link', onclick: async () => { cvBox.hidden = !cvBox.hidden; if (!cvBox.hidden && !got) { got = true; cvBox.textContent = 'Loading…'; try { cvBox.textContent = (await get('/cvs/' + d.cv.id + '/text')).text; } catch (e) { got = false; cvBox.textContent = e.message; } } } }, 'Text read from it')] : 'none recorded'),
        h('dt', {}, 'Dated experience'), h('dd', {}, m?.experience?.note || years(p.total_experience_years)),
        h('dt', {}, 'Education'), h('dd', {}, (p.education || []).map(e => `${e.degree}${e.field ? ', ' + e.field : ''} (${e.institution}${e.graduation_year ? ', ' + e.graduation_year : ''})`).join('; ') || 'none found')),
      d.cv?.identity_status === 'mismatch' ? h('div', { class: 'alert' }, d.cv.identity?.reason) : null,
      cvBox,
      h('details', {}, h('summary', {}, `Profile submitted with this application (${(p.work_history || []).length} roles, ${(p.skills || []).length} skills)`),
        (p.work_history || []).map(w => h('div', { class: 'chk' }, h('span', { class: 'grow' }, `${w.title} · ${w.company}`), h('span', { class: 'm' }, w.start === 'unknown' ? 'dates not stated' : `${w.start} – ${w.end || 'present'}`))),
        h('div', {}, tags((p.skills || []).map(s => s.name + (s.level === 'demonstrated' ? '' : ' (listed)')))),
        (p.gaps || []).length ? h('div', { class: 'note' }, 'Reading warnings: ', p.gaps.join(' · ')) : null,
        p.extracted_by ? h('p', { class: 'm small' }, `CV read by: ${engineText(p.extracted_by)}${p.text_source?.startsWith('ocr') ? ' · scanned CV, text read with OCR' : ''}`) : null,
        (p.ai_additions || []).length ? h('details', {}, h('summary', { class: 'small' }, `${p.ai_additions.length} item(s) added by the AI reader, each found in the CV text`), h('ul', {}, p.ai_additions.map(a => h('li', { class: 'm small' }, a)))) : null),
      h('a', { href: '#/candidate/' + cand.id, class: 'small' }, 'Open candidate record'));

    mount(root, h('a', { class: 'back', href: '#/job/' + d.job.id }, '← ' + d.job.title),
      h('div', { class: 'page-head' }, h('div', {}, h('div', { class: 'eyebrow' }, 'Evidence file'), h('h1', {}, cand.full_name), h('p', { class: 'm' }, `Application for ${d.job.title}`)),
        h('span', { class: 'stamp ' + (d.status === 'rejected' ? 'bad' : ['shortlisted', 'interview', 'offer'].includes(d.status) ? 'ok' : 'open') }, STAGE[d.status])),
      h('div', { class: 'layout' },
        h('div', {}, identity,
          h('div', { class: 'card' }, h('h2', {}, 'Match to this opening'), matchView(m),
            d.match_history.length ? h('details', {}, h('summary', {}, `Earlier results (${d.match_history.length})`), d.match_history.map(x => h('div', { class: 'tl' }, h('span', { class: 'm' }, fmt(x.replaced_at)), h('span', {}, `${x.score}% · replaced: ${x.reason || 'recalculated'}`)))) : null),
          ai ? h('details', { class: 'card' }, h('summary', {}, `Fit summary and suggested interview questions · ${engineText(ai.engine)}`), h('p', {}, ai.summary), tags(ai.strengths, 'g'), tags(ai.gaps, 'w'), tags(ai.risks || [], 'b'),
            ai.interview_questions?.length ? h('ol', {}, ai.interview_questions.map(q => h('li', { class: 'm' }, q))) : null,
            h('p', { class: 'm small' }, 'Advisory only: a person makes every decision.')) : null,
          h('div', { class: 'card' }, h('h2', {}, 'Skill test'), assessmentPanel(d, act)),
          h('h2', { style: { margin: '24px 0 16px' } }, 'Originality'), originalityView(d.originality, { act, post, appId: id, assessments: d.assessments }),
          h('details', { class: 'card' }, h('summary', {}, `Activity history (${d.timeline.length})`), d.timeline.map(t => h('div', { class: 'tl' }, h('span', { class: 'm' }, fmt(t.created_at)),
            h('span', {}, `${t.actor_role} · ${t.action.replace('application.', '').replace('assessment.', 'skill test ').replace('originality.', 'originality ').replaceAll('_', ' ')}${t.detail?.verdict ? ' → ' + t.detail.verdict + ' (' + t.detail.kind + ')' : ''}${t.detail?.to ? ' → ' + STAGE[t.detail.to] : ''}${t.detail?.note ? ' · “' + t.detail.note + '”' : ''}`))))),
        h('aside', {}, h('div', { class: 'card', style: { borderColor: 'var(--line2)' } }, h('div', { class: 'eyebrow' }, 'Your decision'), stepper(d.status), h('div', { class: 'section' }, reviewPanel(d, act)), err),
          h('div', { class: 'card' }, h('div', { class: 'eyebrow' }, 'Scores'), h('dl', { class: 'kv' },
            h('dt', {}, 'Overall'), h('dd', { class: 'num' }, h('b', {}, pct(m?.score)), m?.provisional ? ' (CV only)' : ''), h('dt', {}, 'CV match'), h('dd', { class: 'num' }, pct(m?.cv_score)),
            h('dt', {}, 'Assessment'), h('dd', { class: 'num' }, m?.assessment == null ? '–' : Math.round(m.assessment) + '/100')),
            (d.originality?.cv || d.originality?.answers) ? h('dl', { class: 'kv' }, h('dt', {}, 'CV originality'), h('dd', {}, d.originality.cv ? badge(...ORIG_SHORT[d.originality.cv.level]) : '–'),
              h('dt', {}, 'Answer originality'), h('dd', {}, d.originality.answers ? badge(...ORIG_SHORT[d.originality.answers.level]) : '–')) : null,
            h('p', { class: 'm small' }, 'Evidence for you to weigh. None of it decides anything.')),
          messagePanel(d, act),
          d.reviews.length ? h('div', { class: 'card' }, h('div', { class: 'eyebrow' }, 'Review notes'), d.reviews.map(r => h('div', { class: 'tl', style: { gridTemplateColumns: '1fr' } },
            h('span', { class: 'm' }, `${fmt(r.created_at)} · ${r.reviewer}`), h('span', {}, r.decision ? [badge(STAGE[r.decision] || r.decision, r.decision === 'rejected' ? 'bad' : 'ok'), ' '] : null, r.task_score != null ? `Assessment score set to ${r.task_score}. ` : '', r.note)))) : null)));
  }
  await draw();
}

function assessmentPanel(d, act) {
  const id = d.id, out = [];
  const live = d.assessments.find(a => !['failed', 'evaluated'].includes(a.status));
  const last = d.assessments[d.assessments.length - 1];
  if ((!d.assessments.length || (last && ['failed', 'evaluated'].includes(last.status) && !live)) && ['applied', 'cv_reviewed', 'ai_evaluated'].includes(d.status) && !live)
    out.push(h('button', { class: 'p', onclick: act(() => post(`/applications/${id}/assessment`)) }, last?.status === 'failed' ? 'Try generating again' : last ? 'Write a new skill test' : 'Write a skill test'));
  if (!d.assessments.length) out.push(h('p', { class: 'm' }, 'No skill test yet.'));
  for (const a of [...d.assessments].reverse()) {
    const latest = a === last;
    const box = [h('div', { class: 'row sp' }, h('h3', { style: { margin: 0 } }, `Attempt ${a.attempt}`), stateBadge(a.state)),
      a.questions_by ? h('p', { class: 'm small' }, `Questions written by: ${engineText(a.questions_by)}`) : null];
    if (a.status === 'failed') box.push(h('div', { class: 'note' }, 'Generation failed. Nothing was sent.'));
    if (a.status === 'draft' && a.task) box.push(taskEditor(a, act));
    if (['sent', 'started'].includes(a.status)) box.push(h('p', { class: 'm' }, `${a.status === 'sent' ? 'Sent' : 'Started'} ${fmt(a.started_at || a.sent_at)} · due ${fmt(a.due_at)}${a.draft_saved_at ? ' · draft last saved ' + fmt(a.draft_saved_at) : ''}`));
    if (a.evaluation) box.push(evalView({ ...a.evaluation }, { questions: a.task.questions, answers: a.answers }));
    else if (a.answers) box.push(h('p', { class: 'm' }, `Submitted ${fmt(a.submitted_at)}.`), a.task.questions.map((q, i) => h('div', { class: 'qa' },
      h('div', { class: 'qp' }, `${i + 1}. ${q.prompt}`), h('div', { class: 'ans' + ((a.answers[q.id] || '').trim() ? '' : ' empty') }, (a.answers[q.id] || '').trim() || '(no answer)'))));
    if (a.status === 'submitted' && a.eval_status === 'failed') box.push(h('div', { class: 'alert' }, 'Automatic scoring failed: ', a.eval_error || 'unknown error', '. The answers above are stored safely and were not scored as 0.'),
      h('button', { onclick: act(() => post(`/assessments/${a.id}/rescore`)) }, 'Retry scoring'));
    if (latest && (a.status === 'evaluated' || a.can_retry_scoring) && ['ai_evaluated', 'human_review', 'assessment_submitted'].includes(d.status)) {
      const why = h('input', { placeholder: 'Reason (optional, kept in the history)', 'aria-label': 'Reason for the second attempt' });
      const canSend = ['ai_evaluated', 'human_review'].includes(d.status);
      const offer = (fresh, send) => act(async () => { await post(`/assessments/${a.id}/retake`, { fresh, send, note: why.value || undefined }); toast(send ? 'Second attempt sent to the candidate' : 'Draft created: edit and send it below'); });
      box.push(h('details', { open: !!d.second_attempt_hint }, h('summary', {}, 'Offer a second attempt'),
        d.second_attempt_hint ? h('div', { class: 'human' }, d.second_attempt_hint) : h('p', { class: 'm' }, 'Your decision. This attempt, its answers and its score stay on file either way.'),
        why, h('div', { class: 'row' }, canSend ? h('button', { class: 'p', onclick: offer(true, true) }, 'Send a new test (new questions)') : null,
          canSend ? h('button', { onclick: offer(false, true) }, 'Send the same questions again') : null,
          h('button', { onclick: offer(false, false) }, 'Create a draft to edit first'))));
    }
    out.push(h('div', { class: 'section' }, box));
  }
  return h('div', {}, out);
}

function messagePanel(d, act) {
  const first = d.candidate.full_name.split(' ')[0], job = d.job.title;
  const T = { '': ['', ''],
    info: [`A question about your application for ${job}`, `Hello ${first},\n\nThank you for applying. Before we go further, could you tell us:\n\n- \n\nMany thanks.`],
    interview: [`Invitation to talk about ${job}`, `Hello ${first},\n\nWe enjoyed reading your application and would like to invite you to a conversation. Would any of these times suit you?\n\n- \n\nPlease reply with what works for you.`],
    retake: [`A second attempt at the ${job} skill test`, `Hello ${first},\n\nWe would like to give you another go at the skill test. You will find it in your TalentBridge account under Applications. Take your time and answer in your own words.`],
    thanks: [`Your application for ${job}`, `Hello ${first},\n\nThank you for the time you put into your application. `] };
  const subj = h('input', { placeholder: 'Subject', 'aria-label': 'Subject' }), text = h('textarea', { placeholder: 'Write to the candidate…', style: { minHeight: '110px' }, 'aria-label': 'Message' });
  const pick = h('select', { 'aria-label': 'Start from', onchange: e => { const [a, b] = T[e.target.value]; if (e.target.value) { subj.value = a; text.value = b; } } },
    [['', 'Start from…'], ['info', 'Ask for information'], ['interview', 'Invite to interview'], ['retake', 'Offer a second attempt'], ['thanks', 'Thank / update']].map(([k, v]) => h('option', { value: k }, v)));
  return h('div', { class: 'card' }, h('div', { class: 'eyebrow' }, 'Follow up with the candidate'), pick, subj, text,
    h('button', { class: 'p', onclick: act(async () => { const r = await post(`/applications/${d.id}/email`, { subject: subj.value, body: text.value }); toast(r.note); }) }, 'Send message'),
    h('p', { class: 'm small', style: { marginTop: '8px' } }, 'You write it; nothing is sent automatically. The candidate sees it in their account, and by e-mail when an e-mail service is connected.'),
    (d.messages || []).length ? h('details', {}, h('summary', {}, `Sent (${d.messages.length})`), d.messages.map(m => h('div', { class: 'tl', style: { gridTemplateColumns: '1fr' } },
      h('span', { class: 'm' }, `${fmt(m.created_at)} · ${m.sender} · ${m.status === 'sent' ? 'e-mailed' : 'in their account'}`), h('b', {}, m.subject)))) : null);
}

function taskEditor(a, act) {
  const t = structuredClone(a.task);
  const title = h('input', { value: t.title }), scen = h('textarea', { value: t.scenario }), mins = h('input', { type: 'number', min: 15, max: 120, value: t.minutes });
  const qs_ = t.questions.map(q => ({ q, p: h('textarea', { value: q.prompt }), r: h('textarea', { value: q.rubric }), pts: h('input', { type: 'number', min: 1, max: 100, value: q.max_points }) }));
  const collect = () => ({ title: title.value, scenario: scen.value, minutes: +mins.value, questions: qs_.map(x => ({ id: x.q.id, prompt: x.p.value, rubric: x.r.value, max_points: +x.pts.value, ...(x.q.expected_points ? { expected_points: x.q.expected_points } : {}) })) });
  return h('div', {}, h('p', { class: 'm' }, 'Review and edit before it goes to the candidate. The rubric is never shown to them.'), field('Title', title), field('Scenario', scen), field('Minutes', mins),
    qs_.map((x, i) => h('div', { class: 'q' }, field(`Question ${i + 1}`, x.p), field('Rubric (private)', x.r), field('Points', x.pts))),
    h('div', { class: 'row' }, h('button', { onclick: act(() => patch(`/assessments/${a.id}`, collect())) }, 'Save edits'),
      h('button', { class: 'p', onclick: act(async () => { await patch(`/assessments/${a.id}`, collect()); await post(`/assessments/${a.id}/send`); toast('Sent to candidate'); }) }, 'Send to candidate')));
}

function reviewPanel(d, act) {
  const id = d.id, next = d.allowed_next;
  const score = h('input', { type: 'number', min: 0, max: 100, placeholder: 'optional' }), note = h('textarea', { placeholder: 'What you checked and why', style: { minHeight: '80px' } });
  const hasEval = d.assessments.some(a => a.status === 'evaluated');
  const LABEL = { human_review: 'Start human review', cv_reviewed: 'Mark CV reviewed', shortlisted: 'Shortlist', rejected: 'Reject', interview: 'Move to interview', offer: 'Move to offer', closed: 'Close application' };
  const decide = to => act(async () => {
    if (to === 'rejected' && !confirm('Reject this application? The candidate will see “Not progressing”.')) throw new Error('Cancelled.');
    if (d.status === 'human_review' && (to === 'shortlisted' || to === 'rejected')) await post(`/applications/${id}/review`, { note: note.value, decision: to, task_score: score.value === '' ? null : +score.value });
    else await post(`/applications/${id}/transition`, { to, note: note.value || undefined });
    toast(`Moved to ${STAGE[to]}`);
  });
  return h('div', {}, field('Review note', note), hasEval ? field('Override assessment score (0–100)', score) : null,
    h('div', { class: 'actions' },
      next.map(to => h('button', { class: to === 'shortlisted' || (to === 'human_review') ? 'p' : to === 'rejected' ? 'd' : '', onclick: decide(to) }, LABEL[to])),
      h('button', { onclick: act(async () => { if (!note.value.trim() && score.value === '') throw new Error('Write a note or set a score first.'); await post(`/applications/${id}/review`, { note: note.value, task_score: score.value === '' ? null : +score.value }); toast('Note saved'); }) }, 'Save note only')),
    !next.length ? h('p', { class: 'm small' }, d.status === 'closed' ? 'This application is closed.' : 'Waiting for the candidate or the scoring; no manual step is available now.') : null);
}

export async function candidates(root) {
  const st = { page: 1, q: '', sort: 'newest', min_years: '', skill: '', profile_status: '' }, tbody = h('tbody'), pg = h('div'), err = h('div', { class: 'err', role: 'alert' });
  async function load() {
    const r = await get('/candidates' + qs({ ...st, limit: 25 }));
    mount(tbody, r.data.map(c => h('tr', { class: 'link', onclick: () => { location.hash = '#/candidate/' + c.id; } }, h('td', {}, h('a', { href: '#/candidate/' + c.id }, c.full_name), c.cv_warnings ? [' ', badge('CV ownership', 'bad')] : null),
      h('td', { class: 'hide-sm' }, c.email), h('td', { class: 'r num' }, c.applications), h('td', { class: 'r num' }, c.total_years == null ? '–' : c.total_years), h('td', { class: 'hide-sm' }, tags((c.top_skills || []).slice(0, 3))),
      h('td', {}, badge(c.profile_status, c.profile_status === 'confirmed' ? 'ok' : c.profile_status === 'draft' ? 'warn' : '')))));
    if (!r.data.length) mount(tbody, h('tr', {}, h('td', { colspan: 6 }, empty('No candidates found', 'Try a different search, or add someone above.'))));
    mount(pg, pager(r, n => { st.page = n; load(); }));
  }
  const nm = h('input', { placeholder: 'Full name' }), em = h('input', { type: 'email', placeholder: 'Email' });
  mount(root, h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Candidates'), h('p', { class: 'm' }, 'People who applied to your openings, plus records your organisation created.'))),
    h('details', { class: 'card' }, h('summary', {}, 'Add a candidate'), field('Full name', nm), field('Email', em), err,
    h('p', { class: 'm' }, 'If this person later registers with the same email, they take over this record.'), h('button', { class: 'p', onclick: async () => {
      err.textContent = ''; try { const c = await post('/candidates', { full_name: nm.value, email: em.value }); location.hash = '#/candidate/' + c.id; } catch (e) { err.textContent = detailsText(e); } } }, 'Create')),
    h('div', { class: 'row', style: { marginBottom: '10px' } }, h('input', { type: 'search', placeholder: 'Search name or email', 'aria-label': 'Search candidates', oninput: debounce(e => { st.q = e.target.value; st.page = 1; load(); }) }),
      h('input', { type: 'search', placeholder: 'Filter by skill, e.g. sql', 'aria-label': 'Filter by skill', oninput: debounce(e => { st.skill = e.target.value.trim(); st.page = 1; load(); }) }),
      h('select', { 'aria-label': 'Profile status', onchange: e => { st.profile_status = e.target.value; st.page = 1; load(); } }, [['', 'Any profile'], ['confirmed', 'Confirmed'], ['draft', 'Draft'], ['empty', 'No CV yet']].map(([k, v]) => h('option', { value: k }, v))),
      h('select', { 'aria-label': 'Sort', onchange: e => { st.sort = e.target.value; load(); } }, [['newest', 'Newest'], ['name', 'Name'], ['experience', 'Most experience']].map(([k, v]) => h('option', { value: k }, v)))),
    h('div', { class: 'card tbl' }, h('table', {}, h('thead', {}, h('tr', {}, [['Name', ''], ['Email', 'hide-sm'], ['Applications', 'r'], ['Years', 'r'], ['Skills', 'hide-sm'], ['Profile', '']].map(([x, c]) => h('th', { class: c }, x)))), tbody)), pg);
  await load();
}

export async function candidate(root, id) {
  let timer = null; onLeave(() => clearTimeout(timer));
  async function draw() {
    const c = await get('/candidates/' + id);
    if (c.cvs.some(x => ['uploaded', 'extracting', 'analysing'].includes(x.stage))) { clearTimeout(timer); timer = setTimeout(draw, 1500); }
    const input = h('input', { type: 'file', accept: '.pdf,.docx', 'aria-label': 'CV file' }), err = h('div', { class: 'err', role: 'alert' });
    const p = c.profile;
    mount(root, h('a', { class: 'back', href: '#/candidates' }, '← Candidates'),
      h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, c.full_name), h('p', { class: 'm' }, `${c.email}${c.phone ? ' · ' + c.phone : ''} · ${c.has_account ? 'has an account' : 'record managed by your organisation'}`)),
        badge('Profile ' + c.profile_status, c.profile_status === 'confirmed' ? 'ok' : 'warn')),
      h('div', { class: 'card' }, h('h2', {}, 'Applications'), c.applications.length ? h('div', { class: 'tbl' }, h('table', {}, h('thead', {}, h('tr', {}, ['Opening', 'Stage', 'Overall', 'CV used'].map((x, i) => h('th', { class: i === 2 ? 'r' : '' }, x)))),
        h('tbody', {}, c.applications.map(a => h('tr', { class: 'link', onclick: () => { location.hash = '#/application/' + a.id; } }, h('td', {}, h('a', { href: '#/application/' + a.id }, a.title)), h('td', {}, a.status_label),
          h('td', { class: 'r num' }, pct(a.match_score)), h('td', { class: 'm' }, a.cv_name || '–')))))) : h('p', { class: 'm' }, 'None yet. Add them to an opening from its page.')),
      h('div', { class: 'card' }, h('h2', {}, 'CV files'), c.cvs.length ? null : h('p', { class: 'm' }, 'No CV you can view.'), c.cvs.map(x => { const box = h('pre', { hidden: true }); let got = false;
        return h('div', { class: 'section' }, h('div', { class: 'row sp' }, h('div', {}, h('b', {}, x.original_name), ' ', x.active ? badge('current profile', 'ok') : null, ' ', identityBadge(x.identity_status),
            h('div', { class: x.stage === 'failed' ? 'err' : 'm' }, x.stage === 'failed' ? x.error_message : x.message, ' · ', fmt(x.created_at), x.used_for?.length ? ' · used for ' + x.used_for.join(', ') : '')),
          h('div', { class: 'row' }, x.stage === 'ready' ? h('button', { class: 's', onclick: async () => { box.hidden = !box.hidden; if (!box.hidden && !got) { got = true; box.textContent = 'Loading…'; try { box.textContent = (await get('/cvs/' + x.id + '/text')).text; } catch (e) { got = false; box.textContent = e.message; } } } }, 'Text read from CV') : null,
            h('a', { href: `/api/v1/cvs/${x.id}/file` }, 'Download'))),
          x.identity_status === 'mismatch' ? h('div', { class: 'alert' }, x.identity?.reason, ' ',
            h('button', { class: 's', onclick: async ev => { ev.target.disabled = true; try { const r = await post(`/cvs/${x.id}/reassign`, {}); toast(`Moved to ${x.extracted_name}'s record (${r.applications_moved.length} application(s))`); location.hash = '#/candidate/' + r.candidate_id; } catch (e) { toast(detailsText(e)); ev.target.disabled = false; } } },
              `Move to ${x.extracted_name || 'its owner'}'s record`)) : null,
          (x.warnings || []).length ? h('div', { class: 'note' }, 'Reading warnings: ', x.warnings.join(' · ')) : null, box); }),
        h('div', { class: 'section' }, h('div', { class: 'row' }, input, h('button', { class: 'p', onclick: async ev => {
          if (!input.files[0]) return err.textContent = 'Choose a file first.';
          const fd = new FormData(); fd.append('file', input.files[0]); ev.target.disabled = true;
          try { const r = await api('POST', `/candidates/${id}/cvs`, fd); if (!r.files[0].ok) err.textContent = r.files[0].error.message; else draw(); } catch (e) { err.textContent = e.message; } ev.target.disabled = false;
        } }, 'Upload CV for this person')), err)),
      p ? h('div', { class: 'card' }, h('h2', {}, 'Current profile'), h('p', { class: 'm' }, 'Applications use the profile submitted with them; this is the latest version.'),
        h('h3', {}, 'Experience'), (p.work_history || []).length ? p.work_history.map(w => h('div', { class: 'chk' }, h('span', { class: 'grow' }, `${w.title} · ${w.company}`), h('span', { class: 'm' }, w.start === 'unknown' ? 'dates not stated' : `${w.start} – ${w.end || 'present'}`))) : h('p', { class: 'm' }, 'None found.'),
        h('h3', {}, 'Education'), (p.education || []).map(e => h('div', { class: 'chk' }, h('span', { class: 'grow' }, `${e.degree}${e.field ? ', ' + e.field : ''} · ${e.institution}`), h('span', { class: 'm' }, e.graduation_year || ''))),
        h('h3', {}, 'Skills'), tags((p.skills || []).map(s => s.name + (s.level === 'demonstrated' ? '' : ' (listed)')))) : null,
      c.managed && !c.has_account ? h('div', { class: 'card' }, h('button', { class: 'd', onclick: async ev => {
        if (!ev.target.dataset.sure) { ev.target.dataset.sure = 1; ev.target.textContent = 'Click again to permanently delete'; return; }
        try { await del('/candidates/' + id); toast('Candidate deleted'); location.hash = '#/candidates'; } catch (e) { toast(e.message); }
      } }, 'Delete this record')) : null);
  }
  await draw();
}

export async function team(root) {
  const r = await get('/team');
  mount(root, h('h1', {}, 'Your team'), h('div', { class: 'card tbl' }, h('table', {}, h('thead', {}, h('tr', {}, ['Name', 'Email', 'Status', 'Last sign-in'].map(x => h('th', {}, x)))),
    h('tbody', {}, r.data.map(m => h('tr', {}, h('td', {}, m.full_name), h('td', {}, m.email), h('td', {}, m.status), h('td', {}, fmt(m.last_login_at) || 'never')))))),
    h('p', { class: 'm' }, 'New recruiters are approved by a platform administrator before they can sign in.'));
}

function editPanel(j, id) {
  const err = h('div', { class: 'err', role: 'alert' });
  const f = { title: h('input', { value: j.title }), desc: h('textarea', { value: j.description || '' }), req: h('input', { value: j.required_skills.join(', ') }),
    pref: h('input', { value: j.preferred_skills.join(', ') }), custom: h('input', { value: j.custom_requirements.join(', ') }), years: h('input', { type: 'number', min: 0, max: 50, value: j.min_years }),
    edu: h('select', {}, EDU.map(e => h('option', { value: e, selected: j.education_level === e }, e.replace('_', ' ')))), brief: h('input', { value: j.task_brief || '' }),
    auto: h('input', { type: 'checkbox', checked: !!j.auto_assessment, id: 'auto-edit' }) };
  return h('details', { class: 'card' }, h('summary', {}, 'Edit this opening'),
    h('div', { class: 'g2' }, h('div', {}, field('Title', f.title), field('Minimum years of experience', f.years), field('Minimum education', f.edu), field('Assessment scenario', f.brief)),
      h('div', {}, field('Required skills (comma-separated)', f.req), field('Preferred skills', f.pref), field('Other requirements', f.custom))),
    field('Description', f.desc), h('label', { class: 'cb', for: 'auto-edit' }, f.auto, "Write and send each candidate's assessment automatically when they apply"), err,
    h('p', { class: 'm' }, 'Changing requirements affects scores calculated from now on; existing applications keep their stored result until they are rescored, and earlier results are kept.'),
    h('button', { class: 'p', onclick: async ev => {
      err.textContent = ''; ev.target.disabled = true;
      try { await patch('/jobs/' + id, { title: f.title.value, description: f.desc.value, required_skills: csv(f.req.value), preferred_skills: csv(f.pref.value), custom_requirements: csv(f.custom.value),
        min_years: +f.years.value || 0, education_level: f.edu.value, task_brief: f.brief.value || null, auto_assessment: f.auto.checked });
        toast('Opening updated'); location.hash = '#/job/' + id; location.reload(); }
      catch (e) { err.textContent = detailsText(e); ev.target.disabled = false; }
    } }, 'Save changes'));
}

export async function compare(root, jid, idsCsv) {
  const r = await get(`/jobs/${jid}/compare?ids=${encodeURIComponent(idsCsv)}`);
  const A = r.applications, icon = { match: ['Shown', 'ok'], partial: ['Partial', 'warn'], missing: ['Not found', ''], unknown: ['Not parsed', 'info'] };
  const names = [...new Map(A.flatMap(a => a.skills).map(s => [s.kind + s.skill, s])).values()].sort((x, y) => (x.kind === 'required' ? 0 : 1) - (y.kind === 'required' ? 0 : 1));
  const status = (a, s) => (a.skills.find(x => x.skill === s.skill && x.kind === s.kind) || { status: 'missing' }).status;
  const row = (label, fn, cls = '') => h('tr', {}, h('th', { class: 'wrap' }, label), A.map(a => h('td', { class: cls }, fn(a))));
  mount(root, h('a', { class: 'back', href: '#/job/' + jid }, '← ' + r.job.title), h('h1', {}, 'Compare candidates'),
    h('p', { class: 'm' }, 'Built from stored results. Scores are guidance for a human reviewer, not a ranking decision.'),
    h('div', { class: 'card tbl' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, ''), A.map(a => h('th', { class: 'wrap' }, h('a', { href: '#/application/' + a.id }, a.candidate), h('div', { class: 'm' }, STAGE[a.status]))))),
      h('tbody', {},
        row('Overall match', a => h('b', { class: 'num' }, pct(a.score), a.provisional ? ' (CV only)' : '')),
        row('CV match', a => h('span', { class: 'num' }, pct(a.cv_score))),
        row('Dated experience', a => years(a.years)),
        row('Assessment', a => a.assessment == null ? '–' : h('b', { class: 'num' }, Math.round(a.assessment) + '/100')),
        ['relevance', 'depth', 'accuracy', 'communication', 'structure'].map(k => row({ relevance: 'Relevance', depth: 'Depth', accuracy: 'Points covered', communication: 'Clarity', structure: 'Structure' }[k], a => a.criteria ? Math.round(a.criteria[k]) : '–', 'num')),
        row('Review flags', a => (a.flags || []).length ? (a.flags || []).join(', ').replaceAll('_', ' ') : '–', 'm wrap'),
        row('Similarity to other applicants', a => origBadge(a.originality) || '–'),
        h('tr', {}, h('th', { colspan: A.length + 1, class: 'wrap' }, 'Skills evidence')),
        names.map(s => row(`${s.skill}${s.kind === 'preferred' ? ' (preferred)' : ''}`, a => badge(...icon[status(a, s)]))),
        row('Strengths', a => a.strengths.length ? a.strengths.slice(0, 3).join(' · ') : '–', 'wrap m'),
        row('Gaps', a => a.gaps.length ? a.gaps.slice(0, 3).join(' · ') : '–', 'wrap m')))));
}
