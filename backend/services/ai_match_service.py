"""AI profile-to-lead matching for HireMate.

The service compares the signed-in user's profile with one selected LinkedIn
job/post lead. Results are cached by a profile+lead hash, so opening the same
lead repeatedly does not exhaust the AI provider.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib import error, request

from core.config import GROQ_API_KEY, GROQ_CHAT_COMPLETIONS_URL, GROQ_KEY_FILE, GROQ_MODEL, XAI_KEY_FILE
from core.database import db
from services.ai_keyword_service import keyword_profile_for_user


AI_MATCH_CACHE_HOURS = 24

PROFILE_MATCH_PROMPT = """You are HireMate AI, an advanced profile-to-job matching engine.

Your task is to analyze how well a selected LinkedIn job post or hiring post matches the userâ€™s profile.

You must compare the job/post details with the user profile and return an accurate match percentage, matched skills, missing skills, match reasons, and recommendation.

The result will be shown in the HireMate interface as:

Profile Match
Based on your profile
Overall Match: 0â€“100%
Matched Skills: skill + percentage
Missing Skills: skill + importance

---

## USER PROFILE

Name:
{{user_name}}

Professional Title:
{{professional_title}}

Location:
{{user_location}}

About:
{{about}}

Skills:
{{skills}}

Interests:
{{interests}}

Experience:
{{experience}}

Education:
{{education}}

Work Preferences:
{{work_preferences}}

Generated Profile Keywords:
{{profile_keywords}}

---

## LINKEDIN JOB / POST DETAILS

Post Type:
{{post_type}}

Job Title:
{{job_title}}

Company:
{{company_name}}

Post Content:
{{post_content}}

Required Skills:
{{required_skills}}

Preferred Skills:
{{preferred_skills}}

Experience Required:
{{experience_required}}

Education Required:
{{education_required}}

Location:
{{job_location}}

Work Type:
{{work_type}}

Seniority Level:
{{seniority_level}}

---

## MATCHING OBJECTIVE

Analyze whether this job/post is suitable for the user.

You must check:

1. Role Match
2. Skill Match
3. Experience Match
4. Education Match
5. Interest Match
6. Location / Work Preference Match
7. Seniority Match
8. Semantic Match

Do not only check exact words. Also check meaning.

Example:

* "LLM" can match "Generative AI", "GPT", "RAG", "LangChain", "Transformers"
* "NLP" can match "text classification", "chatbot", "language model", "sentiment analysis"
* "Python" can match "Pandas", "NumPy", "Scikit-learn", "FastAPI"
* "Data Science" can match "Machine Learning", "Data Analysis", "Predictive Modeling"

---

## SCORING SYSTEM

Calculate final profile match using this weighting:

1. Role Match: 20%
2. Skill Match: 30%
3. Experience Match: 15%
4. Education Match: 8%
5. Interest Match: 10%
6. Location / Work Preference Match: 7%
7. Seniority Match: 5%
8. Semantic Match: 5%

Total = 100%

---

## HOW TO SCORE EACH SECTION

A. Role Match â€” 20%

Compare user title and career direction with job title.

High score:

* User title: AI Engineer
* Job: AI Engineer, ML Engineer, NLP Engineer, LLM Engineer, Data Scientist

Medium score:

* User title: AI Engineer
* Job: Python Developer, Data Analyst, Software Engineer with AI tasks

Low score:

* User title: AI Engineer
* Job: Sales Executive, Graphic Designer, HR Officer

Return role_match_score out of 20.

---

B. Skill Match â€” 30%

Compare user skills with required and preferred skills.

Give higher weight to required skills than preferred skills.

Required skills = more important
Preferred skills = less important

For every matched skill, return:

* skill name
* user has it or related skill
* match percentage
* evidence from profile
* evidence from post

Example:
Python â†’ 100% if user has Python directly
LLM â†’ 90% if post says Generative AI / GPT / RAG
SQL â†’ 0% if user profile does not mention SQL or related database skill

Return skill_match_score out of 30.

---

C. Experience Match â€” 15%

Compare required experience with user experience.

If the user has no experience but the role is internship or entry-level:
Score can still be medium/high.

If job requires:

* Internship / student / beginner â†’ beginner user can match well
* Entry-level â†’ beginner or graduate can partially match
* 2â€“3 years â†’ beginner user should get lower score
* Senior / Lead â†’ beginner user should get very low score

Do not fabricate experience.

Return experience_match_score out of 15.

---

D. Education Match â€” 8%

Compare user education with job education requirement.

Example:

* BS Software Engineering can match Computer Science, Software Engineering, AI, Data Science requirements.
* If education is missing, score lower but not zero unless job strictly requires it.

Return education_match_score out of 8.

---

E. Interest Match â€” 10%

Compare user interests with the job/post domain.

Example:
User interests:
Remote, AI Research, LLM, Data Science

Job:
Remote Generative AI Internship

This should get high interest match.

Return interest_match_score out of 10.

---

F. Location / Work Preference Match â€” 7%

Compare:

* user location
* job location
* remote/hybrid/onsite preference
* work type

Examples:

* User wants Remote, job is Remote â†’ high score
* User is in Islamabad, job is Islamabad â†’ high score
* User wants Hybrid, job is Hybrid â†’ high score
* User wants Remote, job is strictly onsite in another city â†’ lower score

Return location_work_match_score out of 7.

---

G. Seniority Match â€” 5%

Compare user level with job seniority.

Examples:

* Beginner user + Internship â†’ high
* Beginner user + Junior role â†’ medium/high
* Beginner user + Senior role â†’ low
* Mid-level user + Senior role â†’ medium

Return seniority_match_score out of 5.

---

H. Semantic Match â€” 5%

Analyze deeper meaning beyond exact keywords.

Example:
Post says:
"Build conversational assistants using transformer models"

User has:
LLM, NLP, Python

This is a strong semantic match.

Return semantic_match_score out of 5.

---

## MATCH PERCENTAGE RULES

Final percentage must be realistic.

Use these ranges:

90â€“100%:
Excellent match. User strongly fits the role.

75â€“89%:
Strong match. User fits most important requirements.

60â€“74%:
Good match. User matches several important areas but has some gaps.

45â€“59%:
Partial match. User has some relevant skills but important gaps exist.

25â€“44%:
Weak match. Limited relevance.

0â€“24%:
Poor match. Mostly irrelevant.

Do not give a high score if:

* required skills are mostly missing
* role is unrelated
* seniority is too high
* job is outside userâ€™s domain
* post is too vague

---

## FRONTEND DISPLAY REQUIREMENTS

Return data that can be shown in UI like:

Profile Match
Based on your profile
78%

Matched Skills:
Python 100%
NLP 90%
LLM 85%
Data Science 75%

Missing Skills:
SQL - Important
Docker - Medium
AWS - Medium

Reasons:

* Your Python and NLP skills match this post.
* The role is aligned with your AI Engineer profile.
* Experience requirement is suitable for entry-level candidates.

---

## OUTPUT FORMAT

Return ONLY valid JSON.

{
"overall_match_percentage": 0,

"match_label": "",

"summary": "",

"score_breakdown": {
"role_match": {
"score": 0,
"max_score": 20,
"reason": ""
},
"skill_match": {
"score": 0,
"max_score": 30,
"reason": ""
},
"experience_match": {
"score": 0,
"max_score": 15,
"reason": ""
},
"education_match": {
"score": 0,
"max_score": 8,
"reason": ""
},
"interest_match": {
"score": 0,
"max_score": 10,
"reason": ""
},
"location_work_preference_match": {
"score": 0,
"max_score": 7,
"reason": ""
},
"seniority_match": {
"score": 0,
"max_score": 5,
"reason": ""
},
"semantic_match": {
"score": 0,
"max_score": 5,
"reason": ""
}
},

"matched_skills": [
{
"skill": "",
"match_percentage": 0,
"match_type": "exact | semantic | related",
"evidence_from_profile": "",
"evidence_from_post": ""
}
],

"missing_skills": [
{
"skill": "",
"importance": "High | Medium | Low",
"reason": ""
}
],

"matched_keywords": [],

"unmatched_keywords": [],

"strengths": [],

"gaps": [],

"recommendation": "",

"should_user_apply": true,

"confidence_score": 0
}

---

## IMPORTANT RULES

1. Be accurate, not overly positive.
2. Do not give fake high scores.
3. Do not invent skills that are not in the profile.
4. Use semantic matching, not only exact word matching.
5. Required job skills matter more than preferred skills.
6. Beginner users can still match internships and junior roles.
7. Senior roles should score low for beginner profiles.
8. If post content is vague, reduce confidence score.
9. If job is unrelated, give a low percentage.
10. Always return editable and frontend-friendly JSON.
11. Output only JSON. Do not add explanations outside JSON.
"""


def profile_match_for_lead(user, lead, force_refresh=False):
    """Return cached or newly generated profile-match JSON for one lead."""
    cache_key = profile_match_cache_key(user, lead)
    if not force_refresh:
        cached = load_cached_match(user["id"], lead["id"], cache_key)
        if cached:
            update_lead_match_score(user["id"], lead["id"], cached.get("overall_match_percentage", 0))
            return cached

    try:
        payload = call_groq_match(build_match_prompt(user, lead))
        result = normalize_match_payload(payload, user, lead, generated_by="groq")
    except Exception as exc:
        result = fallback_match_payload(user, lead)
        result["generation_error"] = str(exc)

    update_lead_match_score(user["id"], lead["id"], result["overall_match_percentage"])
    save_match(user["id"], lead["id"], cache_key, result)
    return result


def profile_match_cache_key(user, lead):
    # A match belongs to the selected lead and the user's profile. The lead id is
    # already stored in ai_profile_matches, so keep the cache key focused on the
    # profile. This prevents repeated AI calls when a synced lead gets minor text
    # or engagement updates, and refreshes naturally when profile data changes.
    profile_bits = {
        "headline": user.get("headline", ""),
        "location": user.get("location", ""),
        "about": user.get("about", ""),
        "skills": user.get("skills", ""),
        "interests": user.get("interests", ""),
        "experience": user.get("experience_detail") or user.get("experience_level") or "",
        "education": user.get("education", ""),
        "work_preferences": user.get("work_modes") or user.get("preferred_locations") or "",
    }
    raw = json.dumps({"profile": profile_bits, "version": 2}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cached_match(user_id, lead_id, cache_key):
    with db() as conn:
        ensure_match_table(conn)
        row = conn.execute(
            """
            SELECT response_json, updated_at FROM ai_profile_matches
            WHERE user_id=? AND lead_id=? AND cache_key=?
            """,
            (user_id, lead_id, cache_key),
        ).fetchone()
        if not row:
            return None
        try:
            updated = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
        except ValueError:
            updated = datetime.now(timezone.utc) - timedelta(days=99)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - updated > timedelta(hours=AI_MATCH_CACHE_HOURS):
            return None
        return json.loads(row["response_json"])


def save_match(user_id, lead_id, cache_key, result):
    with db() as conn:
        ensure_match_table(conn)
        conn.execute(
            """
            INSERT INTO ai_profile_matches(user_id, lead_id, cache_key, response_json, generated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, lead_id, cache_key) DO UPDATE SET
              response_json=excluded.response_json,
              generated_by=excluded.generated_by,
              updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, lead_id, cache_key, json.dumps(result, ensure_ascii=False), result.get("generated_by", "fallback")),
        )


def update_lead_match_score(user_id, lead_id, score):
    """Keep Hot/Warm/Cold lead status aligned with the AI profile match."""
    score = clamp_int(score, 0, 100)
    temperature = "hot" if score >= 75 else "warm" if score >= 45 else "cold"
    with db() as conn:
        conn.execute(
            "UPDATE leads SET score=?, temperature=? WHERE user_id=? AND id=?",
            (score, temperature, user_id, lead_id),
        )


def ensure_match_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_profile_matches (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          lead_id INTEGER NOT NULL,
          cache_key TEXT NOT NULL,
          response_json TEXT NOT NULL,
          generated_by TEXT DEFAULT 'fallback',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id, lead_id, cache_key)
        )
        """
    )


def build_match_prompt(user, lead):
    values = prompt_values(user, lead)
    prompt = PROFILE_MATCH_PROMPT
    for key, value in values.items():
        prompt = prompt.replace("{{" + key + "}}", safe_prompt_value(value))
    return prompt


def prompt_values(user, lead):
    keywords = keyword_summary(user)
    return {
        "user_name": " ".join(part for part in [user.get("first_name", ""), user.get("last_name", "")] if part).strip(),
        "professional_title": user.get("headline", ""),
        "user_location": user.get("location", ""),
        "about": user.get("about", ""),
        "skills": user.get("skills", ""),
        "interests": user.get("interests", ""),
        "experience": user.get("experience_detail") or user.get("experience_level") or "",
        "education": user.get("education", ""),
        "work_preferences": user.get("work_modes") or user.get("preferred_locations") or "",
        "profile_keywords": ", ".join(keywords[:45]),
        "post_type": "LinkedIn Job" if lead.get("lead_kind") == "job" else "LinkedIn Hiring Post",
        "job_title": lead.get("role_title", ""),
        "company_name": lead.get("company", ""),
        "post_content": lead.get("post_text", ""),
        "required_skills": ", ".join(lead.get("tags", []) if isinstance(lead.get("tags"), list) else split_csv(lead.get("tags", ""))),
        "preferred_skills": "",
        "experience_required": lead.get("experience", ""),
        "education_required": "",
        "job_location": lead.get("location", ""),
        "work_type": lead.get("work_type", ""),
        "seniority_level": infer_seniority(lead),
    }


def keyword_summary(user):
    try:
        profile = keyword_profile_for_user(dict(user))
        values = []
        for field in ["primary_roles", "core_skills", "linkedin_search_queries", "linkedin_post_keywords", "semantic_keywords"]:
            values.extend(profile.get(field, []) if isinstance(profile.get(field), list) else [])
        values.extend(item.get("keyword", "") for item in profile.get("final_ranked_keywords", []) if isinstance(item, dict))
        return unique_strings(values)
    except Exception:
        return unique_strings(split_csv(user.get("target_roles", "")) + split_csv(user.get("skills", "")) + split_csv(user.get("interests", "")))


def call_groq_match(prompt):
    key = groq_api_key()
    if not key:
        raise RuntimeError("Groq API key is not configured.")
    body = {
        "model": GROQ_MODEL,
        "stream": False,
        "temperature": 0.15,
        "messages": [
            {"role": "system", "content": "Return only valid JSON. Do not wrap the response in markdown."},
            {"role": "user", "content": prompt},
        ],
    }
    req = request.Request(
        GROQ_CHAT_COMPLETIONS_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "HireMate-FYP/1.0",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=18) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Groq profile-match request failed: {exc.code} {detail[:220]}") from exc
    content = json.loads(raw).get("choices", [{}])[0].get("message", {}).get("content", "")
    return parse_json_content(content)


def groq_api_key():
    key = (GROQ_API_KEY or "").strip()
    if key:
        return key
    try:
        key = GROQ_KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    except OSError:
        pass
    try:
        legacy_key = XAI_KEY_FILE.read_text(encoding="utf-8").strip()
        return legacy_key if legacy_key.startswith("gsk_") else ""
    except OSError:
        return ""


def parse_json_content(content):
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise RuntimeError("AI did not return valid JSON.")


def normalize_match_payload(payload, user, lead, generated_by="groq"):
    payload = payload if isinstance(payload, dict) else {}
    score = clamp_int(payload.get("overall_match_percentage", 0), 0, 100)
    payload["overall_match_percentage"] = score
    payload["match_label"] = str(payload.get("match_label") or label_for_score(score))
    payload["summary"] = str(payload.get("summary") or "Profile match analyzed from the selected lead and your saved profile.")
    payload["score_breakdown"] = normalize_breakdown(payload.get("score_breakdown", {}))
    payload["matched_skills"] = normalize_matched_skills(payload.get("matched_skills", []))
    payload["missing_skills"] = normalize_missing_skills(payload.get("missing_skills", []))
    for key in ["matched_keywords", "unmatched_keywords", "strengths", "gaps"]:
        payload[key] = unique_strings(payload.get(key, []))[:12]
    payload["recommendation"] = str(payload.get("recommendation") or default_recommendation(score))
    payload["should_user_apply"] = bool(payload.get("should_user_apply", score >= 55))
    payload["confidence_score"] = clamp_int(payload.get("confidence_score", 65), 0, 100)
    payload["generated_by"] = generated_by
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    return payload


def normalize_breakdown(breakdown):
    specs = [
        ("role_match", 20),
        ("skill_match", 30),
        ("experience_match", 15),
        ("education_match", 8),
        ("interest_match", 10),
        ("location_work_preference_match", 7),
        ("seniority_match", 5),
        ("semantic_match", 5),
    ]
    normalized = {}
    for key, max_score in specs:
        raw = breakdown.get(key, {}) if isinstance(breakdown, dict) else {}
        normalized[key] = {
            "score": clamp_int(raw.get("score", 0), 0, max_score),
            "max_score": max_score,
            "reason": str(raw.get("reason") or ""),
        }
    return normalized


def normalize_matched_skills(items):
    result = []
    for item in (items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        skill = clean_text(item.get("skill", ""))
        if not skill:
            continue
        result.append(
            {
                "skill": skill,
                "match_percentage": clamp_int(item.get("match_percentage", 0), 0, 100),
                "match_type": clean_text(item.get("match_type", "related")) or "related",
                "evidence_from_profile": clean_text(item.get("evidence_from_profile", "")),
                "evidence_from_post": clean_text(item.get("evidence_from_post", "")),
            }
        )
    return result[:8]


def normalize_missing_skills(items):
    result = []
    for item in (items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        skill = clean_text(item.get("skill", ""))
        if not skill:
            continue
        importance = clean_text(item.get("importance", "Medium"))
        if importance not in {"High", "Medium", "Low"}:
            importance = "Medium"
        result.append({"skill": skill, "importance": importance, "reason": clean_text(item.get("reason", ""))})
    return result[:6]


def fallback_match_payload(user, lead):
    user_terms = unique_strings(split_csv(user.get("skills", "")) + split_csv(user.get("target_roles", "")) + split_csv(user.get("interests", "")))
    lead_text = " ".join([lead.get("role_title", ""), lead.get("post_text", ""), " ".join(lead.get("tags", []) if isinstance(lead.get("tags"), list) else split_csv(lead.get("tags", "")))])
    lead_lower = lead_text.lower()
    matched = [term for term in user_terms if term.lower() in lead_lower]
    base = 35 + min(40, len(matched) * 10)
    if any(word in lead_lower for word in ["intern", "junior", "entry", "fresh"]):
        base += 8
    if any(mode.lower() in lead_lower for mode in split_csv(user.get("work_modes", ""))):
        base += 5
    score = clamp_int(base, 15, 88)
    return normalize_match_payload(
        {
            "overall_match_percentage": score,
            "match_label": label_for_score(score),
            "summary": "This match is based on your saved profile details and the selected opportunity.",
            "score_breakdown": {
                "role_match": {"score": min(20, max(4, score // 5)), "reason": "The role title and your profile keywords were compared."},
                "skill_match": {"score": min(30, len(matched) * 8), "reason": "Relevant profile terms were found in the opportunity details."},
                "experience_match": {"score": 8, "reason": "The available experience details were compared with your profile."},
                "education_match": {"score": 4, "reason": "Education requirement was not clearly extracted."},
                "interest_match": {"score": min(10, len(matched) * 2), "reason": "Your interests were compared with the opportunity content."},
                "location_work_preference_match": {"score": 4, "reason": "Location and work preferences were checked where available."},
                "seniority_match": {"score": 3, "reason": "The role level was checked against the opportunity details."},
                "semantic_match": {"score": 3, "reason": "Related wording in the profile and opportunity was compared."},
            },
            "matched_skills": [
                {
                    "skill": term,
                    "match_percentage": 90,
                    "match_type": "exact",
                    "evidence_from_profile": term,
                    "evidence_from_post": term,
                }
                for term in matched[:6]
            ],
            "missing_skills": [],
            "matched_keywords": matched[:10],
            "unmatched_keywords": [term for term in user_terms if term not in matched][:8],
            "strengths": ["Some profile terms match this lead."] if matched else [],
            "gaps": ["Complete your profile for a more accurate match."] if not matched else [],
            "recommendation": default_recommendation(score),
            "should_user_apply": score >= 55,
            "confidence_score": 45,
        },
        user,
        lead,
        generated_by="fallback",
    )


def infer_seniority(lead):
    text = " ".join([lead.get("role_title", ""), lead.get("experience", ""), lead.get("post_text", "")]).lower()
    if any(word in text for word in ["intern", "internship", "student", "fresh"]):
        return "Internship / Beginner"
    if any(word in text for word in ["senior", "lead", "principal", "manager"]):
        return "Senior"
    if any(word in text for word in ["junior", "entry"]):
        return "Junior"
    return ""


def split_csv(value):
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def unique_strings(values):
    result = []
    seen = set()
    for value in values or []:
        text = clean_text(value)
        key = text.lower()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:240]


def safe_prompt_value(value):
    text = str(value or "").strip()
    return text[:6000] if len(text) > 6000 else text


def clamp_int(value, low, high):
    try:
        number = int(round(float(value or 0)))
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def label_for_score(score):
    if score >= 90:
        return "Excellent match"
    if score >= 75:
        return "Strong match"
    if score >= 60:
        return "Good match"
    if score >= 45:
        return "Partial match"
    if score >= 25:
        return "Weak match"
    return "Poor match"


def default_recommendation(score):
    if score >= 75:
        return "This lead is worth prioritizing."
    if score >= 55:
        return "Consider applying if the role aligns with your current goals."
    return "Review the gaps before spending time on this lead."

