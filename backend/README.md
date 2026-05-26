# HireMate Backend

Local backend for HireMate using Python standard library + SQLite.

## Quick start

1. Open PowerShell in this folder:

   ```powershell
   cd "D:\FYP\frontend.ver1 - Copy\backend"
   ```

2. Start the API:

   ```powershell
   python .\run.py
   ```

3. Open the frontend through the backend:

   ```text
   http://localhost:8000/landing.html
   ```

## Demo account

- Email: `demo@hiremate.local`
- Password: `Demo@123`

## LinkedIn data

The real project flow is:

1. Register a user.
2. Complete `onboarding.html` with headline, about, skills, interests, target roles, locations, work mode and LinkedIn cookie.
3. The backend saves the profile to SQLite.
4. The backend searches LinkedIn using those filters through `/api/linkedin/sync`.
5. Fetched results are ranked and stored in the `leads` table.

The sync is intentionally conservative:

- max 12 leads per sync
- max 3 LinkedIn search requests per sync
- random 5-15 second delay between requests
- stops on CAPTCHA/checkpoint/rate-limit signals
- stores only job/lead fields needed by HireMate
- deduplicates leads by LinkedIn URL/result id

For a safe fallback FYP demo, use:

```powershell
python .\scripts\import_sample_posts.py
```

This imports realistic LinkedIn-style hiring posts into SQLite, ranks them, and makes them appear in the frontend.

Live LinkedIn fetching is implemented in `services/linkedin_service.py`. It searches public LinkedIn Jobs by your filters and can also try authenticated content search when the user provides a valid `li_at` cookie. LinkedIn can change markup or block automated requests, so keep the cookie private and use this only for supervised academic testing. Do not use proxy rotation, CAPTCHA solving, or high-volume collection for this project.
