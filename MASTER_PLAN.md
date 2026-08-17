# MASTER PLAN — Automated History & Science Facts YouTube Channel

**Owner:** [your name/handle]
**Repo:** [to be created]
**Purpose of this file:** This is the single source of truth for Antigravity IDE (or any AI coding agent) to build, modify, and extend this project. Any agent working on this repo should read this file first, follow its architecture, and update the "Changelog / Agent Notes" section at the bottom after making changes.

---

## 0. Reality check (read before building)

This channel is designed to run with **zero manual involvement per video** (script → media → voice → render → upload, fully automatic on a schedule). Be aware of the tradeoffs baked into that choice, so nobody is surprised later:

- YouTube's "inauthentic content" policy (updated July 2025, clarified July 2026) explicitly excludes **AI videos with little human input, narration over reused stock clips, and mass-produced/templated content** from monetization eligibility. Fully automated pipelines are the exact pattern this targets.
- Mitigation strategy used in this plan (see §4): maximize **per-video originality signals** even without human review — varied script structuring, non-repetitive hooks, dynamic pacing, unique thumbnails, topic diversity — so output doesn't look templated, even though the pipeline is automated.
- This is a **risk-managed automation**, not a guarantee. Expect to monitor channel health (Studio warnings, monetization status) periodically even if you don't touch individual videos.
- Realistic monetization timeline: 500 subs + 3 videos + 3,000 watch hours (90 days) unlocks early features; full ad revenue needs 1,000 subs + 4,000 watch hours/12mo. At 2 videos/day of 8-15 min content, this is a **3-6 month runway minimum** before meaningful revenue, assuming consistent retention.

---

## 1. Niche & Brand

**Niche:** History & science facts / "did you know" explainer content (long-form, 8-15 min)

**Why this niche:**
- Works natively with generic stock footage (space, nature, cities, archives, old-photo-style B-roll) — matches Pexels/Pixabay's strengths
- $5-12 CPM range, evergreen (doesn't decay in relevance)
- Low compliance risk — explicitly avoids the financial/health/legal advice categories now excluded from monetization
- Huge topic well (never runs out of content ideas — history + science + "unexplained" combined gives near-infinite unique angles)

**Channel identity (fill in / let Antigravity generate options):**
- Channel name: [TBD — e.g. "Forgotten Frames", "Quiet Curiosities", "The Unknown Record"]
- Tone: documentary-style, calm authoritative narration, mystery/intrigue framing on hooks
- Target audience: US-based, 18-45, curious/casual learners, YouTube "background learning" viewers
- Upload cadence: 2 long-form videos/day (8-15 min)

---

## 2. Current State of the Codebase

Existing local tool (`youtube-automation-free/`) is a **Flask web app** with:
- `core/script_generator.py` — Groq API script generation
- `core/media_searcher.py` — Pexels/Pixabay stock footage fetching
- `core/tts_engine.py` — neural TTS voiceover generation
- `core/video_composer.py` — assembles final MP4
- `core/time_estimator.py` — predicts render time
- `main.py` — Flask server with a job queue, SSE progress streaming, and a browser UI

**This UI-driven, server-based design does not fit GitHub Actions or a "zero-touch" pipeline.** It needs restructuring (see §3) into: a scheduled CLI pipeline (runs headless), a YouTube upload step, and a separate lightweight dashboard for monitoring/control — not for manually triggering each video.

---

## 3. Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  GitHub Actions (scheduled, 2x/day cron)                    │
│                                                               │
│  1. topic_selector.py   → pick next topic (avoid repeats)   │
│  2. script_generator.py → Groq API                          │
│  3. media_searcher.py   → Pexels/Pixabay                    │
│  4. tts_engine.py       → voiceover                         │
│  5. video_composer.py   → render MP4                        │
│  6. thumbnail_gen.py    → auto-generate thumbnail (NEW)     │
│  7. youtube_uploader.py → upload via YouTube Data API (NEW) │
│  8. dashboard_writer.py → push status JSON to gh-pages (NEW)│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  GitHub Pages Dashboard (static site, reads status JSON)     │
│  - Video queue / history                                     │
│  - Upload status, errors, logs                               │
│  - Manual override: pause pipeline, force-run, edit topic list│
│  - API usage stats (Groq/Pexels/Pixabay quota tracking)      │
└─────────────────────────────────────────────────────────────┘
```

### Required refactors from existing code:
1. **Strip Flask/UI dependency from the core pipeline.** `core/*.py` modules are reusable as-is — keep them. Replace `main.py` with `pipeline.py`, a plain script: `python pipeline.py --topic "..."` that runs steps 2-5 above and exits (no server, no threads, no job queue needed for the automated path).
2. **New module: `topic_selector.py`** — maintains a rotating/expanding topic list (JSON or CSV) so two runs a day never repeat, and periodically pulls fresh topic ideas (can use Groq itself to brainstorm batches of 50 topics at a time, stored in `data/topic_queue.json`).
3. **New module: `thumbnail_gen.py`** — auto-generates a thumbnail (Pillow-based: pull a strong frame or stock image + bold text overlay). Thumbnails are one of the single biggest CTR levers — do not skip this.
4. **New module: `youtube_uploader.py`** — uses the YouTube Data API v3 `videos.insert` endpoint with OAuth2 (refresh token stored as a GitHub Secret). Sets title, description, tags, category, and the **"altered/synthetic content" disclosure flag** (required for AI narration + AI-assisted visuals under current policy).
5. **New module: `dashboard_writer.py`** — after each run, writes a `status.json` (recent runs, errors, upload URLs, quota usage) to a `docs/` folder or a `gh-pages` branch, which the dashboard reads client-side.
6. **`.gitignore`** — must exclude `.env`, `temp/`, `output/*.mp4`, `__pycache__/`. Never commit real API keys.
7. **Secrets management** — `GROQ_API_KEY`, `PIXABAY_API_KEY`, `PEXELS_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` all go into GitHub repo Secrets, injected as env vars in the Actions workflow — never hardcoded.

### GitHub Actions workflow (`.github/workflows/publish.yml`)
- Scheduled cron: 2 runs/day, spaced ~8-10 hours apart (e.g. 09:00 and 19:00 UTC — adjust to when your target US audience is most active, roughly late morning and evening US time)
- Each run: checkout → install deps → run `pipeline.py` → run `youtube_uploader.py` → run `dashboard_writer.py` → commit status JSON to `gh-pages`
- Video output should **not** be committed to the main repo (file size). Either upload directly to YouTube from the Actions runner (video never touches git) or use a short-lived artifact if debugging is needed.

---

## 4. Content Strategy (the part automation can't fake)

Since there's no human review step, these need to be **built into the pipeline logic itself**, not left to chance:

- **Topic diversity enforcement:** `topic_selector.py` should track category balance (e.g. don't run 5 space topics in a row) and avoid near-duplicate titles (fuzzy-match against history of past 90 days).
- **Hook variation:** maintain 8-10 different hook templates in the Groq prompt (question hook, myth-busting hook, "you won't believe" hook, cold-open scene hook, statistic hook) and rotate/randomize which one the script generator is instructed to use — prevents the "same structure re-rendered with different nouns" pattern flagged by policy.
- **Script prompt quality:** the Groq prompt should explicitly request narrative structure (setup → tension → payoff), not a flat list of facts read aloud — this is the single biggest lever for both retention *and* avoiding the "reads other material verbatim" flag.
- **Metadata quality:** title, description, and tags should be generated per-video (not templated boilerplate), include a real content summary, and match actual video content.
- **Disclosure:** every upload sets YouTube's "altered or synthetic content" toggle, since narration + AI-selected visuals qualifies. Non-negotiable — skipping this risks penalty even if content quality is fine.
- **Periodic self-audit (monthly):** even in a zero-touch setup, budget 20 minutes once a month to actually watch 2-3 recent uploads and check Studio for any content warnings. This isn't "per video involvement" — it's channel health monitoring, and skipping it entirely is how channels get silently throttled without anyone noticing for weeks.

---

## 4b. Metadata Generation Prompt (title / description / tags)

This is the single highest-leverage prompt in the whole pipeline — it runs with zero human review, so it needs to be engineered once, carefully, rather than left generic. Use this as the system/instruction prompt inside `script_generator.py` (or a new `metadata_generator.py` called right after script generation, so it has the actual script content to work from — never generate metadata blind before the script exists).

```
You are a YouTube SEO specialist for a history/science facts channel targeting a US English-speaking audience. Given the video script below, generate:

1. TITLE (60-70 characters max):
   - Use ONE of these proven patterns, rotate across videos, never repeat the same pattern twice in a row:
     a) Curiosity gap: "The [Topic] Detail Nobody Talks About"
     b) Number/list: "5 [Topic] Facts That Sound Fake (But Aren't)"
     c) Question hook: "Why Did [Historical Event] Actually Happen?"
     d) Myth-bust: "The Truth About [Common Belief] Is Not What You Think"
     e) Stakes/scale: "The [Topic] That Changed Everything"
   - Must accurately reflect the script content — no clickbait that isn't paid off in the video
   - Front-load the specific noun/topic in the first 40 characters (helps both CTR and search)
   - No ALL CAPS, no more than one emoji if any

2. DESCRIPTION (150-300 words):
   - First 2 sentences must work standalone (shown in search/suggested previews) — restate the hook, don't just repeat the title
   - Include 3-5 sentences summarizing what's actually covered (real content summary, not vague teasing)
   - Include a natural-language paragraph with likely search terms a curious viewer would type (not a keyword-stuffed list)
   - End with a one-line channel description + upload schedule note
   - Do NOT use engagement-bait phrases like "like and subscribe" as the primary CTA — one soft mention max

3. TAGS (15-20 tags):
   - Mix of broad (history, science facts) and specific (the exact topic, related figures/events/concepts)
   - Include 2-3 long-tail phrases matching how someone would actually search ("why did X happen", "true story of X")
   - No unrelated trending tags just for reach — must match actual content

4. CATEGORY: classify as one of [Education, Science & Technology, Entertainment] based on content

Output as JSON: {"title": "...", "description": "...", "tags": [...], "category": "..."}
```

Log every generated title's pattern (a/b/c/d/e) to `data/title_pattern_history.json` so `topic_selector.py` or a future prompt revision can enforce rotation and, once you have real Studio data, correlate pattern choice with actual CTR.

---

## 4c. Agent Memory Files (for Antigravity / any coding agent working this repo)

Long chat sessions lose context. To prevent Antigravity from forgetting decisions, re-doing finished work, or losing track of secrets handling, this repo must maintain two persistent files that every agent session reads FIRST before making changes:

### `HISTORY.md`
A running development log, append-only. Every agent session should add an entry before ending, in this format:

```
## [YYYY-MM-DD] — Session summary
- What was done: ...
- Files changed: ...
- What's still pending / next step: ...
- Any decisions made and why (so a future session doesn't re-litigate them): ...
```

Rule for agents: **read the full `HISTORY.md` before starting any work**, resume from the "next step" of the most recent entry, and never redo a completed phase from §6 of this plan without checking here first.

### `CREDENTIALS.md`
**This file documents WHICH credentials the project needs and WHERE they live — it must never contain actual secret values.** This is important enough to repeat: no real API keys, tokens, or passwords go in any `.md` file that's tracked by git, ever. Format:

```
## Required Credentials

| Name                  | Purpose                        | Stored as                  | Status      |
|------------------------|---------------------------------|------------------------------|-------------|
| GROQ_API_KEY           | Script generation               | GitHub Secret               | ✅ set       |
| PIXABAY_API_KEY        | Stock video/image search        | GitHub Secret               | ✅ set       |
| PEXELS_API_KEY         | Stock video/image search        | GitHub Secret               | ✅ set       |
| YOUTUBE_CLIENT_ID      | OAuth for upload API            | GitHub Secret               | ⬜ pending   |
| YOUTUBE_CLIENT_SECRET  | OAuth for upload API            | GitHub Secret               | ⬜ pending   |
| YOUTUBE_REFRESH_TOKEN  | OAuth for upload API            | GitHub Secret               | ⬜ pending   |

## Where these actually live
All real values are set in: Repo Settings → Secrets and variables → Actions.
Never paste real key values into this file, any code comment, any commit message, or any chat/agent session log.
If a key is ever accidentally exposed (committed, pasted, logged), rotate it immediately at the provider dashboard.

## Setup status notes
(Agent: log here when a credential is added/rotated, and by what process, WITHOUT the value itself — e.g. "2026-08-17: YOUTUBE_REFRESH_TOKEN obtained via OAuth playground, added to GitHub Secrets, tested with test upload — success.")
```

This gives Antigravity a persistent memory of *what's configured* without ever putting live secrets somewhere they could leak. Add both files in Phase 1, before any other work.

---

## 4d. Shorts Strategy

Shorts are added as a **repurposing layer**, not a separate generation pipeline — this avoids doubling API costs and doubling the "mass-produced content" surface area.

- New module: `shorts_extractor.py`, runs after `video_composer.py` on the same long-form output
- Extracts 2-4 short segments (30-60s) per long-form video: the hook, and 1-3 standout "fact" moments (use script scene metadata to identify candidates — refine selection later using real retention data once available)
- Reformats to 9:16, burns in captions (captions matter even more on Shorts — many watch muted)
- Queues each clip for upload via the same `youtube_uploader.py`, tagged as Shorts (YouTube auto-detects via aspect ratio + duration, but ensure `#Shorts` is in title/description too)
- Rationale: Shorts drive discovery and can count toward YPP eligibility via views (3M Shorts views/90 days path), while long-form remains the actual revenue engine (higher CPM). Shorts feed the funnel; they don't replace it.

Add `shorts_extractor.py` to Phase 2 of the build.

## 4e. Where Video Files Live

- **During generation:** GitHub Actions runner's local disk only, for the duration of that single job — wiped automatically after each run
- **Permanent storage:** YouTube itself. `youtube_uploader.py` uploads directly from the runner to YouTube in the same job (render → upload → done); the file never needs to persist elsewhere
- **What actually persists in the repo:** only metadata — title, YouTube video ID/URL, timestamp, status, logs — written to `status.json` by `dashboard_writer.py`. No video binaries are ever committed to git or GitHub Pages
- **Failure handling (optional, Phase 4+):** if upload fails after render succeeds, either (a) simplest: discard and re-render on next retry, or (b) temporarily hold the file in Google Drive via API until upload retry succeeds, then delete. Start with (a); only add (b) if failed-render costs become a real problem

---

## 5. Dashboard Spec (GitHub Pages)

**Stack:** static HTML/CSS/JS (no backend — reads `status.json` from the repo via GitHub Pages)

**Screens:**
1. **Home/Overview** — today's upload status, next scheduled run, subscriber/view snapshot (via YouTube Analytics API, optional Phase 2)
2. **Video Queue** — list of generated videos: title, topic, status (queued/rendering/uploaded/failed), YouTube link
3. **Logs** — expandable log viewer per run (from `dashboard_writer.py` output)
4. **Settings** — topic list editor (edit `topic_queue.json` via GitHub API using a personal access token stored in browser localStorage — user-provided, never committed)
5. **API Usage** — Groq/Pexels/Pixabay/YouTube quota tracking so you see before hitting limits

**Auth model:** since this is a public GitHub Pages site, actual control actions (edit topics, pause pipeline) should use a **GitHub Personal Access Token you paste into the dashboard yourself** (stored only in your browser, never sent anywhere but GitHub's API directly from your browser). The dashboard itself is read-only/public-safe by default.

---

## 6. Build Phases (for Antigravity to execute in order)

**Phase 1 — Safety & CLI refactor**
- [ ] Add `.gitignore`, verify no secrets in any tracked file
- [ ] Create `HISTORY.md` and `CREDENTIALS.md` per §4c — read/update these every session from here on
- [ ] Convert `main.py` → `pipeline.py` (headless CLI mode using existing `core/` modules)
- [ ] Test one full local run end-to-end via CLI (no Flask)

**Phase 2 — Topic system & thumbnails**
- [ ] Build `topic_selector.py` with rotation/diversity logic
- [ ] Build `thumbnail_gen.py`

**Phase 3 — YouTube upload**
- [ ] Set up Google Cloud project + OAuth consent screen + YouTube Data API v3
- [ ] Build `youtube_uploader.py`, test with one manual upload
- [ ] Wire in synthetic-content disclosure flag

**Phase 4 — GitHub Actions automation**
- [ ] Write `.github/workflows/publish.yml`
- [ ] Add all secrets to repo settings
- [ ] Dry-run on manual trigger before enabling cron

**Phase 5 — Dashboard**
- [ ] Build static dashboard, deploy to GitHub Pages
- [ ] Wire `dashboard_writer.py` into the pipeline

**Phase 6 — Monitor & iterate**
- [ ] Run for 2 weeks, watch retention/CTR in Studio
- [ ] Adjust hook templates / topic mix based on real performance data (this is the one place data, not guesswork, should drive changes)

---

## Changelog / Agent Notes
*(Antigravity or any future agent: log what you changed and why, here, each session.)*

- [Date] — Initial plan created.
