"""
main.py — Unified FastAPI server for Vedanta Study.
Combines: Catalog browser, RAG Chat, GitaVerse Study, Wiki, Transcription.
Password-protected via HTTP Basic Auth.
"""

import os, sys, re, time, json, hashlib, asyncio, logging, threading
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import chromadb
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from sse_starlette.sse import EventSourceResponse
from starlette.templating import Jinja2Templates

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

load_dotenv()

from config import (
    CHROMA_DIR, LLM_MODEL, LLM_BASE_URL, LLM_API_KEY,
    TOP_K_RESULTS, RETRIEVAL_CANDIDATES, MAX_CONTEXT_TOKENS, SOURCE_ROOTS,
    OPENROUTER_LLM_MODEL, OPENROUTER_LLM_BASE_URL, OPENROUTER_LLM_API_KEY,
    EMBEDDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_BASE_URL, EMBEDDING_DIMENSIONS,
    RERANK_TOP_K,
)
from embedding import embedding_fn
from indexer import build_index, index_stats
from progress import get_progress, reset_progress, finish_progress
from wiki_manager import ensure_wiki, search_wiki, get_wiki_stats, wiki_ingest_source, write_page, update_index, log_entry, read_page, page_path, page_exists, PAGES_DIRS, INDEX_FILE, LOG_FILE
from wiki_manager import _read as wiki_read
from prompts import SYSTEM_PROMPT
from retrieval import QueryRewriter, Retriever, LLMReranker, DiversitySelector, ContextAssembler
from conversation import ConversationManager
import qa_history

import catalog_builder
from catalog_builder import build_catalog, build_transcript_map, has_transcript, CATALOG_JSON, build_state as catalog_build_state
from transcriber import run_transcription, get_transcribe_task, get_all_transcribe_tasks, transcribe_tasks
from publisher import publish_to_github, publish_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("vedanta")

# ── Auth ────────────────────────────────────────────────────
PASSWORD = os.environ.get("PASSWORD", "") or os.environ.get("VEDANTA_PASSWORD", "")
security = HTTPBasic(auto_error=False)

async def verify_auth(credentials: Optional[HTTPBasicCredentials] = Depends(security)):
    if not PASSWORD:
        return True
    if not credentials:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    if credentials.password != PASSWORD:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return True

IS_RENDER = os.environ.get("RENDER", "").lower() in ("true", "1", "yes") or os.environ.get("CLOUD_RUN", "").lower() in ("true", "1", "yes")

# ── Globals ─────────────────────────────────────────────────
client = None
collection = None
llm_client = None
or_client = None
index_ready = False
query_rewriter = None
retriever = None
reranker = None
diversity_selector = None
context_assembler = None
conv_manager = None
_reindex_task = None

# Batch transcription queue
_batch_queue = []
_batch_current = None
_batch_completed = []
_batch_failed = []

from openai import OpenAI as OpenAI_Client

# ── Lifespan ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, collection, llm_client, or_client, index_ready
    global query_rewriter, retriever, reranker, diversity_selector, context_assembler, conv_manager

    # Init ChromaDB
    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        collection = client.get_or_create_collection(
            name="vedanta", embedding_function=embedding_fn, metadata={"hnsw:space": "cosine"}
        )
        index_ready = True
    except Exception as e:
        logger.warning(f"ChromaDB init: {e}")

    # Init LLM clients
    if LLM_API_KEY:
        llm_client = OpenAI_Client(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    if OPENROUTER_LLM_API_KEY:
        or_client = OpenAI_Client(api_key=OPENROUTER_LLM_API_KEY, base_url=OPENROUTER_LLM_BASE_URL)

    # Init pipeline components
    query_rewriter = QueryRewriter(llm_client, model=LLM_MODEL, or_client=or_client)
    retriever = Retriever(collection)
    reranker = LLMReranker(llm_client, model=LLM_MODEL, or_client=or_client)
    diversity_selector = DiversitySelector()
    context_assembler = ContextAssembler()
    conv_manager = ConversationManager()

    # Build transcript map from Transcripts 2/
    build_transcript_map()

    # Load catalog
    if os.path.exists(CATALOG_JSON):
        with open(CATALOG_JSON, encoding="utf-8") as f:
            app.state.catalog_data = json.load(f)
    else:
        app.state.catalog_data = None

    yield

app = FastAPI(title="Vedanta Study", lifespan=lifespan)
app.state.catalog_data = None

# ── Auth middleware on all routes ───────────────────────────
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if PASSWORD:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            from fastapi.responses import Response
            return Response(status_code=401, headers={"WWW-Authenticate": "Basic"}, content="Unauthorized")
        import base64
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            _, pw = decoded.split(":", 1)
            if pw != PASSWORD:
                return Response(status_code=401, headers={"WWW-Authenticate": "Basic"})
        except Exception:
            return Response(status_code=401, headers={"WWW-Authenticate": "Basic"})
    response = await call_next(request)
    return response

# ================================================================
#  FRONTEND ROUTE
# ================================================================
@app.get("/", response_class=HTMLResponse, dependencies=[Depends(verify_auth)])
async def serve_home():
    html_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>Vedanta Study</h1><p>UI not found.</p>")

# ================================================================
#  CATALOG ROUTES
# ================================================================
@app.get("/api/catalog", dependencies=[Depends(verify_auth)])
async def api_catalog():
    if app.state.catalog_data is None and os.path.exists(CATALOG_JSON):
        with open(CATALOG_JSON, encoding="utf-8") as f:
            app.state.catalog_data = json.load(f)
    if app.state.catalog_data is None:
        return JSONResponse({"error": "Catalog still building"}, status_code=503)
    return app.state.catalog_data

@app.get("/api/build-status", dependencies=[Depends(verify_auth)])
async def api_build_status():
    return catalog_build_state

@app.get("/api/build-events", dependencies=[Depends(verify_auth)])
async def api_build_events():
    async def event_generator():
        last = None
        while True:
            with catalog_builder._state_lock:
                cur = dict(catalog_builder.build_state)
            if cur != last:
                yield {"data": json.dumps(cur)}
                if cur.get("stage") == "done":
                    yield {"event": "done", "data": json.dumps(cur)}
                    break
                elif cur.get("stage") == "error":
                    yield {"event": "error", "data": json.dumps(cur)}
                    break
                last = cur
            await asyncio.sleep(0.3)
    return EventSourceResponse(event_generator())

@app.get("/api/catalog-grid", dependencies=[Depends(verify_auth)])
async def api_catalog_grid(request: Request, section: str = "", playlist: str = "", q: str = ""):
    data = app.state.catalog_data
    if data is None:
        if os.path.exists(CATALOG_JSON):
            with open(CATALOG_JSON, encoding="utf-8") as f:
                data = json.load(f)
            app.state.catalog_data = data
        else:
            return HTMLResponse('<div class="no-results">Catalog not available</div>')
    from catalog_builder import has_transcript as ht
    return templates.TemplateResponse("catalog_partial.html", {
        "request": request, "sections": data.get("sections", []),
        "section": section, "playlist": playlist, "q": q,
    })

@app.post("/api/refresh", dependencies=[Depends(verify_auth)])
async def api_refresh():
    def on_new_videos(video_ids):
        logger.info(f"Detected {len(video_ids)} new videos, publishing...")
        publish_to_github(new_video_ids=video_ids)

    def progress_cb(stage, progress, message):
        pass

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, lambda: _run_refresh(progress_cb, on_new_videos))

    return {"status": "started"}

def _run_refresh(progress_cb, on_new_videos):
    global index_ready
    catalog, new_vids = build_catalog(progress_callback=progress_cb, on_new_videos=on_new_videos, quick=True)
    if catalog:
        app.state.catalog_data = catalog
    build_transcript_map()
    if not IS_RENDER:
        try:
            import subprocess
            subprocess.run([sys.executable, "build_android.py"],
                           cwd=os.path.dirname(os.path.abspath(__file__)),
                           capture_output=True, timeout=300)
        except Exception as e:
            logger.error(f"build_android.py: {e}")
    if new_vids:
        logger.info(f"Triggered publish for {len(new_vids)} new videos")
        import subprocess, os
        subprocess.run(['git', 'push'], cwd=os.path.dirname(os.path.abspath(__file__)), check=True)

@app.get("/api/publish-status", dependencies=[Depends(verify_auth)])
async def api_publish_status():
    return publish_state

@app.get("/api/transcript/{video_id}", dependencies=[Depends(verify_auth)])
async def api_transcript(video_id: str):
    from catalog_builder import _TRANSCRIPT_MAP
    fp = _TRANSCRIPT_MAP.get(video_id) if _TRANSCRIPT_MAP else None
    if not fp or not os.path.exists(fp):
        return {"found": False}
    try:
        from publish_transcript import markdown_to_html
        with open(fp, "r", encoding="utf-8") as f:
            md = f.read()
        html = markdown_to_html(md, context="talk")
        return {"found": True, "html": html}
    except Exception as e:
        return {"found": False, "error": str(e)}

@app.get("/transcript/{video_id}", dependencies=[Depends(verify_auth)])
async def transcript_page(video_id: str):
    result = await api_transcript(video_id)
    if not result.get("found"):
        return HTMLResponse("<h1>Transcript not found</h1><p><a href='/'>Back to catalog</a></p>")
    html_body = result.get("html", "")
    title_match = re.search(r'<h1>(.*?)</h1>', html_body)
    title = title_match.group(1) if title_match else "Transcript"
    page = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} — Transcript</title>
<style>
  body {{ font-family:Georgia,serif; line-height:1.8; max-width:800px; margin:0 auto; padding:40px 20px; background:#fcf9f5; color:#1a1a2e; }}
  h1 {{ font-family:'Playfair Display',Georgia,serif; font-size:24px; color:#C76B1E; }}
  h2 {{ font-size:20px; margin-top:24px; }}
  blockquote {{ margin:12px 0; padding:10px 14px; border-left:3px solid #C76B1E; background:#fff5eb; border-radius:4px; }}
  blockquote strong {{ font-size:18px; font-family:'Noto Sans Devanagari',serif; }}
  p {{ margin-bottom:10px; }}
  a.back {{ display:inline-block; margin-bottom:16px; color:#C76B1E; text-decoration:none; font-size:13px; }}
  a.back:hover {{ text-decoration:underline; }}
  hr {{ border:none; border-top:1px solid #e8e0d8; margin:20px 0; }}
</style>
</head>
<body>
<a class="back" href="javascript:window.close()">← Close tab</a>
{html_body}
</body></html>"""
    return HTMLResponse(page)

# ================================================================
#  TRANSCRIPTION ROUTES
# ================================================================
_transcribe_lock = threading.Lock()

@app.post("/api/transcribe", dependencies=[Depends(verify_auth)])
async def api_transcribe(req: Request):
    data = await req.json()
    video_id = data.get("videoId")
    title = data.get("title", "Unknown")
    url = data.get("url", "")
    playlist_folder = data.get("playlistFolder", "Satsangs")

    if not video_id:
        return {"status": "error", "message": "Missing videoId"}
    if IS_RENDER:
        return {"status": "error", "message": "Transcription not available on Render (run locally)"}

    with _transcribe_lock:
        existing = get_transcribe_task(video_id)
        if existing and existing.get("stage") not in ("done", "error"):
            return {"status": "already_running"}

    threading.Thread(target=run_transcription, args=(video_id, title, url, playlist_folder, _on_transcribe_done), daemon=True).start()
    return {"status": "started"}

@app.post("/api/transcribe/batch", dependencies=[Depends(verify_auth)])
async def api_transcribe_batch(req: Request):
    global _batch_queue, _batch_current, _batch_completed, _batch_failed
    data = await req.json()
    video_ids = data.get("videoIds", [])
    if not video_ids:
        return {"status": "error", "message": "No videoIds provided"}
    if IS_RENDER:
        return {"status": "error", "message": "Transcription not available on Render"}

    catalog = app.state.catalog_data
    if not catalog:
        if os.path.exists(CATALOG_JSON):
            with open(CATALOG_JSON, encoding="utf-8") as f:
                catalog = json.load(f)
    talk_map = {}
    for sec in catalog.get("sections", []):
        for pl in sec.get("items", []):
            for t in pl.get("talks", []):
                talk_map[t["videoId"]] = t

    queue = []
    for vid in video_ids:
        t = talk_map.get(vid, {})
        queue.append({
            "videoId": vid,
            "title": t.get("title", "Unknown"),
            "playlistFolder": t.get("playlistFolder", "Satsangs"),
            "url": t.get("url", f"https://youtube.com/watch?v={vid}"),
        })

    with _transcribe_lock:
        _batch_queue = queue
        _batch_current = None
        _batch_completed = []
        _batch_failed = []

    threading.Thread(target=_process_batch_queue, daemon=True).start()
    return {"status": "started", "queued": len(queue)}

@app.get("/api/transcribe/batch-status", dependencies=[Depends(verify_auth)])
async def api_batch_status():
    with _transcribe_lock:
        return {
            "queued": len(_batch_queue),
            "current": _batch_current,
            "completed": _batch_completed,
            "failed": _batch_failed,
            "all_tasks": get_all_transcribe_tasks(),
        }

@app.post("/api/transcribe/batch/cancel", dependencies=[Depends(verify_auth)])
async def api_batch_cancel():
    global _batch_queue
    with _transcribe_lock:
        _batch_queue = []
    return {"status": "cancelled"}

@app.get("/api/transcribe/status/{video_id}", dependencies=[Depends(verify_auth)])
async def api_transcribe_status(video_id: str):
    t = get_transcribe_task(video_id)
    if not t:
        return {"stage": "not_found", "progress": 0, "message": "Not found"}
    return t

def _on_transcribe_done(video_id, title):
    build_transcript_map()
    if app.state.catalog_data:
        for sec in app.state.catalog_data.get("sections", []):
            for pl in sec.get("items", []):
                for t in pl.get("talks", []):
                    if t["videoId"] == video_id:
                        t["hasTranscript"] = True
    logger.info(f"Transcript complete: {title}")

def _process_batch_queue():
    global _batch_queue, _batch_current, _batch_completed, _batch_failed
    while True:
        with _transcribe_lock:
            if not _batch_queue:
                break
            item = _batch_queue.pop(0)
            _batch_current = item["videoId"]
        vid = item["videoId"]
        run_transcription(vid, item["title"], item["url"], item["playlistFolder"], _on_transcribe_done)
        t = get_transcribe_task(vid)
        if t and t.get("stage") == "error":
            with _transcribe_lock:
                _batch_failed.append(vid)
        else:
            with _transcribe_lock:
                _batch_completed.append(vid)
        with _transcribe_lock:
            _batch_current = None

# ================================================================
#  CHAT ROUTES (from vedanta-chat app.py)
# ================================================================
@app.get("/api/status", dependencies=[Depends(verify_auth)])
async def api_status():
    global index_ready
    stats = {}
    if collection:
        try:
            stats = {"chunks": collection.count()}
        except Exception:
            pass
    if not isinstance(stats, dict):
        stats = {"chunks": 0}
    if "chunks" not in stats:
        stats["chunks"] = 0
    wiki_stats = {}
    try:
        wiki_stats = get_wiki_stats()
    except Exception:
        pass
    avail = {}
    if llm_client:
        avail[LLM_MODEL] = "DeepSeek V4 Pro"
    if or_client:
        avail[OPENROUTER_LLM_MODEL] = "OpenRouter Free"
    return {
        "index_ready": index_ready,
        "stats": stats,
        "wiki": wiki_stats,
        "available_models": avail,
        "is_render": IS_RENDER,
    }

@app.post("/api/chat", dependencies=[Depends(verify_auth)])
async def api_chat(req: Request):
    global index_ready, query_rewriter, retriever, reranker, diversity_selector, context_assembler, conv_manager
    data = await req.json()
    question = data.get("question", "").strip()
    model_choice = data.get("model", "deepseek")
    session_id = data.get("sessionId", "default")
    if not question:
        return {"error": "No question provided"}, 400
    if not index_ready:
        return JSONResponse({"error": "Index not ready"}, status_code=503)

    selected_client = or_client if model_choice == "openrouter" else llm_client
    selected_model = OPENROUTER_LLM_MODEL if model_choice == "openrouter" else LLM_MODEL
    if not selected_client:
        return JSONResponse({"error": f"Model '{model_choice}' not available"}, status_code=503)

    start = time.time()
    quick = data.get("quick", True)

    if quick:
        # Quick mode: skip rewrite + reranker, fewer candidates, 1 LLM call
        retrieval_query = query_rewriter.expand_vedanta_terms(question) if query_rewriter else question
        candidates = retriever.retrieve(retrieval_query, k=TOP_K_RESULTS) if retriever else []
        diverse = candidates
    else:
        # Deep mode: full pipeline (rewrite, 40 candidates, rerank, diversify)
        rewritten = query_rewriter.rewrite(question) if query_rewriter else question
        candidates = retriever.retrieve(rewritten, k=RETRIEVAL_CANDIDATES) if retriever else []
        ranked = reranker.rerank(rewritten, candidates) if reranker else candidates
        diverse = diversity_selector.select(ranked, top_k=TOP_K_RESULTS) if diversity_selector else ranked[:TOP_K_RESULTS]

    context, source_names = context_assembler.assemble(diverse) if context_assembler else ("", [])

    conv = conv_manager.get_conversation(session_id) if conv_manager else []
    conversation_text = ""
    for turn in conv[-4:]:
        conversation_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n"

    system = SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Conversation so far:\n{conversation_text}\n\nContext:\n{context}\n\nQuestion: {question}\n\nPlease provide a detailed answer citing sources with [Source: filename]."},
    ]

    try:
        resp = selected_client.chat.completions.create(
            model=selected_model, messages=messages, max_tokens=8192, temperature=0.3
        )
        answer = resp.choices[0].message.content.strip() if resp.choices else ""
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    elapsed = time.time() - start
    if conv_manager:
        conv_manager.add_turn(session_id, question, answer)

    # Save to history
    qa_id = qa_history.add_entry(question, answer, source_names)

    return {
        "answer": answer,
        "sources": source_names[:5],
        "time": round(elapsed, 2),
        "model": selected_model,
        "qa_id": qa_id,
    }

@app.post("/api/reindex", dependencies=[Depends(verify_auth)])
async def api_reindex(req: Request):
    global _reindex_task
    data = await req.json() if req.headers.get("content-type") == "application/json" else {}
    mode = data.get("mode", "incremental")
    if _reindex_task and not _reindex_task.done():
        return {"status": "already_running"}

    loop = asyncio.get_event_loop()

    def _run():
        global index_ready
        try:
            build_index(collection=collection, mode=mode)
        except Exception as e:
            logger.error(f"Reindex error: {e}")
        finally:
            index_ready = True

    _reindex_task = loop.run_in_executor(None, _run)
    return {"status": "started", "mode": mode}

@app.get("/api/reindex-progress", dependencies=[Depends(verify_auth)])
async def api_reindex_progress():
    return get_progress()

# ================================================================
#  WIKI ROUTES
# ================================================================
@app.get("/api/wiki", dependencies=[Depends(verify_auth)])
async def api_wiki(category: str = None, page: str = None):
    ensure_wiki()
    if category and page:
        content = read_page(category, page)
        if not content:
            return JSONResponse({"error": "Page not found"}, status_code=404)
        return {"content": content, "category": category, "title": page}
    stats = get_wiki_stats()
    pages = {}
    for cat, dir_path in PAGES_DIRS.items():
        if os.path.isdir(dir_path):
            files = sorted([f[:-3] for f in os.listdir(dir_path) if f.endswith(".md")])
            pages[cat] = files
    index = wiki_read(INDEX_FILE) if os.path.exists(INDEX_FILE) else ""
    log = wiki_read(LOG_FILE) if os.path.exists(LOG_FILE) else ""
    return {"stats": stats, "pages": pages, "index": index[:2000], "log": log[:2000]}

@app.post("/api/wiki-save", dependencies=[Depends(verify_auth)])
async def api_wiki_save(req: Request):
    data = await req.json()
    category = data.get("category", "concepts")
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    if not title or not content:
        return {"status": "error", "message": "Missing title or content"}
    write_page(category, title, content)
    update_index(category, title)
    log_entry(category, title)
    return {"status": "saved"}

@app.post("/api/wiki-reformat", dependencies=[Depends(verify_auth)])
async def api_wiki_reformat(req: Request):
    data = await req.json()
    text = data.get("text") or data.get("answer", "")
    if not text:
        return {"status": "error", "error": "No text"}
    try:
        resp = llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "Reformat this as a clean wiki page with sections."},
                {"role": "user", "content": text},
            ],
            max_tokens=4096,
        )
        reformatted = resp.choices[0].message.content.strip()
        return {"status": "ok", "content": reformatted}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/wiki-ingest", dependencies=[Depends(verify_auth)])
async def api_wiki_ingest():
    threading.Thread(target=wiki_ingest_source, daemon=True).start()
    return {"status": "started"}

@app.get("/api/qa-history", dependencies=[Depends(verify_auth)])
async def api_qa_history(filter_type: str = "all"):
    return qa_history.get_entries(filter_type)

@app.post("/api/save-md", dependencies=[Depends(verify_auth)])
async def api_save_md(req: Request):
    data = await req.json()
    content = data.get("content", "")
    title = data.get("title", "chat_export")
    safe = re.sub(r'[^\w\s-]', '', title)[:60] or "vedanta-answer"
    safe = safe.strip("-").lower()[:60]
    import io
    buf = io.BytesIO(content.encode("utf-8"))
    return StreamingResponse(
        buf,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={safe}.md"},
    )

@app.get("/api/sources", dependencies=[Depends(verify_auth)])
async def api_sources():
    return {"chunks": collection.count() if collection else 0}

@app.get("/api/source/{path:path}", dependencies=[Depends(verify_auth)])
async def api_source(path: str):
    for root in SOURCE_ROOTS:
        full = os.path.join(root, path)
        if os.path.isfile(full):
            return FileResponse(full, headers={"Content-Disposition": f"inline; filename=\"{os.path.basename(full)}\""})
    return JSONResponse({"error": "File not found"}, status_code=404)

# ================================================================
#  GITAVERSE ROUTES
# ================================================================
from gitaverse.pipeline import analyze_freetext as analyze_verse
from gitaverse.dictionary import mw_lookup, dhatu_lookup, gloss_from_dict
from gitaverse.scripture_ref import find_matching_verse


@app.post("/api/gitaverse/parse-words", dependencies=[Depends(verify_auth)])
async def api_gitaverse_parse_words(req: Request):
    data = await req.json()
    verse_text = data.get("verse_text", "").strip()
    text_name = data.get("text_name", "Student's verse")
    location = data.get("location", {})
    if not verse_text:
        return {"error": "No verse text"}
    passage = analyze_verse(
        verse_text,
        text_name=text_name,
        location=location,
        use_cache=True,
        use_llm=False,
        use_rag=False,
    )
    return {"passage": passage.model_dump()}


@app.post("/api/gitaverse/analyze", dependencies=[Depends(verify_auth)])
async def api_gitaverse_analyze(req: Request):
    data = await req.json()
    verse_text = data.get("verse_text", "").strip()
    style = data.get("style", "swamiji")
    use_llm = data.get("use_llm", True)
    use_rag = data.get("use_rag", True)
    use_cache = data.get("use_cache", True)
    text_name = data.get("text_name", "Student's verse")
    location = data.get("location", {})
    if not verse_text:
        return {"error": "No verse text"}
    passage = analyze_verse(
        verse_text,
        text_name=text_name,
        location=location,
        use_cache=use_cache,
        use_llm=use_llm,
        use_rag=use_rag,
        style=style,
    )
    return {"passage": passage.model_dump()}


@app.post("/api/gitaverse/translate", dependencies=[Depends(verify_auth)])
async def api_gitaverse_translate(req: Request):
    data = await req.json()
    verse_text = data.get("verse_text", "").strip()
    words = data.get("words", [])
    if not verse_text:
        return {"error": "No verse text"}
    try:
        from gitaverse.llm_client import generate_simple_translation
        result = generate_simple_translation(verse_text, words)
        return {"translation": result.get("translation", ""), "notes": result.get("notes", "")}
    except Exception as e:
        logger.warning("Translation failed: %s", e)
        return {"error": str(e)}


@app.post("/api/gitaverse/index", dependencies=[Depends(verify_auth)])
async def api_gitaverse_index(req: Request):
    data = await req.json()
    verse_text = data.get("verse_text", "")
    location = data.get("location", {})
    if not verse_text:
        return {"error": "No verse text"}
    title = location.get("book", "") or location.get("chapter", "") or "Sanskrit verse"
    loc_str = "-".join(str(v) for v in location.values()) if location else "free"
    from indexer import _process_file, load_index_state, save_index_state
    import tempfile
    passage_id = f"gv-{loc_str}-{hashlib.md5(verse_text.encode()).hexdigest()[:8]}"
    fp = os.path.join(tempfile.gettempdir(), f"{passage_id}.md")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\n---\n\n{verse_text}")
    state = load_index_state()
    chunks, _ = _process_file(fp, collection)
    state[fp] = hashlib.md5(open(fp, "rb").read()[:8192]).hexdigest() + str(os.path.getsize(fp))
    save_index_state(state)
    return {"status": "ok", "chunks_indexed": len(chunks) if chunks else 0}

@app.get("/api/gitaverse/history", dependencies=[Depends(verify_auth)])
async def api_gitaverse_history(limit: int = 50):
    import sqlite3
    import json as _json
    db_path = os.path.join(os.path.dirname(__file__), "gitaverse_cache.sqlite3")
    if not os.path.exists(db_path):
        return {"entries": []}
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT text_id, location_key, json_data, fetched_at FROM passages ORDER BY fetched_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    entries = []
    seen = set()
    for row in rows:
        data = _json.loads(row[2])
        dev = data.get("dev_text", "")
        key = (row[0], row[1])
        if key in seen:
            continue
        seen.add(key)
        loc = data.get("location", {})
        entries.append({
            "text_id": data.get("text_id", row[0]),
            "location_key": row[1],
            "text_name": data.get("text_name", "Untitled"),
            "location": loc,
            "location_label": " — ".join(str(loc[k]) for k in ("book", "chapter", "verse", "sutra", "quarter") if k in loc) if loc else "",
            "dev_preview": dev[:80] if dev else "",
            "fetched_at": row[3],
            "has_analysis": bool(data.get("english_commentaries")),
        })
    return {"entries": entries}

@app.get("/api/gitaverse/cached-passage", dependencies=[Depends(verify_auth)])
async def api_gitaverse_cached(text_id: str = "free-text", location_key: str = ""):
    if not location_key:
        return {"found": False}
    import sqlite3
    import json as _json
    db_path = os.path.join(os.path.dirname(__file__), "gitaverse_cache.sqlite3")
    if not os.path.exists(db_path):
        return {"found": False}
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT text_id, location_key, json_data, fetched_at FROM passages WHERE text_id=? AND location_key=? LIMIT 1",
        (text_id, location_key),
    ).fetchone()
    conn.close()
    if not row:
        return {"found": False}
    data = _json.loads(row[2])
    return {"found": True, "passage": data, "fetched_at": row[3]}

@app.delete("/api/gitaverse/cached-passage", dependencies=[Depends(verify_auth)])
async def api_gitaverse_delete(text_id: str = "free-text", location_key: str = ""):
    if not location_key:
        return {"status": "missing_key"}
    import sqlite3
    db_path = os.path.join(os.path.dirname(__file__), "gitaverse_cache.sqlite3")
    if not os.path.exists(db_path):
        return {"status": "not_found"}
    conn = sqlite3.connect(db_path)
    conn.execute(
        "DELETE FROM passages WHERE text_id=? AND location_key=?",
        (text_id, location_key),
    )
    conn.commit()
    conn.close()
    return {"status": "deleted"}

@app.get("/api/gitaverse/dictionary-lookup", dependencies=[Depends(verify_auth)])
async def api_gitaverse_dict(word: str = ""):
    if not word:
        return {"error": "No word"}
    mw = mw_lookup(word)
    dh = dhatu_lookup(word)
    gloss = gloss_from_dict(word)
    return {"mw": mw, "dhatu": dh, "gloss": gloss}

@app.post("/api/gitaverse/scripture-match", dependencies=[Depends(verify_auth)])
async def api_gitaverse_scripture(req: Request):
    data = await req.json()
    verse = data.get("verse", "")
    if not verse:
        return {"error": "No verse"}
    return find_matching_verse(verse)

# ================================================================
#  STATIC FILES
# ================================================================
@app.get("/swamiji.jpg", dependencies=[Depends(verify_auth)])
async def serve_photo():
    fp = os.path.join(os.path.dirname(__file__), "Swamiji.jpg")
    if os.path.exists(fp):
        return FileResponse(fp, media_type="image/jpeg")
    return JSONResponse({"error": "Not found"}, status_code=404)

# ================================================================
#  ENTRY POINT
# ================================================================
def main():
    port = int(os.environ.get("PORT", 8765))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Vedanta Study server starting on http://localhost:{port}")
    if PASSWORD:
        print(f"Password protection enabled")
    if IS_RENDER:
        print("Mode: Cloud/Render (transcription disabled)")
    else:
        print("Mode: Local (full features)")
    uvicorn.run("main:app", host=host, port=port, reload=False)

if __name__ == "__main__":
    main()
