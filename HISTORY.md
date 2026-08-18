# Development History & Session Log

This log is append-only. Read before every session to maintain continuity.

## [2026-08-17] — Phase 1: Safety Setup & Headless CLI Refactor Complete
- **What was done:**
  - Read `MASTER_PLAN.md` in full as single source of truth.
  - Created `.gitignore` excluding `.env`, `temp/`, output video/audio (`output/*.mp4`, `*.wav`, `*.mp3`), `*.zip`, and `__pycache__/`.
  - Created persistent memory files `HISTORY.md` and `CREDENTIALS.md` per §4c.
  - Extracted prototype codebase to root and initialized Git tracking.
  - Verified local `.env` exists (with placeholders for keys).
  - Built headless CLI entry point `pipeline.py` with argument parsing (`--topic`, `--duration`, `--aspect`, `--voice`, `--media-pref`, `--no-zoom`, `--mock-script`, `--dry-run`).
  - Added cross-platform UTF-8 stream reconfigurations for Windows console resilience.
  - Executed end-to-end local generation test; verified script handling, media fallback pooling, neural TTS (Edge-TTS) speech synthesis, subtitle timing, audio mixing, and video rendering to MP4 in `output/`.
- **Files changed:**
  - `.gitignore` (NEW)
  - `CREDENTIALS.md` (NEW)
  - `HISTORY.md` (NEW)
  - `pipeline.py` (NEW)
- **What's still pending / next step:**
  - Phase 1 tasks completed.

## [2026-08-17] — Phase 2: Topic System, SEO Metadata, Thumbnails & Shorts Complete
- **What was done:**
  - Analyzed and benchmarked render speeds on standard 2-core GitHub Actions runners vs. local multi-core machines (see decisions below).
  - Built `topic_selector.py` with queue management (`data/topic_queue.json`), 90-day fuzzy anti-collision matching against `data/topic_history.json`, category rotation, and auto-refill via Groq API.
  - Built `metadata_generator.py` strictly implementing the exact prompt template from `MASTER_PLAN.md` §4b (5 rotating title patterns, standalone preview hooks, 15-20 SEO tags, category classification, and pattern logging to `data/title_pattern_history.json`).
  - Built `thumbnail_gen.py` (Pillow-based 1280x720 high-CTR thumbnail creator with bold contrasting typography, dark gradient contrast overlay, and accent badges).
  - Built `shorts_extractor.py` (extracts 2-4 vertical 9:16 clips from long-form output with burned-in captions, #Shorts hashtags, and metadata repurposing per §4d).
  - Updated and unified `pipeline.py` to seamlessly orchestrate all 6 stages (`--auto-topic`, metadata generation, media search, thumbnail creation, TTS voiceover, video assembly, and Shorts extraction).
  - Individually tested all modules via unit dry-runs and end-to-end integration tests.
- **Files changed:**
  - `data/topic_queue.json` (NEW)
  - `data/topic_history.json` (NEW)
  - `data/title_pattern_history.json` (NEW)
  - `topic_selector.py` (NEW)
  - `metadata_generator.py` (NEW)
  - `thumbnail_gen.py` (NEW)
  - `shorts_extractor.py` (NEW)
  - `pipeline.py` (MODIFIED — wired Phase 2 subsystems)
  - `HISTORY.md` (MODIFIED)
- **Decisions Made & Render Time Analysis:**
  - **Render Time Analysis**: On a 2-core GitHub Actions runner, Python-level PIL per-frame Ken Burns zoom requires ~25-35s per 1s of 1080p video (~4.5 to 5 hours for a 10-minute video), which exceeds standard CI efficiency budgets and risks hitting the 6-hour execution timeout. In contrast, static / video-clip rendering takes ~0.8-1.2x realtime (approx 8-12 minutes for a 10-minute video).
  - **Decision**: Made `--no-zoom` (static/stock-video mode) the default in CI/automated GitHub Actions environments (detected via `CI=true`), while keeping `--zoom` available for local generation runs. Stock video clips already provide natural camera motion without Python CPU overhead.
- **What's still pending / next step:**
  - Phase 2 tasks completed.

## [2026-08-17] — Phase 3: YouTube API Upload System & Compliance Setup Complete
- **What was done:**
  - Researched and verified official YouTube Data API v3 documentation:
    1. Verified disclosure field name: `status.containsSyntheticMedia` (boolean, part="snippet,status").
    2. Verified `videos.insert` multipart/resumable upload structure and category mapping.
    3. Verified `thumbnails.set` custom thumbnail upload API.
  - Built `youtube_auth_setup.py`: Local one-time OAuth 2.0 helper with local redirect server (`http://localhost:8080/`) to obtain the permanent `YOUTUBE_REFRESH_TOKEN` for GitHub Secrets and `.env`.
  - Built `youtube_uploader.py`: Headless upload engine with resumable chunking, exponential backoff retries, category mapping, custom thumbnail attachment, privacy status selection (default `private`), and mandatory `status.containsSyntheticMedia: true` disclosure.
  - Tested `youtube_uploader.py` via dry-run simulation, validating request payloads, compliance flags, and category mapping.
  - Updated `CREDENTIALS.md` with OAuth secret documentation.
- **Files changed:**
  - `youtube_auth_setup.py` (NEW)
  - `youtube_uploader.py` (NEW)
  - `CREDENTIALS.md` (MODIFIED)
  - `HISTORY.md` (MODIFIED)
- **Decisions Made & YouTube Compliance Notes:**
  - Verified `status.containsSyntheticMedia: true` flag was introduced in YouTube Data API v3 in October 2024 to satisfy YouTube's AI disclosure policy.
  - Set default upload privacy to `private` to allow manual review of video, thumbnail, and metadata before making videos public.
- **What's still pending / next step:**
  - Phase 3 code completed.

## [2026-08-17] — Phase 4: GitHub Actions Automation Complete
- **What was done:**
  - Built `.github/workflows/publish.yml`:
    1. Automated scheduled execution (2x/day at 14:00 UTC and 22:00 UTC for US morning/evening peak audience).
    2. Manual `workflow_dispatch` trigger with inputs for custom topic override, video duration, privacy level, and dry-run toggle.
    3. Python 3.10 environment setup with pip caching, FFmpeg, and Linux font packages.
    4. Auto-commit step syncing updated `data/topic_history.json`, `data/title_pattern_history.json`, `data/topic_queue.json`, and `HISTORY.md` back to repository with `[skip ci]`.
  - Updated `pipeline.py` with `--upload` and `--upload-shorts` CLI flags and configurable privacy settings.
  - Updated `requirements.txt` with Google API client packages for Linux runners.
  - Created dedicated walkthrough artifact `walkthrough_phase_4.md`.
  - Tested unified pipeline with upload flags in dry-run mode.
  - Pushed codebase to remote repository `https://github.com/Ayubkhokhar/youtube-updated.git` on branch `main`.
  - Sanitized local git remote configuration to ensure no credentials remain stored in local config.
- **Files changed:**
  - `.github/workflows/publish.yml` (NEW)
  - `pipeline.py` (MODIFIED)
  - `requirements.txt` (MODIFIED)
  - `HISTORY.md` (MODIFIED)
- **What's still pending / next step:**
  - Proceed to **Phase 5 — GitHub Pages Status Dashboard**:
    1. Build `dashboard_writer.py` (generates `status.json` with pipeline health, recent videos, queue status, and CTR trends).
    2. Build static HTML/CSS/JS dashboard (`docs/index.html` or `gh-pages`) to monitor pipeline runs headlessly.

## [2026-08-18] — REAL LIVE PIPELINE EXECUTION TEST (NON-MOCK)
- **What was done:**
  - Configured real live `GROQ_API_KEY` in `.env`.
  - Executed full live pipeline (NON-MOCK, NON-DRY-RUN):
    - Topic: `The Dancing Plague of 1518: Mass Hysteria in Strasbourg` (auto-selected from queue).
    - Script Generation: Live Groq API (`openai/gpt-oss-120b` endpoint) generated a 3-scene, 78-word script with dynamic hooks.
    - SEO Metadata Generation: Generated 60-char title (Pattern `a`: Curiosity Gap), 115-word SEO description with standalone hook, and 18 tags.
    - Thumbnail Generation: Rendered 1280x720 CTR thumbnail with category badge.
    - TTS Voiceover: Generated 33.5s of neural audio via Edge-TTS (`en-US-GuyNeural`) with word-level subtitles.
    - Video Encoding: Successfully composed and rendered master MP4 video (`output/the-dancing-plague-of-1518-detail-nobody-talks-about_3f5057.mp4`).
    - Shorts Extraction: Extracted 30.0s vertical 9:16 Short (`output/shorts/short_1_dancing-plague-1518_98923.mp4`).
  - Total Render Duration: 740.9s.
- **Files generated:**
  - `output/the-dancing-plague-of-1518-detail-nobody-talks-about_3f5057.mp4` (REAL MP4 VIDEO)
  - `output/thumb_the-dancing-plague-of-1518-detail-nobody.jpg` (REAL THUMBNAIL)
  - `output/shorts/short_1_dancing-plague-1518_98923.mp4` (REAL 9:16 SHORT)

## [2026-08-18] — METADATA WIRING ROOT CAUSE & SECOND REAL UPLOAD TEST
- **Root Cause Analysis:**
  1. *Metadata Disconnect*: The initial run was split into two commands: `pipeline.py` rendered the video without `--upload`, and then `youtube_uploader.py` was invoked directly via CLI (`py youtube_uploader.py --video ...`) without explicit `--title`, `--desc`, `--tags` arguments. `youtube_uploader.py`'s standalone CLI parsed the raw filename for title and defaulted to a 1-line fallback description and 3 generic tags.
  2. *Thumbnail Attachment Timing*: Calling `thumbnails().set` immediately after `videos().insert` can encounter eventual consistency delays before YouTube's backend registers the video ID for thumbnail attachment.
  3. *Windows Temp File Lock*: MoviePy/imageio held an open handle on video clips when `cleanup_temp()` called `shutil.rmtree` on Windows.
- **Fixes Implemented:**
  1. `pipeline.py` now writes sidecar JSON metadata (`<video_basename>_metadata.json` and `latest_metadata.json`) containing the complete generated SEO metadata and thumbnail path.
  2. `youtube_uploader.py` now automatically detects and parses the sidecar metadata JSON file whenever `--title` or `--desc` are omitted, eliminating silent fallbacks.
  3. `upload_thumbnail` now includes a 3-second initialization delay and a 3-attempt retry loop with backoff.
  4. `cleanup_temp()` uses `gc.collect()` and `shutil.rmtree(..., ignore_errors=True)` to prevent Windows process file lock exceptions.
- **Second Real Live Execution Results (Unified Pipeline & Upload):**
  - **Topic**: `The Voynich Manuscript: The Book Nobody Can Read` (Mysteries & Cryptography)
  - **Video ID**: `84ezE1lAGZk`
  - **Live URL**: `https://youtu.be/84ezE1lAGZk`
  - **Title**: `5 Voynich Manuscript Facts That Sound Fake (But Aren't)` (Pattern `b`: Listicle)
  - **Description**: Complete 150+ word SEO description with historical context, search intent queries, and channel branding.
  - **Tags**: 15 targeted tags (`Voynich Manuscript`, `medieval manuscripts`, `cryptography history`, `why is the Voynich Manuscript undecipherable`, etc.)
  - **Category**: `Education` (ID: 27)
  - **Privacy**: `private`
  - **Altered/Synthetic Media Disclosure**: `status.containsSyntheticMedia: true`
  - **Custom Thumbnail**: `output/thumb_5-voynich-manuscript-facts-that-sound-fa.jpg` attached via `thumbnails().set`.
  - **Vertical Short**: `output/shorts/short_1_voynich-manuscript-mystery_d2349.mp4` (30.0s).






- **Any decisions made and why:**
  - Added `--mock-script` flag to `pipeline.py` to allow offline/unit verification of the full video composition pipeline without requiring active Groq API quotas during local test iterations.
  - Replaced UI-dependent `main.py` entrypoint with clean headless `pipeline.py` callable both via CLI and programmatically (`run_pipeline(...)`).
