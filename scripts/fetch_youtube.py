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


# =========================================================
# YOUTUBE CHANNELS
#
# key:
#   VRChat側で使用する固定ID
#
# handle:
#   YouTubeの @ハンドル
# =========================================================

CHANNELS = [
    {
        "key": "gon",
        "handle": "@gon_vl",
    },
    {
        "key": "yoh",
        "handle": "@yohtubedayo",
    },
    {
        "key": "yohgon",
        "handle": "@yoh_gon",
    },
]


# 1チャンネルあたり最大50動画
MAX_VIDEOS = 50

# 1サムネイル
THUMB_WIDTH = 320
THUMB_HEIGHT = 180

# 1ページ6件
PAGE_SIZE = 6
COLUMNS = 3
ROWS = 2


# =========================================================
# PATHS
# =========================================================

ROOT = Path(__file__).resolve().parent.parent

DOCS = ROOT / "docs"

THUMB_ROOT = (
    DOCS
    / "thumb_pages"
)


# =========================================================
# HTTP
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
                "GON-VRChat-YouTube-Updater/2.0"
        }
    )

    with urlopen(
        request,
        timeout=30
    ) as response:

        return json.loads(
            response
            .read()
            .decode("utf-8")
        )


# =========================================================
# CHANNEL
# =========================================================

def get_channel_info(handle):

    api_handle = (
        handle
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
            + handle
        )


    channel = (
        data["items"][0]
    )


    channel_id = (
        channel["id"]
    )


    channel_title = (
        channel["snippet"]
        ["title"]
    )


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
# VIDEOS
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


        video_id = (
            details.get(
                "videoId"
            )
        )


        if not video_id:
            continue


        title = html.unescape(
            snippet.get(
                "title",
                "Untitled"
            )
        )


        if title in (
            "Private video",
            "Deleted video"
        ):
            continue


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


        thumbnails = (
            snippet.get(
                "thumbnails",
                {}
            )
        )


        thumbnail_url = None


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


        # API側にサムネイルURLが無い場合の保険
        if not thumbnail_url:

            thumbnail_url = (
                "https://i.ytimg.com/vi/"
                + video_id
                + "/hqdefault.jpg"
            )


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
# THUMBNAIL DOWNLOAD
# =========================================================

def download_thumbnail(url):

    try:

        request = Request(
            url,
            headers={
                "User-Agent":
                    "GON-VRChat-YouTube-Updater/2.0"
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
# THUMBNAIL PAGES
# =========================================================

def create_thumbnail_pages(
    channel_key,
    videos
):

    channel_dir = (
        THUMB_ROOT
        / channel_key
    )


    channel_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    # 古いページを削除
    for old_file in (
        channel_dir
        .glob("*.jpg")
    ):

        old_file.unlink()


    page_count = math.ceil(
        len(videos)
        / PAGE_SIZE
    )


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


        filename = (
            channel_dir
            / f"{page:02d}.jpg"
        )


        sheet.save(
            filename,
            "JPEG",
            quality=85,
            optimize=True,
        )


        print(
            "Created thumbnail:",
            channel_key,
            page,
            filename
        )


    return page_count


# =========================================================
# JSON VIDEO DATA
# =========================================================

def create_output_videos(
    videos
):

    result = []


    for index, video in enumerate(
        videos
    ):

        result.append(
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


    return result


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "======================================"
    )

    print(
        "YouTube Multi Channel Feed Update"
    )

    print(
        "======================================"
    )


    DOCS.mkdir(
        parents=True,
        exist_ok=True
    )


    THUMB_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )


    output_channels = []


    # =====================================================
    # CHANNEL LOOP
    # =====================================================

    for config in CHANNELS:

        channel_key = (
            config["key"]
        )

        channel_handle = (
            config["handle"]
        )


        print()
        print(
            "--------------------------------------"
        )

        print(
            "Loading:",
            channel_key,
            channel_handle
        )


        (
            channel_id,
            channel_title,
            uploads_id
        ) = get_channel_info(
            channel_handle
        )


        print(
            "Channel ID:",
            channel_id
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
                channel_key,
                videos
            )
        )


        # ---------------------------------------------
        # JSON CHANNEL OBJECT
        # ---------------------------------------------

        output_channels.append(
            {
                "key":
                    channel_key,

                "channelId":
                    channel_id,

                "channelHandle":
                    channel_handle,

                "channelTitle":
                    channel_title,

                "count":
                    len(videos),

                "pageSize":
                    PAGE_SIZE,

                "pageCount":
                    page_count,

                "thumbnailPath":
                    (
                        "thumb_pages/"
                        + channel_key
                        + "/"
                    ),

                "videos":
                    create_output_videos(
                        videos
                    ),
            }
        )


    # =====================================================
    # FINAL JSON
    # =====================================================

    result = {

        "version":
            2,

        "updatedAt":
            (
                datetime
                .now(timezone.utc)
                .isoformat()
            ),

        "pageSize":
            PAGE_SIZE,

        "maxVideosPerChannel":
            MAX_VIDEOS,

        "channelCount":
            len(
                output_channels
            ),

        "channels":
            output_channels,
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


    print()
    print(
        "======================================"
    )

    print(
        "Created:",
        output_file
    )

    print(
        "Channels:",
        len(output_channels)
    )

    print(
        "Update completed successfully."
    )

    print(
        "======================================"
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()