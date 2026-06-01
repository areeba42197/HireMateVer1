"""
Public LinkedIn post discovery.

This collector does not use ban-bypass techniques. It searches public web
indexes for LinkedIn post URLs that match the user's skills/interests and turns
the result snippets into post leads. When a public LinkedIn post page is readable
without a login wall, it enriches the snippet with the page text.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib import request
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

from core.config import LINKEDIN_MAX_RESULTS_PER_SYNC
from services.linkedin_service import LinkedInSession, ai_keywords, build_keywords, clean_html_text, polite_delay, split_csv
from services.post_analysis_service import analyze_post_text


PUBLIC_SEARCH_LIMIT = 8
PUBLIC_SEARCH_KEYWORD_BATCH = 4


def collect_public_linkedin_posts(user, keyword_offset=0, include_meta=False):
    keywords = public_post_keywords(user)
    if not keywords:
        result = ([], ["Add skills, interests, or target roles before public post search."])
        return (*result, {"keywords_used": [], "keyword_count": 0}) if include_meta else result

    shift = int(keyword_offset or 0) % len(keywords)
    keywords = keywords[shift:] + keywords[:shift]
    selected_keywords = keywords[:PUBLIC_SEARCH_KEYWORD_BATCH]
    posts = []
    errors = []

    for keyword in selected_keywords:
        if len(posts) >= PUBLIC_SEARCH_LIMIT:
            break
        polite_delay()
        try:
            results = search_duckduckgo_posts(keyword)
            if not results:
                errors.append(f"public-search:{keyword}:0 indexed post results")
            for result in results:
                if len(posts) >= PUBLIC_SEARCH_LIMIT:
                    break
                posts.append(public_result_to_post(result, keyword, user))
        except Exception as exc:
            errors.append(f"public-search:{keyword}:{exc}")

    deduped = {}
    for post in posts:
        deduped[post["source_post_id"]] = post
    if not deduped and not errors:
        errors.append("No indexed public LinkedIn posts matched this profile.")
    result = (list(deduped.values())[:LINKEDIN_MAX_RESULTS_PER_SYNC], errors)
    meta = {"keywords_used": selected_keywords, "keyword_count": len(keywords)}
    return (*result, meta) if include_meta else result


def public_post_keywords(user):
    ai_terms = ai_keywords(user, purpose="posts")
    if ai_terms:
        return [
            item
            for term in ai_terms[:20]
            for item in (f'site:linkedin.com/posts "{term}"', f'site:linkedin.com/feed/update "{term}"')
        ]
    skills = split_csv(user.get("skills", ""))
    interests = split_csv(user.get("interests", ""))
    roles = split_csv(user.get("target_roles", "")) or skills[:3]
    base = build_keywords(
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
    focused = []
    for term in base:
        term = term.replace("<", " ").replace(">", " ")
        focused.append(f'site:linkedin.com/posts "{term}"')
        focused.append(f'site:linkedin.com/feed/update "{term}"')
    return list(dict.fromkeys(focused))


def search_duckduckgo_posts(keyword):
    url = "https://duckduckgo.com/html/?q=" + quote_plus(keyword)
    req = request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with request.urlopen(req, timeout=15) as response:
        html = response.read().decode("utf-8", errors="ignore")
    return parse_duckduckgo_results(html)


def parse_duckduckgo_results(html):
    results = []
    blocks = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|</body>)', html, flags=re.I | re.S)
    for href, title_html, tail in blocks:
        link = unwrap_duckduckgo_url(unescape(href))
        if not is_linkedin_post_url(link):
            continue
        snippet = clean_html_text(first_match(tail, r'class="result__snippet"[^>]*>(.*?)</a>') or tail)
        title = clean_html_text(title_html)
        results.append({"url": link, "title": title, "snippet": snippet})
        if len(results) >= PUBLIC_SEARCH_LIMIT:
            break
    return results


def unwrap_duckduckgo_url(url):
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc:
        wrapped = parse_qs(parsed.query).get("uddg", [""])[0]
        if wrapped:
            return unquote(wrapped).split("?")[0]
    return url.split("?")[0]


def is_linkedin_post_url(url):
    lowered = (url or "").lower()
    return "linkedin.com/posts/" in lowered or "linkedin.com/feed/update/" in lowered


def public_result_to_post(result, keyword, user=None):
    enriched = enrich_public_post(result.get("url", ""), keyword, user)
    text = enriched.get("post_text") or fallback_public_post_text(result, keyword)
    if len(text) < 80:
        text = f"Public LinkedIn post result for {keyword}: {text}"
    url = result.get("url", "")
    public_author = enriched.get("author_name") or infer_public_author(result.get("title", ""), text)
    analysis = analyze_post_text(text, public_author, result.get("title", ""))
    company = public_author or analysis["company"]
    if company.lower().startswith("linkedin "):
        company = public_author or "LinkedIn Post"
    return {
        "source_post_id": "linkedin-public-post-" + stable_id(url or text),
        "lead_kind": "post",
        "company": company,
        "role_title": analysis["role_title"],
        "author_name": analysis["author_name"] or public_author,
        "author_title": enriched.get("author_title") or "LinkedIn",
        "post_text": text,
        "post_url": url,
        "likes": enriched.get("likes", 0),
        "comments": enriched.get("comments", 0),
        "reposts": enriched.get("reposts", 0),
        "posted_at": enriched.get("posted_at") or datetime.now(timezone.utc).isoformat(),
        "comment_items": enriched.get("comment_items", []),
        "reaction_items": {
            "source": enriched.get("source", "public web index"),
            "query": keyword,
            "summary": analysis["summary"],
            "posted_label": enriched.get("posted_label", ""),
            "source_search_url": "https://duckduckgo.com/html/?q=" + quote_plus(keyword),
        },
        "tags": analysis["tags"],
    }


def enrich_public_post(url, keyword, user=None):
    """Best-effort enrichment from the public LinkedIn post page.

    Public pages are inconsistent: sometimes LinkedIn exposes structured JSON,
    sometimes only meta snippets, and sometimes an authwall. Keep this tolerant
    and let the caller fall back to the search result snippet.
    """
    if not is_linkedin_post_url(url):
        return {}
    try:
        html = fetch_public_post_html(url, user)
    except Exception:
        return {}
    if page_requires_login(html):
        return {}
    payload = extract_public_post_payload(html)
    payload["source"] = "public linkedin page"
    payload["post_url"] = url
    payload.setdefault("reaction_items", {})
    payload["reaction_items"]["query"] = keyword
    return payload


def fetch_public_post_html(url, user=None):
    cookie = (user or {}).get("linkedin_cookie", "")
    if cookie:
        try:
            session = LinkedInSession(
                cookie,
                user_agent=(user or {}).get("linkedin_user_agent", ""),
                accept_language=(user or {}).get("linkedin_accept_language", ""),
            )
            return session.open_text(url, accept="text/html,application/xhtml+xml")
        except Exception:
            pass
    req = request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )
    with request.urlopen(req, timeout=12) as response:
        return response.read().decode("utf-8", errors="ignore")


def page_requires_login(html):
    text = clean_html_text(html[:12000]).lower()
    return any(term in text for term in ("authwall", "sign in to view", "join linkedin", "security verification", "checkpoint"))


def extract_public_post_payload(html):
    json_objects = extract_json_ld_objects(html)
    text = best_public_post_text(html, json_objects)
    author = best_public_author(html, json_objects)
    if author.get("title", "").strip().lower() == author.get("name", "").strip().lower():
        author["title"] = ""
    metrics = extract_public_metrics(html, json_objects)
    posted_at, posted_label = extract_public_time(html, json_objects)
    return {
        "post_text": text,
        "author_name": author.get("name", ""),
        "author_title": author.get("title", ""),
        "likes": metrics.get("likes", 0),
        "comments": metrics.get("comments", 0),
        "reposts": metrics.get("reposts", 0),
        "posted_at": posted_at,
        "posted_label": posted_label,
        "comment_items": extract_public_comments(html, json_objects),
    }


def extract_json_ld_objects(html):
    objects = []
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html or "", flags=re.I | re.S):
        try:
            data = json.loads(unescape(raw).strip())
        except Exception:
            continue
        if isinstance(data, list):
            objects.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                objects.extend(item for item in graph if isinstance(item, dict))
            objects.append(data)
    return objects


def best_public_post_text(html, json_objects):
    candidates = []
    decoded_html = unescape(html or "")
    for item in walk_dicts(json_objects):
        for key in ("articleBody", "text", "description", "commentary", "commentaryText"):
            value = item.get(key)
            if isinstance(value, str):
                candidates.append(value)
            elif isinstance(value, dict):
                nested = first_text_field(value)
                if nested:
                    candidates.append(nested)
    candidates.extend(meta_values(html, ("og:description", "twitter:description", "description")))
    for raw in re.findall(r'"(?:articleBody|text|description|commentary)"\s*:\s*"((?:\\.|[^"\\]){80,})"', decoded_html, flags=re.I | re.S):
        candidates.append(decode_jsonish_text(raw))
    candidates.extend(extract_linkedin_commentary_strings(decoded_html))
    cleaned = [clean_public_post_text(value) for value in candidates]
    cleaned = [value for value in cleaned if len(value) >= 80]
    if not cleaned:
        return ""
    return max(cleaned, key=len)[:5000]


def extract_linkedin_commentary_strings(html):
    values = []
    patterns = [
        r'"commentary"\s*:\s*\{[^{}]*"text"\s*:\s*"((?:\\.|[^"\\]){80,})"',
        r'"commentaryText"\s*:\s*"((?:\\.|[^"\\]){80,})"',
        r'"attributedText"\s*:\s*\{[^{}]*"text"\s*:\s*"((?:\\.|[^"\\]){80,})"',
        r'"textDirection"\s*:\s*"[^"]+"\s*,\s*"text"\s*:\s*"((?:\\.|[^"\\]){80,})"',
    ]
    for pattern in patterns:
        for raw in re.findall(pattern, html or "", flags=re.I | re.S):
            values.append(decode_jsonish_text(raw))
    return values


def best_public_author(html, json_objects):
    decoded_html = unescape(html or "")
    actor = extract_linkedin_actor(decoded_html)
    if actor.get("name"):
        if not actor.get("title"):
            actor["title"] = nearby_actor_title(decoded_html, actor["name"])
        return actor
    for item in walk_dicts(json_objects):
        author = item.get("author") or item.get("creator")
        if isinstance(author, dict):
            name = clean_html_text(author.get("name", ""))
            title = clean_html_text(author.get("jobTitle", "") or author.get("description", ""))
            if name:
                return {"name": name[:90], "title": title[:140]}
        if isinstance(author, str) and author.strip():
            return {"name": clean_html_text(author)[:90], "title": ""}
    title = first_meta_value(html, ("og:title", "twitter:title")) or first_match(html, r"<title[^>]*>(.*?)</title>")
    visible = clean_html_text(decoded_html)
    name = infer_public_author(title, visible)
    author_title = ""
    if name:
        author_title = first_match(visible, re.escape(name) + r"\s*(?:•|\|)?\s*([^•|]{8,120}?)\s+\d+\s*(?:m|h|d|w|mo|minute|hour|day|week|month)")
    return {"name": name, "title": clean_html_text(author_title)}


def nearby_actor_title(decoded_html, name):
    idx = decoded_html.find('"text":"' + name)
    if idx < 0:
        return ""
    window = decoded_html[max(0, idx - 2200) : idx + 600]
    title = first_match(window, r'"description"\s*:\s*\{.*?"text"\s*:\s*"([^"]{2,220})"')
    return clean_html_text(decode_jsonish_text(title))[:140]


def extract_linkedin_actor(decoded_html):
    name = first_match(decoded_html, r'"name"\s*:\s*\{[^{}]*"text"\s*:\s*"([^"]{2,120})"[^{}]*"accessibilityText"\s*:\s*"\1"')
    if name:
        name_text = clean_html_text(decode_jsonish_text(name))[:90]
        idx = decoded_html.find('"text":"' + name)
        window = decoded_html[max(0, idx - 2500) : idx + 800] if idx >= 0 else decoded_html
        title = first_match(window, r'"description"\s*:\s*\{[^{}]*"text"\s*:\s*"([^"]{2,220})"')
        return {"name": name_text, "title": clean_html_text(decode_jsonish_text(title))[:140]}
    blocks = re.findall(r'\$type":"com\.linkedin\.voyager\.dash\.feed\.component\.actor\.ActorComponent".{0,4500}', decoded_html or "", flags=re.S)
    for block in blocks:
        name = first_match(block, r'"name"\s*:\s*\{[^{}]*"text"\s*:\s*"([^"]{2,120})"')
        title = first_match(block, r'"description"\s*:\s*\{[^{}]*"text"\s*:\s*"([^"]{2,200})"')
        if name:
            return {"name": clean_html_text(decode_jsonish_text(name))[:90], "title": clean_html_text(decode_jsonish_text(title))[:140]}
    name = first_match(decoded_html, r'"firstName"\s*:\s*"([^"]+)","lastName"\s*:\s*"([^"]+)".{0,220}"publicIdentifier"\s*:\s*"[^"]+"')
    if name:
        return {"name": clean_html_text(name), "title": ""}
    return {"name": "", "title": ""}


def extract_public_metrics(html, json_objects):
    metrics = {"likes": 0, "comments": 0, "reposts": 0}
    decoded_html = unescape(html or "")
    activity_metrics = extract_linkedin_activity_metrics(decoded_html)
    if activity_metrics:
        metrics.update(activity_metrics)
    for item in walk_dicts(json_objects):
        stats = item.get("interactionStatistic")
        if isinstance(stats, dict):
            stats = [stats]
        if not isinstance(stats, list):
            continue
        for stat in stats:
            if not isinstance(stat, dict):
                continue
            count = first_int(stat.get("userInteractionCount") or stat.get("interactionCount"))
            label = json.dumps(stat, ensure_ascii=False).lower()
            if "comment" in label:
                metrics["comments"] = max(metrics["comments"], count)
            elif "share" in label or "repost" in label:
                metrics["reposts"] = max(metrics["reposts"], count)
            elif "like" in label or "reaction" in label:
                metrics["likes"] = max(metrics["likes"], count)
    visible = clean_html_text(decoded_html)
    metrics["likes"] = max(metrics["likes"], count_metric(visible, r"(?:reactions?|likes?)"))
    metrics["comments"] = max(metrics["comments"], count_metric(visible, r"comments?"))
    metrics["reposts"] = max(metrics["reposts"], count_metric(visible, r"(?:reposts?|shares?)"))
    return metrics


def extract_linkedin_activity_metrics(decoded_html):
    activity_id = first_match(decoded_html, r"urn:li:activity:(\d{8,})")
    if not activity_id:
        return {}
    block = ""
    pattern = r'\{[^{}]*"urn"\s*:\s*"urn:li:activity:' + re.escape(activity_id) + r'".{0,2600}?"entityUrn"\s*:\s*"urn:li:fsd_socialActivityCounts:urn:li:activity:' + re.escape(activity_id) + r'".{0,600}?\}'
    match = re.search(pattern, decoded_html, flags=re.S)
    if match:
        block = match.group(0)
    else:
        marker = '"entityUrn":"urn:li:fsd_socialActivityCounts:urn:li:activity:' + activity_id + '"'
        idx = decoded_html.find(marker)
        if idx >= 0:
            block = decoded_html[max(0, idx - 2200) : idx + 800]
    if not block:
        return {}
    likes = first_int(first_match(block, r'"numLikes"\s*:\s*(\d+)'))
    comments = first_int(first_match(block, r'"numComments"\s*:\s*(\d+)'))
    reposts = first_int(first_match(block, r'"numShares"\s*:\s*(\d+)'))
    if not likes:
        likes = sum(first_int(value) for value in re.findall(r'"count"\s*:\s*(\d+)\s*,\s*"reactionType"', block))
    return {"likes": likes, "comments": comments, "reposts": reposts}


def extract_public_time(html, json_objects):
    decoded_html = unescape(html or "")
    linked_label = first_match(decoded_html, r'"subDescription"\s*:\s*\{[^{}]*"text"\s*:\s*"([^"]*(?:mo|[mhdw])\s*•[^"]*)"')
    if linked_label:
        clean_label = clean_html_text(decode_jsonish_text(linked_label)).replace("•", "").strip()
        return relative_label_to_iso(clean_label), clean_label
    for item in walk_dicts(json_objects):
        for key in ("datePublished", "dateCreated", "uploadDate", "createdAt", "publishedAt"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), ""
    raw = first_match(decoded_html, r"<time[^>]+datetime=[\"']([^\"']+)")
    if raw:
        return raw, ""
    visible = clean_html_text(decoded_html)
    label = first_match(visible, r"\b(\d+\s*(?:m|h|d|w|mo|minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago)\b")
    if not label:
        label = first_match(visible, r"\b(\d+\s*(?:m|h|d|w|mo))\b\s*(?:Edited)?\s*(?:We are|Hiring|#|Location|Requirements)")
    return relative_label_to_iso(label), label


def extract_public_comments(html, json_objects):
    comments = []
    for item in walk_dicts(json_objects):
        if item.get("@type") and "comment" not in str(item.get("@type")).lower():
            continue
        text = first_text_field(item)
        if not text:
            continue
        author = item.get("author")
        author_name = ""
        if isinstance(author, dict):
            author_name = clean_html_text(author.get("name", ""))
        elif isinstance(author, str):
            author_name = clean_html_text(author)
        text = clean_public_post_text(text)
        if len(text) >= 20 and text not in [comment["text"] for comment in comments]:
            comments.append({"author": author_name or "LinkedIn member", "text": text[:800]})
        if len(comments) >= 5:
            break
    return comments


def walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def first_text_field(value):
    if not isinstance(value, dict):
        return ""
    for key in ("text", "articleBody", "description", "commentary"):
        child = value.get(key)
        if isinstance(child, str) and child.strip():
            return child
        if isinstance(child, dict):
            nested = first_text_field(child)
            if nested:
                return nested
    return ""


def meta_values(html, names):
    values = []
    for name in names:
        pattern = r'<meta[^>]+(?:property|name)=["\']' + re.escape(name) + r'["\'][^>]+content=["\']([^"\']+)'
        values.extend(unescape(match) for match in re.findall(pattern, html or "", flags=re.I | re.S))
        pattern = r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']' + re.escape(name) + r'["\']'
        values.extend(unescape(match) for match in re.findall(pattern, html or "", flags=re.I | re.S))
    return values


def first_meta_value(html, names):
    values = meta_values(html, names)
    return values[0] if values else ""


def clean_public_post_text(value):
    text = decode_jsonish_text(value)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = text.replace("\\n", "\n").replace("\\/", "/").replace('\\"', '"')
    text = re.sub(r"(?<!\n)\s+(Location:)", r"\n\n\1", text)
    text = re.sub(r"(?<!\n)\s+(Requirements:)", r"\n\n\1", text)
    text = re.sub(r"(?<!\n)\s+(Responsibilities:|Key Responsibilities:|Required Skills:|Skills Required:)", r"\n\n\1", text)
    text = re.sub(r"(?<!\n)\s+([•▪◦-]\s+)", r"\n\1", text)
    text = remove_placeholder_symbols(text)
    text = re.sub(r"\s*(?:\.\.\.|â€¦|…)\s*more\s*", " ", text, flags=re.I)
    text = re.sub(r"\bsee more\b", " ", text, flags=re.I)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line and line.lower() not in {"like", "comment", "repost", "send"}]
    return "\n".join(lines).strip()


def remove_placeholder_symbols(text):
    # Some Windows/browser extraction paths expose unsupported emoji as "??".
    # Keep genuine question punctuation, but remove standalone symbol runs that
    # sit where emoji/bullets were in the LinkedIn post.
    text = re.sub(r"(?m)^\s*\?{1,4}\s*$", "", text)
    text = re.sub(r"(?m)^\s*\?{1,4}\s+", "", text)
    text = re.sub(r"\s+\?{2,4}(?=\s|$)", " ", text)
    text = re.sub(r"(?<=\s)\?{2,4}\s+", "", text)
    return text


def fallback_public_post_text(result, keyword):
    snippet = clean_public_post_text(result.get("snippet", ""))
    title = clean_html_text(result.get("title", ""))
    if len(snippet) >= 80:
        return snippet
    title_text = re.sub(r"\s*-\s*LinkedIn\s*$", "", title, flags=re.I)
    return clean_public_post_text(" ".join(part for part in [title_text, snippet] if part).strip())


def decode_jsonish_text(value):
    value = value or ""
    try:
        return json.loads(f'"{value}"')
    except Exception:
        return unescape(value)


def count_metric(text, label_pattern):
    match = re.search(r"(\d[\d,]*(?:\.\d+)?\s*[KkMm]?)\s+" + label_pattern, text or "", flags=re.I)
    return compact_int(match.group(1)) if match else 0


def compact_int(value):
    raw = str(value or "0").replace(",", "").strip()
    match = re.match(r"(\d+(?:\.\d+)?)\s*([KkMm]?)", raw)
    if not match:
        return first_int(raw)
    number = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "k":
        number *= 1000
    elif suffix == "m":
        number *= 1000000
    return int(number)


def first_int(value):
    try:
        return int(str(value or "0").replace(",", ""))
    except (TypeError, ValueError):
        return 0


def relative_label_to_iso(label):
    match = re.search(r"\b(\d+)\s*(mo|m|h|d|w|minutes?|hours?|days?|weeks?|months?)(?:\s+ago)?\b", label or "", flags=re.I)
    if not match:
        return ""
    amount = int(match.group(1))
    unit = match.group(2).lower()
    seconds = {
        "m": 60,
        "minute": 60,
        "minutes": 60,
        "h": 3600,
        "hour": 3600,
        "hours": 3600,
        "d": 86400,
        "day": 86400,
        "days": 86400,
        "w": 604800,
        "week": 604800,
        "weeks": 604800,
        "mo": 2592000,
        "month": 2592000,
        "months": 2592000,
    }.get(unit, 0)
    if not seconds:
        return ""
    return datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - amount * seconds, timezone.utc).isoformat()


def infer_public_author(title, text=""):
    title = clean_html_text(title)
    parts = [part.strip() for part in re.split(r"\s+\|\s+", title) if part.strip()]
    if len(parts) >= 2 and "linkedin" not in parts[1].lower():
        return parts[1][:80]
    match = re.search(r"#\s*([A-Z][A-Za-z .'-]{2,80})[’']?s Post\b", text or title)
    if match:
        return match.group(1).strip()[:80]
    if " on linkedin" in title.lower():
        return title.split(" on LinkedIn")[0].strip()[:80] or "LinkedIn Public Post"
    if ":" in title:
        return title.split(":", 1)[0].strip()[:80] or "LinkedIn Public Post"
    return "LinkedIn Public Post"


def stable_id(value):
    return hashlib.sha1((value or "").encode("utf-8", errors="ignore")).hexdigest()[:16]


def first_match(text, pattern):
    match = re.search(pattern, text or "", flags=re.I | re.S)
    return match.group(1) if match else ""
