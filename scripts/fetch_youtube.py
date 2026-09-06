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


# =========================================================
# SETTINGS
# =========================================================

API_KEY = os.environ["YOUTUBE_API_KEY"]

# 取得したいYouTubeチャンネル
CHANNEL_HANDLE = "@gon_vl"

# 最大取得動画数
MAX_VIDEOS = 50

# サムネイル1枚あたり
THUMB_WIDTH = 320
THUMB_HEIGHT = 180

# VRChat UI
PAGE_SIZE = 6
COLUMNS = 3
ROWS = 2


# =========================================================
# PATHS
# =========================================================

ROOT = Path(__file__).resolve().parent.parent

DOCS = ROOT / "docs"

THUMB_PAGES = (
    DOCS
    / "thumb_pages"
)


# =========================================================
# HTTP JSON
# =========================================================

def get_json(base_url, params):

    url = (
        base_url
        + "?"
        + urlencode(params)
    )

    request = Request(
        url,
        headers={
            "User-Agent":
                "GON-VRChat-YouTube-Updater/1.0"
        }
    )

    with urlopen(
        request,
        timeout=30
    ) as response:

        text = (
            response
            .read()
            .decode("utf-8")
        )

        return json.loads(text)


# =========================================================
# GET CHANNEL / UPLOADS PLAYLIST
# =========================================================

def get_uploads_playlist():

    # @ を除いたハンドルをAPIへ渡す
    api_handle = (
        CHANNEL_HANDLE
        .lstrip("@")
    )

    data = get_json(
        "https://www.googleapis.com/youtube/v3/channels",
        {
            "part":
                "snippet,contentDetails",

            "forHandle":
                api_handle,

            "key":
                API_KEY,
        },
    )

    if not data.get("items"):

        raise RuntimeError(
            "YouTube channel was not found: "
            + CHANNEL_HANDLE
        )


    channel = (
        data["items"][0]
    )


    # Channel ID
    channel_id = (
        channel["id"]
    )


    # Channel Name
    channel_title = (
        channel["snippet"]["title"]
    )


    # Uploads Playlist ID
    uploads_id = (
        channel["contentDetails"]
        ["relatedPlaylists"]
        ["uploads"]
    )


    return (
        channel_id,
        channel_title,
        uploads_id
    )


# =========================================================
# GET LATEST VIDEOS
# =========================================================

def get_latest_videos(
    playlist_id
):

    data = get_json(
        "https://www.googleapis.com/youtube/v3/playlistItems",
        {
            "part":
                "snippet,contentDetails",

            "playlistId":
                playlist_id,

            "maxResults":
                MAX_VIDEOS,

            "key":
                API_KEY,
        },
    )


    videos = []


    for item in data.get(
        "items",
        []
    ):

        snippet = item.get(
            "snippet",
            {}
        )

        details = item.get(
            "contentDetails",
            {}
        )


        # ---------------------------------------------
        # VIDEO ID
        # ---------------------------------------------

        video_id = (
            details.get("videoId")
        )

        if not video_id:
            continue


        # ---------------------------------------------
        # TITLE
        # ---------------------------------------------

        title = html.unescape(
            snippet.get(
                "title",
                "Untitled"
            )
        )


        # 削除済み・非公開動画を除外
        if title in (
            "Private video",
            "Deleted video"
        ):
            continue


        # ---------------------------------------------
        # PUBLISHED DATE
        # ---------------------------------------------

        # videoPublishedAtを優先
        published_at = (
            details.get(
                "videoPublishedAt",
                ""
            )
        )

        if not published_at:

            published_at = (
                snippet.get(
                    "publishedAt",
                    ""
                )
            )


        # ---------------------------------------------
        # THUMBNAIL
        # ---------------------------------------------

        thumbnails = (
            snippet.get(
                "thumbnails",
                {}
            )
        )


        thumbnail_url = None


        # 一番高い解像度を使用
        for quality in (
            "maxres",
            "standard",
            "high",
            "medium",
            "default",
        ):

            if quality in thumbnails:

                thumbnail_url = (
                    thumbnails[
                        quality
                    ]["url"]
                )

                break


        # ---------------------------------------------
        # SAVE
        # ---------------------------------------------

        videos.append(
            {
                "videoId":
                    video_id,

                "title":
                    title,

                "publishedAt":
                    published_at,

                "videoUrl":
                    (
                        "https://www.youtube.com/watch?v="
                        + video_id
                    ),

                "_thumbnailSource":
                    thumbnail_url,
            }
        )


    # 最新順
    videos.sort(
        key=lambda video:
            video["publishedAt"],
        reverse=True,
    )


    return videos[
        :MAX_VIDEOS
    ]


# =========================================================
# DOWNLOAD THUMBNAIL
# =========================================================

def download_thumbnail(
    url
):

    # URL無し
    if not url:

        return Image.new(
            "RGB",
            (
                THUMB_WIDTH,
                THUMB_HEIGHT
            ),
            (
                20,
                20,
                20
            ),
        )


    try:

        request = Request(
            url,
            headers={
                "User-Agent":
                    "GON-VRChat-YouTube-Updater/1.0"
            }
        )


        with urlopen(
            request,
            timeout=30
        ) as response:

            image_data = (
                response.read()
            )


        image = Image.open(
            BytesIO(
                image_data
            )
        )


        image = (
            image.convert("RGB")
        )


        image = image.resize(
            (
                THUMB_WIDTH,
                THUMB_HEIGHT
            ),
            Image.LANCZOS,
        )


        return image


    except Exception as exc:

        print(
            "Thumbnail error:",
            url,
            exc
        )


        return Image.new(
            "RGB",
            (
                THUMB_WIDTH,
                THUMB_HEIGHT
            ),
            (
                20,
                20,
                20
            ),
        )


# =========================================================
# CREATE 3x2 THUMBNAIL SHEETS
# =========================================================

def create_thumbnail_pages(
    videos
):

    THUMB_PAGES.mkdir(
        parents=True,
        exist_ok=True
    )


    page_count = math.ceil(
        len(videos)
        / PAGE_SIZE
    )


    # 古い画像を削除
    for old_file in (
        THUMB_PAGES
        .glob("*.jpg")
    ):

        old_file.unlink()


    # ---------------------------------------------
    # PAGE
    # ---------------------------------------------

    for page in range(
        page_count
    ):


        sheet = Image.new(
            "RGB",
            (
                THUMB_WIDTH
                * COLUMNS,

                THUMB_HEIGHT
                * ROWS,
            ),
            (
                20,
                20,
                20
            ),
        )


        # -----------------------------------------
        # 6 VIDEOS
        # -----------------------------------------

        for slot in range(
            PAGE_SIZE
        ):

            index = (
                page
                * PAGE_SIZE
                + slot
            )


            if index >= len(videos):
                continue


            thumbnail = (
                download_thumbnail(
                    videos[index]
                    ["_thumbnailSource"]
                )
            )


            column = (
                slot
                % COLUMNS
            )


            row = (
                slot
                // COLUMNS
            )


            x = (
                column
                * THUMB_WIDTH
            )


            y = (
                row
                * THUMB_HEIGHT
            )


            sheet.paste(
                thumbnail,
                (
                    x,
                    y
                )
            )


        # -----------------------------------------
        # SAVE
        # -----------------------------------------

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


        print(
            "Created thumbnail page:",
            filename
        )


    return page_count


# =========================================================
# CREATE VIDEOS.JSON
# =========================================================

def write_json(
    channel_id,
    channel_title,
    videos,
    page_count
):

    DOCS.mkdir(
        parents=True,
        exist_ok=True
    )


    output_videos = []


    for index, video in enumerate(
        videos
    ):

        output_videos.append(
            {
                "index":
                    index,

                "videoId":
                    video[
                        "videoId"
                    ],

                "title":
                    video[
                        "title"
                    ],

                "publishedAt":
                    video[
                        "publishedAt"
                    ],

                "videoUrl":
                    video[
                        "videoUrl"
                    ],
            }
        )


    # =====================================================
    # FINAL JSON
    # =====================================================

    result = {

        "version":
            1,

        "updatedAt":
            (
                datetime
                .now(timezone.utc)
                .isoformat()
            ),

        "channelId":
            channel_id,

        "channelHandle":
            CHANNEL_HANDLE,

        "channelTitle":
            channel_title,

        "count":
            len(
                output_videos
            ),

        "pageSize":
            PAGE_SIZE,

        "pageCount":
            page_count,

        "videos":
            output_videos,
    }


    output_file = (
        DOCS
        / "videos.json"
    )


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


    print(
        "Created JSON:",
        output_file
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "================================"
    )

    print(
        "YouTube Feed Update"
    )

    print(
        "Target:",
        CHANNEL_HANDLE
    )

    print(
        "================================"
    )


    # ---------------------------------------------
    # CHANNEL
    # ---------------------------------------------

    (
        channel_id,
        channel_title,
        uploads_id
    ) = get_uploads_playlist()


    print(
        "Channel ID:",
        channel_id
    )

    print(
        "Channel Handle:",
        CHANNEL_HANDLE
    )

    print(
        "Channel Name:",
        channel_title
    )

    print(
        "Uploads Playlist:",
        uploads_id
    )


    # ---------------------------------------------
    # VIDEOS
    # ---------------------------------------------

    videos = get_latest_videos(
        uploads_id
    )


    print(
        "Videos:",
        len(videos)
    )


    # ---------------------------------------------
    # THUMBNAILS
    # ---------------------------------------------

    page_count = (
        create_thumbnail_pages(
            videos
        )
    )


    print(
        "Pages:",
        page_count
    )


    # ---------------------------------------------
    # JSON
    # ---------------------------------------------

    write_json(
        channel_id,
        channel_title,
        videos,
        page_count,
    )


    print(
        "================================"
    )

    print(
        "Update completed successfully."
    )

    print(
        "================================"
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()