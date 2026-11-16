"""Fictional demo content: three openings and the answers three invented candidates give. Nothing here is a real person."""

JOBS = {
    "analyst": {
        "title": "Data Analyst", "kind": "job",
        "description": "Turn business data into reporting that managers use. You will write SQL, build dashboards and explain findings to non-technical stakeholders.",
        "required_skills": ["SQL", "Excel", "Data analysis"], "preferred_skills": ["Power BI", "Python"],
        "min_years": 2, "education_level": "bachelor",
        "custom_requirements": ["Dashboard experience", "Stakeholder reporting"],
        "task_brief": "A retailer's weekend sales have dropped 12% in two regions and management wants to know why.",
    },
    "backend": {
        "title": "Backend Python Developer", "kind": "job",
        "description": "Build and maintain Python web services and REST APIs. You will own features from design to deployment.",
        "required_skills": ["Python", "REST APIs", "SQL", "Git"], "preferred_skills": ["Docker", "AWS"],
        "min_years": 3, "education_level": "bachelor",
        "custom_requirements": ["Built and deployed web applications"],
        "task_brief": "Design an API for a booking service that must stay fast when traffic doubles.",
    },
    "marketing": {
        "title": "Digital Marketing Executive", "kind": "job",
        "description": "Run SEO and content campaigns, grow our social channels and report on results.",
        "required_skills": ["SEO", "Content marketing", "Google Analytics"], "preferred_skills": ["Social media", "Copywriting"],
        "min_years": 1, "education_level": "bachelor",
        "custom_requirements": ["Campaign reporting"],
        "task_brief": None,
    },
    "challenge": {
        "title": "Data Storytelling Challenge 2026", "kind": "competition",
        "description": "An open competition for students and early-career analysts: turn a public sales dataset into a short, evidence-based story for a non-technical audience.",
        "required_skills": ["Data analysis", "Excel", "Data Visualization"], "preferred_skills": ["Power BI", "SQL"],
        "min_years": 0, "education_level": "none",
        "custom_requirements": ["Presenting findings"],
        "task_brief": "You have one week of store sales data and must explain to a shop owner which change would most improve weekend revenue.",
    },
}

ACCOUNTS = {
    "admin": ("admin@talentbridge.demo", "DemoAdmin#2026"),
    "recruiter": ("recruiter@talentbridge.demo", "DemoRecruiter#2026", "Riya Sharma", "Demo Hiring Co"),
}
CANDIDATE_PASSWORD = "DemoCandidate#2026"

# (key, full name, email, sample file, job to apply to, answers or None)
ANSWERS = {
    ("priya", "analyst"): [
        "I would start by confirming what counts as revenue, for example whether refunds are excluded, and which quarter the manager means. Then I would join the orders table to the customers table on customer id, filter the order date to the last quarter with a where clause, group by customer, sum the order value and order by that total descending with a limit of five. Before sending it I would check for duplicate order rows and null customer ids, and I would reconcile the total revenue against the finance report. Finally I would give the manager the five names with revenue and a short note on any assumptions.",
        "First I would copy the raw file so I keep the original, then remove duplicate rows, trim spaces and standardise the date column into one format. For blank cells I would decide case by case whether to fill them, flag them or exclude them, and note this. Next I would use a pivot table by region and month, with XLOOKUP to bring in the region names from a lookup table, then compare the pivot total with the grand total of the clean data to make sure nothing was lost. Finally I would add a simple chart and a short summary of the main numbers for the team.",
        "In the customer churn project I was the only analyst, so I owned it end to end. I pulled 20,000 customer records with SQL, cleaned them in Python using pandas, and tested which behaviours predicted churn, such as fewer orders in the last 60 days. I presented the drivers in a Power BI dashboard for the retention team. The result was a shortlist of three drivers, and the team used it to target a re-engagement offer. Next time I would validate the findings with an A/B test earlier and document the data definitions better.",
        "I would first clarify with management what a weekend drop of 12% means and compare it with the same weeks last year to separate seasonality from a real change. Then I would query sales by region, store, product category and day, and check data quality for missing days or duplicate rows. If the drop is concentrated in one category or store group I would dig into promotions, stock-outs and footfall. I would verify the numbers by reconciling with the finance totals and ask a colleague to review. Finally I would build a short Power BI dashboard and explain the finding and a recommendation to the managers in plain language, including what the data cannot tell us.",
    ],
    ("rohan", "backend"): [
        "First I would measure before changing anything: check the request logs and timing metrics, reproduce the slow call and profile it, and look at the query plan with EXPLAIN. Order history endpoints are often slow because of an N+1 query in the ORM or a missing index, so I would check the database queries, add an index on customer id and order date, and add pagination so one request never loads thousands of rows. If the data is read far more than it changes I would add caching with Redis. I would write a regression test and a small load test with the fix, deploy it to staging, then release it with monitoring and an alert on response time so I know if it comes back.",
        "I use PostgreSQL daily, though not as an analyst. I would join orders to customers on the customer id, filter the order date to last quarter, group by customer and sum the amount, order descending and limit to five. I would check for null values and duplicates and compare the sum with a direct total query to validate it. I would also look at the query plan and add an index if it is slow.",
        "At CloudNest I own the booking-related services. I designed the REST APIs in Flask and FastAPI, packaged them in Docker and set up deployment to AWS with a CI/CD pipeline in GitHub Actions. The result was stable releases and about 2 million requests a day. I also added Redis caching, which reduced latency by 35 percent. If I did it again I would add load tests earlier and write the runbook while building, not afterwards.",
        "First I would clarify the expected traffic, the main booking operations and the consistency needs, for example no double bookings. Then I would define endpoints such as POST and GET on bookings, with validation, authentication and proper status codes like 400, 404 and 409. For speed I would add database indexes, pagination, caching with Redis for read-heavy calls and a queue for slow work like emails, and I would plan horizontal scaling behind a load balancer. I would test with automated tests and a load test, monitor with logs and metrics, and document the API with OpenAPI so the team can use it.",
    ],
    ("meera", "marketing"): [
        "I would start with keyword research to find what people search for and the search intent, then improve titles, headings and meta descriptions of the blog posts and add internal links. I would also check that pages load quickly on mobile. To see if it worked I would track rankings and organic traffic in Google Analytics and Search Console every month.",
        "In the first week I would set the goal, for example 500 sign-ups, and define the audience. Then I would plan a content calendar with blog posts, a newsletter and social posts across the four weeks. At the end I would measure traffic, engagement and sign-ups and report what worked.",
        "At GreenSprout I plan and run SEO and content campaigns. I grew organic traffic by 45 percent in a year by publishing blog posts based on keyword research and reporting every month in Google Analytics. The founders used the reports to decide on the next topics. I would improve by testing headlines and tracking conversion, not only traffic.",
        "I would first understand the goals and the current performance, then audit the existing content and keywords. I would plan the campaigns for SEO and social media with a calendar, publish content, and track results in Google Analytics. I would report to the team every month.",
    ],
    ("rohan", "analyst"): [
        "I would join the tables and sort by revenue and take the top five.",
        "I would open it in Excel and fix the duplicates and blank cells, then make a table by region.",
        "It was a small queue project that I built in Python and published on GitHub. I wrote the code and tests. It was used by a few people.",
        "I would look at the data to see where the drop is and tell the manager.",
    ],
    # Two applicants who submit the same generated answers (one left the chatbot's opening line in). Shown side by side to the reviewer.
    ("arjun", "analyst"): [       'Certainly! Here is a structured approach. First, I would clarify the definition of revenue and the reporting period with the stakeholder. Then I would write a SQL query that joins the '
        'orders table to the customers table, filters on the order date for the last quarter, groups by customer and sums the order amount. Finally, I would order the result in descending order, '
        'limit it to the top five rows and validate the totals against the finance report before sharing.',
        'To clean the dataset, I would begin by creating a backup of the raw file. Next, I would remove duplicate rows, standardise date formats and trim whitespace from text fields. For missing '
        'values, I would evaluate each column and either impute, flag or remove the rows depending on business impact. I would then build a pivot table by region, add a simple chart, and document '
        'every transformation so that the analysis is reproducible.',
        'In my previous role I was responsible for building dashboards end to end. I gathered requirements from stakeholders, wrote the SQL to prepare the data, and designed the visuals so that '
        'managers could track performance at a glance. The result was a significant reduction in manual reporting effort. If I did it again, I would involve end users earlier and automate data '
        'quality checks.',
        'I would start by clarifying the scope of the 12% weekend decline and confirming the baseline period. Then I would segment sales by region, store, product category and day to isolate where '
        'the drop is concentrated. I would compare against the same weeks last year to rule out seasonality, check for stock-outs, pricing changes and promotions, and validate the data pipeline. '
        'Finally, I would present the findings with a clear recommendation and next steps.'],
    ("sana", "analyst"): [       'First, I would clarify the definition of revenue and the reporting period with the stakeholder. Then I would write a SQL query that joins the orders table to the customers table, filters on '
        'the order date for the last quarter, groups by customer and sums the order amount. Finally, I would order the result in descending order, limit it to the top five rows and validate the '
        'totals against the finance report before sharing.',
        'To clean the dataset, I would begin by creating a backup of the raw file. Next, I would remove duplicate rows, standardise date formats and trim whitespace from text fields. For missing '
        'values, I would evaluate each column and either impute, flag or remove the rows depending on business impact. I would then build a pivot table by region, add a simple chart, and document '
        'every transformation so that the analysis is reproducible.',
        'In my previous role I was responsible for building dashboards end to end. I gathered requirements from stakeholders, wrote the SQL to prepare the data, and designed the visuals so that '
        'managers could track performance at a glance. The result was a big reduction in manual reporting effort. If I did it again, I would involve end users earlier and automate data quality '
        'checks.',
        'I would start by clarifying the scope of the 12% weekend decline and confirming the baseline period. Then I would segment sales by region, store, product category and day to isolate where '
        'the drop is concentrated. I would compare against the same weeks last year to rule out seasonality, check for stock-outs, pricing changes and promotions, and validate the data pipeline. '
        'Finally, I would present the findings with a clear recommendation and next steps.'],
}

# who applies where; answers=None means the candidate applied but has not started the assessment
CANDIDATES = [
    ("priya", "Priya Nair", "priya.nair@talentbridge.demo", "cv_priya_nair_data_analyst.pdf", [("analyst", True)]),
    ("rohan", "Rohan Mehta", "rohan.mehta@talentbridge.demo", "cv_rohan_mehta_software_engineer.pdf", [("backend", True), ("analyst", True)]),
    ("meera", "Meera Kapoor", "meera.kapoor@talentbridge.demo", "cv_meera_kapoor_marketing.docx", [("marketing", True), ("analyst", False)]),
    # template CVs and shared answers: what the originality checks are for
    ("arjun", "Arjun Rao", "arjun.rao@talentbridge.demo", "cv_arjun_rao_template.pdf", [("analyst", True)]),
    ("sana", "Sana Iqbal", "sana.iqbal@talentbridge.demo", "cv_sana_iqbal_template.pdf", [("analyst", True)]),
    ("dev", "Dev Malhotra", "dev.malhotra@talentbridge.demo", "cv_dev_malhotra_template.pdf", [("analyst", False)]),
]
# minutes between Start and Submit in the seeded data (default 26). The two shared submissions arrive in 3 minutes.
MINUTES_TAKEN = {("arjun", "analyst"): 3, ("sana", "analyst"): 4}
