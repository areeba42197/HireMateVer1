import json
import hashlib
import http.cookiejar
import random
import re
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import quote_plus
from urllib import request

from core.config import (
    LINKEDIN_MAX_DELAY_SECONDS,
    LINKEDIN_MAX_RESULTS_PER_SYNC,
    LINKEDIN_MAX_SEARCH_QUERIES,
    LINKEDIN_MIN_DELAY_SECONDS,
)


REALISTIC_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36 Edg/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]


def parse_manual_posts(payload):
    """
    Accepts a list of LinkedIn-style posts from JSON pasted by the user/admin.
    This is the recommended data path for the FYP demo because it is reliable,
    auditable, and does not depend on fragile LinkedIn page structure.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, str):
        return json.loads(payload)
    raise ValueError("Expected a JSON list of posts.")


def fetch_keyword_page(keyword, li_at_cookie, user_agent="", accept_language=""):
    """
    Experimental only. LinkedIn may block automated page requests, and its terms
    and markup can change. Keep this disabled in production and prefer official,
    exported, or user-approved data sources.
    """
    if not li_at_cookie:
        raise ValueError("LinkedIn li_at cookie is required for live testing.")
    session = LinkedInSession(li_at_cookie, user_agent=user_agent, accept_language=accept_language)
    session.bootstrap()
    encoded = quote_plus(keyword)
    url = f"https://www.linkedin.com/search/results/content/?keywords={encoded}"
    html = session.open_text(url, accept="text/html,application/xhtml+xml")
    if page_is_blocked(html):
        raise RuntimeError("LinkedIn checkpoint/CAPTCHA detected. Sync stopped.")
    posts = extract_posts_from_html(html)
    try:
        voyager = session.open_text(
            "https://www.linkedin.com/voyager/api/search/blended"
            + f"?count=10&filters=List(resultType-%3ECONTENT)&keywords={encoded}&origin=GLOBAL_SEARCH_HEADER&q=all&start=0",
            accept="application/vnd.linkedin.normalized+json+2.1",
            restli=True,
        )
        posts.extend(extract_posts_from_json(voyager))
    except Exception:
        pass
    if not posts and looks_logged_out(html):
        raise RuntimeError("LinkedIn returned a logged-out page. Save a fresh full Cookie header from an active LinkedIn tab.")
    return posts


class LinkedInSession:
    def __init__(self, cookie_header, user_agent="", accept_language=""):
        self.jar = http.cookiejar.CookieJar()
        self.opener = request.build_opener(request.HTTPCookieProcessor(self.jar))
        self.seed_cookies(cookie_header)
        self.user_agent = user_agent or random.choice(REALISTIC_USER_AGENTS)
        self.accept_language = accept_language or "en-US,en;q=0.9"

    def seed_cookies(self, cookie_header):
        cookie_header = (cookie_header or "").strip()
        parts = [part.strip() for part in cookie_header.split(";") if part.strip()]
        if len(parts) == 1 and "=" not in parts[0]:
            parts = ["li_at=" + parts[0]]
        for part in parts:
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            self.jar.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=name.strip(),
                    value=value.strip().strip('"'),
                    port=None,
                    port_specified=False,
                    domain=".linkedin.com",
                    domain_specified=True,
                    domain_initial_dot=True,
                    path="/",
                    path_specified=True,
                    secure=True,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False,
                )
            )

    def csrf_token(self):
        for cookie in self.jar:
            if cookie.name == "JSESSIONID":
                return cookie.value.strip('"')
        return ""

    def headers(self, accept, restli=False):
        headers = random_headers(
            {
                "User-Agent": self.user_agent,
                "Accept": accept,
                "Accept-Language": self.accept_language,
                "Referer": "https://www.linkedin.com/feed/",
                "Origin": "https://www.linkedin.com",
            }
        )
        csrf = self.csrf_token()
        if csrf:
            headers["csrf-token"] = csrf
        if restli:
            headers["x-restli-protocol-version"] = "2.0.0"
            headers["x-li-lang"] = "en_US"
        return headers

    def open_text(self, url, accept="text/html", restli=False):
        req = request.Request(url, headers=self.headers(accept, restli))
        with self.opener.open(req, timeout=10) as response:
            if response.status in (403, 429, 999):
                raise RuntimeError(f"LinkedIn block/rate-limit response: {response.status}")
            return response.read().decode("utf-8", errors="ignore")

    def bootstrap(self):
        self.open_text("https://www.linkedin.com/feed/", accept="text/html,application/xhtml+xml")


def sync_linkedin_for_profile(user, max_results=LINKEDIN_MAX_RESULTS_PER_SYNC, job_start=0, include_posts=True, keyword_offset=0):
    """
    Builds LinkedIn searches from the user's onboarding profile and returns
    normalized post/job dictionaries. It first tries authenticated content search
    using the user's li_at cookie, then also reads public LinkedIn job-search HTML
    because it is more reliable for job opportunity discovery.
    """
    locations = split_csv(user.get("preferred_locations", "")) or [user.get("location") or "Pakistan"]
    keywords = ai_keywords(user, purpose="jobs")
    if keywords:
        shift = int(keyword_offset or 0) % len(keywords)
        keywords = keywords[shift:] + keywords[:shift]
    collected = []
    errors = []

    post_budget = max(1, LINKEDIN_MAX_SEARCH_QUERIES)
    job_budget = max(2, LINKEDIN_MAX_SEARCH_QUERIES)

    cookie = user.get("linkedin_cookie", "")
    if cookie and include_posts:
        for keyword in keywords:
            if len([p for p in collected if p.get("lead_kind") == "post"]) >= max_results // 2 or post_budget <= 0:
                break
            try:
                polite_delay()
                found = fetch_keyword_page(
                    keyword,
                    cookie,
                    user_agent=user.get("linkedin_user_agent", ""),
                    accept_language=user.get("linkedin_accept_language", ""),
                )
                collected.extend(found)
                post_budget -= 1
            except Exception as exc:
                errors.append(f"content:{keyword}:{exc}")
                post_budget -= 1
                if is_block_signal(str(exc)):
                    break
        if not [p for p in collected if p.get("lead_kind") == "post"]:
            errors.append("content search returned 0 readable post leads; falling back to LinkedIn Jobs")

    for keyword in keywords:
        for location in locations[:2]:
            if len(collected) >= max_results or job_budget <= 0:
                break
            try:
                polite_delay()
                collected.extend(fetch_public_jobs(keyword, location, start=job_start))
                job_budget -= 1
            except Exception as exc:
                errors.append(f"jobs:{keyword}:{exc}")
                job_budget -= 1
                if is_block_signal(str(exc)):
                    return list(unique_posts(collected).values())[:max_results], errors
        if len(collected) >= max_results or job_budget <= 0:
            break

    return list(unique_posts(collected).values())[:max_results], errors


def polite_delay():
    time.sleep(random.uniform(LINKEDIN_MIN_DELAY_SECONDS, LINKEDIN_MAX_DELAY_SECONDS))


def random_headers(extra=None):
    headers = {
        "User-Agent": random.choice(REALISTIC_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }
    if extra:
        headers.update(extra)
    return headers


def is_block_signal(message):
    lowered = (message or "").lower()
    return any(term in lowered for term in ("429", "999", "captcha", "checkpoint", "forbidden", "too many requests"))


def unique_posts(posts):
    unique = {}
    for item in posts:
        text = item.get("post_text", "")
        if not text:
            continue
        key = item.get("source_post_id") or str(abs(hash(text)))
        item.setdefault("source", "linkedin")
        item.setdefault("scraped_at", datetime.now(timezone.utc).isoformat())
        unique[key] = item
    return unique


def split_csv(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


TECH_PROFILE_TERMS = {
    "ai", "artificial intelligence", "machine learning", "ml", "data", "software",
    "developer", "engineer", "programming", "python", "javascript", "react",
    "backend", "frontend", "full stack", "cloud", "cyber", "devops", "qa",
}

TERM_ALIASES = {
    "pharmasist": "pharmacist",
    "pharmacyst": "pharmacist",
    "teching": "teaching",
}


def is_technical_profile(roles, skills, interests):
    profile_text = " ".join(list(roles or []) + list(skills or []) + list(interests or [])).lower()
    for term in TECH_PROFILE_TERMS:
        needle = re.sub(r"\s+", " ", str(term or "").strip().lower())
        if not needle:
            continue
        if needle in {"ai", "ml"}:
            pattern = rf"(?<![a-z0-9.]){re.escape(needle)}(?![a-z0-9.])"
        else:
            pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
        if re.search(pattern, profile_text):
            return True
    return False


def normalize_keyword_term(value):
    text = str(value or "").strip()
    for typo, replacement in TERM_ALIASES.items():
        text = re.sub(rf"\b{re.escape(typo)}\b", replacement, text, flags=re.I)
    return text


def build_keywords(roles, skills, interests, experience_level="", work_modes="", preferred_locations="", education="", experience_detail="", headline="", about=""):
    terms = []
    technical = is_technical_profile(roles, skills, interests)
    clean_roles = [normalize_keyword_term(role) for role in roles if role and len(role) <= 70]
    clean_skills = [normalize_keyword_term(skill) for skill in skills if skill and len(skill) <= 45]
    ignored_interests = {"remote", "onsite", "on-site", "hybrid", "freelance", "internship"}
    modifiers = []
    for value in split_csv(work_modes)[:2]:
        modifiers.append(value)
    if experience_level:
        modifiers.append(experience_level)
    for role in clean_roles:
        terms.append(f"{role} hiring")
        terms.append(f'"{role}" "we are hiring"')
        for modifier in modifiers[:3]:
            terms.append(f"{role} {modifier} hiring")
        for skill in clean_skills[:4]:
            terms.append(f"{role} {skill}")
    if not clean_roles:
        for skill in clean_skills[:5]:
            terms.append(f"{skill} jobs hiring")
            if experience_level:
                terms.append(f"{skill} {experience_level} hiring")
            if technical:
                terms.append(f"{skill} developer hiring")
    for interest in interests[:3]:
        interest_clean = normalize_keyword_term(interest)
        if interest_clean.lower() in ignored_interests:
            continue
        if clean_roles:
            terms.append(f"{clean_roles[0]} {interest_clean}")
        elif interest_clean:
            terms.append(f"{interest} opportunity")
    for location in split_csv(preferred_locations)[:2]:
        for role in clean_roles[:2]:
            terms.append(f"{role} {location}")
    return list(dict.fromkeys([term for term in terms if term.strip()]))


def ai_keywords(user, purpose="jobs"):
    """Load AI-generated keywords and enrich them with direct profile terms."""
    skills = split_csv(user.get("skills", ""))
    interests = split_csv(user.get("interests", ""))
    roles = split_csv(user.get("target_roles", "")) or split_csv(user.get("headline", "")) or skills[:3]
    profile_terms = build_keywords(
        roles,
        skills,
        interests,
        user.get("experience_level", ""),
        user.get("work_modes", ""),
        user.get("preferred_locations", ""),
        user.get("education", ""),
        user.get("experience_detail", ""),
        user.get("headline", ""),
        user.get("about", ""),
    )
    try:
        from services.ai_keyword_service import keyword_queue

        keywords = keyword_queue(user, purpose=purpose)
        if keywords:
            return list(dict.fromkeys([term for term in profile_terms + keywords if term.strip()]))
    except Exception:
        pass
    return profile_terms


def fetch_public_jobs(keyword, location, start=0):
    url = (
        "https://www.linkedin.com/jobs/search/?"
        + f"keywords={quote_plus(keyword)}&location={quote_plus(location)}&f_TPR=r86400&start={int(start or 0)}"
    )
    req = request.Request(
        url,
        headers=random_headers(),
    )
    with request.urlopen(req, timeout=12) as response:
        if response.status in (403, 429, 999):
            raise RuntimeError(f"LinkedIn block/rate-limit response: {response.status}")
        html = response.read().decode("utf-8", errors="ignore")
    if page_is_blocked(html):
        raise RuntimeError("LinkedIn checkpoint/CAPTCHA detected. Sync stopped.")
    jobs = extract_jobs_from_html(html, keyword, location)
    for job in jobs[:4]:
        link = job.get("post_url")
        if not link:
            continue
        try:
            polite_delay()
            details = fetch_job_detail(link)
            if details:
                job.update({key: value for key, value in details.items() if value})
        except Exception:
            pass
    return jobs


def fetch_job_detail(url):
    req = request.Request(url, headers=random_headers())
    with request.urlopen(req, timeout=12) as response:
        if response.status in (403, 429, 999):
            raise RuntimeError(f"LinkedIn block/rate-limit response: {response.status}")
        html = response.read().decode("utf-8", errors="ignore")
    if page_is_blocked(html):
        raise RuntimeError("LinkedIn checkpoint/CAPTCHA detected. Sync stopped.")
    title = clean_html_text(first_match(html, r"<h1[^>]*>(.*?)</h1>"))
    company = clean_html_text(first_match(html, r"class=\"[^\"]*topcard__org-name-link[^\"]*\"[^>]*>(.*?)</a>"))
    description = clean_job_description(html)
    if not description:
        description = clean_html_text(decode_jsonish_text(first_match(html, r'"description"\s*:\s*"((?:\\.|[^"\\]){80,})"')))
    if not title:
        title = clean_html_text(decode_jsonish_text(first_match(html, r'"title"\s*:\s*"((?:\\.|[^"\\]){5,})"')))
    if not company:
        company = clean_html_text(decode_jsonish_text(first_match(html, r'"hiringOrganization"\s*:\s*\{[^{}]*"name"\s*:\s*"((?:\\.|[^"\\]){2,})"')))
    criteria = re.findall(r"class=\"[^\"]*description__job-criteria-subheader[^\"]*\"[^>]*>(.*?)</h3>\s*<span[^>]*>(.*?)</span>", html, flags=re.I | re.S)
    lines = []
    if description:
        lines.append(description)
    if criteria:
        reqs = []
        for label, value in criteria:
            reqs.append(f"{clean_html_text(label)}: {clean_html_text(value)}")
        lines.append("\n".join(reqs))
    return {
        "company": company,
        "role_title": title,
        "post_text": "\n\n".join(lines).strip(),
        "comments": extract_applicant_count(html),
    }


def clean_job_description(html):
    blocks = [
        first_match(html, r"class=\"[^\"]*show-more-less-html__markup[^\"]*\"[^>]*>(.*?)</section>"),
        first_match(html, r"class=\"[^\"]*show-more-less-html__markup[^\"]*\"[^>]*>(.*?)</div>\s*</div>"),
        decode_jsonish_text(first_match(html, r'"description"\s*:\s*"((?:\\.|[^"\\]){80,})"')),
    ]
    for block in blocks:
        text = clean_job_html_text(block)
        if len(text) > 60:
            return text
    return ""


def clean_job_html_text(value):
    """Keep LinkedIn job description spacing while stripping unsafe markup."""
    text = value or ""
    text = re.sub(r"<\s*(br|/p|/div|/section|/li|/ul|/ol)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*(p|div|section|ul|ol)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*li\b[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"<\s*(h[1-6]|strong|b)\b[^>]*>", "\n**", text, flags=re.I)
    text = re.sub(r"<\s*/\s*(h[1-6]|strong|b)\s*>", "**\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def page_is_blocked(html):
    lowered = (html or "").lower()
    hard_signals = [
        "<title>security verification",
        "/checkpoint/challenge",
        "authwall",
        "verify you are a human",
        "unusual traffic",
        "too many requests",
    ]
    return any(signal in lowered for signal in hard_signals)


def looks_logged_out(html):
    lowered = (html or "").lower()
    return any(signal in lowered for signal in ("sign in", "authwall", "/login", "join linkedin"))


def clean_html_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def extract_jobs_from_html(html, keyword, location):
    cards = re.findall(r"<div[^>]+class=\"[^\"]*base-card[^\"]*\".*?</div>\s*</div>", html, flags=re.I | re.S)
    posts = []
    for idx, card in enumerate(cards[:LINKEDIN_MAX_RESULTS_PER_SYNC]):
        title = clean_html_text(first_match(card, r"class=\"[^\"]*base-search-card__title[^\"]*\"[^>]*>(.*?)</"))
        company = clean_html_text(first_match(card, r"class=\"[^\"]*base-search-card__subtitle[^\"]*\"[^>]*>.*?<a[^>]*>(.*?)</a>"))
        job_location = clean_html_text(first_match(card, r"class=\"[^\"]*job-search-card__location[^\"]*\"[^>]*>(.*?)</"))
        link = extract_job_link(card)
        posted_at = extract_posted_at(card)
        applicants = extract_applicant_count(card)
        detail_line = extract_job_meta_line(card)
        if not title:
            continue
        post_text = "\n\n".join(
            part for part in [
                f"Location: {job_location or location}",
                "HireMate could not read the full LinkedIn job description during this safe sync. Open the LinkedIn job page to view the complete description and apply.",
            ]
            if part
        )
        posts.append({
            "source_post_id": "linkedin-job-" + stable_id(link or post_text),
            "lead_kind": "job",
            "company": company or "LinkedIn Job",
            "role_title": title,
            "author_name": company or "",
            "author_title": "LinkedIn Jobs",
            "post_text": post_text,
            "post_url": link,
            "location": job_location or location,
            "work_type": "Remote" if "remote" in (keyword + " " + title).lower() else "",
            "employment_type": "Full-time",
            "likes": 0,
            "comments": applicants,
            "reposts": 0,
            "reaction_items": {
                "applicant_text": detail_line.get("applicant_text", ""),
                "posted_label": detail_line.get("posted_label", ""),
            },
            "posted_at": posted_at or datetime.now(timezone.utc).isoformat(),
        })
    return posts


def extract_job_meta_line(card):
    """Return the visible LinkedIn card labels, e.g. '2 hours ago' and '19 applicants'."""
    text = clean_html_text(card)
    posted = first_match(text, r"(\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago)")
    applicants = first_match(text, r"(\d[\d,]*\s+(?:people\s+clicked\s+apply|people\s+applied|applicants?))")
    return {"posted_label": posted, "applicant_text": applicants}


def extract_posted_at(card):
    raw = first_match(card, r"<time[^>]+datetime=\"([^\"]+)\"")
    if raw:
        return raw.strip()
    text = clean_html_text(card)
    relative = first_match(text, r"(\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago)")
    return relative_to_iso(relative)


def extract_applicant_count(html):
    raw = first_match(html, r"(\d[\d,]*)\s+applicants?")
    if not raw:
        raw = first_match(html, r"(\d[\d,]*)\s+people\s+applied")
    if not raw:
        raw = first_match(html, r"(\d[\d,]*)\s+people\s+clicked\s+apply")
    return first_int(raw)


def relative_to_iso(value):
    if not value:
        return ""
    amount = first_int(first_match(value, r"(\d+)"))
    lower = value.lower()
    seconds = 0
    if "minute" in lower:
        seconds = amount * 60
    elif "hour" in lower:
        seconds = amount * 3600
    elif "day" in lower:
        seconds = amount * 86400
    elif "week" in lower:
        seconds = amount * 7 * 86400
    elif "month" in lower:
        seconds = amount * 30 * 86400
    return datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - seconds, timezone.utc).isoformat() if seconds else ""


def first_match(text, pattern):
    match = re.search(pattern, text or "", flags=re.I | re.S)
    return match.group(1) if match else ""


def extract_job_link(card):
    link = first_match(card, r"href=\"([^\"]*/jobs/view/[^\"]+)\"")
    if not link:
        return ""
    link = unescape(link).split("?")[0]
    if link.startswith("/"):
        link = "https://www.linkedin.com" + link
    return link


def stable_id(value):
    return hashlib.sha1((value or "").encode("utf-8", errors="ignore")).hexdigest()[:16]


def extract_posts_from_html(html):
    # This is deliberately conservative. It extracts post-like text blocks and
    # lightweight engagement/comment snippets visible in the returned HTML.
    chunks = re.findall(r'"text"\s*:\s*"((?:\\.|[^"\\]){80,})"', html, flags=re.I | re.S)
    chunks += re.findall(r"<span[^>]*>(.*?)</span>", html, flags=re.I | re.S)
    posts = []
    for chunk in chunks:
        text = decode_jsonish_text(chunk)
        text = re.sub(r"<[^>]+>", " ", text)
        text = clean_html_text(text)
        lower = text.lower()
        if len(text) > 80 and any(term in lower for term in ("hiring", "looking for", "developer", "internship", "job")):
            comment_items = extract_comment_snippets(html)
            reaction_items = extract_reaction_counts(html)
            post_url = extract_best_post_url(html, text)
            posts.append({
                "post_text": text,
                "source_post_id": "linkedin-live-" + stable_id(post_url or text),
                "lead_kind": "post",
                "company": "LinkedIn Post",
                "role_title": "Hiring Opportunity",
                "post_url": post_url,
                "likes": reaction_items.get("likes", 0),
                "comments": len(comment_items),
                "reposts": reaction_items.get("reposts", 0),
                "comment_items": comment_items,
                "reaction_items": reaction_items,
                "posted_at": extract_best_post_time(html) or datetime.now(timezone.utc).isoformat(),
            })
    return posts[:LINKEDIN_MAX_RESULTS_PER_SYNC]


def extract_posts_from_json(raw):
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    candidates = []
    walk_json(payload, candidates)
    posts = []
    seen = set()
    for candidate in candidates:
        text = clean_html_text(candidate.get("text", ""))
        lower = text.lower()
        key = candidate.get("url") or text
        if key in seen:
            continue
        seen.add(key)
        if len(text) > 80 and any(term in lower for term in ("hiring", "looking for", "developer", "internship", "job", "remote", "apply")):
            posts.append(
                {
                    "post_text": text,
                    "source_post_id": "linkedin-json-" + stable_id(key),
                    "lead_kind": "post",
                    "company": "LinkedIn Post",
                    "role_title": "Hiring Opportunity",
                    "author_name": candidate.get("author", ""),
                    "post_url": candidate.get("url", ""),
                    "likes": candidate.get("likes", 0),
                    "comments": len(candidate.get("comments", [])),
                    "reposts": candidate.get("reposts", 0),
                    "comment_items": candidate.get("comments", []),
                    "reaction_items": {"likes": candidate.get("likes", 0), "reposts": candidate.get("reposts", 0)},
                    "posted_at": candidate.get("posted_at") or datetime.now(timezone.utc).isoformat(),
                }
            )
    return posts[:LINKEDIN_MAX_RESULTS_PER_SYNC]


def walk_json(value, candidates):
    if isinstance(value, dict):
        text = first_text_value(value)
        if text:
            candidates.append(
                {
                    "text": text,
                    "url": first_url_value(value),
                    "posted_at": first_time_value(value),
                    "author": first_author_value(value),
                    "likes": first_metric_value(value, ("numLikes", "likeCount", "reactionCount", "totalReactionCount")),
                    "reposts": first_metric_value(value, ("numShares", "shareCount", "repostCount")),
                    "comments": extract_json_comments(value),
                }
            )
        for key, child in value.items():
            walk_json(child, candidates)
    elif isinstance(value, list):
        for child in value:
            walk_json(child, candidates)


def first_text_value(value):
    for key in ("commentary", "text", "description"):
        child = value.get(key)
        if isinstance(child, str) and len(child) > 40:
            return child
        if isinstance(child, dict):
            nested = first_text_value(child)
            if nested:
                return nested
    return ""


def first_url_value(value):
    for key in ("permalink", "url", "postUrl", "shareUrl"):
        child = value.get(key)
        if isinstance(child, str) and "linkedin.com" in child:
            return child.split("?")[0]
    urn = value.get("urn") or value.get("entityUrn") or ""
    if isinstance(urn, str) and "activity:" in urn:
        return "https://www.linkedin.com/feed/update/" + urn
    return ""


def first_time_value(value):
    for key in ("createdAt", "createdTime", "postedAt", "publishedAt", "date"):
        child = value.get(key)
        if isinstance(child, str) and child:
            return child
        if isinstance(child, (int, float)) and child > 1000000000:
            ts = child / 1000 if child > 100000000000 else child
            return datetime.fromtimestamp(ts, timezone.utc).isoformat()
    return ""


def first_author_value(value):
    for key in ("authorName", "actorName", "name"):
        child = value.get(key)
        if isinstance(child, str) and 2 <= len(child) <= 120:
            return child
    return ""


def first_metric_value(value, keys):
    for key in keys:
        child = value.get(key)
        if isinstance(child, int):
            return child
    return 0


def extract_json_comments(value):
    comments = []
    for key in ("comments", "commentary"):
        child = value.get(key)
        if isinstance(child, list):
            for item in child[:5]:
                if isinstance(item, dict):
                    text = clean_html_text(first_text_value(item))
                    if text:
                        comments.append({"author": first_author_value(item) or "LinkedIn member", "text": text})
    return comments[:5]


def extract_best_post_url(html, text):
    for match in re.findall(r"https://www\.linkedin\.com/feed/update/[^\"'<\s]+", html or ""):
        return unescape(match).split("?")[0]
    activity = first_match(html, r"urn:li:activity:(\d+)")
    if activity:
        return "https://www.linkedin.com/feed/update/urn:li:activity:" + activity
    return ""


def extract_best_post_time(html):
    raw = first_match(html, r'"createdAt"\s*:\s*(\d{10,13})')
    if raw:
        value = int(raw)
        ts = value / 1000 if value > 100000000000 else value
        return datetime.fromtimestamp(ts, timezone.utc).isoformat()
    return first_match(html, r"<time[^>]+datetime=\"([^\"]+)\"")


def decode_jsonish_text(value):
    try:
        return json.loads(f'"{value}"')
    except Exception:
        return unescape(value or "")


def extract_comment_snippets(html):
    snippets = []
    for raw in re.findall(r'"commentary"\s*:\s*\{[^{}]*"text"\s*:\s*"((?:\\.|[^"\\]){25,})"', html, flags=re.I | re.S):
        text = clean_html_text(decode_jsonish_text(raw))
        if text and text not in snippets:
            snippets.append(text)
        if len(snippets) >= 5:
            break
    return [{"author": "LinkedIn member", "text": text} for text in snippets]


def extract_reaction_counts(html):
    lowered = html.lower()
    likes = first_int(first_match(lowered, r"(\d[\d,]*)\s+(?:reactions|likes)"))
    comments = first_int(first_match(lowered, r"(\d[\d,]*)\s+comments?"))
    reposts = first_int(first_match(lowered, r"(\d[\d,]*)\s+reposts?"))
    return {"likes": likes, "comments": comments, "reposts": reposts}


def first_int(value):
    try:
        return int(str(value or "0").replace(",", ""))
    except ValueError:
        return 0
