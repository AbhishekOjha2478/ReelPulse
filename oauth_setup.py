"""One-time interactive script: grants this app permission to upload to YOUR
YouTube channel and stores a refresh token so publisher.py can run unattended
afterwards.

A service account (used for the old Drive-staging prototype) cannot upload to
a personal YouTube channel -- only OAuth2 user consent can. Run this once,
locally, in a browser-capable environment:

    python oauth_setup.py

You need a Google Cloud project with the YouTube Data API v3 enabled and an
OAuth Client ID (type "Desktop app") downloaded as client_secret.json in this
directory (or point YOUTUBE_OAUTH_CLIENT_SECRETS_FILE at it).
"""

from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import YOUTUBE_OAUTH_CLIENT_SECRETS_FILE, YOUTUBE_OAUTH_TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_OAUTH_CLIENT_SECRETS_FILE, SCOPES)
    credentials = flow.run_local_server(port=0)

    with open(YOUTUBE_OAUTH_TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(credentials.to_json())

    print(f"Saved OAuth token to {YOUTUBE_OAUTH_TOKEN_FILE}")
    print("publisher.py will use this to upload unattended. Keep this file secret.")


if __name__ == "__main__":
    main()
