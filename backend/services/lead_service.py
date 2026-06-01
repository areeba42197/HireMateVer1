import json
import hashlib
import re
import time as monotonic_time
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone

from core.database import db, rows_to_dicts
from services.post_analysis_service import analyze_post_text, is_generic_author, is_generic_role


HIRING_TERMS = {
    "hiring",
    "we're hiring",
    "we are hiring",
    "job",
    "opening",
    "position",
    "role",
    "internship",
    "remote",
    "developer",
    "engineer",
    "apply",
    "vacancy",
}

HIRING_INTENT_TERMS = {
    "hiring",
    "we're hiring",
    "we are hiring",
    "looking for",
    "seeking",
    "need a",
    "need an",
    "opening",
    "open role",
    "position",
    "vacancy",
    "apply",
    "job opportunity",
    "internship opportunity",
}

TECH_DOMAIN_TERMS = {
    "ai", "artificial intelligence", "machine learning", "ml", "data science",
    "software", "developer", "engineer", "programming", "python", "javascript",
    "typescript", "react", "node", "backend", "frontend", "full stack", "cloud",
    "devops", "cyber", "qa", "database", "api", "django", "flask", "next.js",
}

SKILL_TERMS = {
    "react": "React.js",
    "react.js": "React.js",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "python": "Python",
    "django": "Django",
    "node": "Node.js",
    "node.js": "Node.js",
    "html": "HTML",
    "css": "CSS",
    "ai": "AI",
    "ml": "Machine Learning",
}

LEAD_LIST_COLUMNS = """
id, user_id, source, lead_kind, source_post_id, company, role_title, author_name, author_title,
substr(post_text, 1, 900) AS post_text, post_url, location, work_type, employment_type, experience,
salary, likes, comments, reposts, posted_at, score, temperature, status, tags,
comments_json, reactions_json, created_at
"""

LEAD_CACHE_TTL_SECONDS = 180
_lead_list_cache = {}
_lead_detail_cache = {}
_dashboard_cache = {}

DOMAIN_TERM_ALIASES = {
    "pharmasist": "pharmacist",
    "pharmacyst": "pharmacist",
    "teching": "teaching",
}


def _lead_cache_now():
    return monotonic_time.monotonic()


def _lead_cache_get(cache, key):
    cached = cache.get(key)
    if not cached:
        return None
    created_at, value = cached
    if _lead_cache_now() - created_at > LEAD_CACHE_TTL_SECONDS:
        cache.pop(key, None)
        return None
    return deepcopy(value)


def _lead_cache_set(cache, key, value):
    cache[key] = (_lead_cache_now(), deepcopy(value))
    if len(cache) > 300:
        oldest_key = min(cache, key=lambda item: cache[item][0])
        cache.pop(oldest_key, None)


def clear_lead_cache(user_id=None, lead_id=None):
    if user_id is None:
        _lead_list_cache.clear()
        _lead_detail_cache.clear()
        _dashboard_cache.clear()
        return
    user_key = str(user_id)
    for key in list(_lead_list_cache.keys()):
        if key[0] == user_key:
            _lead_list_cache.pop(key, None)
    for key in list(_lead_detail_cache.keys()):
        if key[0] == user_key and (lead_id is None or key[1] == str(lead_id)):
            _lead_detail_cache.pop(key, None)
    _dashboard_cache.pop(user_key, None)


def split_csv(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def classify_temperature(score):
    if score >= 75:
        return "hot"
    if score >= 45:
        return "warm"
    return "cold"


def sync_cached_match_temperatures(conn, user_id):
    """Align dashboard/list categories with saved AI profile-match scores.

    Listing pages should not call the AI for every lead because that would slow
    down the product and waste API quota. Instead, whenever an AI match has
    already been generated, the cached percentage becomes the lead score used
    by Hot/Warm/Cold filters and counts.
    """
    rows = conn.execute(
        """
        SELECT m.lead_id, m.response_json
        FROM ai_profile_matches m
        WHERE m.user_id=?
          AND NOT EXISTS (
            SELECT 1 FROM ai_profile_matches newer
            WHERE newer.user_id=m.user_id
              AND newer.lead_id=m.lead_id
              AND datetime(newer.updated_at) > datetime(m.updated_at)
          )
        """,
        (user_id,),
    ).fetchall()
    updates = []
    for row in rows:
        try:
            payload = json.loads(row["response_json"] or "{}")
        except json.JSONDecodeError:
            continue
        score = max(0, min(100, int(float(payload.get("overall_match_percentage", 0) or 0))))
        updates.append((int(row["lead_id"]), score, classify_temperature(score)))
    if not updates:
        return
    score_case = " ".join(["WHEN ? THEN ?"] * len(updates))
    temperature_case = " ".join(["WHEN ? THEN ?"] * len(updates))
    ids = [lead_id for lead_id, _, _ in updates]
    params = []
    for lead_id, score, _ in updates:
        params.extend([lead_id, score])
    for lead_id, _, temperature in updates:
        params.extend([lead_id, temperature])
    params.append(user_id)
    params.extend(ids)
    conn.execute(
        f"""
        UPDATE leads
        SET score=CASE id {score_case} ELSE score END,
            temperature=CASE id {temperature_case} ELSE temperature END
        WHERE user_id=? AND id IN ({",".join(["?"] * len(ids))})
        """,
        params,
    )


def extract_role(text):
    patterns = [
        r"(?:hiring|looking for|need|seeking)\s+(?:a|an)?\s*([A-Za-z0-9 /\-.+#]+?(?:developer|engineer|intern|assistant|designer|specialist|manager))",
        r"([A-Za-z0-9 /\-.+#]+?(?:developer|engineer|intern|assistant|designer|specialist|manager))\s+(?:needed|required|role|position)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(1).strip(" -.!").title()
    return "Hiring Opportunity"


def extract_tags(text):
    found = []
    lower = text.lower()
    for key, label in SKILL_TERMS.items():
        if contains_domain_term(lower, [key]) and label not in found:
            found.append(label)
    return found[:8]


def profile_text(user):
    return " ".join(
        str(user.get(key, "") or "")
        for key in (
            "headline", "about", "skills", "interests", "target_roles",
            "education", "experience_detail", "experience_level",
            "work_modes", "preferred_locations", "location"
        )
    ).lower()


def contains_domain_term(text, terms):
    haystack = canonical_part(text)
    for term in terms:
        needle = canonical_part(term)
        if not needle:
            continue
        if needle in {"ai", "ml"}:
            pattern = rf"(?<![a-z0-9.]){re.escape(needle)}(?![a-z0-9.])"
        else:
            pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
        if re.search(pattern, haystack):
            return True
    return False


def profile_is_technical(user):
    return contains_domain_term(profile_text(user), TECH_DOMAIN_TERMS)


def lead_is_technical(lead):
    text = " ".join(
        str(lead.get(key, "") or "")
        for key in ("company", "role_title", "post_text", "tags")
    ).lower()
    return contains_domain_term(text, TECH_DOMAIN_TERMS)


def profile_domain_terms(user):
    values = []
    for key in ("target_roles", "skills", "headline", "about", "education", "experience_detail"):
        values.extend(split_csv(user.get(key, "")))
        values.extend(re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{2,}", str(user.get(key, "") or "")))
    blocked = {
        "and", "the", "for", "with", "from", "student", "graduate", "fresh", "remote",
        "full", "time", "part", "job", "jobs", "role", "roles", "internship", "hiring",
        "hybrid", "onsite", "on-site", "years", "year", "experience", "level", "junior",
        "senior", "entry", "preferred", "location", "work", "mode", "islamabad",
        "pakistan", "united", "states", "state", "city", "onsite", "management",
        "manager", "system", "systems", "operation", "operations", "support",
        "handling", "module", "workflow", "inventory", "billing", "registration",
        "electronic", "records", "processing"
    }
    clean = []
    for value in values:
        term = canonical_part(value)
        for typo, replacement in DOMAIN_TERM_ALIASES.items():
            term = re.sub(rf"\b{re.escape(typo)}\b", replacement, term)
        if len(term) < 3 or term in blocked:
            continue
        clean.append(term)
    return list(dict.fromkeys(clean))[:40]


def row_matches_current_profile(row, user):
    if not user:
        return True
    try:
        return should_import_lead(dict(row), user)
    except Exception:
        return False


def has_hiring_intent(text):
    lower = (text or "").lower()
    return any(term in lower for term in HIRING_INTENT_TERMS)


def matches_profile_domain(lead, user):
    combined = canonical_part(
        " ".join(
            str(lead.get(key, "") or "")
            for key in ("company", "role_title", "post_text", "tags", "author_title")
        )
    )
    terms = profile_domain_terms(user)
    if not terms:
        return True
    return any(term in combined for term in terms)


def should_import_lead(lead, user):
    if lead.get("lead_kind") == "post" and not has_hiring_intent(lead.get("post_text", "")):
        return False
    user_technical = profile_is_technical(user)
    lead_technical = lead_is_technical(lead)
    if lead_technical and not user_technical:
        return False
    if user_technical and not lead_technical and not matches_profile_domain(lead, user):
        return False
    return matches_profile_domain(lead, user)


def score_post(text, skills_csv, likes=0, comments=0, posted_at=None):
    lower = text.lower()
    hiring_score = 25 if any(term in lower for term in HIRING_TERMS) else 0
    skills = split_csv(skills_csv)
    matched = [skill for skill in skills if skill.lower() in lower]
    skill_score = min(45, len(matched) * 12)
    engagement_score = min(15, int(likes or 0) // 8 + int(comments or 0) // 3)
    recency_score = 10
    if posted_at:
        try:
            dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            recency_score = 15 if age_hours <= 6 else 10 if age_hours <= 48 else 4
        except ValueError:
            recency_score = 8
    score = min(100, hiring_score + skill_score + engagement_score + recency_score)
    return score, matched


def normalize_post(post, user):
    text = post.get("post_text") or post.get("text") or ""
    analysis = analyze_post_text(text, post.get("author_name") or post.get("company") or "", post.get("role_title") or "")
    company = post.get("company") or post.get("author_company") or analysis["company"] or infer_company(text)
    if is_generic_author(company):
        company = analysis["company"] or infer_company(text)
    role_title = post.get("role_title") or analysis["role_title"] or extract_role(text)
    if is_generic_role(role_title):
        role_title = analysis["role_title"] or extract_role(text)
    tags = post.get("tags") or analysis["tags"] or extract_tags(text)
    if isinstance(tags, str):
        tags = split_csv(tags)
    score, matched = score_post(text, user.get("skills", ""), post.get("likes", 0), post.get("comments", 0), post.get("posted_at"))
    if matched:
        tags = list(dict.fromkeys(tags + matched))
    if analysis.get("action_hint") and analysis["action_hint"] not in tags:
        tags = list(tags) + [analysis["action_hint"]]
    return {
        "source_post_id": post.get("source_post_id") or post.get("id") or stable_post_id(text),
        "lead_kind": post.get("lead_kind", "post"),
        "company": company,
        "role_title": role_title,
        "author_name": post.get("author_name", ""),
        "author_title": post.get("author_title", ""),
        "post_text": text,
        "post_url": post.get("post_url", ""),
        "location": post.get("location", "" if post.get("lead_kind", "post") == "post" else "Pakistan"),
        "work_type": post.get("work_type", "Remote" if "remote" in text.lower() else ""),
        "employment_type": post.get("employment_type", "Full-time" if "full" in text.lower() else ""),
        "experience": post.get("experience", ""),
        "salary": post.get("salary", ""),
        "likes": int(post.get("likes", 0) or 0),
        "comments": int(post.get("comments", 0) or 0),
        "reposts": int(post.get("reposts", 0) or 0),
        "posted_at": post.get("posted_at") or datetime.now(timezone.utc).isoformat(),
        "score": score,
        "temperature": classify_temperature(score),
        "tags": ", ".join(tags),
        "comments_json": json.dumps(post.get("comment_items", []), ensure_ascii=False),
        "reactions_json": json.dumps(post.get("reaction_items", {}), ensure_ascii=False),
    }


def stable_post_id(text):
    digest = hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()[:16]
    return "manual-" + digest


def infer_company(text):
    match = re.search(r"at\s+([A-Z][A-Za-z0-9 &.\-]+)", text)
    if match:
        return match.group(1).strip()
    return "LinkedIn Post"


def canonical_part(value):
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def canonical_company(value):
    text = canonical_part(value)
    text = re.sub(r"\b(inc|inc\.|ltd|limited|llc|pvt|private|corp|corporation)\b", "", text)
    return canonical_part(text.strip(" ,.-"))


def compact_text_key(value, limit=420):
    text = canonical_part(value)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^\w\s@.+#-]", " ", text)
    text = canonical_part(text)
    return text[:limit]


def is_missing_job_description_text(value):
    text = canonical_part(value)
    return (
        "detailed job description will appear" in text
        or "could not read the full linkedin job description" in text
        or "open the linkedin job page to view the complete description" in text
    )


JOB_ROLE_STOPWORDS = {
    "entry", "level", "entrylevel", "junior", "senior", "sr", "jr", "remote", "fully",
    "virtual", "admin", "administrator", "assistant", "100", "percent", "full", "time",
    "part", "onsite", "hybrid", "intern", "internship", "associate", "specialist",
    "i", "ii", "iii", "iv", "v", "1", "2", "3", "4", "5",
}


def job_role_family(value):
    text = canonical_part(value).replace("%", " percent ")
    text = re.sub(r"[^a-z0-9+#.\s-]", " ", text)
    tokens = []
    for token in re.split(r"[\s/-]+", text):
        token = token.strip(" .,_()[]{}")
        if not token or token in JOB_ROLE_STOPWORDS:
            continue
        tokens.append(token)
    return " ".join(dict.fromkeys(tokens[:6]))


def lead_quality(row):
    text = row["post_text"] if hasattr(row, "keys") else row.get("post_text", "")
    comments = int((row["comments"] if hasattr(row, "keys") else row.get("comments", 0)) or 0)
    post_url = row["post_url"] if hasattr(row, "keys") else row.get("post_url", "")
    score = 0
    if not is_missing_job_description_text(text):
        score += 1000
    score += min(len(text or ""), 3000) // 10
    score += min(comments, 500)
    if post_url:
        score += 20
    return score


def lead_display_key(row):
    lead_kind = row["lead_kind"] if hasattr(row, "keys") else row.get("lead_kind", "")
    post_url = row["post_url"] if hasattr(row, "keys") else row.get("post_url", "")
    company = row["company"] if hasattr(row, "keys") else row.get("company", "")
    role = row["role_title"] if hasattr(row, "keys") else row.get("role_title", "")
    location = row["location"] if hasattr(row, "keys") else row.get("location", "")
    text = row["post_text"] if hasattr(row, "keys") else row.get("post_text", "")
    if lead_kind == "post":
        if post_url:
            return f"post:url:{canonical_part(post_url).split('?')[0]}"
        return f"post:text:{compact_text_key(text, 700)}"
    role_family = job_role_family(role)
    company_key = canonical_company(company)
    if company_key and role_family:
        return f"job:family:{company_key}:{role_family}"
    if post_url:
        return f"job:url:{canonical_part(post_url).split('?')[0]}"
    text_key = compact_text_key(text, 700)
    if text_key and not is_missing_job_description_text(text):
        return f"job:text:{canonical_part(role)}:{canonical_part(location)}:{text_key}"
    return f"job:identity:{canonical_company(company)}:{canonical_part(role)}:{canonical_part(location)}"


def find_existing_lead(conn, user_id, lead):
    existing = conn.execute(
        "SELECT * FROM leads WHERE user_id=? AND source_post_id=?",
        (user_id, lead["source_post_id"]),
    ).fetchone()
    if existing:
        return existing
    if lead.get("post_url"):
        existing = conn.execute(
            "SELECT * FROM leads WHERE user_id=? AND lead_kind=? AND lower(trim(post_url))=?",
            (user_id, lead["lead_kind"], canonical_part(lead["post_url"])),
        ).fetchone()
        if existing:
            return existing
    text_key = compact_text_key(lead.get("post_text", ""), 700)
    if lead.get("lead_kind") == "post" and text_key:
        existing = conn.execute(
            """
            SELECT * FROM leads
            WHERE user_id=? AND lead_kind='post'
              AND lower(substr(post_text, 1, 900)) LIKE ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (user_id, "%" + text_key[:180] + "%"),
        ).fetchone()
        if existing and compact_text_key(existing["post_text"], 700) == text_key:
            return existing
    if lead.get("lead_kind") == "job" and text_key and not is_missing_job_description_text(lead.get("post_text", "")):
        existing = conn.execute(
            """
            SELECT * FROM leads
            WHERE user_id=? AND lead_kind='job'
              AND lower(trim(role_title))=?
              AND lower(trim(location))=?
            ORDER BY created_at DESC, id DESC
            LIMIT 8
            """,
            (user_id, canonical_part(lead["role_title"]), canonical_part(lead["location"])),
        ).fetchall()
        for row in existing:
            if compact_text_key(row["post_text"], 700) == text_key:
                return row
    if lead.get("lead_kind") == "job":
        company_key = canonical_part(lead.get("company", ""))
        incoming_family = job_role_family(lead.get("role_title", ""))
        if company_key and incoming_family:
            existing = conn.execute(
                """
                SELECT * FROM leads
                WHERE user_id=? AND lead_kind='job'
                  AND lower(trim(company))=?
                ORDER BY CASE WHEN status='saved' THEN 0 ELSE 1 END, created_at DESC, id DESC
                LIMIT 40
                """,
                (user_id, company_key),
            ).fetchall()
            for row in existing:
                if job_role_family(row["role_title"]) == incoming_family:
                    return row
    # LinkedIn can expose the same job with different tracking/source ids.
    # For website display, same user + kind + company + role is one lead.
    return conn.execute(
        """
        SELECT * FROM leads
        WHERE user_id=?
          AND lead_kind=?
          AND lower(trim(company))=?
          AND lower(trim(role_title))=?
          AND lower(trim(location))=?
        ORDER BY CASE WHEN status='saved' THEN 0 ELSE 1 END, created_at DESC, id DESC
        LIMIT 1
        """,
        (
            user_id,
            lead["lead_kind"],
            canonical_part(lead["company"]),
            canonical_part(lead["role_title"]),
            canonical_part(lead["location"]),
        ),
    ).fetchone()


def refresh_existing_lead(conn, existing_id, lead):
    """Refresh duplicate details without changing discovery time or source id."""
    incoming_has_structure = 1 if "\n" in (lead.get("post_text") or "") else 0
    conn.execute(
        """
        UPDATE leads SET
          company=CASE WHEN lower(coalesce(company, '')) IN ('', 'linkedin post', 'linkedin public post', 'public linkedin post')
                         OR lower(coalesce(company, '')) LIKE 'linkedin %'
                         OR lower(coalesce(company, '')) LIKE '% - linkedin%'
                         OR ? LIKE 'linkedin-public-post-%'
                       THEN ? ELSE company END,
          role_title=CASE WHEN lower(coalesce(role_title, '')) IN ('', 'hiring opportunity', 'linkedin public post', 'public linkedin post')
                       THEN ? ELSE role_title END,
          author_name=CASE WHEN lower(coalesce(author_name, '')) IN ('', 'linkedin post', 'linkedin public post', 'public linkedin post')
                       THEN ? ELSE author_name END,
          author_title=CASE WHEN lower(coalesce(author_title, '')) IN ('', 'linkedin')
                         OR lower(coalesce(author_title, ''))=lower(coalesce(author_name, ''))
                       THEN ? ELSE author_title END,
          post_text=CASE WHEN ? > 0 THEN ?
                         WHEN length(?) > length(coalesce(post_text, '')) THEN ?
                         ELSE post_text END,
          post_url=CASE WHEN coalesce(post_url, '')='' THEN ? ELSE post_url END,
          location=CASE WHEN coalesce(location, '')='' THEN ? ELSE location END,
          posted_at=CASE WHEN ? <> '' THEN ? ELSE posted_at END,
          likes=?,
          comments=?,
          reposts=?,
          score=GREATEST(score, ?),
          temperature=CASE WHEN ? > score THEN ? ELSE temperature END,
          tags=CASE WHEN coalesce(tags, '')='' THEN ? ELSE tags END,
          comments_json=CASE WHEN ? != '[]' THEN ? ELSE comments_json END,
          reactions_json=CASE WHEN ? != '{}' THEN ? ELSE reactions_json END
        WHERE id=?
        """,
        (
            lead["source_post_id"],
            lead["company"],
            lead["role_title"],
            lead["author_name"],
            lead["author_title"],
            incoming_has_structure,
            lead["post_text"],
            lead["post_text"],
            lead["post_text"],
            lead["post_url"],
            lead["location"],
            lead["posted_at"],
            lead["posted_at"],
            lead["likes"],
            lead["comments"],
            lead["reposts"],
            lead["score"],
            lead["score"],
            lead["temperature"],
            lead["tags"],
            lead["comments_json"],
            lead["comments_json"],
            lead["reactions_json"],
            lead["reactions_json"],
            existing_id,
        ),
    )


def import_posts(user_id, posts):
    with db() as conn:
        user = dict(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
        imported = []
        for post in posts:
            lead = normalize_post(post, user)
            if not should_import_lead(lead, user):
                continue
            existing = find_existing_lead(conn, user_id, lead)
            if existing:
                refresh_existing_lead(conn, existing["id"], lead)
                continue
            conn.execute(
                """
                INSERT INTO leads (
                  user_id, lead_kind, source_post_id, company, role_title, author_name, author_title,
                  post_text, post_url, location, work_type, employment_type, experience,
                  salary, likes, comments, reposts, posted_at, score, temperature, tags,
                  comments_json, reactions_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, source_post_id) DO UPDATE SET
                  lead_kind=excluded.lead_kind,
                  company=excluded.company,
                  role_title=excluded.role_title,
                  post_text=excluded.post_text,
                  likes=excluded.likes,
                  comments=excluded.comments,
                  reposts=excluded.reposts,
                  score=excluded.score,
                  temperature=excluded.temperature,
                  tags=excluded.tags,
                  comments_json=excluded.comments_json,
                  reactions_json=excluded.reactions_json
                """,
                (
                    user_id,
                    lead["lead_kind"],
                    lead["source_post_id"],
                    lead["company"],
                    lead["role_title"],
                    lead["author_name"],
                    lead["author_title"],
                    lead["post_text"],
                    lead["post_url"],
                    lead["location"],
                    lead["work_type"],
                    lead["employment_type"],
                    lead["experience"],
                    lead["salary"],
                    lead["likes"],
                    lead["comments"],
                    lead["reposts"],
                    lead["posted_at"],
                    lead["score"],
                    lead["temperature"],
                    lead["tags"],
                    lead["comments_json"],
                    lead["reactions_json"],
                ),
            )
            saved = conn.execute(
                "SELECT * FROM leads WHERE user_id=? AND source_post_id=?",
                (user_id, lead["source_post_id"]),
            ).fetchone()
            if saved:
                imported.append(format_lead(saved))
        conn.execute("INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)", (user_id, "posts_imported", json.dumps({"count": len(imported)})))
        clear_lead_cache(user_id)
        return imported


def list_leads(user_id, temperature=None, search=None, limit=50, offset=0, status=None, kind=None):
    limit = max(1, min(int(limit or 12), 30))
    offset = max(0, int(offset or 0))
    cache_key = (
        str(user_id),
        temperature or "",
        search or "",
        limit,
        offset,
        status or "",
        kind or "",
    )
    cached = _lead_cache_get(_lead_list_cache, cache_key)
    if cached is not None:
        return cached
    params = [user_id]
    where = ["user_id=?"]
    if kind in {"job", "post"}:
        where.append("lead_kind=?")
        params.append(kind)
    if temperature and temperature != "all":
        where.append("temperature=?")
        params.append(temperature)
    if status:
        where.append("status=?")
        params.append(status)
    if search:
        where.append("(company LIKE ? OR role_title LIKE ? OR post_text LIKE ? OR tags LIKE ?)")
        q = f"%{search}%"
        params.extend([q, q, q, q])
    with db() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        user = dict(user_row) if user_row else {}
        order_by = """
            created_at DESC,
            posted_at DESC,
            CASE lead_kind WHEN 'post' THEN 0 ELSE 1 END,
            score DESC
            """
        max_fetch_limit = 300
        fetch_limit = min(max_fetch_limit, offset + limit * 3 + 24)
        rows = conn.execute(
            f"""
            SELECT {LEAD_LIST_COLUMNS} FROM leads
            WHERE {' AND '.join(where)}
            ORDER BY {order_by}
            LIMIT ?
            """,
            params + [fetch_limit],
        ).fetchall()
        by_key = {}
        key_order = []
        for row in rows:
            key = lead_display_key(row)
            current = by_key.get(key)
            if current is None:
                key_order.append(key)
                by_key[key] = row
            elif lead_quality(row) > lead_quality(current):
                by_key[key] = row
        unique_rows = [by_key[key] for key in key_order if row_matches_current_profile(by_key[key], user)]
        page_rows = unique_rows[offset:offset + limit]
        items = [format_lead(row) for row in page_rows]
        has_more = len(rows) >= fetch_limit and len(unique_rows) > offset + len(items)
        visible_total = offset + len(items) + (1 if has_more else 0)
        visible_counts = {
            "total": visible_total,
            "hot": sum(1 for row in unique_rows if row["temperature"] == "hot"),
            "warm": sum(1 for row in unique_rows if row["temperature"] == "warm"),
            "cold": sum(1 for row in unique_rows if row["temperature"] == "cold"),
            "saved": sum(1 for row in unique_rows if row["status"] == "saved"),
        }
        live_today_counts = today_lead_counts(conn, user_id, user)
        result = {
            "items": items,
            "total": visible_total,
            "next_offset": offset + len(items),
            "has_more": has_more,
            "counts": {
                "total": visible_counts["total"],
                "hot": visible_counts["hot"],
                "warm": visible_counts["warm"],
                "cold": visible_counts["cold"],
                "saved": visible_counts["saved"],
                "all_kinds_total": visible_total,
                "jobs": sum(1 for row in unique_rows if row["lead_kind"] == "job"),
                "posts": sum(1 for row in unique_rows if row["lead_kind"] == "post"),
            },
            "today_counts": live_today_counts,
        }
        _lead_cache_set(_lead_list_cache, cache_key, result)
        return result


def get_lead(user_id, lead_id):
    cache_key = (str(user_id), str(lead_id))
    cached = _lead_cache_get(_lead_detail_cache, cache_key)
    if cached is not None:
        return cached.get("lead")
    with db() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        user = dict(user_row) if user_row else {}
        row = conn.execute("SELECT * FROM leads WHERE user_id=? AND id=?", (user_id, lead_id)).fetchone()
        if row and not row_matches_current_profile(row, user):
            row = None
        lead = format_lead(row) if row else None
        if lead:
            _lead_cache_set(_lead_detail_cache, cache_key, {"ok": True, "lead": lead})
        return lead


def update_lead_status(user_id, lead_id, status):
    allowed = {"new", "saved", "archived"}
    status = status if status in allowed else "new"
    with db() as conn:
        current = conn.execute("SELECT status FROM leads WHERE user_id=? AND id=?", (user_id, lead_id)).fetchone()
        if current and current["status"] == "saved" and status == "saved":
            row = conn.execute("SELECT * FROM leads WHERE user_id=? AND id=?", (user_id, lead_id)).fetchone()
            lead = format_lead(row) if row else None
            if lead:
                lead["already_saved"] = True
            return lead
        conn.execute("UPDATE leads SET status=? WHERE user_id=? AND id=?", (status, user_id, lead_id))
        row = conn.execute("SELECT * FROM leads WHERE user_id=? AND id=?", (user_id, lead_id)).fetchone()
        lead = format_lead(row) if row else None
        clear_lead_cache(user_id, lead_id)
        if lead:
            _lead_cache_set(_lead_detail_cache, (str(user_id), str(lead_id)), {"ok": True, "lead": lead})
        return lead


def today_lead_counts(conn, user_id, user=None):
    start_utc, end_utc = daily_count_window_utc()
    rows = conn.execute(
        """
        SELECT {columns} FROM leads
        WHERE user_id=? AND datetime(created_at) >= datetime(?) AND datetime(created_at) < datetime(?)
        ORDER BY created_at DESC, posted_at DESC, score DESC
        """.format(columns=LEAD_LIST_COLUMNS),
        (user_id, start_utc, end_utc),
    ).fetchall()
    by_key = {}
    for row in rows:
        key = lead_display_key(row)
        current = by_key.get(key)
        if current is None or lead_quality(row) > lead_quality(current):
            by_key[key] = row
    unique_rows = [row for row in by_key.values() if row_matches_current_profile(row, user)]
    return {
        "total": len(unique_rows),
        "hot": sum(1 for row in unique_rows if row["temperature"] == "hot"),
        "warm": sum(1 for row in unique_rows if row["temperature"] == "warm"),
        "cold": sum(1 for row in unique_rows if row["temperature"] == "cold"),
        "saved": sum(1 for row in unique_rows if row["status"] == "saved"),
    }


def daily_count_window_utc():
    """
    Daily sidebar counts use HireMate's operating day: 7:00 AM to 3:00 AM
    Asia/Karachi time. SQLite CURRENT_TIMESTAMP is UTC, so compare in UTC.
    """
    local_tz = timezone(timedelta(hours=5))
    now = datetime.now(local_tz)
    if now.hour >= 7:
        start_local = datetime.combine(now.date(), time(7, 0), tzinfo=local_tz)
        end_local = datetime.combine(now.date() + timedelta(days=1), time(3, 0), tzinfo=local_tz)
    else:
        start_local = datetime.combine(now.date() - timedelta(days=1), time(7, 0), tzinfo=local_tz)
        end_local = datetime.combine(now.date(), time(3, 0), tzinfo=local_tz)
    return (
        start_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        end_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )


def weekly_count_window_utc(weeks_back=0):
    """Return the Monday-to-Sunday reporting week in UTC for dashboard stats."""
    local_tz = timezone(timedelta(hours=5))
    now = datetime.now(local_tz)
    monday = now.date() - timedelta(days=now.weekday(), weeks=int(weeks_back or 0))
    start_local = datetime.combine(monday, time(0, 0), tzinfo=local_tz)
    end_local = start_local + timedelta(days=7)
    return (
        start_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        end_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )


def format_lead(row):
    item = dict(row)
    if item.get("lead_kind") == "job":
        item["post_text"] = clean_legacy_job_text(item.get("post_text", ""))
    item["tags"] = split_csv(item.get("tags"))
    try:
        item["comment_items"] = json.loads(item.get("comments_json") or "[]")
    except json.JSONDecodeError:
        item["comment_items"] = []
    try:
        item["reaction_items"] = json.loads(item.get("reactions_json") or "{}")
    except json.JSONDecodeError:
        item["reaction_items"] = {}
    return item


def clean_legacy_job_text(text):
    text = text or ""
    if text.startswith("About this job:"):
        return text[len("About this job:"):].strip()
    if text.startswith("About this job\n"):
        lines = text.splitlines()
        return "\n".join(lines[1:]).strip()
    if not text.startswith("LinkedIn job result for "):
        return text
    match = re.search(
        r":\s*(.*?)\s+is hiring\s+(.*?)\.\s+Location:\s+(.*?)\.\s+Apply or review details on LinkedIn\.?",
        text,
        flags=re.I | re.S,
    )
    if not match:
        return re.sub(r"^LinkedIn job result for\s+[^:]+:\s*", "", text).strip()
    company, title, location = [part.strip() for part in match.groups()]
    return f"Location: {location}\n\nHireMate could not read the full LinkedIn job description during this safe sync. Open the LinkedIn job page to view the complete description and apply."


def dashboard(user_id):
    cached = _lead_cache_get(_dashboard_cache, str(user_id))
    if cached is not None:
        return cached
    with db() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        user = dict(user_row) if user_row else {}
        drafts = conn.execute("SELECT COUNT(*) pending FROM drafts WHERE user_id=? AND status='pending'", (user_id,)).fetchone()
        week_start, week_end = weekly_count_window_utc()
        last_week_start, last_week_end = weekly_count_window_utc(1)
        approved = conn.execute(
            """
            SELECT COUNT(*) approved
            FROM drafts
            WHERE user_id=? AND status='approved'
              AND datetime(updated_at) >= datetime(?) AND datetime(updated_at) < datetime(?)
            """,
            (user_id, week_start, week_end),
        ).fetchone()
        last_approved = conn.execute(
            """
            SELECT COUNT(*) approved
            FROM drafts
            WHERE user_id=? AND status='approved'
              AND datetime(updated_at) >= datetime(?) AND datetime(updated_at) < datetime(?)
            """,
            (user_id, last_week_start, last_week_end),
        ).fetchone()
        recent_rows = conn.execute(
            """
            SELECT """ + LEAD_LIST_COLUMNS + """ FROM leads
            WHERE user_id=?
            ORDER BY created_at DESC, CASE lead_kind WHEN 'post' THEN 0 ELSE 1 END, posted_at DESC, score DESC
            LIMIT 40
            """,
            (user_id,),
        ).fetchall()
        recent_by_key = {}
        recent_order = []
        for row in recent_rows:
            key = lead_display_key(row)
            current = recent_by_key.get(key)
            if current is None:
                recent_order.append(key)
                recent_by_key[key] = row
            elif lead_quality(row) > lead_quality(current):
                recent_by_key[key] = row
        recent_order = [key for key in recent_order if row_matches_current_profile(recent_by_key[key], user)]
        all_rows = conn.execute(
            f"""
            SELECT {LEAD_LIST_COLUMNS} FROM leads
            WHERE user_id=?
            ORDER BY created_at DESC, posted_at DESC, score DESC
            LIMIT 500
            """,
            (user_id,),
        ).fetchall()
        all_by_key = {}
        for row in all_rows:
            key = lead_display_key(row)
            current = all_by_key.get(key)
            if current is None or lead_quality(row) > lead_quality(current):
                all_by_key[key] = row
        relevant_rows = [row for row in all_by_key.values() if row_matches_current_profile(row, user)]
        counts = {
            "total": len(relevant_rows),
            "hot": sum(1 for row in relevant_rows if row["temperature"] == "hot"),
            "warm": sum(1 for row in relevant_rows if row["temperature"] == "warm"),
            "cold": sum(1 for row in relevant_rows if row["temperature"] == "cold"),
            "saved": sum(1 for row in relevant_rows if row["status"] == "saved"),
        }
        today_counts = today_lead_counts(conn, user_id, user)
        result = {
            "counts": counts,
            "today_counts": today_counts,
            "pending_drafts": drafts["pending"],
            "approved_drafts": approved["approved"],
            "approved_last_week": last_approved["approved"],
            "approved_week_delta": (approved["approved"] or 0) - (last_approved["approved"] or 0),
            "recent_leads": [format_lead(recent_by_key[key]) for key in recent_order[:3]],
        }
        _lead_cache_set(_dashboard_cache, str(user_id), result)
        return result


def sample_posts():
    now = datetime.now(timezone.utc)
    return [
        {
            "source_post_id": "sample-tv-react",
            "company": "TechVentures PK",
            "role_title": "Frontend Developer (Remote)",
            "author_name": "Asad Hussain",
            "author_title": "HR Manager",
            "post_text": "We're hiring a Frontend Developer with React.js, JavaScript, REST APIs, HTML and CSS experience. Remote-friendly role with flexible hours. Interested candidates can DM portfolio.",
            "location": "Lahore, Pakistan",
            "work_type": "Remote",
            "employment_type": "Full-time",
            "experience": "1-3 years",
            "salary": "Competitive PKR",
            "likes": 48,
            "comments": 12,
            "reposts": 3,
            "posted_at": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "source_post_id": "sample-systems-rn",
            "company": "Systems Limited",
            "role_title": "React Native Developer",
            "author_name": "Maria Khan",
            "author_title": "Talent Acquisition",
            "post_text": "Hiring React Native developer with strong JavaScript fundamentals for a mobile banking application. Experience with APIs and clean UI development required.",
            "location": "Karachi, Pakistan",
            "work_type": "Hybrid",
            "employment_type": "Full-time",
            "experience": "1-2 years",
            "likes": 35,
            "comments": 8,
            "posted_at": (now - timedelta(hours=3)).isoformat(),
        },
        {
            "source_post_id": "sample-netsol-python",
            "company": "Netsol Technologies",
            "role_title": "Python / Django Developer",
            "author_name": "Hammad Ali",
            "author_title": "Engineering Lead",
            "post_text": "Looking for Python developer with Django experience to work on our fintech product. REST APIs, database design, and problem solving are important.",
            "location": "Lahore, Pakistan",
            "work_type": "On-site",
            "employment_type": "Full-time",
            "experience": "2-3 years",
            "likes": 21,
            "comments": 4,
            "posted_at": (now - timedelta(hours=5)).isoformat(),
        },
        {
            "source_post_id": "sample-lums-ra",
            "company": "LUMS",
            "role_title": "CS Research Assistant",
            "author_name": "Dr. Sana Malik",
            "author_title": "Faculty Member",
            "post_text": "Research assistant position available in our AI/ML lab. Students with Python, NLP, and strong programming background are encouraged to apply.",
            "location": "Lahore, Pakistan",
            "work_type": "On-site",
            "employment_type": "Part-time",
            "experience": "Student / Fresh",
            "likes": 14,
            "comments": 2,
            "posted_at": (now - timedelta(hours=8)).isoformat(),
        },
        {
            "source_post_id": "sample-arbisoft-intern",
            "company": "Arbisoft",
            "role_title": "Software Engineer Intern",
            "author_name": "People Team",
            "author_title": "Recruitment",
            "post_text": "Internship opportunity for CS/SE students. Fresh talent with strong data structures, HTML, CSS, JavaScript or Python basics can drop their resume.",
            "location": "Lahore, Pakistan",
            "work_type": "On-site",
            "employment_type": "Internship",
            "experience": "Fresh / Student",
            "likes": 5,
            "comments": 1,
            "posted_at": (now - timedelta(days=2)).isoformat(),
        },
    ]
