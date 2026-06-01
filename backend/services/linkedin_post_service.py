"""
LinkedIn post collection for HireMate.

This module is intentionally separate from the jobs scraper. It only attempts
authenticated content/post search using the user's saved LinkedIn session cookie
and never falls back to job results. Keep the request volume small: LinkedIn
content pages are fragile, personalized, and may return redirects or sparse
HTML/JSON when it does not want to expose readable post data.
"""

from core.config import LINKEDIN_MAX_RESULTS_PER_SYNC, LINKEDIN_MAX_SEARCH_QUERIES
from services.linkedin_service import (
    LinkedInSession,
    ai_keywords,
    build_keywords,
    extract_posts_from_html,
    extract_posts_from_json,
    is_block_signal,
    looks_logged_out,
    page_is_blocked,
    polite_delay,
    split_csv,
    unique_posts,
)
from urllib.parse import quote_plus


def collect_posts_for_profile(user, keyword_offset=0, result_start=0, include_meta=False):
    """Return LinkedIn post-like leads for a user profile.

    The collector uses content-only LinkedIn search surfaces. It requires a
    fresh cookie that includes `li_at`; a full Cookie header with `JSESSIONID`
    is more reliable because Voyager endpoints use that value as a CSRF token.
    """
    cookie = user.get("linkedin_cookie", "")
    if not cookie:
        result = ([], ["No LinkedIn session cookie saved."])
        return (*result, {"keywords_used": [], "keyword_count": 0}) if include_meta else result

    keywords = profile_keywords(user)
    if not keywords:
        result = ([], ["Add target roles, skills, or interests before collecting posts."])
        return (*result, {"keywords_used": [], "keyword_count": 0}) if include_meta else result

    shift = int(keyword_offset or 0) % len(keywords)
    keywords = keywords[shift:] + keywords[:shift]
    selected_keywords = keywords[:LINKEDIN_MAX_SEARCH_QUERIES]
    session = LinkedInSession(
        cookie,
        user_agent=user.get("linkedin_user_agent", ""),
        accept_language=user.get("linkedin_accept_language", ""),
    )
    collected = []
    errors = []

    try:
        session.bootstrap()
    except Exception as exc:
        result = ([], [f"LinkedIn session bootstrap failed: {exc}"])
        meta = {"keywords_used": selected_keywords, "keyword_count": len(keywords)}
        return (*result, meta) if include_meta else result

    for keyword in selected_keywords:
        if len(collected) >= LINKEDIN_MAX_RESULTS_PER_SYNC:
            break
        polite_delay()
        try:
            found, keyword_errors = collect_posts_for_keyword(session, keyword, int(result_start or 0))
            collected.extend(found)
            errors.extend(keyword_errors)
        except Exception as exc:
            errors.append(f"posts:{keyword}:{exc}")
            if is_block_signal(str(exc)):
                break

    posts = list(unique_posts(collected).values())[:LINKEDIN_MAX_RESULTS_PER_SYNC]
    if not posts and not errors:
        errors.append("LinkedIn did not expose readable post content for these filters.")
    result = (posts, errors)
    meta = {"keywords_used": selected_keywords, "keyword_count": len(keywords)}
    return (*result, meta) if include_meta else result


def profile_keywords(user):
    """Use AI-generated post keywords first, then profile-only terms as backup."""
    terms = ai_keywords(user, purpose="posts")
    if terms:
        return terms
    skills = split_csv(user.get("skills", ""))
    interests = split_csv(user.get("interests", ""))
    roles = split_csv(user.get("target_roles", "")) or skills[:3]
    return build_keywords(
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


def collect_posts_for_keyword(session, keyword, result_start=0):
    encoded = quote_plus(keyword)
    posts = []
    errors = []

    # Browser HTML content search sometimes includes embedded post text.
    html = session.open_text(
        f"https://www.linkedin.com/search/results/content/?keywords={encoded}&origin=GLOBAL_SEARCH_HEADER",
        accept="text/html,application/xhtml+xml",
    )
    if page_is_blocked(html):
        raise RuntimeError("LinkedIn checkpoint/CAPTCHA detected. Post collection stopped.")
    if looks_logged_out(html):
        raise RuntimeError("LinkedIn returned a logged-out page. Save a fresh full Cookie header.")
    html_posts = extract_posts_from_html(html)
    posts.extend(html_posts)
    if not html_posts:
        errors.append(f"html:{keyword}:0 readable posts")

    # Voyager's normalized JSON search is often cleaner when the cookie includes
    # JSESSIONID for CSRF. If it fails, keep any HTML posts already found.
    try:
        voyager = session.open_text(
            "https://www.linkedin.com/voyager/api/search/blended"
            + f"?count=10&filters=List(resultType-%3ECONTENT)&keywords={encoded}"
            + f"&origin=GLOBAL_SEARCH_HEADER&q=all&start={max(0, int(result_start or 0))}",
            accept="application/vnd.linkedin.normalized+json+2.1",
            restli=True,
        )
        json_posts = extract_posts_from_json(voyager)
        posts.extend(json_posts)
        if not json_posts:
            errors.append(f"voyager:{keyword}:0 readable posts")
    except Exception as exc:
        errors.append(f"voyager:{keyword}:{exc}")

    return posts, errors
