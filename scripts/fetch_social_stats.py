import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


OUTPUT_PATH = Path("docs/social_stats.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
}

TIMEOUT = 25


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_text(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # script/styleを除外し、HTML上で見えているテキストを検索しやすくする
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return " ".join(soup.stripped_strings)


def parse_human_count(raw):
    """
    619K -> 619000
    1.2M -> 1200000
    523,057 -> 523057
    523 057 -> 523057
    """
    value = raw.strip().upper()
    value = value.replace(",", "").replace(" ", "")

    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KMB]?)", value)
    if not match:
        raise ValueError(f"Unsupported count format: {raw}")

    number = float(match.group(1))
    suffix = match.group(2)

    multiplier = {
        "": 1,
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
    }[suffix]

    return int(round(number * multiplier))


def format_count(value):
    return f"{int(value):,}"


def load_previous():
    if not OUTPUT_PATH.exists():
        return {}

    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def previous_platform(previous, key):
    old = previous.get(key)

    if isinstance(old, dict) and isinstance(old.get("count"), int):
        return old

    return {
        "count": 0,
        "display": "N/A",
        "source": "",
        "sourceUrl": "",
        "lastSuccessAt": None,
        "status": "no_previous_value",
    }


def fetch_youtube():
    url = "https://socialblade.com/youtube/handle/gon_vl/realtime"
    text = fetch_text(url)

    patterns = [
        r"\bsubscribers\s+([0-9][0-9., ]*\s*[KMB]?)\b",
        r"\b([0-9][0-9., ]*\s*[KMB]?)\s+subscribers\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            count = parse_human_count(match.group(1))
            return count, url

    raise ValueError("YouTube subscriber count was not found")


def fetch_x():
    urls = [
        "https://site.twstalker.com/gonsan_vl",
        "https://twstalker.com/gonsan_vl",
        "https://w.twstalker.com/gonsan_vl",
    ]

    last_error = None

    for url in urls:
        try:
            text = fetch_text(url)

            patterns = [
                r"\bFollowers\s+([0-9][0-9., ]*\s*[KMB]?)\b",
                r"\b([0-9][0-9., ]*\s*[KMB]?)\s+Followers\b",
            ]

            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    count = parse_human_count(match.group(1))
                    return count, url

            last_error = ValueError("X follower count was not found")
        except Exception as e:
            last_error = e

    raise last_error or RuntimeError("X fetch failed")


def fetch_twitch():
    url = "https://streamscharts.com/channels/gon_vl"
    text = fetch_text(url)

    # FAQには1人単位のFollower数が載ることがあるので、まずこちらを優先
    patterns = [
        r"followers count is\s+([0-9][0-9,\s]*)\s+followers",
        r"\bFollowers\s+([0-9][0-9., ]*\s*[KMB]?)\b",
        r"\b([0-9][0-9., ]*\s*[KMB]?)\s+followers\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            count = parse_human_count(match.group(1))
            return count, url

    raise ValueError("Twitch follower count was not found")


def update_platform(previous, key, source_name, fetcher):
    fetched_at = now_iso()

    try:
        count, source_url = fetcher()

        return {
            "count": count,
            "display": format_count(count),
            "source": source_name,
            "sourceUrl": source_url,
            "lastSuccessAt": fetched_at,
            "status": "ok",
        }

    except Exception as e:
        old = previous_platform(previous, key)

        print(f"[WARN] {key}: {type(e).__name__}: {e}")

        # 一時的にスクレイピング失敗しても、前回値を消さない
        old = dict(old)
        old["status"] = "stale"
        old["lastError"] = f"{type(e).__name__}: {e}"

        return old


def main():
    previous = load_previous()

    result = {
        "version": 1,
        "updatedAt": now_iso(),
        "youtube": update_platform(
            previous,
            "youtube",
            "Social Blade",
            fetch_youtube,
        ),
        "x": update_platform(
            previous,
            "x",
            "TwStalker",
            fetch_x,
        ),
        "twitch": update_platform(
            previous,
            "twitch",
            "Streams Charts",
            fetch_twitch,
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
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
