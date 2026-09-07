# VRC GON FanRoom - YouTube Redirect Worker

VRChatの固定VRCUrlから、GitHub Pages上の最新 `videos.json` を参照して
対象YouTubeへ302 Redirectする Cloudflare Worker です。

---

## 目的

VRChat / Udon は実行時に任意のURL文字列を VRCUrl へ変換できません。
そのためVRChat World側には固定のVRCUrlを登録しておき、
このWorkerがリクエスト時に最新のYouTube URLへリダイレクトします。

```
VRChat (固定VRCUrl)
  ↓
Cloudflare Worker  →  302 Redirect
  ↓
YouTube
  ↓
AVPro 再生
```

動画そのものはProxyしません。Redirectのみです。

---

## 既存GitHubシステムとの関係

```
[GitHub Actions]
  YouTube Data API
    ↓
  videos.json 生成
    ↓
  GitHub Pages 公開
    https://miyamotoeiji1011.github.io/VRC_GonFanRoom_YoutubeJson/videos.json

[Cloudflare Worker] (このWorker)
  videos.json 取得 (短時間キャッシュ)
    ↓
  302 Redirect → YouTube
```

GitHub Actions / docs/ フォルダは一切変更しません。

---

## ディレクトリ構成

```
cloudflare/youtube-redirect-worker/
├── src/
│   └── index.ts        # Worker メインコード
├── package.json
├── wrangler.jsonc       # Wrangler 設定 (Worker名・vars)
├── tsconfig.json
├── .gitignore
└── README.md
```

---

## セットアップ

```bash
cd cloudflare/youtube-redirect-worker
npm install
```

---

## ローカル開発

```bash
npm run dev
```

`http://localhost:8787` でローカルWorkerが起動します。

---

## Deploy

Cloudflare アカウントへログインしてからDeployします。

```bash
npx wrangler login   # 初回のみ
npm run deploy
```

DeployするとWorkers.devのURLが表示されます。

---

## API

### GET /play/{channel}/{index}

固定URLを最新のYouTube動画URLへ302 Redirectします。

| パラメータ | 値 |
|---|---|
| channel | `gon` / `yoh` / `yohgon` |
| index | `0` ～ `49` (videos配列の位置) |

```
GET /play/gon/0
→ HTTP 302
  Location: https://www.youtube.com/watch?v=XXXXXXX
  Cache-Control: no-store, no-cache, must-revalidate
```

**Redirectはキャッシュされません。** 毎リクエスト時に最新のvideos.jsonを参照します
(videos.json自体は45秒間短時間キャッシュ)。

---

### GET /resolve/{channel}/{index}

Redirectせず、現在の解決先をJSONで返します (デバッグ用)。

```
GET /resolve/gon/0
→ {
    "ok": true,
    "channel": "gon",
    "index": 0,
    "videoId": "ABC123",
    "title": "動画タイトル",
    "videoUrl": "https://www.youtube.com/watch?v=ABC123",
    "catalogUpdatedAt": "2026-09-07T..."
  }
```

ブラウザで `/play/gon/0` が現在どの動画を指すか確認するために使います。

---

### GET /health

```
GET /health
→ { "ok": true, "service": "youtube-redirect-worker" }
```

---

### GET /

```
GET /
→ { "service": "VRC GON FanRoom YouTube Redirect Worker", "status": "ok" }
```

---

## Workers.dev URLの確認

`npm run deploy` 実行後、ターミナルに以下の形式でURLが表示されます。

```
https://gon-youtube-redirect.<your-subdomain>.workers.dev
```

Cloudflare Dashboard → Workers & Pages → gon-youtube-redirect からも確認できます。

---

## VRChatでの使用

VRChat World (Unity / UdonSharp) 側の VRCUrl フィールドに以下の固定URLを登録します。

```
GON:
  https://<worker-domain>/play/gon/0
  https://<worker-domain>/play/gon/1
  ...

YOH:
  https://<worker-domain>/play/yoh/0
  ...

YOHGON:
  https://<worker-domain>/play/yohgon/0
  ...
```

Worker URLは変化しません。YouTubeへ新動画が投稿されると、
GitHub Actionsが videos.json を更新し (約15分以内)、
Worker経由のRedirect先が自動的に最新動画へ変わります。

World の再Upload は不要です。

---

## エラーコード

| コード | 意味 |
|---|---|
| `CHANNEL_NOT_FOUND` | 存在しないchannelを指定 |
| `INDEX_OUT_OF_RANGE` | index が 0-49 の範囲外 |
| `VIDEO_NOT_FOUND` | 指定indexに動画が存在しない |
| `VIDEO_URL_MISSING` | videoUrlフィールドが空 |
| `VIDEO_URL_INVALID` | YouTube以外のURLが混入 (Open Redirect防止) |
| `CATALOG_FETCH_FAILED` | GitHub Pages取得失敗 |
| `NOT_FOUND` | 存在しないパス |
| `METHOD_NOT_ALLOWED` | GET/HEAD以外のメソッド |
