## Required Credentials

| Name                  | Purpose                        | Stored as                  | Status      |
|------------------------|---------------------------------|------------------------------|-------------|
| GROQ_API_KEY           | Script generation               | GitHub Secret / Local .env  | ⬜ pending (placeholder in .env) |
| PIXABAY_API_KEY        | Stock video/image search        | GitHub Secret / Local .env  | ⬜ pending (placeholder in .env) |
| PEXELS_API_KEY         | Stock video/image search        | GitHub Secret / Local .env  | ⬜ pending (placeholder in .env) |
| YOUTUBE_CLIENT_ID      | OAuth for upload API            | GitHub Secret               | ⬜ pending   |
| YOUTUBE_CLIENT_SECRET  | OAuth for upload API            | GitHub Secret               | ⬜ pending   |
| YOUTUBE_REFRESH_TOKEN  | OAuth for upload API            | GitHub Secret               | ⬜ pending   |

## Where these actually live
All real values are set in: Repo Settings → Secrets and variables → Actions (for GitHub Actions) or local `.env` (for local development).
Never paste real key values into this file, any code comment, any commit message, or any chat/agent session log.
If a key is ever accidentally exposed (committed, pasted, logged), rotate it immediately at the provider dashboard.

## Setup status notes
- 2026-08-17: Created `youtube_auth_setup.py` helper for one-time local OAuth authentication.
- 2026-08-17: Built `youtube_uploader.py` supporting `videos.insert` with verified `status.containsSyntheticMedia: true` flag and `thumbnails.set` custom thumbnail upload.
- 2026-08-17: Next steps for live upload: Add `GROQ_API_KEY` to local `.env`, run `py youtube_auth_setup.py` to authenticate your YouTube channel and populate `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN`.
