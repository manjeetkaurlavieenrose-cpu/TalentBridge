"""Rule-based assessment generation for the local engine.

Questions come from templates keyed by skill (or skill family), then are personalised with facts that are actually in the
candidate's profile (a project or role they listed) and in the job (title, task brief, required skills).
Each question carries `expected_points`: what a good answer covers, with the cue words the scorer looks for.
That makes the rubric explicit and inspectable instead of hidden inside a model.
"""
import re
from . import skills_data as sd
from .matching import skill_status, canon

P = lambda label, *cues: {"point": label, "cues": list(cues)}

# ---- templates -----------------------------------------------------------------------------------------------
BY_SKILL = {
    "seo": ("Explain how you would improve the organic search ranking of a company blog using {skill}. Cover how you would choose keywords, "
            "what you would change on the pages and the site, and how you would tell whether it worked.", [
        P("Researches keywords and search intent", "keyword", "search intent", "volume", "competition", "long-tail", "long tail"),
        P("Improves on-page elements", "title", "meta", "heading", "content", "internal link", "on-page", "alt text"),
        P("Considers technical health", "speed", "mobile", "crawl", "index", "sitemap", "schema", "technical", "core web vitals"),
        P("Builds authority / backlinks", "backlink", "link building", "authority", "outreach", "guest post"),
        P("Measures and reports results", "rank", "traffic", "analytics", "search console", "ctr", "conversion", "report")]),
    "google analytics": ("Website traffic is flat but sign-ups have fallen. Explain how you would use {skill} to find out why, and what you would report.", [
        P("Looks at the conversion funnel / goals", "funnel", "conversion", "sign-up", "goal", "event", "landing page"),
        P("Segments by source, channel or device", "source", "medium", "channel", "device", "segment", "campaign", "organic", "paid"),
        P("Examines user behaviour", "bounce", "engagement", "session", "page", "behaviour", "behavior", "drop-off", "exit"),
        P("Forms a hypothesis and proposes a fix or test", "hypothesis", "test", "fix", "recommend", "a/b", "improve", "optimise", "optimize"),
        P("Reports clearly to stakeholders", "report", "dashboard", "weekly", "monthly", "stakeholder", "kpi", "explain")]),
    "content marketing": ("Plan a four-week {skill} programme for a new product. Explain your goals, audience, content types, publishing plan and how you would measure success.", [
        P("Sets a goal and success metric", "goal", "kpi", "objective", "target", "metric", "leads", "traffic"),
        P("Defines the audience", "audience", "persona", "segment", "customer", "reader", "need"),
        P("Chooses content types and channels", "blog", "video", "newsletter", "social", "channel", "format", "email", "article"),
        P("Plans a calendar / workflow", "calendar", "schedule", "weekly", "plan", "deadline", "workflow", "week"),
        P("Measures and iterates", "measure", "analytics", "engagement", "iterate", "optimise", "optimize", "report", "review")]),
    "sql": ("A manager asks for the top 5 customers by revenue last quarter, from an orders table and a customers table. Describe, step by step, how you would write "
            "and validate the {skill} query.", [
        P("Joins the two tables on a key", "join", "inner join", "left join", "foreign key", "customer id", "merge", "combine"),
        P("Filters to the right date range", "where", "date", "between", "quarter", "filter", "timestamp"),
        P("Aggregates revenue per customer and ranks / limits", "group by", "sum", "aggregate", "order by", "limit", "rank", "top 5", "desc"),
        P("Handles duplicates, nulls and data quality", "duplicate", "distinct", "null", "coalesce", "missing", "dedupe", "data quality"),
        P("Validates the result", "validate", "verify", "reconcile", "check", "sanity", "compare", "test", "cross-check", "total")]),
    "excel": ("You receive a messy monthly sales spreadsheet with duplicate rows, blank cells and inconsistent dates. Explain how you would clean it and summarise it by region "
              "using {skill}.", [
        P("Cleans the data (duplicates, blanks, formats)", "remove duplicates", "duplicate", "trim", "clean", "blank", "missing", "standardise", "standardize", "format"),
        P("Uses lookups or formulas", "vlookup", "xlookup", "index", "match", "formula", "sumif", "countif", "if"),
        P("Summarises with pivots or grouping", "pivot", "summary", "group", "subtotal", "sumifs", "by region"),
        P("Checks the numbers", "check", "validate", "reconcile", "total", "compare", "audit", "sanity"),
        P("Presents the result", "chart", "graph", "present", "share", "dashboard", "report")]),
    "power bi": ("Management wants a dashboard to track weekly sales performance. Using {skill}, explain how you would decide what to show, build it and make sure people use it.", [
        P("Starts from stakeholder needs", "stakeholder", "requirement", "audience", "user", "ask", "question", "need"),
        P("Chooses meaningful metrics", "kpi", "metric", "revenue", "sales", "trend", "target", "measure"),
        P("Prepares and models the data", "data model", "clean", "refresh", "source", "relationship", "transform", "query", "connect"),
        P("Designs clear visuals", "chart", "filter", "slicer", "drill", "layout", "simple", "visual", "colour", "color"),
        P("Tests and gathers feedback", "feedback", "test", "validate", "accuracy", "training", "document", "iterate", "review")]),
    "python": ("You have a CSV file with a million rows of orders. Describe how you would use {skill} to load, clean and summarise it, and how you would keep the script reliable.", [
        P("Loads the data sensibly", "pandas", "read_csv", "load", "chunk", "dataframe", "memory", "csv"),
        P("Cleans it", "clean", "missing", "null", "duplicate", "type", "convert", "dropna", "fillna"),
        P("Transforms and summarises", "groupby", "group by", "aggregate", "merge", "pivot", "summary", "filter"),
        P("Makes the code reliable", "test", "error", "exception", "log", "validate", "function", "reuse", "assert"),
        P("Delivers the output", "output", "export", "report", "chart", "visual", "save", "share")]),
    "rest apis": ("Design a REST API for a booking service. Describe the endpoints, how data is handled, the error cases and how you would keep it fast if traffic doubled.", [
        P("Defines resources and endpoints", "endpoint", "get", "post", "put", "delete", "resource", "route", "url", "bookings"),
        P("Handles data storage", "database", "model", "schema", "table", "orm", "sql", "index", "transaction"),
        P("Validates input and handles errors", "validation", "status code", "400", "404", "409", "error", "authentication", "auth", "permission"),
        P("Plans for performance and scale", "cache", "caching", "pagination", "scale", "load balancer", "queue", "rate limit", "async", "redis"),
        P("Covers testing and operations", "test", "document", "swagger", "openapi", "deploy", "monitor", "log")]),
    "git": ("Two teammates changed the same file and a merge conflict appeared. Explain how you use {skill} to resolve it and keep the team's history clean.", [
        P("Resolves the conflict correctly", "merge", "rebase", "conflict", "resolve", "diff"),
        P("Talks to the other person / reviews", "talk", "communicate", "review", "pull request", "discuss", "ask"),
        P("Verifies after resolving", "test", "build", "verify", "run", "check"),
        P("Keeps history tidy", "commit message", "small commit", "history", "squash", "branch", "feature branch")]),
    "docker": ("A service works on your laptop but fails after deployment. How would you use {skill} and your deployment process to diagnose it and make releases repeatable?", [
        P("Diagnoses with logs and reproduction", "log", "reproduce", "error", "metrics", "debug", "monitor", "trace"),
        P("Checks environment and configuration differences", "environment", "config", "variable", "version", "dependency", "image", "container"),
        P("Automates build and deployment", "pipeline", "ci/cd", "automate", "script", "build", "deploy"),
        P("Plans safe rollout and rollback", "rollback", "staging", "test", "canary", "backup", "health check"),
        P("Documents and prevents recurrence", "document", "runbook", "alert", "review", "postmortem")]),
    "policy analysis": ("You are asked for a short evidence-based brief on a policy question. Using {skill}, outline how you would gather sources, judge their quality, analyse them and write the brief.", [
        P("Defines the question and scope", "question", "scope", "define", "objective", "hypothesis", "framework"),
        P("Gathers varied sources", "source", "literature", "primary", "secondary", "archive", "interview", "survey", "database", "journal", "report"),
        P("Judges credibility and bias", "credib", "bias", "reliab", "triangulat", "cross-check", "verify", "peer-reviewed", "evidence"),
        P("Analyses and compares findings", "analys", "compare", "theme", "synthes", "pattern", "evaluate", "trend"),
        P("Writes for the audience", "brief", "summary", "recommend", "audience", "cite", "reference", "structure", "concise")]),
}
BY_SKILL["research"] = BY_SKILL["policy analysis"]

BY_FAMILY = {
    "sql": BY_SKILL["sql"], "spreadsheet": BY_SKILL["excel"], "bi": BY_SKILL["power bi"], "python": BY_SKILL["python"],
    "backend": BY_SKILL["rest apis"], "vcs": BY_SKILL["git"], "devops": BY_SKILL["docker"], "cloud": BY_SKILL["docker"],
    "marketing_analytics": BY_SKILL["google analytics"], "research": BY_SKILL["policy analysis"],
    "analysis": ("Weekend sales dropped 12% in two regions. Walk through how you would investigate the cause using {skill}.", [
        P("Clarifies the question", "clarify", "define", "question", "hypothesis", "scope", "stakeholder"),
        P("Identifies and extracts the data", "data", "query", "sql", "source", "extract", "collect", "dataset"),
        P("Compares and segments", "compare", "last year", "seasonal", "segment", "region", "product", "baseline", "trend", "breakdown"),
        P("Checks data quality", "duplicate", "null", "missing", "outlier", "quality", "reconcile", "validate", "check"),
        P("Communicates a recommendation", "report", "dashboard", "recommend", "present", "explain", "summary", "chart")]),
    "stats": ("You ran two versions of a landing page and version B converts better. Using {skill}, how would you decide whether the difference is real?", [
        P("States a hypothesis / test", "hypothesis", "null", "test", "significance", "p-value", "confidence"),
        P("Considers sample size and duration", "sample size", "power", "enough data", "duration", "traffic", "size"),
        P("Guards against bias", "random", "control", "bias", "segment", "novelty", "seasonality"),
        P("Uses the right metric and effect size", "conversion", "metric", "rate", "effect size", "lift", "uplift"),
        P("Turns it into a decision with caveats", "recommend", "decision", "risk", "practical", "cost", "rollout", "caveat")]),
    "data_eng": ("A nightly data pipeline sometimes loads duplicate and missing records. How would you diagnose it and make it reliable using {skill}?", [
        P("Investigates with logs and checks", "log", "monitor", "check", "reproduce", "trace", "alert"),
        P("Makes loads idempotent / de-duplicated", "idempotent", "duplicate", "dedupe", "unique", "key", "upsert", "merge"),
        P("Validates completeness", "count", "validate", "reconcile", "missing", "schema", "test", "assert"),
        P("Handles failure and retries", "retry", "fail", "backfill", "rerun", "recover", "alert"),
        P("Documents and prevents recurrence", "document", "runbook", "review", "prevent", "monitor")]),
    "ml": ("You must predict which customers will cancel their subscription. Using {skill}, explain your approach from raw data to a usable result.", [
        P("Defines the target and data", "target", "label", "define", "churn", "data", "historical"),
        P("Prepares features", "feature", "clean", "encode", "missing", "engineer", "transform"),
        P("Splits and validates properly", "train", "test split", "validation", "cross-validation", "leak", "holdout"),
        P("Chooses suitable metrics", "precision", "recall", "auc", "f1", "accuracy", "metric", "imbalance"),
        P("Plans deployment and monitoring", "deploy", "monitor", "drift", "retrain", "bias", "explain", "feedback")]),
    "stats_lang": ("Explain how you would use {skill} to explore a survey dataset and report the findings so that someone else could reproduce them.", [
        P("Loads and cleans data", "load", "import", "clean", "missing", "recode", "variable"),
        P("Describes the data", "mean", "median", "distribution", "summary", "descriptive", "frequency", "cross-tab"),
        P("Applies suitable tests or models", "regression", "t-test", "chi", "correlation", "model", "test", "significance"),
        P("Visualises results", "plot", "chart", "graph", "histogram", "visual"),
        P("Makes work reproducible", "script", "reproduc", "document", "version", "comment", "notebook")]),
    "webdev": ("Describe how you would build a responsive, form-driven web page with {skill}: structure, validation, accessibility, talking to a server and testing.", [
        P("Structures the page / components", "component", "html", "semantic", "layout", "state", "structure", "template"),
        P("Validates input and shows errors", "validate", "error message", "required", "input", "sanitise", "sanitize"),
        P("Handles responsive layout and accessibility", "responsive", "mobile", "accessible", "accessibility", "aria", "keyboard", "contrast"),
        P("Connects to an API with loading/error states", "api", "fetch", "request", "loading", "error state", "async"),
        P("Tests and debugs", "test", "browser", "cross-browser", "debug", "review")]),
    "testing": ("How would you test a new login feature using {skill}? Cover what you would test, how you would automate and how you would report.", [
        P("Designs test cases incl. edge cases", "test case", "edge case", "invalid", "empty", "lockout", "password", "boundary"),
        P("Automates repeatable checks", "automate", "script", "pytest", "selenium", "cypress", "ci", "regression"),
        P("Covers security basics", "security", "injection", "brute", "session", "hash", "rate limit"),
        P("Reports defects clearly", "report", "bug", "steps to reproduce", "severity", "ticket", "log"),
        P("Prioritises by risk", "priorit", "risk", "critical", "coverage", "smoke")]),
    "marketing": ("Plan a four-week campaign to increase sign-ups for a new product using {skill}. Explain goals, audience, channels, content and how you would measure results.", [
        P("Sets goals and KPIs", "goal", "kpi", "objective", "target", "metric", "leads", "sign-ups"),
        P("Defines the audience", "audience", "persona", "segment", "customer", "need"),
        P("Chooses channels and content", "channel", "social", "email", "seo", "ads", "content", "blog", "video"),
        P("Plans schedule and budget", "calendar", "schedule", "budget", "week", "plan", "timeline"),
        P("Measures and optimises", "measure", "analytics", "ab test", "a/b", "optimise", "optimize", "report", "roi", "conversion")]),
    "writing": ("You must produce a 1,000-word article for a general audience. Using {skill}, describe your process from brief to final edit.", [
        P("Clarifies the brief and audience", "brief", "audience", "purpose", "tone", "clarify", "reader"),
        P("Plans structure", "outline", "structure", "headline", "section", "plan", "draft"),
        P("Checks facts and sources", "research", "source", "fact", "verify", "cite", "reference"),
        P("Edits and proofreads", "edit", "proofread", "revise", "grammar", "spelling", "clarity", "tone"),
        P("Uses feedback / optimises for the channel", "feedback", "review", "seo", "keyword", "headline", "channel", "publish")]),
    "comms": ("Describe how you would explain a complex finding to a non-expert audience using {skill}: planning, structure, delivery and checking they understood.", [
        P("Knows the audience", "audience", "non-technical", "level", "background", "need"),
        P("Structures a clear message", "structure", "key message", "story", "summary", "simple", "plain"),
        P("Uses examples or visuals", "example", "visual", "chart", "slide", "analogy", "demo"),
        P("Checks understanding", "question", "feedback", "check", "understood", "recap", "discussion"),
        P("Follows up", "follow up", "follow-up", "document", "email", "next step", "action")]),
    "teaching": ("A learner is struggling with a core idea. Using {skill}, describe how you would diagnose the problem and help them improve.", [
        P("Diagnoses the misunderstanding", "ask", "diagnose", "assess", "question", "understand", "misconception"),
        P("Adapts the explanation", "example", "simplify", "different", "adapt", "visual", "step"),
        P("Gives practice and feedback", "practice", "exercise", "feedback", "quiz", "task"),
        P("Tracks progress", "progress", "track", "measure", "review", "assessment", "goal"),
        P("Keeps the learner motivated", "motivat", "encourage", "confidence", "support", "patience")]),
    "sales": ("A prospective client says your price is too high. Explain how you would handle it using {skill}.", [
        P("Listens and finds the real objection", "listen", "understand", "ask", "objection", "concern", "question"),
        P("Connects price to value", "value", "benefit", "roi", "outcome", "case study", "saving"),
        P("Offers options without caving in", "option", "package", "scope", "trade", "alternative", "discount"),
        P("Moves towards a decision", "close", "next step", "agree", "decision", "proposal", "commit"),
        P("Follows up and records", "follow up", "follow-up", "crm", "record", "note", "relationship")]),
    "customer": ("An unhappy customer reports the same problem for the third time. How would you respond using {skill}?", [
        P("Acknowledges and empathises", "apolog", "empath", "listen", "understand", "acknowledge", "sorry"),
        P("Investigates the history / root cause", "history", "root cause", "reproduce", "investigate", "ticket", "check"),
        P("Fixes or escalates with ownership", "fix", "escalate", "own", "resolve", "solution", "engineer"),
        P("Sets expectations and follows up", "follow up", "follow-up", "update", "timeline", "expect", "confirm"),
        P("Prevents recurrence", "prevent", "feedback", "document", "process", "improve", "knowledge base")]),
    "finance": ("Month-end figures show a 15% variance against budget. Explain how you would investigate and report it using {skill}.", [
        P("Identifies the drivers", "driver", "variance", "line item", "category", "breakdown", "cost", "revenue"),
        P("Verifies the data", "verify", "reconcile", "ledger", "check", "source", "accuracy", "error"),
        P("Compares with prior periods / forecast", "prior", "last year", "forecast", "trend", "budget", "benchmark"),
        P("Explains to stakeholders", "explain", "stakeholder", "report", "commentary", "summary", "manager"),
        P("Recommends actions", "recommend", "action", "adjust", "control", "reforecast", "mitigat")]),
    "hr": ("You must hire for a role and have 80 applicants in two weeks. Using {skill}, describe how you would screen and shortlist them fairly.", [
        P("Starts from clear role criteria", "criteria", "requirement", "job description", "must-have", "scorecard", "competenc"),
        P("Screens in a structured way", "structured", "screen", "shortlist", "consistent", "rubric", "interview"),
        P("Reduces bias", "bias", "fair", "blind", "equal", "diversity", "consistent"),
        P("Communicates with candidates", "communicate", "email", "update", "feedback", "experience", "respond"),
        P("Records decisions", "record", "document", "ats", "decision", "log", "notes")]),
    "pm": ("A project is two weeks behind schedule. Using {skill}, explain how you would regain control.", [
        P("Assesses the real status", "status", "assess", "root cause", "progress", "baseline", "blocker"),
        P("Reprioritises scope", "priorit", "scope", "must-have", "trade-off", "descope", "mvp"),
        P("Communicates with stakeholders", "stakeholder", "communicate", "update", "expectation", "sponsor", "report"),
        P("Manages risks", "risk", "mitigat", "contingency", "dependency", "issue"),
        P("Tracks and adjusts", "track", "plan", "milestone", "daily", "standup", "review", "metric")]),
    "ops": ("An operations process keeps missing its deadlines. Using {skill}, explain how you would find the bottleneck and improve it.", [
        P("Maps the process", "map", "process", "flow", "step", "workflow", "observe"),
        P("Measures to find the bottleneck", "measure", "data", "bottleneck", "cycle time", "delay", "queue"),
        P("Proposes improvements", "improve", "automate", "standardise", "standardize", "remove", "simplify", "change"),
        P("Pilots and checks the effect", "pilot", "test", "trial", "compare", "result", "kpi"),
        P("Gets the team on board", "team", "train", "communicate", "document", "sop", "feedback")]),
    "admin": ("You are asked to organise a two-day team event and manage the paperwork around it using {skill}. Describe your plan, how you track details and how you handle last-minute changes.", [
        P("Plans tasks and deadlines", "plan", "checklist", "schedule", "deadline", "timeline", "task"),
        P("Tracks details accurately", "spreadsheet", "track", "record", "confirm", "list", "database", "detail"),
        P("Coordinates people and vendors", "coordinate", "vendor", "email", "confirm", "communicate", "book"),
        P("Handles changes calmly", "change", "backup", "contingency", "flexible", "adapt", "prioritis"),
        P("Reviews afterwards", "review", "feedback", "cost", "lesson", "report")]),
    "design": ("Redesign a sign-up form that many users abandon. Using {skill}, explain how you would find the problems, design the fix and test it.", [
        P("Finds problems with users/data", "user research", "interview", "analytics", "drop-off", "usability", "observe"),
        P("Designs the improved flow", "wireframe", "prototype", "layout", "simplify", "field", "step"),
        P("Considers accessibility and clarity", "accessib", "contrast", "label", "clear", "error", "mobile"),
        P("Tests the design", "test", "a/b", "feedback", "iterate", "usability test", "validate"),
        P("Collaborates with others", "developer", "stakeholder", "handoff", "collaborate", "review")]),
    "legal": ("A new regulation affects how your team handles customer data. Using {skill}, explain how you would assess the impact and put controls in place.", [
        P("Reads and interprets the requirement", "read", "interpret", "requirement", "regulation", "scope", "legal"),
        P("Assesses current practice (gap analysis)", "gap", "audit", "assess", "current", "risk", "review"),
        P("Defines controls / actions", "control", "policy", "process", "action", "plan", "owner"),
        P("Trains and communicates", "train", "communicate", "awareness", "document", "inform"),
        P("Monitors and records", "monitor", "record", "evidence", "audit", "review")]),
    "security": ("You suspect a user account has been compromised. Using {skill}, describe what you would do in the first hour and afterwards.", [
        P("Contains the incident", "lock", "disable", "revoke", "isolate", "contain", "reset"),
        P("Investigates with logs", "log", "investigate", "timeline", "ip", "evidence", "trace"),
        P("Communicates to the right people", "report", "notify", "escalate", "stakeholder", "inform"),
        P("Fixes the root cause", "root cause", "patch", "mfa", "password", "vulnerab", "fix"),
        P("Prevents recurrence", "monitor", "alert", "policy", "train", "review", "lesson")]),
    "mobile": BY_SKILL["rest apis"],
    "soft": ("Describe a time (real or realistic) when you had to apply {skill} under pressure. Explain the situation, what you did, and what happened.", [
        P("Describes a concrete situation", "situation", "when", "project", "deadline", "team", "problem"),
        P("Explains own actions", "i ", "my role", "decided", "organised", "organized", "led", "asked", "planned"),
        P("States the outcome", "result", "outcome", "delivered", "improved", "achieved", "resolved"),
        P("Reflects on learning", "learn", "next time", "improve", "differently", "feedback")]),
}

GENERIC = ("The {title} role needs {skill}. Explain how you have used it, or would use it, in this role: give a concrete example, the steps you would follow, "
           "how you would check your work and how you would know it was successful.", [
    P("Gives a concrete example", "example", "for instance", "project", "when i", "i used", "i built", "i worked"),
    P("Describes the steps", "first", "then", "next", "step", "process", "approach", "plan"),
    P("Checks quality", "check", "test", "validate", "review", "verify", "accuracy", "feedback"),
    P("Defines success / measures it", "measure", "success", "result", "outcome", "metric", "kpi", "goal")])


# The same skill tests a different competency in a different kind of role (Python for a data analyst vs a backend developer).
BY_CONTEXT = {
    ("python", "backend"): ("A {skill} endpoint that returns a customer's order history has become slow and sometimes times out. Explain how you "
                            "would find the cause, fix it and make sure it does not come back.", [
        P("Measures before changing anything", "profile", "profiling", "log", "metric", "timing", "trace", "reproduce", "query plan", "explain"),
        P("Looks at data access", "index", "n+1", "query", "join", "pagination", "orm", "database", "select"),
        P("Applies a targeted fix", "cache", "caching", "batch", "async", "optimise", "optimize", "refactor", "limit", "background"),
        P("Tests the fix", "test", "unit test", "pytest", "regression", "load test", "benchmark"),
        P("Releases and monitors safely", "deploy", "monitor", "alert", "rollback", "staging", "review")]),
}
BACKEND_FAMILIES = {"backend", "webdev", "devops", "cloud", "mobile"}


def job_context(job):
    fams = {sd.FAMILY.get(sd.canonical(s) or canon(s)) for s in (job.get("required_skills") or [])}
    title = (job.get("title") or "").lower()
    if fams & BACKEND_FAMILIES or re.search(r"\b(backend|back-end|developer|software engineer)\b", title):
        return "backend"
    return None


def template_for(skill_name, context=None):
    key = canon(skill_name)
    k = sd.canonical(skill_name) or key
    if (k, context) in BY_CONTEXT:
        return BY_CONTEXT[(k, context)], k
    if k in BY_SKILL:
        return BY_SKILL[k], k
    fam = sd.FAMILY.get(k)
    if fam in BY_FAMILY:
        return BY_FAMILY[fam], k
    return None, k


def _stems(text):
    from .answer_scorer import content_words, stem
    return {stem(w) for w in content_words(text)}


def overlaps(text, prompts, threshold=0.5):
    """True when most of the distinctive words of `text` already appear in one of `prompts` (the questions would overlap)."""
    a = _stems(text) - {"role", "would", "describe", "explain", "scenario"}
    return bool(a) and any(len(a & _stems(p)) / len(a) >= threshold for p in prompts)


def _key(skill):
    return sd.canonical(skill) or canon(skill)


def _rubric_text(points):
    body = "; ".join(f"{i}) {p['point']}" for i, p in enumerate(points, 1))
    return (f"A good answer covers: {body}. Scoring is by how many of these points the answer addresses, plus depth, structure and clarity. "
            "Keyword-based: a person should read the answer.")[:700]


def _q(prompt, points, weight):
    return {"prompt": prompt[:900], "points": points, "weight": weight}


def evidence_reference(profile, wanted_names):
    """Pick something real from the CV to reference: a project or role that touches a required skill. Returns (label, skills) or None."""
    wanted = {canon(w) for w in wanted_names}

    def hit(text):
        keys = set(sd.find_skills(text)) | {canon(w) for w in wanted if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text.lower())}
        return [k for k in keys if k in wanted or any(canon(w) == k for w in wanted)]
    best = None
    for p in profile.get("projects", []):
        h = hit(p.get("name", "") + " " + p.get("description", ""))
        if h and (best is None or len(h) > len(best[1])):
            best = (f"your project \"{p['name']}\"", h)
    for w in profile.get("work_history", []):
        h = hit(w.get("description", ""))
        if h and (best is None or len(h) > len(best[1]) + 1):
            best = (f"your role as {w['title']} at {w['company']}", h)
    return best


def build_assessment(profile, job):
    """-> assessment dict matching ASSESSMENT_SCHEMA (+ optional expected_points)."""
    title = job.get("title", "this role")
    req = list(job.get("required_skills") or [])
    pref = list(job.get("preferred_skills") or [])
    idx = {canon(s["name"]): s for s in profile.get("skills", [])}
    text = " ".join([w.get("description", "") for w in profile.get("work_history", [])] +
                    [p.get("description", "") for p in profile.get("projects", [])]).lower()
    status = {s: skill_status(s, idx, text)[0] for s in req + pref}

    qs, used, used_tpl = [], set(), set()
    context = job_context(job)
    brief = (job.get("task_brief") or "").strip()
    if not brief:
        desc = re.split(r"(?<=[.!?])\s+", (job.get("description") or "").strip())[0] if job.get("description") else ""
        brief = desc or f"You have just started as {title} and have two weeks to make a visible contribution."

    def add_skill_question(skill, intro="", weight=30):
        tpl, key = template_for(skill, context)
        prompt, points = tpl if tpl else GENERIC
        if key in used or (tpl and id(tpl) in used_tpl):     # two skills sharing one template would ask the same question twice
            return False
        text = prompt.format(skill=skill, title=title)
        if tpl and overlaps(brief, [text]):     # the job's own scenario (question 4) already asks this: test something else
            return False
        used.add(key)
        if tpl: used_tpl.add(id(tpl))
        qs.append(_q(intro + text, points, weight))
        return True

    # 1) core applied question on the most important required skill that has a specific template
    ordered = sorted(req, key=lambda s: (template_for(s, context)[0] is None, req.index(s)))
    for first in ordered:
        if add_skill_question(first, weight=30):
            break

    # the opening sets how long the test is (3-6 questions): 3 drops the second skill question, 5 and 6 add more skills
    try:
        size = max(3, min(6, int(job.get("test_questions") or 4)))
    except (TypeError, ValueError):
        size = 4

    # 2) a skill gap: required skill the CV does not show in use (honest: stated as a gap, not as a failing)
    gaps = [s for s in req if status[s] in ("missing", "partial") and _key(s) not in used]
    has_cv = bool(profile.get("skills") or profile.get("work_history"))       # a preview has no candidate, so no "your CV" wording
    if size >= 4 and not (has_cv and any(add_skill_question(g, intro=f"The role needs {g}, and your CV does not clearly show it in use. ", weight=25) for g in gaps)):
        for nxt in (s for s in ordered if _key(s) not in used):
            if add_skill_question(nxt, weight=25):
                break
    for extra in [s for s in ordered + pref if _key(s) not in used]:           # 5 or 6 questions: further skills of the role
        if len(qs) >= size - 2:
            break
        add_skill_question(extra, weight=20)

    # 3) experience question that quotes something actually in the CV
    ref = evidence_reference(profile, req + pref)
    if ref:
        label, keys = ref
        names = ", ".join(sd.display(k) for k in keys[:3])
        qs.append(_q(f"Your CV mentions {label}. Describe your own part in it, how you used {names}, what the result was, and what you would do differently now.",
                     [P("Explains their own role / ownership", "my role", "i ", "responsible", "owned", "led", "built", "developed", "designed", "worked on"),
                      P("Explains how the named skills were used", *([sd.display(k).lower() for k in keys] + ["using", "used", "approach", "method"])),
                      P("States a concrete result", "result", "outcome", "impact", "improved", "reduced", "increased", "%", "saved", "delivered"),
                      P("Reflects on what to improve", "learn", "improve", "differently", "next time", "challenge", "lesson")], 20))
    else:
        qs.append(_q(f"Describe a piece of work (paid, academic or personal) that is relevant to the {title} role. Say what the problem was, what you did, what the result was and what you would do differently.",
                     [P("Describes the problem", "problem", "challenge", "task", "goal", "needed"),
                      P("Explains own actions", "i ", "my role", "built", "wrote", "analysed", "analyzed", "organised", "organized", "led"),
                      P("States a result", "result", "outcome", "impact", "improved", "reduced", "increased", "delivered", "%"),
                      P("Reflects", "learn", "improve", "differently", "next time", "lesson")], 20))

    # 4) a scenario in the context of this specific job
    tools = [s.lower() for s in (req + pref)][:8]
    if overlaps(brief, [q["prompt"] for q in qs]):
        # the job's scenario repeats a question already asked (e.g. "design a booking API" twice): ask about a different
        # competency instead — running and fixing that work once it is live
        qs.append(_q(f"Scenario for the {title} role: {brief} Your first version is now live, and after a busy week users report slow responses "
                     "and a few incorrect results. Explain how you would investigate, what you would fix first, how you would release the fix safely "
                     "and how you would keep the people affected informed.",
                     [P("Investigates with evidence", "log", "metric", "monitor", "trace", "reproduce", "data", "dashboard", "investigate"),
                      P("Protects correctness of the data", "transaction", "lock", "constraint", "duplicate", "idempotent", "validation", "consistency", "integrity"),
                      P("Prioritises the fix", "priorit", "first", "impact", "root cause", "severity", "workaround", "hotfix"),
                      P("Releases safely", "test", "staging", "rollback", "canary", "feature flag", "deploy", "review"),
                      P("Communicates and prevents recurrence", "communicate", "update", "stakeholder", "status", "postmortem", "alert", "runbook", "lesson")], 25))
    else:
        qs.append(_q(f"Scenario for the {title} role: {brief} Outline how you would approach it: your first steps, the skills and tools you would use, how you would check your work, and how you would report the outcome.",
                     [P("Clarifies the goal and constraints", "clarify", "understand", "ask", "requirement", "goal", "scope", "stakeholder"),
                      P("Lays out a sequence of steps", "plan", "step", "first", "then", "next", "priorit", "approach", "timeline"),
                      P("Names relevant skills / tools of the role", *(tools + ["tool", "method"])),
                      P("Checks quality of the work", "check", "validate", "test", "verify", "review", "quality", "accuracy"),
                      P("Communicates the outcome", "communicate", "report", "explain", "present", "stakeholder", "update", "summary", "recommend")], 25))

    questions = []
    for i, q in enumerate(qs[:6], 1):
        questions.append({"id": f"q{i}", "prompt": q["prompt"], "max_points": q["weight"], "rubric": _rubric_text(q["points"]),
                          "expected_points": [{"point": p["point"], "cues": p["cues"][:20]} for p in q["points"]]})
    intro = (job.get("description") or "").strip().split("\n")[0][:300]
    scenario = (f"You are being considered for the {title} position. {intro + ' ' if intro else ''}"
                "The questions below come from the requirements of this role and, where possible, from work listed on your CV. "
                "Answer in your own words with concrete steps and examples; short, generic answers score low.")
    return {"title": f"{title}: work-sample assessment"[:140], "scenario": scenario[:1800], "minutes": max(20, 8 * len(questions) + 5),
            "questions": questions}
