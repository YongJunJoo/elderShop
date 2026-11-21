"""YouTube OAuth. 처음 한 번 브라우저로 채널 계정에 로그인하면 token.json이 저장된다."""
from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
SECRETS = Path(os.getenv("YT_CLIENT_SECRETS", "secrets/client_secret.json"))
TOKEN = Path(os.getenv("YT_TOKEN", "secrets/token.json"))


def credentials() -> Credentials:
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS), SCOPES)
        creds = flow.run_local_server(port=0)
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def youtube():
    return build("youtube", "v3", credentials=credentials())


def youtube_analytics():
    return build("youtubeAnalytics", "v2", credentials=credentials())
