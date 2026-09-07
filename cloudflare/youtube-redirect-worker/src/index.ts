const ALLOWED_CHANNELS = ["gon", "yoh", "yohgon"] as const;
const MAX_INDEX = 49;
const ALLOWED_YOUTUBE_HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "youtu.be",
  "m.youtube.com",
]);

type Channel = (typeof ALLOWED_CHANNELS)[number];

interface VideoEntry {
  index: number;
  videoId: string;
  title: string;
  publishedAt: string;
  videoUrl: string;
}

interface ChannelEntry {
  key: string;
  channelTitle: string;
  count: number;
  videos: VideoEntry[];
}

interface Catalog {
  version: number;
  updatedAt: string;
  channels: ChannelEntry[];
}

export interface Env {
  CATALOG_URL: string;
}

// In-memory short-term cache (per isolate lifetime, ~30-60s effectively)
let catalogCache: { data: Catalog; fetchedAt: number } | null = null;
const CACHE_TTL_MS = 45_000; // 45 seconds

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

function errorResponse(status: number, code: string): Response {
  return jsonResponse({ ok: false, error: code }, status);
}

function isAllowedYoutubeUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && ALLOWED_YOUTUBE_HOSTS.has(parsed.hostname);
  } catch {
    return false;
  }
}

async function fetchCatalog(catalogUrl: string): Promise<Catalog> {
  const now = Date.now();
  if (catalogCache && now - catalogCache.fetchedAt < CACHE_TTL_MS) {
    return catalogCache.data;
  }

  const res = await fetch(catalogUrl, {
    cf: { cacheTtl: 45, cacheEverything: true },
  });

  if (!res.ok) {
    throw new Error(`CATALOG_FETCH_FAILED: HTTP ${res.status}`);
  }

  const data: Catalog = await res.json();
  catalogCache = { data, fetchedAt: now };
  return data;
}

async function handlePlay(
  channel: string,
  indexStr: string,
  catalogUrl: string,
  headOnly: boolean
): Promise<Response> {
  if (!(ALLOWED_CHANNELS as readonly string[]).includes(channel)) {
    return errorResponse(404, "CHANNEL_NOT_FOUND");
  }

  const index = Number(indexStr);
  if (!Number.isInteger(index) || index < 0 || index > MAX_INDEX) {
    return errorResponse(404, "INDEX_OUT_OF_RANGE");
  }

  let catalog: Catalog;
  try {
    catalog = await fetchCatalog(catalogUrl);
  } catch {
    return errorResponse(502, "CATALOG_FETCH_FAILED");
  }

  const channelEntry = catalog.channels.find((c) => c.key === channel);
  if (!channelEntry) {
    return errorResponse(404, "CHANNEL_NOT_FOUND");
  }

  const video = channelEntry.videos[index];
  if (!video) {
    return errorResponse(404, "VIDEO_NOT_FOUND");
  }

  if (!video.videoUrl) {
    return errorResponse(404, "VIDEO_URL_MISSING");
  }

  if (!isAllowedYoutubeUrl(video.videoUrl)) {
    return errorResponse(502, "VIDEO_URL_INVALID");
  }

  const headers = new Headers({
    Location: video.videoUrl,
    "Cache-Control": "no-store, no-cache, must-revalidate",
    Pragma: "no-cache",
  });

  return new Response(headOnly ? null : null, { status: 302, headers });
}

async function handleResolve(
  channel: string,
  indexStr: string,
  catalogUrl: string
): Promise<Response> {
  if (!(ALLOWED_CHANNELS as readonly string[]).includes(channel)) {
    return errorResponse(404, "CHANNEL_NOT_FOUND");
  }

  const index = Number(indexStr);
  if (!Number.isInteger(index) || index < 0 || index > MAX_INDEX) {
    return errorResponse(404, "INDEX_OUT_OF_RANGE");
  }

  let catalog: Catalog;
  try {
    catalog = await fetchCatalog(catalogUrl);
  } catch {
    return errorResponse(502, "CATALOG_FETCH_FAILED");
  }

  const channelEntry = catalog.channels.find((c) => c.key === channel);
  if (!channelEntry) {
    return errorResponse(404, "CHANNEL_NOT_FOUND");
  }

  const video = channelEntry.videos[index];
  if (!video) {
    return errorResponse(404, "VIDEO_NOT_FOUND");
  }

  if (!video.videoUrl || !isAllowedYoutubeUrl(video.videoUrl)) {
    return errorResponse(502, "VIDEO_URL_INVALID");
  }

  return jsonResponse(
    {
      ok: true,
      channel,
      index,
      videoId: video.videoId,
      title: video.title,
      videoUrl: video.videoUrl,
      catalogUpdatedAt: catalog.updatedAt,
    },
    200
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const method = request.method.toUpperCase();
    if (method !== "GET" && method !== "HEAD") {
      return new Response(JSON.stringify({ ok: false, error: "METHOD_NOT_ALLOWED" }), {
        status: 405,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          Allow: "GET, HEAD",
        },
      });
    }

    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const segments = path.split("/").filter(Boolean);
    const catalogUrl = env.CATALOG_URL;

    // GET /
    if (path === "/") {
      return jsonResponse(
        { service: "VRC GON FanRoom YouTube Redirect Worker", status: "ok" },
        200
      );
    }

    // GET /health
    if (path === "/health") {
      return jsonResponse({ ok: true, service: "youtube-redirect-worker" }, 200);
    }

    // GET /play/{channel}/{index}
    if (segments[0] === "play" && segments.length === 3) {
      return handlePlay(segments[1], segments[2], catalogUrl, method === "HEAD");
    }

    // GET /resolve/{channel}/{index}
    if (segments[0] === "resolve" && segments.length === 3) {
      if (method === "HEAD") {
        return new Response(null, { status: 200 });
      }
      return handleResolve(segments[1], segments[2], catalogUrl);
    }

    return errorResponse(404, "NOT_FOUND");
  },
};
