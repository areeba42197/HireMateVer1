"""AI keyword generation for HireMate LinkedIn discovery.

This service builds a complete profile prompt for the configured AI provider,
validates the JSON response, caches it in SQLite, and exposes small rotating
keyword queues for LinkedIn job and post collectors. If the API is unavailable,
a deterministic profile-only fallback keeps the product usable.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib import request, error

from core.config import (
    AI_KEYWORD_CACHE_HOURS,
    AI_PROVIDER,
    GROQ_API_KEY,
    GROQ_CHAT_COMPLETIONS_URL,
    GROQ_KEY_FILE,
    GROQ_MODEL,
    XAI_API_KEY,
    XAI_CHAT_COMPLETIONS_URL,
    XAI_KEY_FILE,
    XAI_MODEL,
)
from core.database import db


HIREMATE_AI_PROMPT = """You are HireMate AI — an advanced AI-powered LinkedIn job and hiring-post matching engine.

Your task is to deeply analyze a user's profile and generate highly accurate, intelligent, LinkedIn-optimized keywords, search queries, semantic expansions, and matching signals to help the user discover the most relevant jobs, internships, freelance opportunities, research opportunities, startup roles, and hiring posts.

Your objective is NOT to generate simple keyword lists only.

Your objective is to:

* Understand the user's career identity
* Detect the user's experience level
* Infer hidden interests and job intent
* Expand skills semantically
* Generate recruiter-style search phrases
* Predict suitable job roles
* Generate advanced LinkedIn search queries
* Detect matching industries
* Generate beginner-friendly roles if experience is weak
* Generate semantic and intent-based keywords
* Generate negative filters to avoid irrelevant jobs
* Maximize relevant job and post discovery on LinkedIn

You must intelligently analyze ALL profile sections together.

---

## PROFILE WEIGHTING SYSTEM

Use the following importance percentages when generating keywords and matching signals:

1. Professional Title -> 22%
2. Skills -> 20%
3. Experience / Projects -> 15%
4. About Section -> 12%
5. Education -> 5%
6. Interests -> 15%
7. Location + Work Preference -> 4%

Total = 100%

---

## HOW EACH PROFILE FIELD MUST BE ANALYZED

==================================================
A. PROFESSIONAL TITLE ANALYSIS (22%)
====================================

The Professional Title is one of the strongest career signals.

Example:
"AI Engineer | Data Science | LLM | NLP"

Use the title to detect:

* Main career field
* Career specialization
* Industry category
* Suitable job roles
* Technical direction
* Career path
* Seniority level
* Search direction
* Recruiter terminology

Generate:

* Primary job roles
* Secondary job roles
* Career identity keywords
* Recruiter-facing keywords

Example generated roles:
[
"AI Engineer",
"Machine Learning Engineer",
"NLP Engineer",
"LLM Engineer",
"Data Scientist",
"Generative AI Engineer"
]

The title must strongly influence:

* primary_roles
* industry_keywords
* final_ranked_keywords
* linkedin_search_queries

==================================================
B. SKILLS ANALYSIS (23%)
========================

Analyze skills in THREE separate ways.

---

1. Exact Skill Extraction

---

Extract exact skills directly from profile.

Example:
[
"NLP",
"LLM",
"Data Science",
"Python"
]

---

2. Semantic Skill Expansion

---

Expand every skill into related LinkedIn and recruiter terminology.

Example:
{
"LLM": [
"Generative AI",
"Prompt Engineering",
"RAG",
"LangChain",
"GPT",
"Transformers",

],

"NLP": [
"Text Classification",
"BERT",
"Tokenization",
"Sentiment Analysis",
"Named Entity Recognition"
],

"Python": [
"Pandas",
"NumPy",
"FastAPI",
"Flask",
"Automation",
"Backend Development"
],

"Data Science": [
"Machine Learning",
"Data Analysis",
"Visualization",
"Predictive Modeling",
"Statistics"
]
}

---

3. Tool and Technology Inference

---

Infer relevant tools and frameworks from skills.

Example:
[
"PyTorch",
"TensorFlow",
"Hugging Face",
"Scikit-learn",
"LangChain",
"Vector Database",
"ChromaDB",
"FAISS"
]

Skills should generate:

* direct keywords
* semantic keywords
* recruiter terminology
* technology stack keywords
* framework keywords
* AI tool keywords

==================================================
C. EXPERIENCE / PROJECT ANALYSIS (18%)
======================================

Experience is extremely important.

Analyze:

* internships
* projects
* academic projects
* freelance work
* GitHub projects
* final year projects
* research work
* hackathons
* startup work
* volunteer work

If experience is EMPTY:
Infer beginner-level opportunities and entry-level job intent.

Generate:
[
"AI Intern",
"Machine Learning Intern",
"Junior AI Engineer",
"Entry Level Data Scientist",
"NLP Intern",
"AI Trainee",
"Graduate AI Engineer"
]

If experience EXISTS:
Extract:

* tools used
* technologies used
* project domain
* technical depth
* industry relevance
* business domain
* AI specialization
* problem solved
* practical capabilities

Example:
"Built chatbot using LangChain and Ollama"

Generate:
[
"LLM Application Developer",
"RAG Developer",
"Chatbot Developer",
"Conversational AI Engineer",
"LangChain Developer",
"AI Assistant Developer"
]

Experience should influence:

* experience_level_keywords
* tools_and_libraries
* primary_roles
* secondary_roles
* final_ranked_keywords

==================================================
D. ABOUT SECTION ANALYSIS (13%)
===============================

The About section helps detect:

* career goals
* passion areas
* preferred field
* domain interest
* learning direction
* long-term career intent
* AI specialization
* motivation

Example:
"Interested in building AI assistants using LLMs and NLP."

Generate:
[
"AI Assistant Developer",
"Generative AI Intern",
"LLM Application Engineer",
"NLP Research Intern",
"Conversational AI Developer"
]

If About section is EMPTY:
Do NOT invent fake information.
Instead:

* rely more on title and skills
* reduce confidence score slightly
* recommend user to complete About section

The About section should influence:

* linkedin_search_queries
* interest_based_search_queries
* semantic_keywords
* career_direction_keywords

==================================================
E. EDUCATION ANALYSIS (8%)
==========================

Education helps determine:

* student level
* beginner level
* fresh graduate level
* internship eligibility
* academic background
* research suitability
* entry-level suitability

Example:
"BS Software Engineering"

Generate:
[
"Software Engineering Intern",
"AI Intern",
"Machine Learning Trainee",
"Graduate AI Engineer",
"Junior Python Developer"
]

Education should influence:

* experience_level_keywords
* internship-related keywords
* junior-role keywords
* graduate-role keywords

If education is missing:
Do not assume a degree.

==================================================
F. INTEREST ANALYSIS (10%)
==========================

Analyze interests separately from technical skills.

Interests represent:

* preferred opportunity types
* preferred domains
* preferred work style
* preferred industries
* startup preference
* research preference
* freelancing preference
* remote preference
* career direction

Example interests:
[
"Remote",
"AI Research",
"NLP",
"Startups",
"Freelance",
"Data Science"
]

Generate:
[
"Remote AI Internship",
"NLP Research Role",
"Startup AI Engineer",
"Freelance Python Developer",
"Remote Data Science Job"
]

Generate:

* intent-based keywords
* preference-based queries
* domain-interest keywords
* opportunity-type keywords

Do NOT treat interests as direct technical skills unless clearly relevant.

==================================================
G. LOCATION + WORK PREFERENCE ANALYSIS (6%)
===========================================

Use location and work preferences mainly for filtering and ranking.

Example:
Location:
"Islamabad"

Work Preferences:
[
"Remote",
"Hybrid",
"Onsite"
]

Generate:
[
"AI Engineer Islamabad",
"Remote NLP Intern",
"Hybrid Data Science Job Pakistan",
"LLM Engineer Remote"
]

Location and work preferences should:

* improve local relevance
* improve remote matching
* improve recruiter-post matching
* improve ranking quality

Do NOT let location dominate the career direction.

---

## KEYWORD GENERATION REQUIREMENTS

Generate ALL of the following categories.

Do NOT skip any category.

{
"profile_summary": {
"career_domain": "",
"experience_level": "",
"main_specialization": "",
"job_search_intent": "",
"confidence_score": 0
},

"keyword_weights_used": {
"professional_title": 22,
"skills": 23,
"experience_projects": 18,
"about": 13,
"education": 8,
"interests": 10,
"location_work_preference": 6
},

"primary_roles": [],

"secondary_roles": [],

"core_skills": [],

"expanded_skills": [],

"tools_and_libraries": [],

"industry_keywords": [],

"experience_level_keywords": [],

"location_keywords": [],

"work_preference_keywords": [],

"interest_based_keywords": [],

"interest_based_search_queries": [],

"linkedin_post_keywords": [],

"linkedin_search_queries": [],

"semantic_keywords": [],

"career_direction_keywords": [],

"recruiter_style_keywords": [],

"negative_keywords": [],

"final_ranked_keywords": [
{
"keyword": "",
"category": "",
"score": 0
}
]
}

---

## LINKEDIN SEARCH QUERY GENERATION

Generate advanced LinkedIn search queries.

Queries must include combinations of:

* role
* skill
* experience level
* location
* work preference
* recruiter wording
* opportunity type

Examples:
[
"Remote NLP Internship",
"Junior LLM Engineer Islamabad",
"Hiring Generative AI Intern",
"Machine Learning Intern Pakistan",
"AI Research Internship Remote",
"Prompt Engineering Internship",
"Entry Level Data Scientist Remote",
"LangChain Developer Internship"
]

---

## LINKEDIN POST MATCHING LOGIC

The generated keywords will later be used to:

* search LinkedIn jobs
* search recruiter posts
* rank hiring posts
* filter irrelevant opportunities
* detect hidden opportunities

Prioritize:

* recruiter terminology
* hiring phrases
* startup language
* internship language
* AI-related search patterns

Examples:
[
"hiring AI intern",
"looking for NLP engineer",
"junior machine learning engineer needed",
"remote AI opportunity",
"LLM internship",
"generative AI hiring"
]

---

## NEGATIVE KEYWORD GENERATION

Generate negative keywords to avoid irrelevant jobs.

Examples:
[
"Senior",
"Lead",
"Manager",
"Director",
"10+ years",
"Principal Engineer",
"Blockchain",
"Sales"
]

Negative keywords should filter:

* overqualified jobs
* unrelated industries
* unwanted roles
* mismatched seniority levels

---

## IMPORTANT RULES

1. Never generate generic keyword lists only.
2. Use semantic understanding.
3. Infer hidden relevant keywords intelligently.
4. Avoid irrelevant keywords.
5. Avoid senior-level roles for beginners.
6. Prioritize internships and junior roles for students.
7. Use recruiter terminology commonly found on LinkedIn.
8. Generate both exact and semantic keywords.
9. Use profile context holistically.
10. Output ONLY valid JSON.
11. Do NOT include explanations outside JSON.
12. Every keyword must have a purpose.
13. Optimize for maximum LinkedIn hiring-post discovery.
14. Optimize for AI-powered ranking systems.
15. Prioritize realistic and achievable opportunities.
16. If a field has spelling mistakes, infer the closest intended term only when the profile context clearly supports it.
"""


REQUIRED_LIST_FIELDS = [
    "primary_roles",
    "secondary_roles",
    "core_skills",
    "expanded_skills",
    "tools_and_libraries",
    "industry_keywords",
    "experience_level_keywords",
    "location_keywords",
    "work_preference_keywords",
    "interest_based_keywords",
    "interest_based_search_queries",
    "linkedin_post_keywords",
    "linkedin_search_queries",
    "semantic_keywords",
    "career_direction_keywords",
    "recruiter_style_keywords",
    "negative_keywords",
]


def profile_data(user):
    """Map HireMate user fields to the profile block sent to the AI provider."""
    name = " ".join(part for part in [user.get("first_name", ""), user.get("last_name", "")] if part).strip()
    return {
        "name": name,
        "title": user.get("headline", ""),
        "location": user.get("location", ""),
        "about": user.get("about", ""),
        "skills": user.get("skills", ""),
        "interests": user.get("interests", ""),
        "experience": user.get("experience_detail", "") or user.get("experience_level", ""),
        "education": user.get("education", ""),
        "work_preferences": user.get("work_modes", "") or user.get("preferred_locations", ""),
    }


def profile_prompt(user):
    data = profile_data(user)
    return (
        HIREMATE_AI_PROMPT
        + "\n\n## PROFILE DATA\n\n"
        + f"Name:\n{data['name']}\n\n"
        + f"Professional Title:\n{data['title']}\n\n"
        + f"Location:\n{data['location']}\n\n"
        + f"About:\n{data['about']}\n\n"
        + f"Skills:\n{data['skills']}\n\n"
        + f"Interests:\n{data['interests']}\n\n"
        + f"Experience:\n{data['experience']}\n\n"
        + f"Education:\n{data['education']}\n\n"
        + f"Work Preferences:\n{data['work_preferences']}\n"
    )


def profile_hash(user):
    raw = json.dumps(profile_data(user), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def split_csv(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def read_key_file(path):
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def get_ai_provider_config():
    """Return provider settings without exposing secrets to the frontend."""
    groq_key = (GROQ_API_KEY or read_key_file(GROQ_KEY_FILE)).strip()
    xai_key = (XAI_API_KEY or read_key_file(XAI_KEY_FILE)).strip()

    # Many students paste a Groq key into the old xAI file. Auto-detect it so
    # the app continues working while keeping a clean groq_api_key.txt option.
    if not groq_key and xai_key.startswith("gsk_"):
        groq_key = xai_key
        xai_key = ""

    if AI_PROVIDER == "groq" or (AI_PROVIDER == "auto" and groq_key):
        return {
            "name": "groq",
            "api_key": groq_key,
            "model": GROQ_MODEL,
            "url": GROQ_CHAT_COMPLETIONS_URL,
        }
    if AI_PROVIDER in ("xai", "grok") or (AI_PROVIDER == "auto" and xai_key):
        return {
            "name": "grok",
            "api_key": xai_key,
            "model": XAI_MODEL,
            "url": XAI_CHAT_COMPLETIONS_URL,
        }
    return {"name": AI_PROVIDER or "auto", "api_key": "", "model": "", "url": ""}


def keyword_profile_for_user(user, force_refresh=False):
    """Return cached or freshly generated AI keyword JSON for a user."""
    digest = profile_hash(user)
    user_id = user.get("id")
    if not force_refresh and user_id:
        cached = load_cached_keyword_profile(user_id, digest)
        if cached:
            return cached

    provider = get_ai_provider_config()
    if provider["api_key"]:
        try:
            generated = call_ai_keyword_profile(profile_prompt(user), provider)
            profile = normalize_keyword_profile(generated, user, generated_by=provider["name"])
            save_keyword_profile(user_id, digest, profile)
            return profile
        except Exception as exc:
            fallback = fallback_keyword_profile(user)
            fallback["generation_error"] = str(exc)
            save_keyword_profile(user_id, digest, fallback)
            return fallback

    fallback = fallback_keyword_profile(user)
    fallback["generation_error"] = "AI API key is not configured."
    save_keyword_profile(user_id, digest, fallback)
    return fallback


def load_cached_keyword_profile(user_id, digest):
    with db() as conn:
        row = conn.execute(
            "SELECT response_json, updated_at FROM ai_keyword_profiles WHERE user_id=? AND profile_hash=?",
            (user_id, digest),
        ).fetchone()
        if not row:
            return None
        try:
            updated = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
        except ValueError:
            updated = datetime.now(timezone.utc) - timedelta(days=99)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - updated > timedelta(hours=AI_KEYWORD_CACHE_HOURS):
            return None
        return json.loads(row["response_json"])


def save_keyword_profile(user_id, digest, profile):
    if not user_id:
        return
    with db() as conn:
        conn.execute(
            """
            INSERT INTO ai_keyword_profiles(user_id, profile_hash, response_json, generated_by, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
              profile_hash=excluded.profile_hash,
              response_json=excluded.response_json,
              generated_by=excluded.generated_by,
              updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, digest, json.dumps(profile, ensure_ascii=False), profile.get("generated_by", "fallback")),
        )


def call_ai_keyword_profile(prompt, provider):
    payload = {
        "model": provider["model"],
        "stream": False,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "Return only valid JSON. Do not wrap it in markdown."},
            {"role": "user", "content": prompt},
        ],
    }
    req = request.Request(
        provider["url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "HireMate-FYP/1.0",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"{provider['name']} request failed: {exc.code} {detail[:240]}") from exc
    body = json.loads(raw)
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    return parse_json_content(content)


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
        raise


def normalize_keyword_profile(profile, user, generated_by="grok"):
    profile = profile if isinstance(profile, dict) else {}
    profile.setdefault("profile_summary", {})
    profile.setdefault("keyword_weights_used", {
        "professional_title": 22,
        "skills": 23,
        "experience_projects": 18,
        "about": 13,
        "education": 8,
        "interests": 10,
        "location_work_preference": 6,
    })
    for field in REQUIRED_LIST_FIELDS:
        profile[field] = unique_clean_strings(profile.get(field, []))[:40]
    profile["final_ranked_keywords"] = normalize_ranked_keywords(profile.get("final_ranked_keywords", []))
    if not profile["linkedin_search_queries"]:
        profile["linkedin_search_queries"] = fallback_keyword_profile(user)["linkedin_search_queries"]
    if not profile["linkedin_post_keywords"]:
        profile["linkedin_post_keywords"] = fallback_keyword_profile(user)["linkedin_post_keywords"]
    profile["generated_by"] = generated_by
    profile["generated_at"] = datetime.now(timezone.utc).isoformat()
    return profile


def normalize_ranked_keywords(items):
    normalized = []
    if isinstance(items, list):
        for index, item in enumerate(items):
            if isinstance(item, dict):
                keyword = clean_keyword(item.get("keyword", ""))
                if keyword:
                    category = clean_keyword(item.get("category", "general")) or "general"
                    score = int(float(item.get("score", 0) or 0))
                    if score <= 0:
                        score = inferred_rank_score(category, index)
                    normalized.append(
                        {
                            "keyword": keyword,
                            "category": category,
                            "score": max(1, min(100, score)),
                        }
                    )
            else:
                keyword = clean_keyword(str(item))
                if keyword:
                    normalized.append({"keyword": keyword, "category": "general", "score": 50})
    deduped = {}
    for item in normalized:
        key = item["keyword"].lower()
        if key not in deduped or item["score"] > deduped[key]["score"]:
            deduped[key] = item
    return sorted(deduped.values(), key=lambda value: value["score"], reverse=True)[:60]


def inferred_rank_score(category, index):
    """Provide stable ranking when an AI provider returns placeholder scores."""
    lowered = (category or "").lower()
    if "primary" in lowered or "role" in lowered:
        base = 95
    elif "skill" in lowered or "tool" in lowered:
        base = 88
    elif "search" in lowered or "post" in lowered or "recruiter" in lowered:
        base = 82
    elif "location" in lowered or "preference" in lowered:
        base = 72
    else:
        base = 68
    return max(45, base - min(index, 20))


def fallback_keyword_profile(user):
    """Create a minimal keyword profile only from user-provided text.

    This fallback is used only when Grok is unavailable. It does not invent
    domains, tools, seniority, or role families. It simply combines the user's
    own profile words with neutral LinkedIn search intent phrases.
    """
    data = profile_data(user)
    skills = split_csv(data["skills"])
    interests = split_csv(data["interests"])
    roles = profile_terms(user.get("target_roles", "")) or profile_terms(data["title"])
    location_terms = profile_terms(data["location"])
    work_modes = split_csv(data["work_preferences"])
    experience_terms = profile_terms(data["experience"])[:8]
    education_terms = profile_terms(data["education"])[:8]

    primary = unique_clean_strings(roles[:8])
    secondary = []
    for role in primary:
        secondary.extend([
            f"{role} opportunity",
            f"{role} hiring",
            f"{role} internship",
        ])

    post_keywords = []
    search_queries = []
    for role in primary:
        post_keywords.extend([f"hiring {role}", f"looking for {role}", f"{role} needed", f"{role} opportunity"])
        search_queries.extend([f"{role} hiring", f"{role} internship", f"{role} opportunity"])
        for location in location_terms[:2]:
            search_queries.append(f"{role} {location}")
        for mode in work_modes[:3]:
            search_queries.append(f"{mode} {role}")
    for skill in skills[:10]:
        post_keywords.extend([f"{skill} hiring", f"{skill} internship", f"{skill} opportunity"])
        search_queries.extend([f"{skill} job", f"{skill} internship", f"{skill} opportunity"])
        for location in location_terms[:2]:
            search_queries.append(f"{skill} {location}")
    for interest in interests[:6]:
        search_queries.append(f"{interest} opportunity")

    ranked = []
    for score, group, category in [
        (95, primary, "primary_role"),
        (84, skills, "skill"),
        (78, search_queries, "linkedin_search"),
        (72, post_keywords, "linkedin_post"),
    ]:
        for keyword in group:
            ranked.append({"keyword": clean_keyword(keyword), "category": category, "score": score})

    return normalize_keyword_profile(
        {
            "profile_summary": {
                "career_domain": primary[0] if primary else "",
                "experience_level": user.get("experience_level") or "",
                "main_specialization": ", ".join(skills[:3]),
                "job_search_intent": "Find relevant jobs, internships, freelance roles, and hiring posts",
                "confidence_score": 65 if data["title"] or skills else 45,
            },
            "primary_roles": primary,
            "secondary_roles": secondary,
            "core_skills": skills,
            "expanded_skills": skills,
            "tools_and_libraries": skills,
            "industry_keywords": unique_clean_strings(interests + primary),
            "experience_level_keywords": unique_clean_strings(experience_terms + education_terms),
            "location_keywords": unique_clean_strings(location_terms),
            "work_preference_keywords": unique_clean_strings(work_modes + [f"{mode} job" for mode in work_modes]),
            "interest_based_keywords": unique_clean_strings(interests),
            "interest_based_search_queries": unique_clean_strings(search_queries),
            "linkedin_post_keywords": unique_clean_strings(post_keywords),
            "linkedin_search_queries": unique_clean_strings(search_queries),
            "semantic_keywords": unique_clean_strings(skills + interests + primary + secondary + experience_terms + education_terms),
            "career_direction_keywords": unique_clean_strings(primary + secondary),
            "recruiter_style_keywords": unique_clean_strings(post_keywords),
            "negative_keywords": [],
            "final_ranked_keywords": ranked,
        },
        user,
        generated_by="fallback",
    )


def profile_terms(value):
    """Split user-entered phrases without adding external career assumptions."""
    terms = split_csv(value)
    if terms:
        return unique_clean_strings(terms)
    value = clean_keyword(value)
    return [value] if value else []


def keyword_queue(user, purpose="jobs", limit=40):
    """Return a high-quality rotated list of keywords for jobs or post searches."""
    profile = keyword_profile_for_user(user)
    if purpose == "posts":
        fields = [
            "linkedin_post_keywords",
            "recruiter_style_keywords",
            "interest_based_search_queries",
            "linkedin_search_queries",
            "primary_roles",
            "secondary_roles",
        ]
    else:
        fields = [
            "linkedin_search_queries",
            "primary_roles",
            "secondary_roles",
            "experience_level_keywords",
            "interest_based_search_queries",
            "final_ranked_keywords",
        ]
    values = []
    for field in fields:
        raw = profile.get(field, [])
        if field == "final_ranked_keywords":
            values.extend([item.get("keyword", "") for item in raw if isinstance(item, dict)])
        else:
            values.extend(raw if isinstance(raw, list) else [])
    return unique_clean_strings(values)[:limit]


def unique_clean_strings(values):
    result = []
    for value in values or []:
        keyword = clean_keyword(value)
        if keyword and keyword.lower() not in [item.lower() for item in result]:
            result.append(keyword)
    return result


def clean_keyword(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    value = value.strip(" -:;,.")
    return value[:120]
