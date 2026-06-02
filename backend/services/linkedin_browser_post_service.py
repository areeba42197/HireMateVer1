"""
Browser-rendered LinkedIn post collection.

This follows the practical shape of small Selenium LinkedIn post scrapers:
open content search in a browser, let LinkedIn render feed cards, expand visible
post text, scroll gently, and extract only the rendered post fields. It is kept
separate from the jobs scraper because it is slower, more fragile, and depends
on a local browser/driver being available on the user's PC.
"""

import hashlib
import os
import re
import time
from datetime import datetime, timezone
from html import unescape
from http.cookies import SimpleCookie
from urllib.parse import quote_plus

from core.config import LINKEDIN_MAX_RESULTS_PER_SYNC, LINKEDIN_MAX_SEARCH_QUERIES
from services.linkedin_service import ai_keywords, split_csv


HIRING_SIGNAL = re.compile(
    r"(hiring|we are hiring|we're hiring|looking for|job opening|vacancy|internship|developer|engineer|remote|apply|send your cv|dm me)",
    re.I,
)


def collect_posts_with_browser(user, keyword_offset=0, max_posts=8, scrolls=3, exact_link_limit=8, include_meta=False):
    """Collect rendered LinkedIn post cards through Selenium.

    The function uses the user's encrypted cookie after the caller decrypts it.
    It does not try to defeat checkpoints or CAPTCHAs; if LinkedIn asks for a
    manual check, the collection stops and returns a clear error.
    """
    cookie_header = user.get("linkedin_cookie", "")
    if not cookie_header:
        result = ([], ["No LinkedIn session cookie saved."])
        return (*result, {"keywords_used": [], "keyword_count": 0}) if include_meta else result

    keywords = browser_post_keywords(user)
    if not keywords:
        result = ([], ["Add skills, interests, or target roles before collecting posts."])
        return (*result, {"keywords_used": [], "keyword_count": 0}) if include_meta else result

    try:
        webdriver, by, wait, expected_conditions, options_cls = import_selenium()
    except Exception as exc:
        result = ([], [f"Selenium is not ready on this PC: {exc}"])
        return (*result, {"keywords_used": [], "keyword_count": len(keywords)}) if include_meta else result

    shift = int(keyword_offset or 0) % len(keywords)
    all_keywords = keywords
    keywords = all_keywords[shift:] + all_keywords[:shift]
    selected_keywords = keywords[:LINKEDIN_MAX_SEARCH_QUERIES]
    driver = None
    posts = []
    errors = []
    keywords_used = []
    try:
        driver = make_driver(webdriver, options_cls, user)
        seed_linkedin_cookies(driver, cookie_header)
        for keyword in selected_keywords:
            if len(posts) >= max_posts:
                break
            keywords_used.append(keyword)
            try:
                found = collect_keyword_cards(
                    driver,
                    by,
                    wait,
                    expected_conditions,
                    keyword,
                    max_posts=max_posts - len(posts),
                    scrolls=scrolls,
                    exact_link_limit=max(0, exact_link_limit - len(posts)),
                )
            except Exception as exc:
                errors.append(f"browser:{keyword}:{exc}")
                continue
            if found:
                posts.extend(found)
            else:
                errors.append(f"browser:{keyword}:0 rendered posts")
            time.sleep(1.2)
    except Exception as exc:
        errors.append(f"browser:{exc}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    deduped = {}
    for post in posts:
        deduped[post["source_post_id"]] = post
    result = (list(deduped.values())[: min(max_posts, LINKEDIN_MAX_RESULTS_PER_SYNC)], errors)
    meta = {"keywords_used": keywords_used, "keyword_count": len(all_keywords)}
    return (*result, meta) if include_meta else result


def browser_post_keywords(user):
    """Use AI profile keywords first, then fall back to broad profile terms."""
    ai_terms = ai_keywords(user, purpose="posts")
    if ai_terms:
        return list(dict.fromkeys([term for term in ai_terms if str(term).strip()]))[:40]
    skills = split_csv(user.get("skills", ""))
    interests = split_csv(user.get("interests", ""))
    roles = split_csv(user.get("target_roles", "")) or skills[:3]
    terms = []
    for role in roles[:4]:
        terms.extend([role, f"{role} hiring"])
        if user.get("experience_level"):
            terms.append(f"{role} {user.get('experience_level')} hiring")
        for mode in split_csv(user.get("work_modes", ""))[:2]:
            terms.append(f"{role} {mode} hiring")
        for location in split_csv(user.get("preferred_locations", ""))[:2]:
            terms.append(f"{role} {location}")
    for skill in skills[:5]:
        terms.extend([skill, f"{skill} hiring"])
        if roles:
            terms.append(f"{roles[0]} {skill}")
    for interest in interests[:4]:
        if roles:
            terms.append(f"{roles[0]} {interest}")
        else:
            terms.append(interest)
    return list(dict.fromkeys([term for term in terms if term.strip()]))


def import_selenium():
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options

    return webdriver, By, WebDriverWait, EC, Options


def make_driver(webdriver, options_cls, user):
    if os.environ.get("VERCEL") or os.environ.get("CI"):
        os.environ.setdefault("SE_CACHE_PATH", "/tmp/selenium")
    options = options_cls()
    options.add_argument("--window-size=1365,900")
    options.set_capability("pageLoadStrategy", "eager")
    options.add_argument("--lang=en-US")
    if os.environ.get("VERCEL") or os.environ.get("CI"):
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--single-process")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-dev-shm-usage")
    if user.get("linkedin_user_agent"):
        options.add_argument(f"--user-agent={user['linkedin_user_agent']}")
    chrome_bin = os.environ.get("CHROME_BIN", "").strip()
    if chrome_bin:
        options.binary_location = chrome_bin
    driver_path = os.environ.get("CHROMEDRIVER_PATH", "").strip()
    if driver_path:
        from selenium.webdriver.chrome.service import Service

        driver = webdriver.Chrome(service=Service(driver_path), options=options)
    else:
        driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(16)
    driver.set_script_timeout(15)
    return driver


def safe_get(driver, url, wait_seconds=1.5):
    """Open a page without letting a slow LinkedIn render abort collection."""
    try:
        driver.get(url)
    except Exception:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
    time.sleep(wait_seconds)


def seed_linkedin_cookies(driver, cookie_header):
    safe_get(driver, "https://www.linkedin.com/", 1.2)
    for cookie in parse_cookie_header(cookie_header):
        try:
            driver.add_cookie(cookie)
        except Exception:
            continue
    safe_get(driver, "https://www.linkedin.com/feed/", 1.8)


def parse_cookie_header(cookie_header):
    raw = (cookie_header or "").strip()
    if raw and "=" not in raw:
        raw = "li_at=" + raw
    parsed = SimpleCookie()
    parsed.load(raw)
    cookies = []
    for name, morsel in parsed.items():
        value = morsel.value
        if not value:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": ".linkedin.com",
                "path": "/",
                "secure": True,
            }
        )
    return cookies


def collect_keyword_cards(driver, by, wait, expected_conditions, keyword, max_posts=8, scrolls=3, exact_link_limit=8):
    encoded = quote_plus(keyword)
    url = f"https://www.linkedin.com/search/results/content/?keywords={encoded}&origin=GLOBAL_SEARCH_HEADER"
    safe_get(driver, url, 1.8)
    rendered_posts = []
    seen = set()
    resolved_links = 0
    try:
        wait(driver, 4).until(
            expected_conditions.presence_of_element_located(
                (by.CSS_SELECTOR, post_card_selector())
            )
        )
    except Exception:
        if page_needs_attention(driver):
            raise RuntimeError("LinkedIn needs manual login/checkpoint before posts can render.")
        prepare_visible_text_page(driver, by, scrolls)
        return extract_posts_from_visible_text(driver, by, keyword, max_posts, url, exact_link_limit)

    for _ in range(max(1, int(scrolls or 1))):
        expand_visible_posts(driver, by)
        cards = driver.find_elements(by.CSS_SELECTOR, post_card_selector())
        for card in cards:
            post = extract_card(card, by, keyword)
            if not post:
                continue
            if post.get("post_url") and resolved_links < exact_link_limit:
                if not verify_exact_post_url_preserving_page(driver, by, post["post_url"], post["post_text"]):
                    post["post_url"] = ""
                    post["source_post_id"] = "linkedin-browser-" + stable_id(post["post_text"])
                resolved_links += 1
            if (
                not post.get("post_url")
                and resolved_links < exact_link_limit
                and post.get("reaction_items", {}).get("author_profile_url")
            ):
                resolved = resolve_post_url_from_author_activity(
                    driver,
                    by,
                    post["reaction_items"]["author_profile_url"],
                    post["post_text"],
                )
                if resolved:
                    post["post_url"] = resolved
                    post["source_post_id"] = "linkedin-browser-" + stable_id(resolved)
                resolved_links += 1
            key = post["post_url"] or post["post_text"][:220]
            if key in seen:
                continue
            seen.add(key)
            rendered_posts.append(post)
            if len(rendered_posts) >= max_posts:
                return rendered_posts
        try:
            driver.execute_script("window.scrollBy(0, Math.max(500, window.innerHeight * 0.85));")
        except Exception:
            break
        time.sleep(2.2)
    if not rendered_posts:
        prepare_visible_text_page(driver, by, scrolls)
        rendered_posts.extend(extract_posts_from_visible_text(driver, by, keyword, max_posts, url, exact_link_limit))
    return rendered_posts


def post_card_selector():
    return ".feed-shared-update-v2, .update-components-update-v2, [data-urn*='activity'], div[data-id*='urn:li:activity'], article"


def page_needs_attention(driver):
    try:
        text = clean_text(driver.page_source).lower()
    except Exception:
        return False
    return any(term in text for term in ("checkpoint", "captcha", "sign in", "authwall", "security verification"))


def prepare_visible_text_page(driver, by, scrolls):
    """Expand visible text and load a modest number of additional post cards."""
    for _ in range(max(1, int(scrolls or 1))):
        expand_visible_posts(driver, by)
        try:
            driver.execute_script("window.scrollBy(0, Math.max(520, window.innerHeight * 0.9));")
        except Exception:
            break
        time.sleep(1.4)
    expand_visible_posts(driver, by)


def expand_visible_posts(driver, by):
    scrollable_script = "arguments[0].scrollIntoView({block:'center', inline:'nearest'});"
    selectors = [
        ".feed-shared-inline-show-more-text",
        ".feed-shared-inline-show-more-text__see-more-less-toggle",
        "button[aria-label*='see more' i]",
        "button[aria-label*='show more' i]",
        "button[aria-label*='See more' i]",
        "button[aria-expanded='false']",
    ]
    for selector in selectors:
        for button in driver.find_elements(by.CSS_SELECTOR, selector)[:24]:
            try:
                label = clean_text((button.get_attribute("aria-label") or "") + " " + button.text).lower()
                if selector == "button[aria-expanded='false']" and "more" not in label:
                    continue
                driver.execute_script(scrollable_script, button)
                time.sleep(0.15)
                driver.execute_script("arguments[0].click();", button)
                time.sleep(0.25)
            except Exception:
                continue
    # Some LinkedIn builds render the control as plain visible text inside the
    # post body. Clicking by text is a fallback for those hashed-class pages.
    for xpath in [
        "//*[normalize-space()='â€¦more']",
        "//*[normalize-space()='...more']",
        "//*[normalize-space()='more']",
        "//*[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'see more')]",
    ]:
        for element in driver.find_elements(by.XPATH, xpath)[:24]:
            try:
                driver.execute_script(scrollable_script, element)
                time.sleep(0.15)
                driver.execute_script("arguments[0].click();", element)
                time.sleep(0.25)
            except Exception:
                continue


def extract_card(card, by, keyword):
    text = first_text(
        card,
        by,
        [
            ".feed-shared-update-v2__description-wrapper",
            ".update-components-text",
            ".feed-shared-text",
        ],
    ) or clean_text(card.text)
    if len(text) < 80:
        return None
    author = first_text(
        card,
        by,
        [
            ".update-components-actor__name",
            ".update-components-actor__title",
            ".feed-shared-actor__name",
            ".feed-shared-actor__title",
        ],
    )
    author_title = first_text(
        card,
        by,
        [
            ".update-components-actor__description",
            ".feed-shared-actor__description",
            ".update-components-actor__sub-description",
        ],
    )
    url = first_href(card, by)
    author_profile_url = first_author_profile_href(card, by)
    full_text = clean_text(card.text)
    posted_label = first_posted_label((card.text or "").splitlines())
    return {
        "source_post_id": "linkedin-browser-" + stable_id(url or text),
        "lead_kind": "post",
        "company": author or "LinkedIn Post",
        "role_title": "",
        "author_name": author,
        "author_title": author_title,
        "post_text": text,
        "post_url": url,
        "likes": count_metric(full_text, "reactions?") or count_metric(full_text, "likes?"),
        "comments": count_metric(full_text, "comments?"),
        "reposts": count_metric(full_text, "reposts?"),
        "posted_at": relative_label_to_iso(posted_label) or datetime.now(timezone.utc).isoformat(),
        "comment_items": [],
        "reaction_items": {
            "source": "selenium-rendered",
            "query": keyword,
            "posted_label": posted_label,
            "author_profile_url": author_profile_url,
            "source_search_url": f"https://www.linkedin.com/search/results/content/?keywords={quote_plus(keyword)}&origin=GLOBAL_SEARCH_HEADER",
        },
    }


def extract_posts_from_visible_text(driver, by, keyword, max_posts=8, search_url="", exact_link_limit=8):
    """Fallback for LinkedIn pages that render posts with hashed class names."""
    try:
        body = driver.find_element(by.TAG_NAME, "body").text
    except Exception:
        return []
    blocks = re.split(r"(?:^|\n)Feed post(?:\n|$)", body)
    posts = []
    for block in blocks:
        if len(posts) >= max_posts:
            break
        post = extract_visible_text_block(block, keyword, "", search_url, "")
        if post:
            posts.append(post)
    return posts


def visible_post_urls(driver, by):
    urls = []
    for selector in ["a[href*='/feed/update/']", "a[href*='/posts/']", "a[href*='activity-']"]:
        for anchor in driver.find_elements(by.CSS_SELECTOR, selector):
            try:
                href = (anchor.get_attribute("href") or "").split("?")[0]
            except Exception:
                href = ""
            href = normalize_post_url(href)
            if href and href not in urls:
                urls.append(href)
    return urls


def visible_author_profile_urls(driver, by):
    urls = []
    for anchor in driver.find_elements(by.CSS_SELECTOR, "a[href*='linkedin.com/in/']"):
        try:
            href = (anchor.get_attribute("href") or "").split("?")[0]
            text = clean_text(anchor.text)
        except Exception:
            href = ""
            text = ""
        if href and text and href not in urls:
            urls.append(href.rstrip("/") + "/")
    return urls


def extract_visible_text_block(block, keyword, post_url="", search_url="", author_profile_url=""):
    lines = [clean_line(line) for line in (block or "").splitlines()]
    lines = [line for line in lines if line]
    if len(lines) < 6:
        return None
    author = lines[0]
    if looks_like_navigation_author(author):
        return None
    author_title = ""
    for line in lines[1:5]:
        if not re.search(r"^(3rd\+|2nd|1st|follow|\d+[hmwd]|edited)$", line, flags=re.I):
            author_title = line
            break
    start = next((idx + 1 for idx, line in enumerate(lines[:12]) if line.lower() == "follow"), 4)
    end = len(lines)
    for idx, line in enumerate(lines[start:], start=start):
        lowered = line.lower()
        if lowered in {"like", "comment", "repost", "send"} or lowered == "view job":
            end = idx
            break
    content_lines = [
        line
        for line in lines[start:end]
        if line.lower() not in {"more", "see more", "...more", "â€¦more"} and not re.fullmatch(r"\d+", line)
    ]
    text = clean_post_content(content_lines)
    if len(clean_text(text)) < 80:
        return None
    posted_label = first_posted_label(lines)
    key = post_url or f"{keyword}|{author}|{text[:220]}"
    return {
        "source_post_id": "linkedin-browser-text-" + stable_id(key),
        "lead_kind": "post",
        "company": author or "LinkedIn Post",
        "role_title": "",
        "author_name": author,
        "author_title": author_title,
        "post_text": text,
        "post_url": post_url,
        "likes": count_visible_metric(lines, "reaction"),
        "comments": count_visible_metric(lines, "comment"),
        "reposts": count_visible_metric(lines, "repost"),
        "posted_at": relative_label_to_iso(posted_label) or datetime.now(timezone.utc).isoformat(),
        "comment_items": [],
        "reaction_items": {
            "source": "selenium-rendered-text",
            "query": keyword,
            "posted_label": posted_label,
            "source_search_url": search_url,
            "author_profile_url": author_profile_url,
        },
    }


def resolve_post_url_from_author_activity(driver, by, author_profile_url, post_text):
    """Best-effort exact permalink recovery from the author's recent activity."""
    if not author_profile_url:
        return ""
    original_url = driver.current_url
    try:
        activity_url = author_profile_url.rstrip("/") + "/recent-activity/all/"
        safe_get(driver, activity_url, 2.5)
        expand_visible_posts(driver, by)
        candidates = []
        for selector in ["a[href*='/feed/update/']", "a[href*='/posts/']", "a[href*='activity-']"]:
            for anchor in driver.find_elements(by.CSS_SELECTOR, selector):
                href = normalize_post_url(anchor.get_attribute("href") or "")
                if href and href not in candidates:
                    candidates.append(href)
        body = clean_text(driver.find_element(by.TAG_NAME, "body").text)
        exact = best_activity_url_for_text(body, driver.page_source or "", post_text, candidates)
        if exact and verify_exact_post_url_preserving_page(driver, by, exact, post_text):
            return exact
    except Exception:
        return ""
    finally:
        try:
            safe_get(driver, original_url, 1.2)
        except Exception:
            pass
    return ""


def normalize_post_url(url):
    """Return only exact LinkedIn post permalinks, never profile/search URLs."""
    href = (url or "").split("?")[0].strip()
    if href.startswith("/feed/update/") or href.startswith("/posts/"):
        href = "https://www.linkedin.com" + href
    activity = re.search(r"urn:li:activity:(\d+)", href)
    if activity:
        return "https://www.linkedin.com/feed/update/urn:li:activity:" + activity.group(1) + "/"
    if re.search(r"/posts/[^/]*activity[-:](\d+)", href):
        activity_id = re.search(r"/posts/[^/]*activity[-:](\d+)", href).group(1)
        return "https://www.linkedin.com/feed/update/urn:li:activity:" + activity_id + "/"
    if "/feed/update/" in href and "linkedin.com" in href:
        return href.rstrip("/") + "/"
    return ""


def verify_exact_post_url_preserving_page(driver, by, url, post_text):
    original_url = driver.current_url
    try:
        return verify_exact_post_url(driver, by, normalize_post_url(url), post_text)
    finally:
        try:
            if original_url and driver.current_url != original_url:
                safe_get(driver, original_url, 1.2)
        except Exception:
            pass


def similar_post_text(page_text, post_text):
    words = [word for word in re.findall(r"[A-Za-z0-9+#.]{4,}", post_text.lower()) if word not in {"with", "this", "that", "from", "have"}]
    if not words:
        return False
    sample = words[:18]
    hits = sum(1 for word in sample if word in page_text.lower())
    return hits >= max(5, len(sample) // 2)


def best_activity_url_for_text(activity_text, page_source, post_text, candidate_urls=None):
    activity_ids = unique_activity_ids(page_source)
    candidate_urls = candidate_urls or []
    target_words = important_words(post_text)
    if not target_words:
        return ""
    blocks = re.split(r"(?:^|\n)Feed post number \d+(?:\n|$)", activity_text or "")
    best = {"score": 0, "phrase": 0, "index": -1, "activity_id": ""}
    runner_up = 0

    # The visible activity stream is the strongest signal because it contains
    # the same rendered text that was scraped from search. The IDs can appear
    # many times in LinkedIn's page source, so we keep their first-seen order.
    for index, block in enumerate(blocks[1:]):
        score = text_overlap_score(block, target_words)
        phrase = phrase_match_score(block, post_text)
        weighted = score + (phrase * 4)
        if weighted > best["score"] + (best["phrase"] * 4):
            runner_up = best["score"] + (best["phrase"] * 4)
            best = {
                "score": score,
                "phrase": phrase,
                "index": index,
                "activity_id": activity_ids[index] if index < len(activity_ids) else "",
            }
        elif weighted > runner_up:
            runner_up = weighted

    # Fallback for LinkedIn builds where visible post blocks and hidden activity
    # IDs are not in the same order. Score the HTML/JSON window around each
    # activity id and pick the one whose surrounding payload contains the post.
    source_matches = best_activity_id_from_source_windows(page_source, post_text, target_words)
    if source_matches:
        source_id, source_score, source_phrase, second_score = source_matches
        source_weighted = source_score + (source_phrase * 4)
        if source_weighted > best["score"] + (best["phrase"] * 4):
            runner_up = max(runner_up, second_score)
            best = {"score": source_score, "phrase": source_phrase, "index": -1, "activity_id": source_id}

    threshold = strict_match_threshold(target_words)
    weighted_best = best["score"] + (best["phrase"] * 4)
    if best["score"] < threshold and best["phrase"] < 2:
        return ""
    if runner_up and weighted_best - runner_up < 3 and best["phrase"] == 0:
        return ""
    if best["activity_id"]:
        return "https://www.linkedin.com/feed/update/urn:li:activity:" + best["activity_id"] + "/"
    if best["index"] < len(candidate_urls):
        return candidate_urls[best["index"]]
    if len(activity_ids) == 1 and best["score"] >= threshold:
        return "https://www.linkedin.com/feed/update/urn:li:activity:" + activity_ids[0] + "/"
    return ""


def verify_exact_post_url(driver, by, url, post_text):
    """Open the candidate permalink and verify it renders the same post text."""
    if not url or "linkedin.com/feed/update/" not in url:
        return False
    try:
        safe_get(driver, url, 2.5)
        expand_visible_posts(driver, by)
        driver.execute_script("window.scrollBy(0, Math.max(250, window.innerHeight * 0.35));")
        time.sleep(1.0)
        expand_visible_posts(driver, by)
        body = clean_post_content(driver.find_element(by.TAG_NAME, "body").text.splitlines())
        target_words = important_words(post_text)
        if not target_words:
            return False
        score = text_overlap_score(body, target_words)
        phrase = phrase_match_score(body, post_text)
        return score >= strict_match_threshold(target_words) or (phrase >= 2 and score >= max(5, strict_match_threshold(target_words) - 5))
    except Exception:
        return False


def strict_match_threshold(target_words):
    sample_size = min(30, len(target_words))
    return max(8, int(sample_size * 0.68))


def unique_activity_ids(page_source):
    ids = []
    for activity_id in re.findall(r"urn:li:activity:(\d+)", page_source or ""):
        if activity_id not in ids:
            ids.append(activity_id)
    return ids


def best_activity_id_from_source_windows(page_source, post_text, target_words):
    """Find the activity id whose nearby HTML/JSON best matches the post text."""
    if not page_source:
        return None
    best = ("", 0, 0, 0)
    second = 0
    for activity_id in unique_activity_ids(page_source):
        score = 0
        phrase = 0
        pattern = re.escape("urn:li:activity:" + activity_id)
        for match in re.finditer(pattern, page_source):
            start = max(0, match.start() - 9000)
            end = min(len(page_source), match.end() + 9000)
            window = htmlish_to_text(page_source[start:end])
            score = max(score, text_overlap_score(window, target_words))
            phrase = max(phrase, phrase_match_score(window, post_text))
        weighted = score + (phrase * 4)
        if weighted > best[1] + (best[2] * 4):
            second = best[1] + (best[2] * 4)
            best = (activity_id, score, phrase, second)
        elif weighted > second:
            second = weighted
    if not best[0]:
        return None
    return best[0], best[1], best[2], second


def phrase_match_score(text, post_text):
    """Count longer human-readable phrases that appear in both texts."""
    haystack = normalize_for_match(text)
    score = 0
    for phrase in key_phrases(post_text):
        if phrase and phrase in haystack:
            score += 1
    return score


def key_phrases(post_text):
    phrases = []
    for line in (post_text or "").splitlines():
        cleaned = normalize_for_match(line)
        if len(cleaned) >= 34:
            phrases.append(cleaned[:120])
    if phrases:
        return phrases[:5]
    words = important_words(post_text)
    return [" ".join(words[index : index + 6]) for index in range(0, max(0, len(words) - 5), 3)][:5]


def normalize_for_match(text):
    return clean_text(text).lower()


def htmlish_to_text(value):
    value = unescape(value or "")
    value = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\\n", " ").replace("\\\"", '"')
    return clean_text(value)


def important_words(text):
    stop = {"with", "this", "that", "from", "have", "your", "will", "about", "what", "when", "where", "there", "their", "they", "looking"}
    words = []
    for word in re.findall(r"[A-Za-z0-9+#.]{4,}", (text or "").lower()):
        if word not in stop and word not in words:
            words.append(word)
    return words[:30]


def text_overlap_score(text, target_words):
    lowered = (text or "").lower()
    return sum(1 for word in target_words[:30] if word in lowered)


def looks_like_navigation_author(value):
    lowered = clean_text(value).lower()
    return (
        not lowered
        or lowered.endswith("notifications")
        or lowered in {"home", "my network", "jobs", "messaging", "notifications", "me", "for business", "posts"}
    )


def count_visible_metric(lines, metric):
    joined = " ".join(lines)
    if metric == "reaction":
        return count_metric(joined, "reactions?")
    return count_metric(joined, metric + "s?")


def first_posted_label(lines):
    for line in lines[:10]:
        match = re.search(r"\b(\d+)\s*([hmwd])\b", line.lower())
        if match:
            unit = {"h": "hours", "m": "minutes", "d": "days", "w": "weeks"}.get(match.group(2), "hours")
            return f"{match.group(1)} {unit} ago"
    return ""


def relative_label_to_iso(label):
    match = re.search(r"\b(\d+)\s+(minutes?|hours?|days?|weeks?)\s+ago\b", label or "", flags=re.I)
    if not match:
        return ""
    amount = int(match.group(1))
    unit = match.group(2).lower()
    seconds = {
        "minute": 60,
        "minutes": 60,
        "hour": 3600,
        "hours": 3600,
        "day": 86400,
        "days": 86400,
        "week": 604800,
        "weeks": 604800,
    }.get(unit, 0)
    if not seconds:
        return ""
    return datetime.fromtimestamp(time.time() - amount * seconds, timezone.utc).isoformat()


def first_text(card, by, selectors):
    for selector in selectors:
        try:
            value = clean_text(card.find_element(by.CSS_SELECTOR, selector).text)
            if value:
                return value
        except Exception:
            continue
    return ""


def first_href(card, by):
    selectors = ["a[href*='/feed/update/']", "a[href*='/posts/']", "a[href*='activity-']"]
    for selector in selectors:
        try:
            href = normalize_post_url(card.find_element(by.CSS_SELECTOR, selector).get_attribute("href") or "")
            if href:
                return href
        except Exception:
            continue
    return ""


def first_author_profile_href(card, by):
    for selector in ["a[href*='linkedin.com/in/']", "a[href^='/in/']"]:
        try:
            href = (card.find_element(by.CSS_SELECTOR, selector).get_attribute("href") or "").split("?")[0]
            if href:
                if href.startswith("/in/"):
                    href = "https://www.linkedin.com" + href
                return href.rstrip("/") + "/"
        except Exception:
            continue
    return ""


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def clean_line(value):
    return re.sub(r"[ \t]+", " ", value or "").strip()


def clean_post_content(lines):
    cleaned = []
    previous_blank = False
    for line in lines:
        line = clean_line(line)
        if not line:
            if not previous_blank:
                cleaned.append("")
            previous_blank = True
            continue
        cleaned.append(line)
        previous_blank = False
    return "\n".join(cleaned).strip()


def count_metric(text, word):
    match = re.search(r"(\d[\d,]*)\s+" + word, text or "", flags=re.I)
    return int(match.group(1).replace(",", "")) if match else 0


def stable_id(value):
    return hashlib.sha1((value or "").encode("utf-8", errors="ignore")).hexdigest()[:16]











