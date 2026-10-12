import os
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.exceptions import GoogleAuthError

VIDEO_PATH = Path("output/short.mp4")
STORY_PATH = Path("output/story.txt")

CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    if not VIDEO_PATH.exists():
        raise FileNotFoundError(f"Video not found: {VIDEO_PATH}")

    if not STORY_PATH.exists():
        raise FileNotFoundError(f"Story not found: {STORY_PATH}")

    story = STORY_PATH.read_text(encoding="utf-8")

    title = "حكاية كرتونية جديدة"
    for line in story.splitlines():
        if line.strip().startswith("عنوان القصة:"):
            title = line.split(":", 1)[1].strip()
            break

    title = f"{title} #Shorts"[:100]

    description = (
        "حكاية كرتونية باللهجة المصرية! 🍿\n"
        "تابعنا للمزيد من القصص والحكايات.\n\n"
        "#Shorts #قصص_كرتونية #حكايات"
    )

    credentials = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES,
    )

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    video = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [
                "قصص كرتونية",
                "قصص مصرية",
                "حكايات",
                "Shorts",
            ],
            "categoryId": "22",
            "defaultLanguage": "ar",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(VIDEO_PATH),
        mimetype="video/mp4",
        chunksize=5 * 1024 * 1024,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=video,
        media_body=media,
        notifySubscribers=False,
    )

    response = None

    while response is None:
        status, response = request.next_chunk()

        if status:
            progress = int(status.progress() * 100)
            print(f"Upload progress: {progress}%")

    video_id = response["id"]

    print("Upload successful!")
    print(f"Video ID: {video_id}")
    print(f"Video URL: https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    try:
        main()
    except (GoogleAuthError, FileNotFoundError, KeyError, ValueError) as error:
        print(f"Upload failed: {error}")
        sys.exit(1)
    except Exception as error:
        print(f"Upload failed: {error}")
        sys.exit(1)
