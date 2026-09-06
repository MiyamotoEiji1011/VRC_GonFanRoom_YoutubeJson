import os
import json
import html
import math
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request

from PIL import Image


API_KEY = os.environ["YOUTUBE_API_KEY"]
CHANNEL_ID = os.environ["YOUTUBE_CHANNEL_ID"]

MAX_VIDEOS = 50

THUMB_WIDTH = 320
THUMB_HEIGHT = 180

PAGE_SIZE = 6
COLUMNS = 3
ROWS = 2

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
THUMB_PAGES = DOCS / "thumb_pages"


def get_json(base_url, params):
    url = base_url + "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "User-Agent": "GON-VRChat-YouTube-Updater/1.0"
        }
    )

    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_uploads_playlist():
    data = get_json(
        "https://www.googleapis.com/youtube/v3/channels",
        {
            "part": "snippet,contentDetails",
            "id": CHANNEL_ID,
            "key": API_KEY,
        },
    )

    if not data.get("items"):
        raise RuntimeError("YouTube channel was not found.")

    channel = data["items"][0]

    channel_title = channel["snippet"]["title"]

    uploads_id = (
        channel["contentDetails"]
        ["relatedPlaylists"]
        ["uploads"]
    )

    return channel_title, uploads_id


def get_latest_videos(playlist_id):
    data = get_json(
        "https://www.googleapis.com/youtube/v3/playlistItems",
        {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": MAX_VIDEOS,
            "key": API_KEY,
        },
    )

    videos = []

    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        details = item.get("contentDetails", {})

        video_id = details.get("videoId")

        if not video_id:
            continue

        title = html.unescape(
            snippet.get("title", "Untitled")
        )

        # Private / deleted placeholders are ignored.
        if title in ("Private video", "Deleted video"):
            continue

        thumbnails = snippet.get("thumbnails", {})

        thumbnail_url = None

        for quality in (
            "maxres",
            "standard",
            "high",
            "medium",
            "default",
        ):
            if quality in thumbnails:
                thumbnail_url = thumbnails[quality]["url"]
                break

        videos.append(
            {
                "videoId": video_id,
                "title": title,
                "publishedAt": snippet.get("publishedAt", ""),
                "videoUrl":
                    "https://www.youtube.com/watch?v="
                    + video_id,
                "_thumbnailSource": thumbnail_url,
            }
        )

    videos.sort(
        key=lambda video: video["publishedAt"],
        reverse=True,
    )

    return videos[:MAX_VIDEOS]


def download_thumbnail(url):
    if not url:
        return Image.new(
            "RGB",
            (THUMB_WIDTH, THUMB_HEIGHT),
            (20, 20, 20),
        )

    try:
        request = Request(
            url,
            headers={
                "User-Agent":
                    "GON-VRChat-YouTube-Updater/1.0"
            }
        )

        with urlopen(request, timeout=30) as response:
            image_data = response.read()

        image = Image.open(BytesIO(image_data))
        image = image.convert("RGB")

        image = image.resize(
            (THUMB_WIDTH, THUMB_HEIGHT),
            Image.LANCZOS,
        )

        return image

    except Exception as exc:
        print("Thumbnail error:", url, exc)

        return Image.new(
            "RGB",
            (THUMB_WIDTH, THUMB_HEIGHT),
            (20, 20, 20),
        )


def create_thumbnail_pages(videos):
    THUMB_PAGES.mkdir(
        parents=True,
        exist_ok=True
    )

    page_count = math.ceil(
        len(videos) / PAGE_SIZE
    )

    # Remove old pages.
    for old_file in THUMB_PAGES.glob("*.jpg"):
        old_file.unlink()

    for page in range(page_count):

        sheet = Image.new(
            "RGB",
            (
                THUMB_WIDTH * COLUMNS,
                THUMB_HEIGHT * ROWS,
            ),
            (20, 20, 20),
        )

        for slot in range(PAGE_SIZE):
            index = page * PAGE_SIZE + slot

            if index >= len(videos):
                continue

            thumb = download_thumbnail(
                videos[index]["_thumbnailSource"]
            )

            column = slot % COLUMNS
            row = slot // COLUMNS

            x = column * THUMB_WIDTH
            y = row * THUMB_HEIGHT

            sheet.paste(
                thumb,
                (x, y)
            )

        filename = (
            THUMB_PAGES
            / f"{page:02d}.jpg"
        )

        sheet.save(
            filename,
            "JPEG",
            quality=85,
            optimize=True,
        )

        print("Created:", filename)

    return page_count


def write_json(channel_title, videos, page_count):
    DOCS.mkdir(
        parents=True,
        exist_ok=True
    )

    output_videos = []

    for index, video in enumerate(videos):
        output_videos.append(
            {
                "index": index,
                "videoId": video["videoId"],
                "title": video["title"],
                "publishedAt": video["publishedAt"],
                "videoUrl": video["videoUrl"],
            }
        )

    result = {
        "version": 1,
        "updatedAt":
            datetime.now(timezone.utc)
            .isoformat(),
        "channelId": CHANNEL_ID,
        "channelTitle": channel_title,
        "count": len(output_videos),
        "pageSize": PAGE_SIZE,
        "pageCount": page_count,
        "videos": output_videos,
    }

    output_file = DOCS / "videos.json"

    with output_file.open(
        "w",
        encoding="utf-8"
    ) as fp:
        json.dump(
            result,
            fp,
            ensure_ascii=False,
            indent=2,
        )

    print("Created:", output_file)


def main():
    channel_title, uploads_id = (
        get_uploads_playlist()
    )

    print("Channel:", channel_title)
    print("Uploads:", uploads_id)

    videos = get_latest_videos(
        uploads_id
    )

    print("Videos:", len(videos))

    page_count = create_thumbnail_pages(
        videos
    )

    write_json(
        channel_title,
        videos,
        page_count,
    )


if __name__ == "__main__":
    main()