STAGES = ["applied", "cv_reviewed", "assessment_sent", "assessment_started", "assessment_submitted", "ai_evaluated",
          "human_review", "shortlisted", "rejected", "interview", "offer", "closed"]
TRANSITIONS = {
    "applied": {"cv_reviewed", "rejected", "closed"},
    "cv_reviewed": {"assessment_sent", "human_review", "rejected", "closed"},
    "assessment_sent": {"assessment_started", "rejected", "closed"},
    "assessment_started": {"assessment_submitted", "closed"},
    # human_review from here only when automatic scoring has failed (enforced in the route): the answers still get a human read
    "assessment_submitted": {"ai_evaluated", "human_review"},
    "ai_evaluated": {"human_review", "assessment_sent"},   # assessment_sent = retake granted
    "human_review": {"shortlisted", "rejected", "assessment_sent"},
    "shortlisted": {"interview", "rejected", "closed"},
    "interview": {"offer", "rejected", "closed"},
    "offer": {"closed"},
    "rejected": {"closed"},
    "closed": set(),
}
# Targets a recruiter may request through the API. The rest are set only by system events.
MANUAL = {"cv_reviewed", "human_review", "shortlisted", "rejected", "interview", "offer", "closed"}
LABEL = {"applied": "Applied", "cv_reviewed": "CV reviewed", "assessment_sent": "Assessment sent", "assessment_started": "Assessment started",
         "assessment_submitted": "Assessment submitted", "ai_evaluated": "Scored", "human_review": "Human review", "shortlisted": "Shortlisted",
         "rejected": "Rejected", "interview": "Interview", "offer": "Offer", "closed": "Closed"}
CANDIDATE_LABEL = {"applied": "Application received", "cv_reviewed": "Under review", "assessment_sent": "Assessment waiting for you",
                   "assessment_started": "Assessment in progress", "assessment_submitted": "Assessment submitted",
                   "ai_evaluated": "Under review", "human_review": "Under review", "shortlisted": "Shortlisted",
                   "rejected": "Not progressing", "interview": "Interview stage", "offer": "Offer stage", "closed": "Closed"}


def can(cur, to):
    return to in TRANSITIONS.get(cur, set())
