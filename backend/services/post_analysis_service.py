"""
LinkedIn post analysis helpers.

The post collectors intentionally stay small and source-focused: one collector
reads authenticated LinkedIn content search, one reads public search snippets,
and the browser collector reads visible feed cards. This module turns those raw
post bodies into structured lead fields that the rest of HireMate can trust.
"""

import re


GENERIC_AUTHORS = {
    "",
    "linkedin",
    "linkedin post",
    "linkedin public post",
    "public linkedin post",
}

GENERIC_ROLES = {
    "",
    "hiring opportunity",
    "linkedin public post",
    "linkedin hiring post",
    "public linkedin post",
}

ROLE_WORDS = (
    "developer",
    "engineer",
    "intern",
    "analyst",
    "scientist",
    "designer",
    "manager",
    "specialist",
    "assistant",
    "consultant",
    "executive",
    "architect",
    "administrator",
    "officer",
    "lead",
)

SKILL_LABELS = {
    "python": "Python",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "react": "React.js",
    "node": "Node.js",
    "sql": "SQL",
    "aws": "AWS",
    "azure": "Azure",
    "ai": "AI",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "data science": "Data Science",
    "nlp": "NLP",
    "llm": "LLM",
}


def analyze_post_text(text, author_name="", title_hint=""):
    """Return structured lead hints from raw LinkedIn post text."""
    clean_text = normalize_spaces(text)
    author = clean_author(author_name)
    role = extract_role_title(clean_text) or extract_role_title(title_hint)
    company = extract_company(clean_text, author)
    tags = extract_skill_tags(clean_text)
    action = extract_action_hint(clean_text)
    return {
        "role_title": role or "Hiring Opportunity",
        "company": company or author or "LinkedIn Post",
        "author_name": author,
        "tags": tags,
        "action_hint": action,
        "summary": summarize_post(clean_text),
    }


def is_generic_role(value):
    return normalize_spaces(value).lower() in GENERIC_ROLES


def is_generic_author(value):
    return normalize_spaces(value).lower() in GENERIC_AUTHORS


def normalize_spaces(value):
    return re.sub(r"\s+", " ", value or "").strip()


def clean_author(value):
    text = normalize_spaces(value)
    if not text:
        return ""
    # LinkedIn actor blocks often contain role/location metadata after a newline;
    # after whitespace normalization this keeps the visible person/company name.
    parts = re.split(r"\s+(?:\d+(?:st|nd|rd|th)|followers?|connections?|view|follow)\b", text, maxsplit=1, flags=re.I)
    return parts[0].strip(" -|")[:90]


def extract_role_title(text):
    if not text:
        return ""
    patterns = [
        r"(?:we'?re|we are|now|currently)?\s*hiring\s+(?:for\s+)?(?:a|an|multiple)?\s*([A-Za-z0-9 /+.#,&-]{3,80}?(?:%s))\b" % "|".join(ROLE_WORDS),
        r"(?:looking for|seeking|need|required|opening for|vacancy for)\s+(?:a|an|multiple)?\s*([A-Za-z0-9 /+.#,&-]{3,80}?(?:%s))\b" % "|".join(ROLE_WORDS),
        r"(?:role|position|job title)\s*[:\-]\s*([A-Za-z0-9 /+.#,&-]{3,80}?(?:%s))\b" % "|".join(ROLE_WORDS),
        r"\b([A-Za-z0-9 /+.#,&-]{3,80}?(?:%s))\s+(?:role|position|opening|vacancy|internship)\b" % "|".join(ROLE_WORDS),
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            role = trim_role(match.group(1))
            if role:
                return role
    return ""


def trim_role(value):
    value = normalize_spaces(value)
    value = re.split(r"\b(?:at|in|for|with|remote|onsite|hybrid|location|salary|apply|dm|send)\b", value, maxsplit=1, flags=re.I)[0]
    value = value.strip(" .,:;|-")
    if len(value) < 3:
        return ""
    words = value.split()
    if len(words) > 9:
        value = " ".join(words[-9:])
    return value.title()


def extract_company(text, author=""):
    patterns = [
        r"\b([A-Z][A-Za-z0-9 &.,'-]{2,70})\s+(?:is|are)\s+hiring\b",
        r"\bjoin\s+([A-Z][A-Za-z0-9 &.,'-]{2,70})\b",
        r"\bat\s+([A-Z][A-Za-z0-9 &.,'-]{2,70})\b",
        r"\bcompany\s*[:\-]\s*([A-Za-z0-9 &.,'-]{2,70})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            company = normalize_spaces(match.group(1)).strip(" .,:;|-")
            company = re.split(r"\b(?:for|in|location|remote|hybrid|onsite|apply|dm|send)\b", company, maxsplit=1, flags=re.I)[0].strip()
            if company and not is_generic_author(company):
                return company[:90]
    if author and not is_generic_author(author):
        return author[:90]
    return ""


def extract_skill_tags(text):
    lower = (text or "").lower()
    tags = []
    for needle, label in SKILL_LABELS.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", lower) and label not in tags:
            tags.append(label)
    return tags[:10]


def extract_action_hint(text):
    if re.search(r"\b(?:dm|inbox|message)\b", text, flags=re.I):
        return "DM mentioned"
    if re.search(r"\b(?:send|share).{0,24}(?:cv|resume)\b", text, flags=re.I):
        return "Resume requested"
    if re.search(r"\bapply\b", text, flags=re.I):
        return "Apply mentioned"
    return ""


def summarize_post(text, limit=520):
    text = normalize_spaces(text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;") + "..."
