"""Built-in skills taxonomy used by the local (no-API) engine.

Format per line:  Display name | family | alias, alias, ...
`family` decides which assessment-question templates apply (see question_bank.py).
The display name itself is always an alias. Matching is whole-word and case-insensitive.
This list is deliberately finite: a skill that is not here is still kept when it appears in a CV's
skills section, but it cannot be auto-detected elsewhere in the text.
"""
import re

RAW = """
SQL|sql|structured query language, t-sql, pl/sql, plsql, sql queries
MySQL|sql|my sql
PostgreSQL|sql|postgres, psql
SQLite|sql|
Oracle|sql|oracle database, oracle db
MongoDB|sql|mongo db, nosql
Excel|spreadsheet|ms excel, microsoft excel, advanced excel, vlookup, xlookup, pivot tables, pivot table
Google Sheets|spreadsheet|g sheets, gsheets
Power BI|bi|powerbi, power-bi, microsoft power bi
Tableau|bi|
Looker|bi|looker studio, google data studio, data studio
Qlik|bi|qlikview, qlik sense
Dashboards|bi|dashboard, dashboarding
Data Visualization|bi|data visualisation, dataviz, data viz
Data Analysis|analysis|data analytics, analysing data, analyzing data, exploratory data analysis, eda
Data Cleaning|analysis|data cleansing, data wrangling, data preparation, data preprocessing
Statistics|stats|statistical analysis, statistical modelling, statistical modeling, hypothesis testing, regression analysis
A/B Testing|stats|ab testing, a/b tests, split testing
Forecasting|stats|demand forecasting, time series
Google Analytics|marketing_analytics|ga4, universal analytics
Web Analytics|marketing_analytics|adobe analytics, mixpanel, hotjar
ETL|data_eng|data pipelines, data pipeline, data pipelines
Data Modeling|data_eng|data modelling, dimensional modeling, data warehouse, data warehousing
Pandas|python|
NumPy|python|
Python|python|python3, python programming
R|stats_lang|r programming, r language, rstudio
SAS|stats_lang|
SPSS|stats_lang|
Stata|stats_lang|
MATLAB|stats_lang|
Machine Learning|ml|ml, predictive modelling, predictive modeling, supervised learning
Deep Learning|ml|neural networks
NLP|ml|natural language processing
scikit-learn|ml|sklearn, scikit learn
TensorFlow|ml|
PyTorch|ml|
BigQuery|data_eng|big query
Snowflake|data_eng|
Spark|data_eng|apache spark, pyspark
Hadoop|data_eng|
Airflow|data_eng|apache airflow
dbt|data_eng|
Java|backend|core java, java 8, java 11, java 17
JavaScript|webdev|js, ecmascript, es6
TypeScript|webdev|ts
C++|backend|cpp
C#|backend|c sharp, csharp
Go|backend|golang
PHP|backend|laravel
Ruby|backend|ruby on rails, rails
Kotlin|backend|
Swift|mobile|swiftui
Rust|backend|
Scala|backend|
Bash|devops|shell scripting, shell script, bash scripting
VBA|spreadsheet|excel macros, macros
Object-Oriented Programming|backend|oop, object oriented programming, object-oriented design
Data Structures|backend|algorithms, data structures and algorithms, dsa
REST APIs|backend|rest api, restful, restful apis, rest, api development, web services
GraphQL|backend|
Microservices|backend|micro services, microservice
Flask|backend|
Django|backend|django rest framework, drf
FastAPI|backend|fast api
Spring Boot|backend|spring, spring framework
Node.js|backend|node, nodejs, node js
Express|backend|express.js, expressjs
Unit Testing|testing|unit tests, pytest, junit, test driven development, tdd, jest, mocha
Test Automation|testing|selenium, cypress, playwright, qa automation, automated testing
Git|vcs|version control, gitlab, bitbucket
GitHub|vcs|github actions
React|webdev|reactjs, react.js, redux
Angular|webdev|angularjs
Vue|webdev|vue.js, vuejs
Next.js|webdev|nextjs
HTML|webdev|html5
CSS|webdev|css3, sass, scss, tailwind, tailwind css, bootstrap
jQuery|webdev|
Flutter|mobile|dart
React Native|mobile|
Android|mobile|android development
iOS|mobile|ios development
Docker|devops|containers, containerization, containerisation
Kubernetes|devops|k8s
AWS|cloud|amazon web services, ec2, s3, lambda, aws lambda
Azure|cloud|microsoft azure
Google Cloud|cloud|gcp, google cloud platform
Linux|devops|unix, ubuntu
CI/CD|devops|continuous integration, continuous deployment, jenkins, circleci, gitlab ci
Terraform|devops|infrastructure as code
Nginx|devops|
Redis|backend|
Kafka|data_eng|apache kafka
RabbitMQ|backend|
Elasticsearch|backend|elastic search
Cybersecurity|security|information security, infosec, network security, penetration testing
Agile|pm|scrum, kanban, sprint planning
Project Management|pm|project planning, pmp, project coordination, project delivery
Product Management|pm|product roadmap, product owner, roadmapping
Stakeholder Management|pm|stakeholder engagement, stakeholder communication, stakeholder reporting
Research|research|qualitative research, quantitative research, literature review, archival research, desk research, field research
Policy Analysis|research|policy research, public policy, policy briefs, policy brief
Survey Design|research|survey research, questionnaire design, survey analysis
Academic Writing|writing|research papers, research paper, academic papers, journal articles
Report Writing|writing|technical writing, writing reports, report preparation, reporting
Content Writing|writing|content creation, blog writing, article writing, blogging
Copywriting|writing|copy writing, ad copy
Editing|writing|proofreading, copy editing, copyediting
Translation|writing|translating, localisation, localization
Public Speaking|comms|presentation skills, debate
Presentations|comms|presentation, powerpoint, ms powerpoint, google slides
Communication|comms|written communication, verbal communication, communication skills
Teaching|teaching|lecturing, tutoring, classroom management, lesson planning
Curriculum Development|teaching|curriculum design, instructional design
Training & Development|hr|employee training, learning and development, corporate training
SEO|marketing|search engine optimization, search engine optimisation, on-page seo, off-page seo, keyword research
SEM|marketing|google ads, google adwords, ppc, paid search, pay per click
Social Media|marketing|social media marketing, social media management, instagram, linkedin marketing, community management
Content Marketing|marketing|content strategy, content calendar, content planning
Email Marketing|marketing|mailchimp, email campaigns, newsletter, newsletters
Digital Marketing|marketing|online marketing, performance marketing, growth marketing
Campaign Management|marketing|marketing campaigns, campaign reporting, campaign planning, campaign analysis
Brand Management|marketing|branding, brand strategy
Market Research|research|competitor analysis, competitive analysis, customer research
CRM|sales|salesforce, hubspot, zoho, customer relationship management
Sales|sales|b2b sales, b2c sales, inside sales, sales targets
Business Development|sales|lead generation, business growth, partnerships
Negotiation|sales|contract negotiation
Account Management|sales|client management, client relations, key accounts
Customer Service|customer|customer support, customer success, helpdesk, help desk, client servicing
Financial Analysis|finance|financial modelling, financial modeling, financial reporting, variance analysis
Accounting|finance|bookkeeping, book keeping, tally, quickbooks, accounts payable, accounts receivable, general ledger
Budgeting|finance|budget management, cost control, financial planning
Auditing|finance|internal audit, audit
Payroll|hr|payroll processing
Recruitment|hr|recruiting, talent acquisition, candidate sourcing, sourcing candidates, screening candidates
Human Resources|hr|hr, employee relations, hr operations, hris
Onboarding|hr|employee onboarding
Compliance|legal|regulatory compliance, policy compliance
Risk Management|legal|risk assessment, risk analysis
Legal Research|legal|legal drafting, contract drafting
Operations Management|ops|operations, process improvement, process optimization, process optimisation
Supply Chain|ops|logistics, procurement, inventory management, vendor management
Data Entry|admin|data management
Administration|admin|administrative support, office administration, office management, scheduling, calendar management
Microsoft Office|admin|ms office, office suite, word, outlook
Google Workspace|admin|g suite, gsuite
UI/UX Design|design|ux design, ui design, user research, wireframing, wireframes, prototyping, user experience
Figma|design|sketch, adobe xd
Canva|design|
Adobe Photoshop|design|photoshop
Adobe Illustrator|design|illustrator
Video Editing|design|premiere pro, final cut, video production
Leadership|soft|team leadership, team management, people management, mentoring, mentorship
Teamwork|soft|collaboration, team player, cross-functional
Problem Solving|soft|critical thinking, analytical thinking, analytical skills
Time Management|soft|prioritisation, prioritization, multitasking
Attention to Detail|soft|detail oriented, detail-oriented
"""


def _parse():
    table = {}          # key(lower display) -> (display, family, [aliases])
    for line in RAW.strip().splitlines():
        disp, fam, aliases = (x.strip() for x in line.split("|"))
        al = [a.strip() for a in aliases.split(",") if a.strip()]
        table[disp.lower()] = (disp, fam, al)
    return table


TABLE = _parse()
FAMILY = {k: v[1] for k, v in TABLE.items()}
DISPLAY = {k: v[0] for k, v in TABLE.items()}

# alias (lower) -> canonical key (lower display). Single-letter or very ambiguous skills are only
# recognised through their longer aliases or when written alone inside a skills list.
AMBIGUOUS = {"r", "go", "c", "sas", "word", "rest", "audit", "operations", "rails", "spring", "node",
             "express", "ts", "js", "hr", "ml", "ga", "sketch", "oracle", "macros", "instagram", "scheduling",
             "debate", "elastic search", "newsletter", "newsletters", "presentation", "reporting", "translating",
             "sales", "research", "communication", "leadership", "teaching", "editing", "administration", "swift",
             "spark", "dart", "compliance", "mentoring", "teamwork", "collaboration", "operations management", "onboarding"}
ALIAS = {}
for key, (disp, fam, al) in TABLE.items():
    ALIAS[key] = key
    for a in al:
        ALIAS.setdefault(a.lower(), key)


def canonical(name):
    """Map any alias/display text to the canonical lower-case key, or None if unknown."""
    return ALIAS.get(re.sub(r"\s+", " ", (name or "").strip().lower()))


def display(key):
    return DISPLAY.get(key, key)


def _compile():
    pats = []
    for a, key in ALIAS.items():
        if a in AMBIGUOUS:      # these need a skills-list context; handled by the parser, not free-text scan
            continue
        pat = re.compile(r"(?<![\w+#./-])" + re.escape(a).replace(r"\ ", r"[\s-]+") + r"(?![\w+#]|-\w)", re.I)
        pats.append((pat, key))
    return pats


_PATTERNS = _compile()


def find_skills(text):
    """Return {canonical_key: [(start, end), ...]} for unambiguous skill mentions in free text."""
    found = {}
    for pat, key in _PATTERNS:
        for m in pat.finditer(text or ""):
            found.setdefault(key, []).append((m.start(), m.end()))
    return found
