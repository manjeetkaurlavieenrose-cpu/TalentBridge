# Demo script (about 12 minutes, fictional data only)

**Before you start**
1. Use a clean data folder so the demo never mixes with real CVs: double-click **start_demo_windows.bat** (Windows) or
   **start_demo_mac.command** (Mac). Both keep demo data in `demo-data/` and open http://localhost:5050.
2. Have these files ready: `sample_data/cv_kiran_desai_undated_role.pdf` and `sample_data/cv_priya_nair_data_analyst.pdf`.
3. Use a normal window for the candidate and a private window for the recruiter.

**Say up front:** "Everything runs on this laptop. With Ollama switched on, a local AI model reads the CV alongside the parser, writes a fit summary, writes the assessment questions for this candidate and this job, and scores every answer, including checking it for technical mistakes. Every AI result is checked by transparent rules, names the engine that produced it, and a person makes every hiring decision."

| Step | Do | Point to make |
|---|---|---|
| 1 | Candidate window → **I am a candidate** → register *Kiran Desai*, `kiran.desai@example.org`, any 10+ character password | Yellow strip: demo mode, fictional data only. |
| 2 | Upload `cv_priya_nair_data_analyst.pdf` | Flagged: "appears to belong to Priya Nair". It is **not** applied to Kiran's profile. Click **Remove**. (This is the bug that used to mix people up.) |
| 3 | Upload `cv_kiran_desai_undated_role.pdf` | "Owner verified". Warnings: one role has no dates (not the same as no experience); certificates may be run together. Experience shows **not verifiable**, not 0. Open "Show the text we read". Fix anything, then **Confirm profile**. |
| 4 | **Openings** → Backend Python Developer → **Check my fit** | Overall = CV match while no assessment. Evidence table: *Shown in use* / *Partial* / *Not found (not proof of absence)* / *Not verifiable*. |
| 5 | **Apply** → **Start assessment** | Four different questions: performance debugging, a skill gap, a project from her own CV, the job's scenario. |
| 6 | Type into question 1, click **Save draft**, go to **Applications**, come back (or reload) | The draft text is restored exactly. |
| 7 | Answer all four (or leave one blank to show the warning) → **Submit answers** | Results show each answer with its score and feedback. A blank answer is labelled *Blank*, not "poor". |
| 8 | Recruiter window → sign in `recruiter@talentbridge.demo` / `DemoRecruiter#2026` | Dashboard tiles (hover for definitions). |
| 9 | Backend Python Developer → Kiran Desai | Identity and CV used on top; same overall score the candidate saw; answers next to each question; scoring detail; earlier results kept. |
| 10 | Write a note → **Start human review** → note → **Shortlist** | Stage timeline updates; note and decision appear in the side panel and activity history; reload to show it persisted. |
| 11 | Openings list → **Export CSV** on the job | Correct names, CV file, CV match, overall, assessment state, decision. |
| 12 | Stop the app (Control+C), start it again, reload | Everything is still there. |
| 13 | Recruiter → **Data Analyst**. Look at the red **Originality** card | Three applicants (Arjun, Dev, Sana) share one CV template; two submitted the same answers. "These are leads to read, not verdicts." |
| 14 | Open **Arjun Rao** → scroll to **Originality** | Exhibit A: the matching sentences, highlighted, per applicant. Exhibit B: identical answers, the chatbot's opening line quoted, and "more words than can be typed in 3 minutes". Scores and stage are untouched. |
| 15 | Write a note → **Not a concern** or **Mark as a concern** | A stamp appears; the verdict is in the activity history; the opening's count of open findings drops. The hiring decision is still made separately, in "Your decision". |
| 16 | Open **Rohan Mehta** (Data Analyst) → **Offer a second attempt** | The page points out a decent CV with a weak test. Send new questions or the same ones; attempt 1 stays on file. |
| 17 | **Follow up with the candidate** → pick "Invite to interview" → **Send message** | The candidate sees it in their account (and by e-mail once an e-mail service is connected). |
| 18 | Opening page → **Skill test for this opening** → **Preview a test** | The questions an applicant would get, with the private marking guide; change the length; **Send to everyone waiting**. |

**Questions you may get**
- *Is this AI?* Yes, when a model is configured (Ollama, LM Studio, a hosted free tier, or Claude). The model reads the CV (each fact it adds must be found in the CV text), summarises fit, writes the questions and scores the answers. The match score itself stays a documented calculation, so every number can be explained. Each result shows which engine produced it; the built-in rule engine takes over automatically if the model is off.
- *Can it tell if an answer is correct?* With a model on, each answer is scored against its rubric and checked for technical errors; possible errors are listed for the recruiter. The rule-based rubric cross-checks the score and large disagreements are flagged. Nonsense or "I don't know" answers score 0 whatever the engine.
- *What about scanned CVs?* With Tesseract installed (free), scanned PDFs are read with OCR and the profile is marked "read with OCR" so the candidate checks it.
- *What if someone uploads a friend's CV?* It is held and flagged; the person can confirm it is theirs (logged) or remove it; a recruiter can move it to its owner's record.
- *Can it tell if a CV or answer was written by AI?* No, and it does not pretend to: no tool can do that reliably. It shows which CVs and answers share text or a template with other applicants, quotes the passages, and leaves the judgement to the reviewer.
- *Does a similarity flag reject someone?* Never. It changes no score and no stage. The reviewer records "not a concern" or "a concern" and then decides as usual.
- *Does the AI cost anything?* No. It uses Ollama, a free program that runs on this computer; TalentBridge finds it by itself. Without it the built-in rule engine does the work.
- *Fairness?* Nothing is decided automatically and no protected attributes are scored. No bias evaluation has been done yet.
