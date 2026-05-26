"""AI draft generation for HireMate messages and LinkedIn comments.

The service keeps prompt construction, Groq API calls, JSON parsing, and safety
normalization separate from database persistence. Drafts are generated only when
the user clicks a Generate button; nothing is posted automatically.
"""

import json
import re
from urllib import error, request

from core.config import GROQ_API_KEY, GROQ_CHAT_COMPLETIONS_URL, GROQ_KEY_FILE, GROQ_MODEL, XAI_KEY_FILE


COMMENT_DRAFT_PROMPT = """You are HireMate AI, an advanced LinkedIn comment draft generation assistant.

Your task is to generate highly professional, relevant, ethical, and context-aware LinkedIn comment drafts that users can use to interact professionally with hiring posts, recruiters, and opportunities on LinkedIn.

The goal is to help users engage with hiring posts professionally without sounding spammy, fake, desperate, offensive, irrelevant, or AI-generated.

The generated comments must be:

* Professional
* Human-like
* Contextually relevant
* Short and engaging
* Grammatically correct
* Ethical
* Non-spammy
* Relevant to the user’s profile and skills

The comments will be shown inside an editable comment box where the user can:

* Edit
* Approve
* Copy
* Regenerate
* Discard

No comment should ever be posted automatically without user approval.

---

## USER PROFILE

Name:
{{user_name}}

Professional Title:
{{professional_title}}

Location:
{{location}}

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

---

## SELECTED LINKEDIN POST

Post Author Name:
{{post_author_name}}

Company Name:
{{company_name}}

Post Type:
{{post_type}}

Job Title / Opportunity:
{{job_title}}

LinkedIn Post Content:
{{post_content}}

Job Requirements:
{{job_requirements}}

Location:
{{job_location}}

Work Type:
{{work_type}}

---

## TASK

Analyze:

1. The LinkedIn post
2. The user profile
3. The user skills
4. The user experience level
5. The relevance between the user and the opportunity

Then generate ONE highly relevant LinkedIn comment draft.

The comment should:

* Sound natural and professional
* Match the user’s experience level
* Relate to the post content
* Mention relevant skills naturally
* Show genuine interest professionally
* Encourage professional engagement
* Avoid sounding copied or automated
* Avoid excessive praise
* Avoid desperation
* Avoid irrelevant details
* Avoid fake claims
* Avoid emojis unless extremely appropriate
* Be suitable for LinkedIn professional standards

---

## COMMENT STYLE RULES

1. Keep comments concise and engaging.
2. Comment length should usually be between 20–60 words.
3. Do not generate long paragraphs.
4. Do not generate generic comments like:

   * "Interested"
   * "Check DM"
   * "I need a job"
   * "Please hire me"
5. Do not use offensive, inappropriate, or spammy language.
6. Do not mention experience the user does not have.
7. If the user is beginner-level, generate beginner-appropriate engagement.
8. If post relevance is low, generate a neutral professional interaction comment.
9. Avoid repetitive wording.
10. Comments must feel human-written.
11. Ensure comments are grammatically correct and ethically appropriate.
12. Prioritize meaningful professional interaction over self-promotion.

---

## COMMENT GENERATION LOGIC

If the post is:

* Internship related → generate student/junior-level engagement
* Research related → generate research-interest engagement
* AI/NLP/LLM related → connect user AI skills naturally
* Startup related → generate innovation-focused engagement
* Freelance related → generate skill-focused interaction

If user experience is missing:

* Present user as learner, enthusiast, beginner, or aspiring professional
* Do NOT fabricate work experience

If post content lacks details:

* Generate a short professional generic engagement comment

---

## SPAM AND SAFETY FILTERING

Before returning the comment:

* Check if comment is spammy
* Check if comment is offensive
* Check if comment is irrelevant
* Check if comment contains fake claims
* Check if comment sounds too robotic

Only return safe and professional comments.

---

## OUTPUT FORMAT

Return ONLY valid JSON.

{
"comment_draft": "",
"tone": "professional",
"comment_type": "",
"relevance_score": 0,
"matched_profile_points": [],
"engagement_goal": "",
"safety_check": {
"is_spammy": false,
"is_offensive": false,
"contains_fake_claims": false,
"is_relevant": true,
"is_professional": true
},
"editable": true
}

---

## EXAMPLE OUTPUT

{
"comment_draft": "This opportunity aligns closely with my interests in AI, NLP, and Generative AI. I have been exploring LLM and Python-based projects recently, and it’s exciting to see opportunities like this being shared. Thank you for posting this opportunity.",

"tone": "professional",

"comment_type": "professional_engagement",

"relevance_score": 88,

"matched_profile_points": [
"AI",
"NLP",
"LLM",
"Python"
],

"engagement_goal": "Professional networking and visibility",

"safety_check": {
"is_spammy": false,
"is_offensive": false,
"contains_fake_claims": false,
"is_relevant": true,
"is_professional": true
},

"editable": true
}
"""


MESSAGE_DRAFT_PROMPT = """You are HireMate AI, a professional LinkedIn message draft generator.

Your task is to generate a polite, professional, non-spammy message that the user can send to the recruiter, hiring manager, or post author after selecting a job post.

You must generate the message based on:
1. User profile
2. User skills
3. User experience level
4. User interests
5. Job/post content
6. Role requirements
7. Location or work preference if available

--------------------------------
USER PROFILE
--------------------------------
Name: {{user_name}}
Professional Title: {{professional_title}}
Location: {{location}}
About: {{about}}
Skills: {{skills}}
Interests: {{interests}}
Experience: {{experience}}
Education: {{education}}

--------------------------------
SELECTED LINKEDIN POST / JOB
--------------------------------
Post Author Name: {{post_author_name}}
Company Name: {{company_name}}
Job Title / Role: {{job_title}}
Post Content: {{post_content}}
Job Requirements: {{job_requirements}}
Location: {{job_location}}
Work Type: {{work_type}}

--------------------------------
TASK
--------------------------------
Generate ONE professional message draft that the user can send.

The message should:
- Be short and clear
- Be polite and respectful
- Be contextually relevant to the job/post
- Mention the role or opportunity naturally
- Connect the user’s skills with the post requirements
- Show interest without sounding desperate
- Avoid exaggerating the user’s experience
- Avoid fake claims
- Avoid spammy wording
- Avoid offensive, inappropriate, or informal language
- Be grammatically correct
- Be editable by the user
- Sound human and professional

--------------------------------
IMPORTANT RULES
--------------------------------
1. Do not claim the user has experience that is not present in the profile.
2. If experience is missing, present the user as interested, skilled, beginner, student, or entry-level.
3. Do not write long paragraphs.
4. Do not use too many buzzwords.
5. Do not include emojis.
6. Do not use aggressive phrases like “I am the perfect candidate.”
7. Do not ask for a job directly in a desperate way.
8. Do not create spammy repeated messages.
9. If the post is irrelevant to the user profile, generate a polite low-confidence message or return a warning.
10. Keep the message between 70 and 120 words.

--------------------------------
OUTPUT FORMAT
--------------------------------
Return only valid JSON:

{
  "message_draft": "",
  "tone": "professional",
  "relevance_score": 0,
  "matched_profile_points": [],
  "safety_check": {
    "is_spammy": false,
    "is_offensive": false,
    "contains_fake_claims": false,
    "is_professional": true
  },
  "editable": true
}
"""


def generate_ai_draft(user, lead, draft_type="message", tone="professional"):
    """Generate a message/comment draft with Groq and return normalized JSON."""
    prompt = build_prompt(user, lead, draft_type, tone)
    payload = call_groq(prompt)
    return normalize_draft_payload(payload, draft_type)


def build_prompt(user, lead, draft_type, tone):
    base = MESSAGE_DRAFT_PROMPT if draft_type == "message" else COMMENT_DRAFT_PROMPT
    values = prompt_values(user, lead)
    values["tone"] = tone or "professional"
    prompt = base
    for key, value in values.items():
        prompt = prompt.replace("{{" + key + "}}", safe_prompt_value(value))
    return prompt + f"\n\nRequested tone: {tone or 'professional'}\n"


def prompt_values(user, lead):
    full_name = " ".join(part for part in [user.get("first_name", ""), user.get("last_name", "")] if part).strip()
    experience = user.get("experience_detail") or user.get("experience_level") or ""
    work_preferences = user.get("work_modes") or user.get("preferred_locations") or ""
    post_type = "LinkedIn Job" if lead.get("lead_kind") == "job" else "LinkedIn Post"
    return {
        "user_name": full_name,
        "professional_title": user.get("headline", ""),
        "location": user.get("location", ""),
        "about": user.get("about", ""),
        "skills": user.get("skills", ""),
        "interests": user.get("interests", ""),
        "experience": experience,
        "education": user.get("education", ""),
        "work_preferences": work_preferences,
        "post_author_name": lead.get("author_name") or lead.get("company") or "",
        "company_name": lead.get("company", ""),
        "post_type": post_type,
        "job_title": lead.get("role_title", ""),
        "post_content": lead.get("post_text", ""),
        "job_requirements": lead.get("post_text", ""),
        "job_location": lead.get("location", ""),
        "work_type": lead.get("work_type", ""),
    }


def safe_prompt_value(value):
    value = str(value or "").strip()
    return value[:6000] if len(value) > 6000 else value


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


def call_groq(prompt):
    key = groq_api_key()
    if not key:
        raise RuntimeError("Groq API key is not configured.")
    body = {
        "model": GROQ_MODEL,
        "stream": False,
        "temperature": 0.35,
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
        with request.urlopen(req, timeout=12) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Groq draft request failed: {exc.code} {detail[:220]}") from exc
    content = json.loads(raw).get("choices", [{}])[0].get("message", {}).get("content", "")
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
        raise RuntimeError("AI did not return valid JSON.")


def normalize_draft_payload(payload, draft_type):
    payload = payload if isinstance(payload, dict) else {}
    key = "message_draft" if draft_type == "message" else "comment_draft"
    content = clean_generated_text(payload.get(key, ""))
    if not content:
        raise RuntimeError("AI returned an empty draft.")
    if draft_type == "message":
        content = enforce_message_length(content)
    payload[key] = content
    payload["tone"] = str(payload.get("tone") or "professional")
    payload["relevance_score"] = int(float(payload.get("relevance_score", 0) or 0))
    payload["matched_profile_points"] = payload.get("matched_profile_points") if isinstance(payload.get("matched_profile_points"), list) else []
    payload["editable"] = True
    safety = payload.get("safety_check") if isinstance(payload.get("safety_check"), dict) else {}
    payload["safety_check"] = {
        "is_spammy": bool(safety.get("is_spammy", False)),
        "is_offensive": bool(safety.get("is_offensive", False)),
        "contains_fake_claims": bool(safety.get("contains_fake_claims", False)),
        "is_professional": bool(safety.get("is_professional", True)),
    }
    if draft_type == "comment":
        payload["safety_check"]["is_relevant"] = bool(safety.get("is_relevant", True))
        payload.setdefault("comment_type", "professional_engagement")
        payload.setdefault("engagement_goal", "Professional networking and visibility")
    return payload


def clean_generated_text(text):
    text = re.sub(r"\s+\n", "\n", str(text or "")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def enforce_message_length(text):
    """Keep message drafts aligned with the 70-120 word requirement."""
    words = text.split()
    if len(words) < 70:
        text = (
            text.rstrip()
            + " I would appreciate the opportunity to learn more about the role, understand the next steps, "
            + "and share any additional details you may need for consideration."
        )
    words = text.split()
    if len(words) > 125:
        text = " ".join(words[:120]).rstrip(" ,;:") + "."
    return text
