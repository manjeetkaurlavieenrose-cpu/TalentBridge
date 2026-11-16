// Views shared by the candidate and recruiter sides. All text goes through h()/textContent, so CV or answer text can never inject markup.
import { h, tags, fmt } from './dom.js';

export const STAGE = { applied: 'Applied', cv_reviewed: 'CV reviewed', assessment_sent: 'Assessment sent', assessment_started: 'Assessment started',
  assessment_submitted: 'Assessment submitted', ai_evaluated: 'Scored', human_review: 'Human review', shortlisted: 'Shortlisted',
  rejected: 'Rejected', interview: 'Interview', offer: 'Offer', closed: 'Closed' };
// the main path an application moves along (rejected / closed end it from any point)
export const PATH = ['applied', 'cv_reviewed', 'assessment_sent', 'assessment_started', 'assessment_submitted', 'ai_evaluated', 'human_review', 'shortlisted', 'interview', 'offer'];

export const meter = v => h('meter', { min: 0, max: 100, value: v ?? 0, low: 40, high: 70, optimum: 100, 'aria-label': `${Math.round(v ?? 0)} percent` });
export const pct = v => (v == null ? '–' : Math.round(v) + '%');
export const badge = (text, tone = '') => h('span', { class: 'badge ' + tone }, text);
// score dial: the number in the middle, the arc around it (colour only changes with meaning, never to rank people)
export const ring = (v, { unit = '%', small = false, tone = '' } = {}) => h('div', { class: 'ring' + (small ? ' sm' : ''), role: 'img', 'aria-label': v == null ? 'no score yet' : `${Math.round(v)}${unit === '%' ? ' percent' : ' out of 100'}`,
  style: { '--p': v == null ? 0 : Math.max(0, Math.min(100, v)), ...(tone ? { '--c': `var(--${tone})` } : {}) } }, h('b', {}, v == null ? '–' : Math.round(v), v == null ? null : h('small', {}, unit)));
const dial = (v, label, opts) => h('div', { class: 'ringbox' }, ring(v, opts), h('div', { class: 'lbl' }, label));

// compact stage timeline: one bar per step, the current step named in words
export function stepper(status) {
  const ended = status === 'rejected' || status === 'closed';
  const idx = PATH.indexOf(status);
  return h('div', {},
    h('div', { class: 'stepper', role: 'img', 'aria-label': `Stage: ${STAGE[status]}` }, PATH.map((s, i) =>
      h('span', { class: 'st ' + (ended ? (i === PATH.length - 1 ? 'end' : '') : i < idx ? 'done' : i === idx ? 'on' : ''), title: STAGE[s] }))),
    h('div', { class: 'stage-now' }, ended ? h('b', {}, STAGE[status]) : [h('b', {}, STAGE[status]), ` · step ${idx + 1} of ${PATH.length}`,
      idx + 1 < PATH.length ? h('span', { class: 'm' }, ` · next: ${STAGE[PATH[idx + 1]]}`) : null]));
}

export function bars(obj, labels, weights) {
  return h('div', {}, Object.entries(obj || {}).map(([k, v]) => h('div', { class: 'bar' }, h('span', {}, labels?.[k] || k),
    h('span', { class: 'track', role: 'img', 'aria-label': `${labels?.[k] || k}: ${Math.round(v)} of 100` }, h('span', { class: 'fill', style: { width: Math.max(0, Math.min(100, v)) + '%' } })),
    h('b', {}, Math.round(v)), h('span', { class: 'w' }, weights?.[k] != null ? `weight ${Math.round(weights[k])}%` : ''))));
}

const SKILL = { match: ['Shown in use', 'ok'], partial: ['Partial', 'warn'], missing: ['Not found', ''], unknown: ['Not parsed', 'info'] };
const REQ = { met: ['Met', 'ok'], partial: ['Partial', 'warn'], unmet: ['Not found', ''] };
const EXP = { met: ['Met', 'ok'], below: ['Below', 'warn'], not_required: ['Not required', ''], missing: ['Not found', ''], unverified: ['Not verifiable', 'info'], partial: ['Partial', 'warn'] };
const COMP = { required: 'Required skills', preferred: 'Preferred skills', experience: 'Experience', education: 'Education', custom: 'Other requirements', assessment: 'Assessment' };

// m = stored or preview match breakdown (same shape everywhere: one calculation feeds every screen)
export function matchView(m, { who = 'recruiter' } = {}) {
  if (!m) return h('p', { class: 'm' }, h('span', { class: 'spin' }), 'Match is being calculated…');
  const req = m.skills.filter(s => s.kind === 'required'), pref = m.skills.filter(s => s.kind === 'preferred');
  const order = Object.keys(COMP).filter(k => m.components[k]);     // fixed order: the API returns keys alphabetically
  const weights = Object.fromEntries(order.map(k => [k, m.components[k].weight]));
  const scores = Object.fromEntries(order.map(k => [k, m.components[k].score]));
  const ex = m.experience || {}, ed = m.education || {};
  const skillRows = list => list.map(s => h('tr', {}, h('td', {}, s.skill), h('td', { class: 'st' }, badge(...SKILL[s.status] || [s.status])), h('td', { class: 'm' }, s.evidence)));
  return h('div', {},
    h('div', { class: 'scoreline' },
      dial(m.score, m.provisional ? 'Overall match (provisional: CV only)' : 'Overall match'),
      m.cv_score != null ? h('div', {}, h('div', { class: 'sub' }, pct(m.cv_score)), h('div', { class: 'lbl' }, 'CV match')) : null,
      m.assessment != null ? h('div', {}, h('div', { class: 'sub' }, Math.round(m.assessment) + '/100'), h('div', { class: 'lbl' }, 'Assessment')) : null),
    h('p', { class: 'm', style: { marginTop: '8px' } }, m.method || '',
      m.provisional ? (who === 'candidate' ? ' Your assessment result is added once it is scored.' : ' The assessment is added once it is scored.') : ''),
    h('h3', {}, 'How the score is built'), bars(scores, COMP, weights),
    h('h3', {}, 'Evidence from the CV'),
    h('div', { class: 'tbl' }, h('table', { class: 'ev' }, h('tbody', {},
      skillRows(req),
      pref.length ? h('tr', {}, h('th', { colspan: 3 }, 'Preferred skills')) : null, skillRows(pref),
      h('tr', {}, h('th', { colspan: 3 }, 'Experience and education')),
      h('tr', {}, h('td', {}, `Experience (asks ${ex.required ?? 0}+ yrs)`), h('td', { class: 'st' }, badge(...(EXP[ex.status] || [ex.ok ? 'Met' : 'Below', ex.ok ? 'ok' : 'warn']))), h('td', { class: 'm' }, ex.note || `${ex.years} years of dated experience`)),
      h('tr', {}, h('td', {}, `Education (asks ${ed.required_label || '–'})`), h('td', { class: 'st' }, badge(...(EXP[ed.status] || [ed.ok ? 'Met' : 'Below', ed.ok ? 'ok' : 'warn']))), h('td', { class: 'm' }, ed.note || '')),
      (m.requirements || []).length ? h('tr', {}, h('th', { colspan: 3 }, 'Other requirements')) : null,
      (m.requirements || []).map(r => h('tr', {}, h('td', {}, r.requirement), h('td', { class: 'st' }, badge(...REQ[r.status])), h('td', { class: 'm' }, r.evidence || '')))))),
    h('p', { class: 'm small' }, '“Not found” means the CV does not mention it; it is not proof the person lacks the skill. “Not verifiable” means the information exists but could not be checked (e.g. roles without dates).'),
    m.similarity && m.similarity.score != null ? h('details', {}, h('summary', {}, `Text overlap with the job ad: ${Math.round(m.similarity.score)}% (not part of the score)`),
      h('p', { class: 'm' }, m.similarity.note), m.similarity.shared_terms?.length ? h('div', {}, tags(m.similarity.shared_terms.slice(0, 15))) : null) : null,
    m.limitations?.length ? h('details', {}, h('summary', {}, 'Limits of this analysis'), h('ul', {}, m.limitations.map(l => h('li', { class: 'm' }, l))),
      m.scoring_version ? h('p', { class: 'm small' }, `Scoring version ${m.scoring_version}${m.as_of ? ' · calculated ' + m.as_of : ''}`) : null) : null);
}

// what produced a result, in words: never calls rule-based output AI
export const engineText = e => {
  if (!e) return 'unknown engine';
  if (e.includes('unavailable')) return 'Rule-based (AI model was unavailable)';
  if (e.startsWith('local-rules')) return e.includes('verified') ? `Rules + AI reader (${e.split('+ ')[1]?.split(' (')[0] || 'model'})` : 'Rule-based';
  const [kind, ...rest] = e.split(':'); const model = rest.join(':') || kind;
  if (kind === 'ollama') return `AI-assisted (local model ${model})`;
  if (kind === 'openai-compatible') return `AI-assisted (model ${model})`;
  if (kind === 'anthropic' || e.startsWith('claude')) return `AI-assisted (Claude ${model.replace(/^claude-/, '')})`;
  return `AI-assisted (${e})`;
};
const FLAG = { model_feedback_repeated: 'the AI gave identical feedback to different questions', ai_and_rules_disagree: 'the AI score and the rule-based cross-check differ by 25+ points', rule_based_scoring: 'automated rule-based scoring', low_confidence: 'low confidence', very_short_answer: 'at least one short answer',
  unverifiable_evidence_removed: 'unverifiable evidence removed', model_unavailable_rules_used: 'model unavailable, rules used', no_scorable_answers: 'no answer long enough to score',
  possible_factual_errors: 'the AI noted possible factual errors', possible_non_answer: 'an answer did not read as a real answer and scored 0',
  model_score_rescaled: 'the AI answered on a 0–100 scale; its score was converted to the question’s points' };
const CRIT = { relevance: 'Relevance', depth: 'Depth', accuracy: 'Points covered', communication: 'Clarity', structure: 'Structure' };
const ANS = { blank: ['Blank', 'bad'], too_short: ['Too short to score', 'warn'], scored: null };

// ev = evaluation; questions = [{id, prompt}] ; answers = {qid: text} (recruiter view passes them; the candidate view has them inline)
export function evalView(ev, { who = 'recruiter', questions = null, answers = null } = {}) {
  const flags = (ev.flags || []).filter(f => who === 'recruiter' || ['rule_based_scoring', 'no_scorable_answers'].includes(f));
  const prompts = Object.fromEntries((questions || []).map(q => [q.id, q.prompt]));
  const none = ev.scorable_answers === 0;
  return h('div', {},
    h('div', { class: 'scoreline' },
      none ? h('div', {}, h('div', { class: 'score' }, 'Not scorable'), h('div', { class: 'lbl' }, `Assessment · ${engineText(ev.model || ev.engine)}`))
        : dial(ev.overall, `Assessment · ${engineText(ev.model || ev.engine)}`, { unit: '/100', tone: 'skyd' }),
      ev.cross_check ? h('div', {}, h('div', { class: 'sub' }, Math.round(ev.cross_check.overall)), h('div', { class: 'lbl' }, 'rule-based cross-check')) : null,
      ev.scorable_answers != null ? h('div', {}, h('div', { class: 'sub' }, `${ev.scorable_answers}/${ev.answers_total ?? ev.per_question.length}`), h('div', { class: 'lbl' }, 'answers long enough to score')) : null,
      h('div', {}, h('div', { class: 'sub' }, Math.round(ev.confidence * 100) + '%'), h('div', { class: 'lbl' }, 'confidence'))),
    flags.length ? h('div', { class: none ? 'alert' : 'note' }, (who === 'recruiter' ? 'Read the answers before deciding: ' : 'Note: ') + flags.map(f => FLAG[f] || f.replaceAll('_', ' ')).join(', ') + '.') : null,
    h('p', {}, ev.summary),
    who === 'recruiter' && (ev.possible_errors || []).length ? h('div', { class: 'note' }, 'Possible errors noted by the AI: ', h('ul', {}, ev.possible_errors.map(e => h('li', {}, e)))) : null,
    h('p', { class: 'm small' }, ev.cross_check ? 'Decision support: an AI model scored each answer against its rubric and checked it for errors; a rule-based rubric cross-checks the score. A person makes the decision.'
      : 'Decision support: the score measures how well answers cover the expected points of each question. A person makes the decision.'),
    h('h3', {}, 'Answers and feedback by question'),
    ev.per_question.map((q, i) => {
      const text = q.answer ?? answers?.[q.question_id] ?? '';
      const st = ANS[q.answer_status];
      return h('div', { class: 'qa' },
        h('div', { class: 'qh' }, h('span', { class: 'qp' }, `${i + 1}. ${q.prompt || prompts[q.question_id] || q.question_id}`),
          h('span', { class: 'num' }, st ? badge(...st) : null, h('b', {}, `${Math.round(q.score)} / ${Math.round(q.max_points)}`))),
        h('div', { class: 'ans' + (text.trim() ? '' : ' empty') }, text.trim() ? text : '(no answer)'),
        h('div', { class: 'm' }, q.rationale),
        (q.covered || []).length ? h('div', {}, h('span', { class: 'm' }, 'Covered: '), tags(q.covered, 'g')) : null,
        (q.missed || []).length ? h('div', {}, h('span', { class: 'm' }, 'Not addressed: '), tags(q.missed)) : null,
        (q.evidence || []).length ? h('div', { class: 'm small' }, 'Quoted: ', q.evidence.map(e => h('i', {}, `“${e}” `))) : null);
    }),
    h('details', {}, h('summary', {}, 'Scoring detail'), h('p', { class: 'm' }, `Scored by: ${ev.model || ev.engine || 'unknown'}.`),
      ev.cross_check ? h('p', { class: 'm' }, `Rule-based cross-check of the same answers: ${Math.round(ev.cross_check.overall)}/100 (per question: ${Object.entries(ev.cross_check.per_question).map(([k, v]) => k + ' ' + Math.round(v)).join(', ')}). Large differences are flagged for the reviewer.`) : null,
      h('h3', {}, 'Criteria (0–100)'), bars(ev.criteria, CRIT),
      ev.method ? h('p', { class: 'm' }, ev.method) : null,
      ev.language_notes?.length ? h('p', { class: 'm' }, 'Wording: ' + ev.language_notes.map(n => `“${n.text}” → “${n.fix}”`).join('; ')) : null,
      ev.scored_at ? h('p', { class: 'm small' }, `Scored ${fmt(ev.scored_at)}${ev.prompt_version ? ' · rubric version ' + ev.prompt_version : ''}`) : null));
}

const STATE_TONE = { scored: 'ok', needs_review: 'bad', processing: 'info', draft: 'warn', sent: 'info', preparing: 'info', not_sent: '', generation_failed: 'bad' };
export const stateBadge = s => s ? badge(s.label, STATE_TONE[s.code] || '') : null;

export const IDENTITY = { match: ['Owner verified', 'ok'], unverified: ['Owner not checked', 'warn'], mismatch: ['Belongs to someone else?', 'bad'],
  confirmed: ['Owner confirmed by candidate', 'ok'], reassigned: ['Moved to its owner', 'info'] };
export const identityBadge = st => st && IDENTITY[st] ? badge(...IDENTITY[st]) : null;


// ---------------------------------------------------------------- originality (recruiter only)
export const ORIG = { none: ['Nothing found', 'ok'], low: ['Slight overlap', ''], medium: ['Similar to another applicant', 'warn'], high: ['Strong match with another applicant', 'bad'] };
export const ORIG_SHORT = { none: ['Clear', 'ok'], low: ['Slight overlap', ''], medium: ['Similar', 'warn'], high: ['Strong match', 'bad'] };
export const origBadge = o => {
  if (!o || (!o.cv && !o.answers)) return null;
  const worst = ['high', 'medium'].find(l => o.cv === l || o.answers === l);
  if (!worst) return null;
  const what = [o.cv === worst || ['medium', 'high'].includes(o.cv) ? 'CV' : null, ['medium', 'high'].includes(o.answers) ? 'answers' : null].filter(Boolean).join(' + ');
  return o.open ? badge(`similar ${what}`, worst === 'high' ? 'bad' : 'warn') : badge(`similar ${what} · reviewed`, '');
};
const passages = list => (list || []).length ? h('div', { class: 'passages' }, list.map(p => h('p', {}, h('span', { class: 'passage' }, p)))) : null;
const who = m => h('a', { href: '#/application/' + m.application_id }, m.candidate);

// one exhibit: what was compared, what was found (with the text), and the reviewer's own verdict
function exhibit(letter, title, kind, o, { act, post, appId, questions }) {
  if (!o) return h('div', { class: 'card exhibit' }, h('span', { class: 'tab' }, `Exhibit ${letter}`), h('h3', { style: { marginTop: 0 } }, title),
    h('p', { class: 'm' }, kind === 'cv' ? 'Being compared with other applicants’ CVs…' : 'Compared once answers are submitted.'));
  const flagged = ['medium', 'high'].includes(o.level);
  const note = h('textarea', { placeholder: 'What you checked and concluded (kept in the activity history)', style: { minHeight: '64px' }, value: o.verdict_note || '' });
  const verdict = v => act(async () => { await post(`/applications/${appId}/originality/${kind}/review`, { verdict: v, note: note.value }); });
  const qn = Object.fromEntries((questions || []).map((q, i) => [q.id, i + 1]));
  const perQ = (o.per_question || []).filter(q => q.matches.length || q.artifacts?.length || q.instructions?.length);
  return h('div', { class: 'card exhibit ' + (flagged && o.verdict !== 'cleared' ? 'concern' : !flagged ? 'fine' : '') },
    h('span', { class: 'tab' }, `Exhibit ${letter}`),
    h('div', { class: 'row sp top-al' }, h('div', {}, h('h3', { style: { marginTop: 0, marginBottom: '4px' } }, title), badge(...ORIG[o.level]),
      h('span', { class: 'm small' }, ` compared with ${o.compared ?? 0} other ${kind === 'cv' ? 'applicant(s)' : 'submission(s)'}`)),
      o.verdict ? h('span', { class: 'stamp ' + (o.verdict === 'cleared' ? 'ok' : 'bad') }, o.verdict === 'cleared' ? 'Reviewed · not a concern' : 'Reviewed · concern') : flagged ? h('span', { class: 'stamp open' }, 'Awaiting your review') : null),
    (o.signals || []).length ? h('ul', { class: 'signals' }, o.signals.map(s => h('li', {}, s.text))) : h('p', { class: 'm' }, o.note || (kind === 'cv' ? 'No shared text or template with any other applicant.' : 'No overlap with any other candidate’s answers.')),
    kind === 'cv' ? (o.matches || []).map(m => h('div', { class: 'match' },
      h('div', { class: 'who' }, h('span', {}, who(m), h('span', { class: 'm' }, m.same_job ? '' : ` · applied for ${m.job_title}`)), badge(...ORIG[m.level])),
      h('div', { class: 'nums' }, h('span', {}, 'word-for-word ', h('b', {}, Math.round(m.verbatim) + '%')), h('span', {}, 'same template ', h('b', {}, Math.round(m.template) + '%')),
        m.same_file ? h('span', {}, h('b', {}, 'identical file')) : null),
      passages(m.passages))) : null,
    kind === 'answers' ? perQ.map(q => h('div', { class: 'match' },
      h('div', { class: 'who' }, h('b', {}, `Question ${qn[q.question_id] || q.question_id}`), badge(...ORIG[q.level])),
      q.matches.map(m => h('div', { style: { marginTop: '6px' } }, h('div', { class: 'nums' }, h('span', {}, who(m), m.same_question ? ' · same question' : ` · their question ${m.other_question_id.replace('q', '')}`),
        m.identical ? h('span', {}, h('b', {}, 'identical text')) : m.level !== 'none' ? h('span', {}, 'overlap ', h('b', {}, Math.round(m.overlap) + '%')) : null,
        m.meaning ? h('span', {}, 'similar meaning ', h('b', {}, Math.round(m.meaning) + '%')) : null), passages(m.passages))),
      (q.artifacts || []).length ? h('p', { class: 'm small' }, 'Chatbot-style text: ', q.artifacts.map(a => h('span', { class: 'passage' }, a.quote + ' '))) : null,
      (q.instructions || []).length ? h('p', { class: 'm small' }, 'Addressed to the scorer: ', q.instructions.map(a => h('span', { class: 'passage' }, a + ' '))) : null)) : null,
    kind === 'answers' && o.speed ? h('p', { class: 'm small' }, `${o.speed.words} words in ${o.speed.minutes} min between Start and Submit (${o.speed.wpm} words/min).`) : null,
    kind === 'cv' && o.stock?.count ? h('p', { class: 'm small' }, `Stock phrases: ${o.stock.count} (${o.stock.examples.slice(0, 4).join(', ')}). Context only.`) : null,
    flagged || o.verdict ? h('div', { class: 'section' }, h('div', { class: 'human' }, 'Your call. Similar text can be innocent (a shared template, a careers-office workshop, a common textbook answer). This finding has not changed any score or stage.'),
      note, h('div', { class: 'row' }, h('button', { class: 'ok', onclick: verdict('cleared') }, 'Not a concern'), h('button', { class: 'd', onclick: verdict('confirmed') }, 'Mark as a concern'),
        o.verdict ? h('button', { class: 'link', onclick: verdict('open') }, 'Clear my verdict') : null),
      o.verdict_at ? h('p', { class: 'm small' }, `Verdict recorded ${fmt(o.verdict_at)}.`) : null) : null);
}

const mmss = n => n >= 60 ? `${Math.floor(n / 60)} min ${n % 60} s` : `${n} s`;
function activityCard(a, questions) {
  if (!a) return h('div', { class: 'card exhibit' }, h('span', { class: 'tab' }, 'Exhibit C'), h('h3', { style: { marginTop: 0 } }, 'How the test was taken'),
    h('p', { class: 'm' }, 'Nothing was recorded for this test (for example it was taken before this check existed). Nothing is claimed either way.'));
  const qn = Object.fromEntries((questions || []).map((q, i) => [q.id, i + 1]));
  return h('div', { class: 'card exhibit ' + (a.notable ? 'concern' : 'fine') }, h('span', { class: 'tab' }, 'Exhibit C'),
    h('div', { class: 'row sp' }, h('h3', { style: { marginTop: 0 } }, 'How the test was taken'), badge(a.notable ? 'Worth a look' : 'Nothing unusual', a.notable ? 'warn' : 'ok')),
    h('div', { class: 'tiles' }, h('div', {}, h('b', {}, a.left_count), h('span', {}, `times the page was left (${mmss(a.left_seconds)} in all)`)),
      h('div', {}, h('b', {}, a.pointer_out_count), h('span', {}, 'times the pointer left the page (weak signal)')),
      h('div', {}, h('b', {}, a.paste_count), h('span', {}, `paste(s), ${a.pasted_chars} characters`)),
      h('div', {}, h('b', {}, Math.round(a.pasted_share * 100) + '%'), h('span', {}, 'of the text was pasted, not typed'))),
    h('ul', { class: 'signals' }, a.notes.map(n => h('li', {}, n))),
    Object.keys(a.per_question).length ? h('details', {}, h('summary', {}, 'By question'), h('table', {}, h('tbody', {}, Object.entries(a.per_question).map(([qid, q]) =>
      h('tr', {}, h('td', {}, `Question ${qn[qid] || qid}`), h('td', { class: 'r num' }, `${q.typed} typed`), h('td', { class: 'r num' }, `${q.pasted} pasted`), h('td', { class: 'r num' }, Math.round(q.pasted_share * 100) + '% pasted')))))) : null,
    h('p', { class: 'm small' }, 'Counts and times only; no text, camera or screen capture. This cannot see another device or a person helping, and an assistive tool can look like pasting. Read it with the answers, not instead of them.'));
}

export function originalityView(o, ctx) {
  const latest = (ctx.assessments || []).filter(a => a.answers).pop();
  return h('div', {}, exhibit('A', 'CV compared with other applicants', 'cv', o?.cv, ctx),
    exhibit('B', 'Test answers compared with other candidates', 'answers', o?.answers, { ...ctx, questions: latest?.task?.questions }),
    latest ? activityCard(latest.activity, latest.task?.questions) : null,
    h('p', { class: 'm small' }, 'These checks compare text with other submissions to your organisation and show what matched. They do not detect whether a person or a model wrote something, and they never accept, reject or re-score anyone.'));
}
