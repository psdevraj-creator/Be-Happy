# Be Happy — Swami Anubhavananda Talks

Self-contained PWA catalog of Vedanta talks from [@smilingswami](https://www.youtube.com/@smilingswami) and [@swamianubhavanandajissatsa8242](https://www.youtube.com/@swamianubhavanandajissatsa8242).

**10,904 talks** across **1,950 playlists** in **8 sections**.

## What's Included

| File | Purpose |
|------|---------|
| `BHTalks.html` | Self-contained catalog — open anywhere, works offline |
| `manifest.json` | PWA manifest for Android "Add to Home Screen" |
| `sw.js` | Service worker for offline cache |
| `icons/` | App icons (192x192, 512x512) |

## How to Use

### Direct download
Download `BHTalks.html` → open in any browser — sidebar works, search works, videos play embedded.

### Install as Android app
1. Host this folder on any web server (GitHub Pages works)
2. Visit the URL on Android Chrome
3. Tap "Add to Home Screen"

The app launches fullscreen with no URL bar. Catalog data works offline (videos need internet).

### Features
- **3 sort modes**: By Playlist | Newest First | A-Z
- **Search** — filters by talk title in real-time
- **Resizable sidebar** — drag to expand
- **YouTube embed** — videos play inline or open in YouTube app
- **Channel badges** — shows @smilingswami / @satsa8242 per talk

## Build from source

```bash
python catalog.py                 # Build catalog from YouTube (optional)
python build_android.py           # Regenerate BHTalks.html + PWA files
```

## Sections
- Upanishads
- Bhagvad Gita
- General Bhagvad Gita Talks
- Advaita Gitas
- Prakarana Granthas
- Yoga & Meditation
- Bhakti & Devotion
- Satsangs
