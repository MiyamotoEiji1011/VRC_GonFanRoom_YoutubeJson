import json
import re
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

import fetch_social_stats as base


# Xだけ検索エンジン経由で取得するラッパー。
# API Key / Secret は不要。
# YouTube / Twitch / JSON保存処理は既存 fetch_social_stats.py をそのまま利用する。

SEARCH_QUERIES = [
    '"GON @gonsan_vl" Followers Following',
    '"gonsan_vl" Followers Following',
    'site:twstalker.com "GON @gonsan_vl" Followers',
]

COUNT_PATTERNS = [
    r"\b([0-9]+(?:\.[0-9]+)?\s*[KMB])\s+Followers\b",
    r"\bFollowers\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*[KMB])\b",
]


def extract_gon_follower_count(text):
    """gonsan_vl の近くにある Followers 数だけを拾う。"""

    normalized = re.sub(r"\s+", " ", text)
    lower = normalized.lower()

    positions = [
        match.start()
        for match in re.finditer("gonsan_vl", lower)
    ]

    # 検索結果によっては @ が省略されるため GON + Followers 全体も最後に確認
    windows = []

    for pos in positions:
        start = max(0, pos - 500)
        end = min(len(normalized), pos + 900)
        windows.append(normalized[start:end])

    if not windows and "gon" in lower:
        windows.append(normalized)

    candidates = []

    for window in windows:
        for pattern in COUNT_PATTERNS:
            for match in re.finditer(pattern, window, re.IGNORECASE):
                try:
                    value = base.parse_human_count(match.group(1))

                    # GONの規模から大きく外れた別アカウントの数値を除外
                    if 100_000 <= value <= 2_000_000:
                        candidates.append(value)
                except Exception:
                    continue

    if not candidates:
        raise ValueError("GON follower count not found in search text")

    # 同じ検索画面に古い値と新しい値が混ざる場合は最大値を採用
    return max(candidates)


def bing_html(query):
    response = requests.get(
        "https://www.bing.com/search",
        params={
            "q": query,
            "setlang": "en-US",
            "cc": "US",
        },
        headers=base.HEADERS,
        timeout=base.TIMEOUT,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = " ".join(soup.stripped_strings)

    return extract_gon_follower_count(text)


def duckduckgo_html(query):
    response = requests.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers=base.HEADERS,
        timeout=base.TIMEOUT,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = " ".join(soup.stripped_strings)

    return extract_gon_follower_count(text)


def bing_rss(query):
    response = requests.get(
        "https://www.bing.com/search",
        params={
            "q": query,
            "format": "rss",
            "setlang": "en-US",
        },
        headers=base.HEADERS,
        timeout=base.TIMEOUT,
    )
    response.raise_for_status()

    root = ET.fromstring(response.text)

    chunks = []

    for item in root.findall(".//item"):
        chunks.append(item.findtext("title") or "")
        chunks.append(item.findtext("description") or "")
        chunks.append(item.findtext("link") or "")

    return extract_gon_follower_count(" ".join(chunks))


def fetch_x():
    # RSSのdescriptionにはFollower数が省略されることがあるので、
    # 通常の検索HTMLを先に試す。
    engines = [
        ("Bing HTML", bing_html),
        ("DuckDuckGo HTML", duckduckgo_html),
        ("Bing RSS", bing_rss),
    ]

    last_error = None

    for engine_name, engine in engines:
        for query in SEARCH_QUERIES:
            try:
                count = engine(query)

                print(
                    f"[OK] x via {engine_name}: "
                    f"{count:,}"
                )

                return count, "https://x.com/gonsan_vl"

            except Exception as e:
                last_error = e

                print(
                    f"[WARN] X {engine_name} failed "
                    f"({query}): "
                    f"{type(e).__name__}: {e}"
                )

    raise last_error or RuntimeError(
        "X follower count could not be found from search indexes"
    )


def main():
    previous = base.load_previous()

    result = {
        "version": 1,
        "updatedAt": base.now_iso(),
        "youtube": base.update_platform(
            previous,
            "youtube",
            "Social Blade",
            base.fetch_youtube,
        ),
        "x": base.update_platform(
            previous,
            "x",
            "Search Index",
            fetch_x,
        ),
        "twitch": base.update_platform(
            previous,
            "twitch",
            "Streams Charts",
            base.fetch_twitch,
        ),
    }

    base.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with base.OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
