"""
publisher.py — Auto-build static catalog + git push for GitHub Pages mirror.
"""

import os, sys, subprocess, threading, time
from pathlib import Path

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
GIT_REPO_DIR = PROJECT_DIR
GITHUB_PAGES_DIR = os.path.join(PROJECT_DIR, "Be_Happy_GitHub")

publish_state = {"stage": "idle", "progress": 0, "message": "", "error": None}
_state_lock = threading.Lock()

def git(*args, cwd=None):
    cwd = cwd or GIT_REPO_DIR
    try:
        r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, timeout=60)
        return r.returncode == 0, r.stdout.strip()
    except Exception as e:
        return False, str(e)

def publish_to_github(new_video_ids=None):
    """Rebuild static HTML, add/commit/push catalog.json + transcripts to GitHub."""
    global publish_state
    try:
        with _state_lock:
            publish_state = {"stage": "publishing", "progress": 0, "message": "Building static pages...", "error": None}

        # Step 1: Run build_android.py
        bap = os.path.join(PROJECT_DIR, "build_android.py")
        if os.path.exists(bap):
            r = subprocess.run([sys.executable, bap], cwd=PROJECT_DIR, capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                print(f"build_android.py warning: {r.stderr[:500]}")
        with _state_lock:
            publish_state["progress"] = 40

        # Step 2: If GitHub Pages dir is within repo, add those changes too
        if os.path.isdir(GITHUB_PAGES_DIR):
            ok, _ = git("add", "-f", "-A", cwd=GITHUB_PAGES_DIR)
        with _state_lock:
            publish_state["progress"] = 50
            publish_state["message"] = "Committing changes..."

        # Step 3: Commit
        msg = "Auto-update catalog"
        if new_video_ids:
            msg += f" ({len(new_video_ids)} new videos)"
        ok, _ = git("commit", "-m", msg)
        with _state_lock:
            publish_state["progress"] = 70
            publish_state["message"] = "Pushing to GitHub Pages..."

        # Step 4: Push Be_Happy_GitHub/ contents to gh-pages branch
        ok, out = git("push", "origin", "gh-pages:gh-pages")
        if not ok:
            raise Exception(f"git push failed: {out[:500]}")
        with _state_lock:
            publish_state["stage"] = "done"
            publish_state["progress"] = 100
            publish_state["message"] = "Published to GitHub Pages!"
    except Exception as e:
        with _state_lock:
            publish_state["stage"] = "error"
            publish_state["error"] = str(e)[:500]
            publish_state["message"] = f"Error: {str(e)[:100]}"
        import traceback
        traceback.print_exc()

def get_publish_status():
    with _state_lock:
        return dict(publish_state)
