#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
youtube_auth_setup.py — One-time local OAuth 2.0 authentication helper.

Run this script locally on your machine to authorize your YouTube channel.
It opens a browser window, completes Google OAuth 2.0 authorization,
and outputs your permanent REFRESH TOKEN for use in .env and GitHub Actions Secrets.

Prerequisites:
1. Go to Google Cloud Console (https://console.cloud.google.com/).
2. Enable "YouTube Data API v3".
3. Under "APIs & Services" -> "OAuth consent screen", select "External", add test user (your Google email).
4. Under "Credentials", click "Create Credentials" -> "OAuth client ID" -> "Desktop App".
5. Download JSON as `client_secrets.json` into this project root, OR enter Client ID & Secret when prompted.
"""

import os
import sys
import json

# Cross-platform UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(__file__), "client_secrets.json")
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


def update_env_file(client_id: str, client_secret: str, refresh_token: str):
    """Safely updates or appends YouTube OAuth credentials in the local .env file."""
    env_vars = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

    env_vars["YOUTUBE_CLIENT_ID"] = client_id
    env_vars["YOUTUBE_CLIENT_SECRET"] = client_secret
    env_vars["YOUTUBE_REFRESH_TOKEN"] = refresh_token

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")
    print(f"✅ Updated local .env with YouTube OAuth credentials.")


def main():
    print("=" * 70)
    print("  YouTube Channel OAuth 2.0 Setup (One-Time Token Generator)")
    print("=" * 70)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = None
    client_id = None
    client_secret = None

    if os.path.exists(CLIENT_SECRETS_FILE):
        print(f"📁 Found {CLIENT_SECRETS_FILE}! Loading client configuration...")
        with open(CLIENT_SECRETS_FILE, "r", encoding="utf-8") as f:
            secret_data = json.load(f)
            # Support both 'installed' and 'web' client structures
            client_info = secret_data.get("installed") or secret_data.get("web") or {}
            client_id = client_info.get("client_id")
            client_secret = client_info.get("client_secret")

        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
        )
    else:
        print("\nℹ️  client_secrets.json not found in root folder.")
        client_id = input("Enter your Google OAuth Client ID: ").strip()
        client_secret = input("Enter your Google OAuth Client Secret: ").strip()

        if not client_id or not client_secret:
            print("❌ Client ID and Secret are required to proceed.")
            sys.exit(1)

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8080/", "http://127.0.0.1:8080/"],
            }
        }
        flow = InstalledAppFlow.from_client_config(
            client_config,
            scopes=SCOPES,
        )

    print("\n🌐 Opening local browser for Google account authorization...")
    print("⚠️  Make sure you log in with the Google account that owns or manages the YouTube channel.")
    print("   If you see a 'Google hasn't verified this app' screen, click 'Advanced' -> 'Go to <app> (unsafe)'.")

    # Run local server to capture the OAuth redirect
    credentials = flow.run_local_server(
        port=8080,
        prompt="consent",
        access_type="offline",
        open_browser=True,
    )

    refresh_token = credentials.refresh_token

    if not refresh_token:
        print("\n⚠️  No refresh token returned! This happens if consent was already granted.")
        print("   To force Google to generate a new refresh token, revoke app access at:")
        print("   https://myaccount.google.com/permissions and run this script again.")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("🎉 OAuth Authorization Successful!")
    print("=" * 70)
    print("\nHere are your persistent credentials:\n")
    print(f"YOUTUBE_CLIENT_ID={client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")

    print("\n" + "-" * 70)
    print("📋 For GitHub Actions Deployment:")
    print("Add these 3 secrets to your GitHub Repository Settings -> Secrets and variables -> Actions:")
    print("  1. YOUTUBE_CLIENT_ID")
    print("  2. YOUTUBE_CLIENT_SECRET")
    print("  3. YOUTUBE_REFRESH_TOKEN")
    print("-" * 70)

    # Save to local .env
    update_env_file(client_id, client_secret, refresh_token)
    print("\nSetup complete! You can now run `py youtube_uploader.py` or test live uploads.")


if __name__ == "__main__":
    main()
