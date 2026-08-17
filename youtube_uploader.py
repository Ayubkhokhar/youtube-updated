#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
youtube_uploader.py — Automated YouTube Video & Thumbnail Upload Client.

Features:
- Headless authentication using OAuth 2.0 refresh token (suitable for GitHub Actions CI/CD).
- Resumable video upload with exponential backoff retry for network resilience.
- Mandatory compliance disclosure: sets `status.containsSyntheticMedia: true` (verified per Oct 2024 YouTube Data API v3 spec).
- Category mapping (Education=27, Science & Technology=28, Entertainment=24).
- Custom high-CTR thumbnail upload via `thumbnails.set`.
- Configurable privacy status (defaults to 'private' for safe manual inspection).
"""

import os
import sys
import time
import json
import random
import argparse
from datetime import datetime

# UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# Standard YouTube category IDs
CATEGORY_MAPPING = {
    "film & animation": "1",
    "autos & vehicles": "2",
    "music": "10",
    "pets & animals": "15",
    "sports": "17",
    "travel & events": "19",
    "gaming": "20",
    "people & blogs": "22",
    "comedy": "23",
    "entertainment": "24",
    "news & politics": "25",
    "howto & style": "26",
    "education": "27",
    "science & technology": "28",
    "nonprofits & activism": "29",
}

RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
MAX_RETRIES = 10


def get_youtube_client(client_id: str = None, client_secret: str = None, refresh_token: str = None):
    """
    Builds an authenticated YouTube Data API v3 client using OAuth2 refresh token.
    """
    import config
    config.reload()

    cid = client_id or os.environ.get("YOUTUBE_CLIENT_ID") or getattr(config, "YOUTUBE_CLIENT_ID", None)
    csec = client_secret or os.environ.get("YOUTUBE_CLIENT_SECRET") or getattr(config, "YOUTUBE_CLIENT_SECRET", None)
    rtoken = refresh_token or os.environ.get("YOUTUBE_REFRESH_TOKEN") or getattr(config, "YOUTUBE_REFRESH_TOKEN", None)

    # Fallback to checking .env directly if config doesn't have it yet
    if not (cid and csec and rtoken):
        env_file = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("YOUTUBE_CLIENT_ID="):
                        cid = cid or line.split("=", 1)[1].strip()
                    elif line.startswith("YOUTUBE_CLIENT_SECRET="):
                        csec = csec or line.split("=", 1)[1].strip()
                    elif line.startswith("YOUTUBE_REFRESH_TOKEN="):
                        rtoken = rtoken or line.split("=", 1)[1].strip()

    if not (cid and csec and rtoken) or "your_" in (cid or ""):
        raise ValueError(
            "Missing YouTube OAuth credentials. Please run `py youtube_auth_setup.py` "
            "to generate YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN."
        )

    creds = Credentials(
        token=None,
        refresh_token=rtoken,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cid,
        client_secret=csec,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
    )

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def upload_thumbnail(youtube, video_id: str, thumbnail_path: str) -> bool:
    """Uploads a custom JPEG thumbnail for a video."""
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        print(f"⚠️ Thumbnail not found at {thumbnail_path}, skipping thumbnail upload.")
        return False

    print(f"🖼️ Uploading custom thumbnail: {thumbnail_path} ...")
    try:
        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
        )
        request.execute()
        print(f"✅ Custom thumbnail successfully attached to video {video_id}!")
        return True
    except Exception as e:
        print(f"⚠️ Failed to upload thumbnail: {e}")
        return False


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list = None,
    category: str = "Education",
    thumbnail_path: str = None,
    privacy_status: str = "private",
    contains_synthetic_media: bool = True,
    self_declared_made_for_kids: bool = False,
    client_id: str = None,
    client_secret: str = None,
    refresh_token: str = None,
    dry_run: bool = False,
) -> dict:
    """
    Uploads a video to YouTube with metadata, custom thumbnail, and synthetic media disclosure flag.

    Returns dict containing video_id, url, and upload metadata.
    """
    if not os.path.exists(video_path) and not dry_run:
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Map category name to ID
    cat_lower = str(category).lower().strip()
    category_id = CATEGORY_MAPPING.get(cat_lower, "27")  # default Education (27)

    # Sanitize title (max 100 chars per YouTube API)
    clean_title = title.strip()
    if len(clean_title) > 100:
        clean_title = clean_title[:97] + "..."

    # Sanitize tags
    clean_tags = [t.strip() for t in (tags or []) if t.strip()][:25]

    # Video resource body
    body = {
        "snippet": {
            "title": clean_title,
            "description": description.strip(),
            "tags": clean_tags,
            "categoryId": category_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy_status,
            "containsSyntheticMedia": contains_synthetic_media,  # Verified disclosure flag per v3 spec
            "selfDeclaredMadeForKids": self_declared_made_for_kids,
        },
    }

    if dry_run:
        print("\n🟡 [youtube_uploader] DRY RUN MODE — Simulating YouTube Upload:")
        print(json.dumps(body, indent=2))
        return {
            "status": "dry_run",
            "video_id": "MOCK_VIDEO_ID_12345",
            "video_url": "https://youtu.be/MOCK_VIDEO_ID_12345",
            "title": clean_title,
            "privacy_status": privacy_status,
            "contains_synthetic_media": contains_synthetic_media,
            "thumbnail_uploaded": bool(thumbnail_path and os.path.exists(thumbnail_path)),
        }

    # Initialize client
    youtube = get_youtube_client(client_id, client_secret, refresh_token)

    # Setup resumable media upload in 4MB chunks
    media = MediaFileUpload(
        video_path,
        chunksize=4 * 1024 * 1024,
        resumable=True,
        mimetype="video/mp4",
    )

    insert_request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"\n🚀 Initiating resumable video upload to YouTube...")
    print(f"   Title: \"{clean_title}\"")
    print(f"   Privacy: {privacy_status}")
    print(f"   Altered/Synthetic Media Flag: {contains_synthetic_media}")

    response = None
    retry_count = 0

    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                print(f"   📤 Upload progress: {progress}% ...", flush=True)
        except googleapiclient.errors.HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                retry_count += 1
                if retry_count > MAX_RETRIES:
                    raise Exception(f"Upload failed after {MAX_RETRIES} retries. HTTP error: {e}")
                sleep_sec = (2 ** retry_count) + random.random()
                print(f"⚠️ Retriable HTTP {e.resp.status} error, retrying in {sleep_sec:.1f}s...")
                time.sleep(sleep_sec)
            else:
                raise e
        except Exception as e:
            retry_count += 1
            if retry_count > MAX_RETRIES:
                raise Exception(f"Upload failed after {MAX_RETRIES} retries: {e}")
            sleep_sec = (2 ** retry_count) + random.random()
            print(f"⚠️ Network error ({e}), retrying in {sleep_sec:.1f}s...")
            time.sleep(sleep_sec)

    video_id = response.get("id")
    video_url = f"https://youtu.be/{video_id}"
    print(f"\n🎉 Video successfully uploaded! Video ID: {video_id}")
    print(f"🔗 Video URL: {video_url}")

    # Upload custom thumbnail if present
    thumbnail_ok = False
    if thumbnail_path:
        thumbnail_ok = upload_thumbnail(youtube, video_id, thumbnail_path)

    return {
        "status": "success",
        "video_id": video_id,
        "video_url": video_url,
        "title": clean_title,
        "privacy_status": privacy_status,
        "contains_synthetic_media": contains_synthetic_media,
        "thumbnail_uploaded": thumbnail_ok,
        "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    parser = argparse.ArgumentParser(description="YouTube Video & Thumbnail Uploader CLI.")
    parser.add_argument("--video", type=str, required=True, help="Path to MP4 video file.")
    parser.add_argument("--title", type=str, default=None, help="Video title.")
    parser.add_argument("--desc", type=str, default="", help="Video description.")
    parser.add_argument("--tags", type=str, default="history,science,facts", help="Comma-separated tags.")
    parser.add_argument("--category", type=str, default="Education", help="Category (Education, Science & Technology).")
    parser.add_argument("--thumbnail", type=str, default=None, help="Path to custom thumbnail JPEG.")
    parser.add_argument("--privacy", type=str, choices=["private", "unlisted", "public"], default="private", help="Privacy setting.")
    parser.add_argument("--no-synthetic-flag", action="store_true", help="Disable synthetic media disclosure.")
    parser.add_argument("--dry-run", action="store_true", help="Validate request body without sending to YouTube.")

    args = parser.parse_args()

    title = args.title or os.path.splitext(os.path.basename(args.video))[0].replace("-", " ").title()
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    res = upload_video(
        video_path=args.video,
        title=title,
        description=args.desc or f"Deep dive into {title}. Subscribe for daily history and science facts.",
        tags=tags,
        category=args.category,
        thumbnail_path=args.thumbnail,
        privacy_status=args.privacy,
        contains_synthetic_media=not args.no_synthetic_flag,
        dry_run=args.dry_run,
    )

    print("\n--- Upload Result ---")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
