"""Fictional CVs and job descriptions used by tests and by the sample_data generator.
Every person, employer and project here is invented. Three different backgrounds on purpose."""
import io, textwrap

PRIYA = """Priya Nair
priya.nair@example.com | +91 98200 11122 | Pune, India
linkedin.com/in/priya-nair-demo | github.com/priyanair-demo

Professional Summary
Data analyst with four years of experience turning retail and supply data into dashboards and decisions.

Experience
Data Analyst | RetailWorks Analytics | Mar 2022 – Present
• Wrote SQL queries on PostgreSQL to build weekly sales and inventory reports for 40 stores.
• Built Power BI dashboards used by regional managers; cut manual reporting time by 60%.
• Cleaned and analysed customer data in Python (pandas) and Excel to find churn drivers.
• Presented findings to stakeholders every month and ran an A/B test on a loyalty offer.

Junior Data Analyst | BlueLeaf Foods | Jul 2020 – Feb 2022
• Maintained Excel models with pivot tables and VLOOKUP for the finance team.
• Automated a daily sales extract with SQL and Python scripts.

Education
B.Sc. in Statistics, Savitribai Phule Pune University, 2020. CGPA: 8.4/10

Skills
SQL, PostgreSQL, Excel, Power BI, Python, pandas, Tableau, Statistics, Data Analysis, Data Visualization

Projects
Customer churn analysis – Analysed 20,000 customer records with Python and SQL and presented the drivers in Power BI.
Store footfall dashboard – Built a Tableau dashboard comparing footfall and sales across 12 stores.

Certifications
Google Data Analytics Certificate, Coursera, 2021

Languages
English (Fluent), Hindi (Native), Marathi (Native)
"""

ROHAN = """ROHAN MEHTA
rohan.mehta@example.com
+91 99876 54321
Bengaluru, India

SUMMARY
Backend-leaning software engineer with six years of experience building and deploying Python web services.

WORK EXPERIENCE

Senior Software Engineer, CloudNest Technologies (Jan 2021 - Present)
- Designed REST APIs in Flask and FastAPI that serve 2 million requests a day.
- Containerised services with Docker and deployed them to AWS (EC2, S3) through a CI/CD pipeline on GitHub Actions.
- Wrote unit tests with pytest and reviewed pull requests; mentored two junior developers.
- Tuned PostgreSQL queries and added Redis caching, reducing API latency by 35%.

Software Engineer, Pixel Forge Labs (Aug 2018 - Dec 2020)
- Built a React and JavaScript front end and a Django back end for an e-commerce site.
- Used Git for version control and worked in an Agile team with two-week sprints.

EDUCATION
B.Tech in Computer Science and Engineering, Visvesvaraya Technological University, 2018, CGPA 8.9

TECHNICAL SKILLS
Python, Flask, Django, FastAPI, JavaScript, React, SQL, PostgreSQL, Docker, AWS, Git, Linux, REST APIs, Redis

PROJECTS
Open-source task queue: A small Python job queue with retries and a web dashboard, published on GitHub.
Expense tracker: Flask and SQLite app with charts, deployed with Docker.

CERTIFICATIONS
AWS Certified Cloud Practitioner - Amazon Web Services - 2022
"""

MEERA = """Meera Kapoor
meera.kapoor@example.com  |  +91 91234 56780  |  Delhi, India

Profile
Content and digital marketing professional with a political science background and three years of campaign experience.

Experience
GreenSprout Media — Digital Marketing Executive (Jun 2022 – Present)
Planned and ran SEO and content marketing campaigns, growing organic traffic by 45% in one year.
Managed the brand's Instagram and LinkedIn accounts and wrote email newsletters in Mailchimp.
Tracked results in Google Analytics and prepared monthly campaign reports for the founders.
Wrote blog posts and web copy; carried out keyword research and competitor analysis.

Civic Voices Foundation — Research and Communications Intern (Jan 2021 – May 2022)
Conducted qualitative research and policy analysis for advocacy briefs.
Drafted press notes and social media posts, and designed posters in Canva.

Education
M.A. in Political Science, Delhi University, 2022
B.A. (Hons) History, Miranda House, Delhi University, 2020

Skills
SEO, Content Marketing, Social Media, Google Analytics, Copywriting, Mailchimp, Canva, Policy Analysis, Research, Public Speaking

Achievements
Won the university inter-college debate championship in 2019.
"""

# A CV whose only role has no dates, with a '| Remote' header, "Bachelor of Arts" and certificates run together on one line:
# the layout that used to produce an empty work history and "0 years". Fictional.
KIRAN = """KIRAN DESAI
Pune, India +91 9000011111 kiran.desai@example.org
Operations | Research
PROFESSIONAL SUMMARY
Analytical graduate with experience in research support and spreadsheet reporting.
EDUCATION
Fergusson College — Bachelor of Arts (Economics & Statistics) | CGPA: 7.9/10
SELECTED PROJECTS
Sales Dashboard (Excel & Power BI)
• Built interactive KPI dashboards using Pivot Tables, Charts and Power BI.
Customer Survey Analysis
• Queried survey responses with SQL using JOIN and GROUP BY and summarised the findings in a short report.
EXPERIENCE
Freelance Research & Administrative Support | Remote
• Conducted online research and organised information into structured reports.
• Built Excel-based reports and dashboards for analysis.
TECHNICAL SKILLS
Analytics: Excel (Advanced), SQL, Power BI
CERTIFICATIONS
Google Analytics Certificate Google Digital Marketing Fundamentals Some Long Course Name Another Programme Title
"""

from app.demo_data import JOBS  # noqa: E402  (single source of truth for the demo openings)

# Answers of different quality for the Data Analyst job (used to prove scoring responds to content)
# Three invented applicants whose CVs come from ONE generated template: the same sentences with different names, employers,
# tools and numbers filled in. Used to demonstrate (and test) template detection. None of them is a real person.
TEMPLATE_CV = """{name}
{email} | {phone} | {city}, India

Professional Summary
Results-driven data analyst with a proven track record of leveraging data to drive business growth in fast-paced environments.
Detail-oriented and passionate about turning complex datasets into actionable insights for cross-functional teams.

Experience
Data Analyst | {c1} | {d1} – Present
• Spearheaded the development of {n1} interactive dashboards in {tool}, improving reporting efficiency by {p1}%.
• Leveraged SQL and Excel to analyse sales data across {n2} regions, driving data-driven decision making.
• Collaborated with cross-functional teams to deliver actionable insights to senior stakeholders.
• Automated recurring reports using Python, reducing manual effort by {p2}%.

Junior Analyst | {c2} | {d2} – {d3}
• Supported the analytics team in cleaning and validating large datasets using Excel and SQL.
• Prepared weekly performance reports that were instrumental in improving customer retention by {p3}%.

Education
{degree}, {uni}, {year}

Skills
SQL, Excel, {tool}, Python, Data Analysis, Data Visualization, Statistics

Certifications
{cert}
"""
ARJUN = TEMPLATE_CV.format(name="Arjun Rao", email="arjun.rao@example.com", phone="+91 98111 22334", city="Hyderabad", c1="Northwind Retail", d1="Jan 2022",
                           n1=12, tool="Power BI", p1=35, n2=6, p2=40, c2="Orbit Logistics", d2="Jun 2020", d3="Dec 2021", p3=15,
                           degree="B.Com. in Business Analytics", uni="Osmania University", year=2020, cert="Microsoft Power BI Data Analyst, 2022")
SANA = TEMPLATE_CV.format(name="Sana Iqbal", email="sana.iqbal@example.com", phone="+91 97222 33445", city="Lucknow", c1="Brightcart Stores", d1="Apr 2021",
                          n1=9, tool="Tableau", p1=28, n2=4, p2=50, c2="Kestrel Finance", d2="Aug 2019", d3="Mar 2021", p3=11,
                          degree="B.Sc. in Mathematics", uni="University of Lucknow", year=2019, cert="Tableau Desktop Specialist, 2021")
DEV = TEMPLATE_CV.format(name="Dev Malhotra", email="dev.malhotra@example.com", phone="+91 96333 44556", city="Chandigarh", c1="Summit Outdoor Gear", d1="Sep 2022",
                         n1=7, tool="Looker", p1=42, n2=5, p2=30, c2="Harbor Health", d2="Jan 2021", d3="Aug 2022", p3=18,
                         degree="B.Tech. in Information Technology", uni="Panjab University", year=2020, cert="Google Data Analytics Certificate, 2021")

STRONG_ANALYST_ANSWER = (
    "First I would clarify the question with the stakeholders and confirm how weekend sales are defined. Then I would write a SQL query "
    "that joins the orders table with the store table, filters the last quarter with a date range, groups by region and weekend day and "
    "sums revenue. I would check for duplicates and null values, and reconcile the totals against the finance report before trusting "
    "the numbers. Next I would compare against the same period last year to separate seasonality from a real drop, and segment by "
    "product category and customer type. Finally I would build a dashboard in Power BI with a trend line and a regional breakdown, "
    "and explain the main finding in plain language to the managers, with a recommendation and the limits of the data."
)
WEAK_ANSWER = "I would look at the data and see what is wrong and tell the manager."
OFF_TOPIC_ANSWER = (
    "I really enjoy long walks on the beach and cooking dinner for my family on weekends. My favourite season is autumn because "
    "the weather is mild and the evenings are quiet and I like reading novels with a cup of tea in the garden."
)


# ------------------------------------------------------------------ file builders
def make_pdf(text, pages=1, width=95):
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(595, 842))
    y = 810
    for raw in text.splitlines() * pages:
        for line in (textwrap.wrap(raw, width) or [""]):
            if y < 50:
                c.showPage(); y = 810
            c.setFont("Helvetica-Bold" if raw.isupper() or raw in ("Experience", "Education", "Skills", "Projects", "Certifications", "Languages", "Profile", "Achievements", "Professional Summary") else "Helvetica", 10)
            c.drawString(50, y, line)
            y -= 14
    c.showPage()
    c.save()
    return buf.getvalue()


def make_docx(text):
    import docx
    d = docx.Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def scanned_like_pdf():
    """A PDF with graphics but no text layer: what a scanned CV looks like to a text extractor."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(50, 50, 300, 300, fill=1)
    c.showPage()
    c.save()
    return buf.getvalue()
