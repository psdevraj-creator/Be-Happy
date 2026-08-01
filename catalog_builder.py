"""
catalog_builder.py — Build/refresh catalog from YouTube channels + transcript scan.
Extracted from catalog.py (Transcription project).
"""

import os, sys, re, json, time, threading, urllib.request, urllib.parse
from datetime import datetime

BASE_DIR = "Transcripts 2"
CHANNEL_CACHE_DIR = "_channel_cache"
CATEGORY_CONFIG = "category_map.json"
CATALOG_JSON = "catalog.json"

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
_API_BASE = "https://www.googleapis.com/youtube/v3"

build_state = {"stage": "idle", "progress": 0, "message": "", "error": None}
_state_lock = threading.Lock()

_VID_RE = re.compile(r'[A-Za-z0-9_-]{11}')
_TRANSCRIPT_MAP = None

def build_transcript_map():
    global _TRANSCRIPT_MAP
    _TRANSCRIPT_MAP = {}
    if not os.path.isdir(BASE_DIR):
        return
    for root, _dirs, files in os.walk(BASE_DIR):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            m = _VID_RE.search(fn)
            if m:
                vid = m.group(0)
                if vid not in _TRANSCRIPT_MAP:
                    _TRANSCRIPT_MAP[vid] = os.path.join(root, fn)

def has_transcript(video_id):
    return _TRANSCRIPT_MAP.get(video_id) is not None

def _yt_api(path, params):
    if not YOUTUBE_API_KEY:
        return None
    params["key"] = YOUTUBE_API_KEY
    url = f"{_API_BASE}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"YouTube API error: {e}")
        return None

_CHANNEL_ID_CACHE = os.path.join(CHANNEL_CACHE_DIR, "channel_ids.json")

def _resolve_channel_id(handle):
    os.makedirs(CHANNEL_CACHE_DIR, exist_ok=True)
    cache = {}
    if os.path.exists(_CHANNEL_ID_CACHE):
        with open(_CHANNEL_ID_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    if handle in cache:
        return cache[handle]
    data = _yt_api("/channels", {"part": "id", "forHandle": handle.lstrip("@")})
    if data and data.get("items"):
        cid = data["items"][0]["id"]
        cache[handle] = cid
        with open(_CHANNEL_ID_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        return cid
    return None

def _extract_handle(channel_url):
    m = re.search(r'@([\w-]+)', channel_url)
    return m.group(0) if m else None

def get_channel_playlists(channel_id, channel_url, force_refetch=False):
    os.makedirs(CHANNEL_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CHANNEL_CACHE_DIR, f"{channel_id}_playlists.json")
    if not force_refetch and os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 86400:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

    handle = _extract_handle(channel_url)
    yt_id = _resolve_channel_id(handle) if handle else None
    if yt_id:
        playlists = []
        page_token = ""
        while page_token is not None:
            params = {"part": "snippet", "channelId": yt_id, "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token
            data = _yt_api("/playlists", params)
            if not data or "items" not in data:
                break
            for entry in data["items"]:
                playlists.append({
                    "title": entry["snippet"]["title"],
                    "url": f"https://www.youtube.com/playlist?list={entry['id']}",
                    "id": entry["id"],
                })
            page_token = data.get("nextPageToken")
        if playlists:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(playlists, f, indent=2, ensure_ascii=False)
            return playlists

    try:
        import yt_dlp
        cookies_file = os.environ.get("COOKIES_FILE", "").strip()
        cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), cookies_file) if cookies_file else ""
        ydl_opts = {"extract_flat": True, "quiet": True}
        if cookies_path and os.path.isfile(cookies_path):
            ydl_opts["cookiefile"] = cookies_path
        else:
            ydl_opts["cookiesfrombrowser"] = ("firefox",)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
        playlists = []
        for entry in info.get("entries", []):
            if entry and entry.get("url") and entry.get("id"):
                playlists.append({
                    "title": entry.get("title", "Unknown"),
                    "url": entry["url"],
                    "id": entry.get("id", ""),
                })
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(playlists, f, indent=2, ensure_ascii=False)
        return playlists
    except Exception as e:
        print(f"Error fetching {channel_id}: {e}")
        return []

def probe_playlist_latest(playlist_id, playlist_url):
    data = _yt_api("/playlistItems", {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 1})
    if data and data.get("items"):
        return data["items"][0]["contentDetails"]["videoId"]
    try:
        import yt_dlp
        cookies_file = os.environ.get("COOKIES_FILE", "").strip()
        cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), cookies_file) if cookies_file else ""
        ydl_opts = {"extract_flat": True, "quiet": True, "playlistreverse": True, "playlistend": 1, "ignoreerrors": True, "sleep_requests": 1.0}
        if cookies_path and os.path.isfile(cookies_path):
            ydl_opts["cookiefile"] = cookies_path
        else:
            ydl_opts["cookiesfrombrowser"] = ("firefox",)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
        entries = info.get("entries", [])
        if entries and entries[0] and entries[0].get("id"):
            return entries[0]["id"]
    except Exception:
        pass
    return None

def get_playlist_videos(playlist_id, playlist_url, force_refetch=False):
    cache_path = os.path.join(CHANNEL_CACHE_DIR, f"videos_{playlist_id}.json")
    if not force_refetch and os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 86400:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

    if YOUTUBE_API_KEY:
        videos = []
        page_token = ""
        while page_token is not None:
            params = {"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token
            data = _yt_api("/playlistItems", params)
            if not data or "items" not in data:
                break
            for entry in data["items"]:
                vid = entry["contentDetails"]["videoId"]
                v = {
                    "id": vid,
                    "title": entry["snippet"]["title"],
                    "url": f"https://youtube.com/watch?v={vid}",
                    "sequence": entry["snippet"].get("position", 0) + 1,
                }
                published = entry["snippet"].get("publishedAt", "")
                if published and len(published) >= 10:
                    v["uploadDate"] = published[:10].replace("-", "")
                videos.append(v)
            page_token = data.get("nextPageToken")
        if videos:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(videos, f, indent=2, ensure_ascii=False)
            return videos

    try:
        import yt_dlp
        cookies_file = os.environ.get("COOKIES_FILE", "").strip()
        cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), cookies_file) if cookies_file else ""
        ydl_opts = {"extract_flat": True, "quiet": True, "sleep_requests": 1.0, "sleep_interval": 5, "max_sleep_interval": 30, "ignoreerrors": True}
        if cookies_path and os.path.isfile(cookies_path):
            ydl_opts["cookiefile"] = cookies_path
        else:
            ydl_opts["cookiesfrombrowser"] = ("firefox",)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
        videos = []
        for idx, entry in enumerate(info.get("entries", []), 1):
            if not entry or not entry.get("id"):
                continue
            v = {
                "id": entry["id"],
                "title": entry.get("title", "Unknown"),
                "url": f"https://youtube.com/watch?v={entry['id']}",
                "sequence": idx,
            }
            upload_date = entry.get("upload_date", "")
            if len(upload_date) == 8 and re.match(r'^\d{8}$', upload_date):
                v["uploadDate"] = upload_date
            videos.append(v)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(videos, f, indent=2, ensure_ascii=False)
        return videos
    except Exception:
        return []

SECTIONS_ORDERED = [
    "Upanishads", "Bhagvad Gita", "General Bhagvad Gita Talks",
    "Advaita Gitas", "Prakarana Granthas", "Yoga & Meditation",
    "Bhakti & Devotion", "Satsangs"
]

def assign_section(playlist_title, category_config):
    for category in category_config.get("categories", []):
        for pattern in category.get("patterns", []):
            if re.search(pattern, playlist_title, re.IGNORECASE):
                return category["name"]
    return "Satsangs"

def clean_path(p):
    p = p.replace("|", "-").replace("/", "-").replace("\\", "-")
    p = re.sub(r'[<>:"/\|?*]', "", p)
    p = p.strip(". ")
    return p[:200]

def build_catalog(progress_callback=None, on_new_videos=None, quick=True):
    global build_state
    def _progress(stage, progress, message):
        with _state_lock:
            build_state["stage"] = stage
            build_state["progress"] = progress
            build_state["message"] = message
        if progress_callback:
            progress_callback(stage, progress, message)

    try:
        category_config = {}
        if os.path.exists(CATEGORY_CONFIG):
            with open(CATEGORY_CONFIG, encoding="utf-8") as f:
                category_config = json.load(f)

        _progress("playlists_smiling", 5, "Fetching playlists from @smilingswami...")
        playlists = get_channel_playlists("smilingswami", "https://www.youtube.com/@smilingswami/playlists", force_refetch=quick)
        ch1 = [{"playlist": p, "channel": "smilingswami"} for p in playlists]

        _progress("playlists_satsa", 10, "Fetching playlists from @swamianubhavanandajissatsa8242...")
        playlists2 = get_channel_playlists("satsa8242", "https://www.youtube.com/@swamianubhavanandajissatsa8242/playlists", force_refetch=quick)
        ch2 = [{"playlist": p, "channel": "satsa8242"} for p in playlists2]

        all_playlists = ch1 + ch2
        total_pl = len(all_playlists)

        old_talks = {}
        old_playlist_map = {}
        if os.path.exists(CATALOG_JSON):
            try:
                with open(CATALOG_JSON, encoding="utf-8") as f:
                    old_data = json.load(f)
                for sec in old_data.get("sections", []):
                    for item in sec.get("items", []):
                        if item.get("type") == "playlist":
                            for talk in item.get("talks", []):
                                old_talks[talk["videoId"]] = talk
                            pn = item.get("name", "")
                            old_playlist_map[pn] = {
                                "section": sec["name"],
                                "talks": item["talks"],
                                "playlistTitle": pn,
                            }
                        elif item.get("type") == "group":
                            for pl in item.get("playlists", []):
                                for talk in pl.get("talks", []):
                                    old_talks[talk["videoId"]] = talk
                                pn = pl.get("playlistTitle", pl.get("name", ""))
                                old_playlist_map[pn] = {
                                    "section": sec["name"],
                                    "talks": pl.get("talks", []),
                                    "playlistTitle": pn,
                                }
            except Exception:
                old_talks = {}
                old_playlist_map = {}

        build_transcript_map()
        _progress("transcripts", 15, "Scanning transcript files...")

        new_video_ids = []
        pl_data_map = {}

        for idx, pl_info in enumerate(all_playlists):
            if quick:
                pct = 20 + int(70 * idx / max(total_pl, 1))
            else:
                pct = 35 + int(40 * idx / max(total_pl, 1))

            pl = pl_info["playlist"]
            channel = pl_info["channel"]
            playlist_title = pl["title"]
            section = assign_section(playlist_title, category_config)

            # Quick mode: probe if playlist needs re-fetching
            if quick and playlist_title in old_playlist_map:
                cache_file = os.path.join(CHANNEL_CACHE_DIR, f"videos_{pl['id']}.json")
                if os.path.exists(cache_file):
                    _progress("videos", pct, f"Checking ({idx+1}/{total_pl}): {playlist_title[:50]}...")
                    latest_id = probe_playlist_latest(pl["id"], pl["url"])
                    if latest_id and latest_id in old_talks:
                        # No new content — reuse old data with updated transcript status
                        if playlist_title not in pl_data_map:
                            old_pl = old_playlist_map[playlist_title]
                            talks = []
                            for t in old_pl["talks"]:
                                t = dict(t)
                                t["hasTranscript"] = has_transcript(t["videoId"])
                                talks.append(t)
                            pl_data_map[playlist_title] = {
                                "section": old_pl.get("section", section),
                                "playlistTitle": playlist_title,
                                "talks": talks,
                            }
                        continue

            # Full re-fetch (new playlist, new content, or non-quick mode)
            _progress("videos", pct, f"Fetching ({idx+1}/{total_pl}): {playlist_title[:50]}...")
            videos = get_playlist_videos(pl["id"], pl["url"], force_refetch=True)
            if not videos:
                if playlist_title in old_playlist_map and playlist_title not in pl_data_map:
                    old_pl = old_playlist_map[playlist_title]
                    talks = []
                    for t in old_pl["talks"]:
                        t = dict(t)
                        t["hasTranscript"] = has_transcript(t["videoId"])
                        talks.append(t)
                    pl_data_map[playlist_title] = {
                        "section": old_pl.get("section", section),
                        "playlistTitle": playlist_title,
                        "talks": talks,
                    }
                continue

            if playlist_title not in pl_data_map:
                pl_data_map[playlist_title] = {
                    "section": section,
                    "playlistTitle": playlist_title,
                    "talks": [],
                }
            for vid in videos:
                vid_id = vid["id"]
                if vid_id not in old_talks:
                    new_video_ids.append(vid_id)
                found = has_transcript(vid_id)
                old = old_talks.get(vid_id, {})
                pl_data_map[playlist_title]["talks"].append({
                    "id": f"t-{vid_id}",
                    "title": vid.get("title", old.get("title", "Unknown")),
                    "videoId": vid_id,
                    "talkNum": vid.get("sequence", old.get("talkNum", 0)),
                    "channel": channel,
                    "hasTranscript": found,
                    "playlistFolder": playlist_title,
                    "url": vid.get("url", old.get("url", f"https://youtube.com/watch?v={vid_id}")),
                    "uploadDate": vid.get("uploadDate", old.get("uploadDate", "")),
                })

        # Preserve old playlists no longer returned by YouTube
        for title, old_pl in old_playlist_map.items():
            if title not in pl_data_map:
                talks = []
                for t in old_pl["talks"]:
                    t = dict(t)
                    t["hasTranscript"] = has_transcript(t["videoId"])
                    talks.append(t)
                pl_data_map[title] = {
                    "section": old_pl["section"],
                    "playlistTitle": title,
                    "talks": talks,
                }

        _progress("organizing", 92, "Organizing catalog...")
        sections_map = {s: [] for s in SECTIONS_ORDERED}
        for pl_title, pl_data in pl_data_map.items():
            section = pl_data["section"]
            if section not in sections_map:
                section = "Satsangs"
            safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', pl_title)[:60]
            sections_map[section].append({
                "type": "playlist",
                "id": f"pl-{safe_id}",
                "name": pl_title[:70],
                "talks": pl_data["talks"],
            })

        sections_out = []
        total_talks = 0
        for sec in SECTIONS_ORDERED:
            items = sections_map.get(sec, [])
            if not items:
                continue
            sec_id = re.sub(r'[^a-z]', '', sec.lower())
            sections_out.append({
                "id": f"sec-{sec_id}",
                "name": sec,
                "items": items,
            })
            for item in items:
                total_talks += len(item.get("talks", []))

        catalog_data = {
            "meta": {
                "title": "Swami Anubhavananda Talks",
                "subtitle": "smilingswami & swamianubhavanandajissatsa8242",
                "generated": datetime.now().strftime("%B %d, %Y"),
                "totalSections": len(sections_out),
                "totalPlaylists": len(pl_data_map),
                "totalTalks": total_talks,
            },
            "sections": sections_out,
        }

        with open(CATALOG_JSON, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, ensure_ascii=False, indent=2)

        _progress("done", 100, "Catalog ready!")
        if new_video_ids and on_new_videos:
            on_new_videos(new_video_ids)
        return catalog_data, new_video_ids
    except Exception as e:
        import traceback
        traceback.print_exc()
        with _state_lock:
            build_state["stage"] = "error"
            build_state["error"] = str(e)
        return None, []
