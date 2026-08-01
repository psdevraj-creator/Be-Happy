"""
build_android.py — Generate self-contained BHTalks.html for Android/offline use.

Reads catalog.json (or falls back to Be_Happy_Lightweight/data.json),
strips heavy fields, embeds catalog into a single standalone HTML file.

Usage:  python build_android.py
"""

import os, sys, json, shutil, re, base64
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(PROJECT_DIR, "Be_Happy_Android", "BHTalks.html")
GITHUB_COPY = os.path.join(PROJECT_DIR, "Be_Happy_GitHub", "index.html")

PHOTO_PATH = os.path.join(PROJECT_DIR, "Swamiji.jpg")


def load_catalog():
    """Read catalog data from catalog.json (preferred) or data.json (fallback)."""
    catalog_path = os.path.join(PROJECT_DIR, "catalog.json")
    data_path = os.path.join(PROJECT_DIR, "Be_Happy_Lightweight", "data.json")

    if os.path.exists(catalog_path):
        with open(catalog_path, encoding="utf-8") as f:
            return json.load(f), "catalog.json"
    elif os.path.exists(data_path):
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
        # Add channel field to all talks (existing data is from @smilingswami)
        for sec in data.get("sections", []):
            for item in sec.get("items", []):
                if item.get("type") == "playlist":
                    for talk in item.get("talks", []):
                        talk["channel"] = "smilingswami"
                        # Remove heavy html field
                        talk.pop("html", None)
                elif item.get("type") == "group":
                    for pl in item.get("playlists", []):
                        for talk in pl.get("talks", []):
                            talk["channel"] = "smilingswami"
                            talk.pop("html", None)
        return data, "Be_Happy_Lightweight/data.json"
    else:
        print("ERROR: Neither catalog.json nor Be_Happy_Lightweight/data.json found.")
        print("Run 'python catalog.py' first to build the catalog.")
        sys.exit(1)


def strip_fields(data):
    """Remove heavy fields not needed for video-only display."""
    for sec in data.get("sections", []):
        for item in sec.get("items", []):
            if item.get("type") == "playlist":
                for talk in item.get("talks", []):
                    talk.pop("hasTranscript", None)
                    talk.pop("playlistFolder", None)
                    talk.pop("url", None)
                    talk.pop("html", None)
            elif item.get("type") == "group":
                for pl in item.get("playlists", []):
                    for talk in pl.get("talks", []):
                        talk.pop("hasTranscript", None)
                        talk.pop("playlistFolder", None)
                        talk.pop("url", None)
                        talk.pop("html", None)
    return data


def photo_base64():
    """Return base64-encoded photo or empty string."""
    import base64
    if os.path.exists(PHOTO_PATH):
        with open(PHOTO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""


# ================================================================
#  BHTalks.html Template
# ================================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Be Happy — Swami Anubhavananda Talks</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Inter:opsz,wght@14..32,300;14..32,400;14..32,500;14..32,600;14..32,700&family=Noto+Sans+Devanagari:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#C76B1E">
<link rel="icon" type="image/png" sizes="192x192" href="icons/icon-192.png">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box;}
:root{--primary:#C76B1E;--primary-soft:#E8914A;--primary-light:#FFF5EB;--primary-muted:#E8D5C0;--bg:#FCF9F5;--surface:#FFFFFF;--text:#1A1A2E;--text-soft:#4A4A5E;--text-muted:#8A8A9E;--border:#E8E0D8;--border-light:#F2ECE4;--nav-bg:#FAF5F0;--radius:12px;--radius-sm:8px;}
body{background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif;font-size:15px;line-height:1.6;}
.hero{background:linear-gradient(135deg,#FAF0E6 0%,#FCF9F5 50%,#FFF8F0 100%);border-bottom:1px solid var(--border);padding:20px 16px 16px;text-align:center;}
.hero-inner{max-width:720px;margin:0 auto;}
.hero-photo{width:80px;height:80px;border-radius:50%;object-fit:cover;border:3px solid var(--primary);margin-bottom:8px;}
.hero h1{font-family:'Playfair Display',serif;font-size:28px;font-weight:600;color:var(--primary);}
.hero .subtitle{font-size:13px;color:var(--text-soft);}
.hero .meta{font-size:11px;color:var(--text-muted);margin-top:4px;}
.layout{display:flex;min-height:calc(100vh - 140px);}
.content{flex:1;min-width:0;padding:12px 16px;max-width:1200px;}
#search{width:100%;padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius-sm);font-family:inherit;font-size:12px;background:var(--surface);color:var(--text);outline:none;box-sizing:border-box;}
#search:focus{border-color:var(--primary);}
.sort-btns{display:flex;gap:2px;margin:6px 0;}
.sort-btn{padding:4px 10px;border:1px solid var(--border);border-radius:12px;background:var(--surface);color:var(--text-muted);font-family:inherit;font-size:10px;cursor:pointer;font-weight:500;}
.sort-btn:hover{background:var(--primary-light);}
.sort-btn.active{background:var(--primary);color:#fff;border-color:var(--primary);}
.breadcrumb{font-size:12px;color:var(--text-muted);margin-bottom:8px;padding:4px 0;border-bottom:1px solid var(--border-light);display:flex;align-items:center;gap:3px;flex-wrap:wrap;}
.breadcrumb a{color:var(--primary);cursor:pointer;text-decoration:none;font-weight:500;}
.breadcrumb a:hover{text-decoration:underline;}
.breadcrumb .sep{color:var(--text-muted);font-size:9px;}
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;margin-bottom:16px;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:14px;cursor:pointer;transition:all 0.2s;}
.card:hover{box-shadow:0 4px 12px rgba(0,0,0,0.05);border-color:var(--primary);transform:translateY(-2px);}
.card-title{font-family:'Playfair Display',serif;font-size:14px;font-weight:600;color:var(--text);margin-bottom:2px;line-height:1.3;}
.card-count{font-size:11px;color:var(--primary);font-weight:600;margin-top:4px;}
.section-card{border-left:4px solid var(--primary);}
.talk-card{padding:10px;}
.talk-card .thumb-placeholder{width:100%;aspect-ratio:16/9;background:var(--border-light);border-radius:6px;margin-bottom:6px;overflow:hidden;}
.talk-card .thumb-placeholder img{width:100%;height:100%;object-fit:cover;}
.talk-card .card-title{font-size:12px;}
.channel-tag{display:inline-block;font-size:9px;background:var(--border-light);padding:1px 5px;border-radius:3px;color:var(--text-muted);}
.side-panel{width:230px;flex-shrink:0;background:var(--nav-bg);border-left:1px solid var(--border);padding:12px;position:sticky;top:0;height:calc(100vh - 140px);overflow-y:auto;transition:width .3s ease;}
.panel-section{margin-bottom:16px;}
.panel-section h3{font-family:'Playfair Display',serif;font-size:13px;color:var(--text);margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--border-light);}
.panel-list{max-height:280px;overflow-y:auto;}
.panel-item{display:flex;align-items:center;gap:4px;padding:3px 6px;font-size:11px;color:var(--text-soft);cursor:pointer;border-radius:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.panel-item:hover{background:var(--primary-light);color:var(--primary);}
.panel-item .del-btn{margin-left:auto;font-size:13px;cursor:pointer;color:var(--text-muted);}
.panel-item .del-btn:hover{color:#c0392b;}
.panel-empty{font-size:11px;color:var(--text-muted);padding:2px 6px;}
.panel-card{display:flex;align-items:center;gap:6px;padding:5px;border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:3px;cursor:pointer;transition:all 0.15s;}
.panel-card:hover{border-color:var(--primary);background:var(--primary-light);}
.panel-card .thumb{width:36px;height:36px;border-radius:4px;overflow:hidden;flex-shrink:0;background:var(--border-light);}
.panel-card .thumb img{width:100%;height:100%;object-fit:cover;}
.panel-card .info{flex:1;min-width:0;}
.panel-card .title{font-size:10px;font-weight:500;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.panel-card .chan{font-size:8px;color:var(--text-muted);}
.panel-card .del-btn{font-size:12px;cursor:pointer;color:var(--text-muted);flex-shrink:0;line-height:1;}
.panel-card .del-btn:hover{color:#c0392b;}
.panel-toggle{position:sticky;top:6px;width:24px;flex-shrink:0;height:24px;background:var(--nav-bg);border:1px solid var(--border);border-left:none;border-radius:0 4px 4px 0;cursor:pointer;font-size:11px;color:var(--primary);display:flex;align-items:center;justify-content:center;z-index:10;padding:0;transition:all .25s;margin-top:8px;}
.panel-toggle:hover{background:var(--primary-light);}
.side-panel.collapsed{width:0;padding:0;border-left:none;overflow:hidden;}
.talk-view{display:none;flex-direction:column;}
.talk-view.active{display:flex;}
.talk-back{font-size:12px;color:var(--primary);cursor:pointer;margin-bottom:6px;display:inline-block;}
.talk-back:hover{text-decoration:underline;}
.talk-header h1{font-family:'Playfair Display',serif;font-size:20px;font-weight:600;color:var(--text);margin-bottom:4px;}
.talk-actions{display:flex;gap:6px;margin:10px 0;flex-wrap:wrap;}
.video-thumb{cursor:pointer;position:relative;display:block;max-width:600px;border-radius:var(--radius);overflow:hidden;margin-bottom:10px;border:1px solid var(--border);}
.video-thumb img{width:100%;display:block;}
.video-thumb .play-icon{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;}
.video-thumb .play-icon::after{content:'\25B6';color:#fff;font-size:20px;margin-left:2px;}
.star-btn{background:none;border:none;cursor:pointer;font-size:20px;line-height:1;vertical-align:middle;}
.video-pane{display:none;flex-shrink:0;position:relative;background:#000;border-radius:var(--radius) var(--radius) 0 0;overflow:hidden;width:100%;aspect-ratio:16/9;max-height:60vh;}
.video-pane.active{display:block;}
.video-pane iframe{width:100%;height:100%;border:none;}
.video-close{position:absolute;top:6px;right:6px;z-index:10;background:rgba(0,0,0,0.6);color:#fff;border:none;width:26px;height:26px;border-radius:50%;cursor:pointer;font-size:14px;}
.divider{display:none;height:8px;cursor:ns-resize;background:var(--border);flex-shrink:0;}
.divider.active{display:block;}
.divider:hover{background:var(--primary-light);}
.watch-btn,.load-btn,.transcribe-btn{display:inline-flex;align-items:center;gap:4px;padding:7px 14px;border-radius:var(--radius-sm);cursor:pointer;font-family:inherit;font-size:12px;font-weight:500;border:none;transition:background 0.2s;}
.watch-btn{background:var(--primary);color:#fff;}
.watch-btn:hover{background:#B05E18;}
.load-btn{background:var(--primary-soft);color:#fff;}
.transcribe-btn{background:var(--primary);color:#fff;}
.youtube-link{display:inline-flex;align-items:center;gap:4px;padding:7px 14px;border-radius:var(--radius-sm);cursor:pointer;font-family:inherit;font-size:12px;font-weight:500;text-decoration:none;transition:background 0.2s;background:var(--text);color:#fff;}
.youtube-link:hover{opacity:0.8;}
@media (max-width:768px){
.panel-toggle{display:none;}
.layout{flex-direction:column;}
.side-panel{width:100%;border-left:none;border-top:1px solid var(--border);height:auto;max-height:180px;}
.card-grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));}
.hero h1{font-size:22px;}
.hero-photo{width:60px;height:60px;}
.content{padding:8px 10px;}
}

</style>
</head>
<body>
<header class="hero">
<div class="hero-inner">
<img class="hero-photo" src="data:image/jpeg;base64,BASE64_PHOTO" alt="Swami">
<h1>Be Happy</h1>
<p class="subtitle">Discourses on Vedanta by Swami Anubhavananda</p>
<p class="meta" id="meta"></p>
</div>
</header>
<div class="layout">
<main class="content">
<input type="text" id="search" placeholder="Search talks..." autocomplete="off">
<div class="sort-btns">
<button class="sort-btn active" data-mode="playlist" onclick="setCardMode('playlist')">By Playlist</button>
<button class="sort-btn" data-mode="date" onclick="setCardMode('date')">By Date</button>
<button class="sort-btn" data-mode="alpha" onclick="setCardMode('alpha')">A-Z</button>
</div>
<div class="breadcrumb" id="breadcrumb"></div>
<div id="cardGrid"></div>
<div class="talk-view" id="talkView">
<div class="talk-header" id="talkHeader"></div>
<div class="video-pane" id="videoPane">
<button class="video-close" id="videoClose">&times;</button>
<div id="player"></div>
</div>
<div class="divider" id="divider"></div>
</div>
</main>
<button class="panel-toggle" id="panelToggle" onclick="togglePanel()" title="Hide panel">&#9664;</button>
<aside class="side-panel" id="sidePanel">
<div class="panel-section"><h3>⭐ Favourites</h3><div class="panel-list" id="favList"><div class="panel-empty">No favourites yet</div></div></div>
<div class="panel-section"><h3>⌚ Recent</h3><div class="panel-list" id="recentList"><div class="panel-empty">No recent talks</div></div></div>
</aside>
</div>
<script type="application/json" id="catalog-data">
/*CATALOG_DATA*/
</script>
<script>
// ── LOAD CATALOG FROM DATA SCRIPT TAG ──────────────────────
var CATALOG_DATA = {sections:[]};
(function(){
  var el = document.getElementById("catalog-data");
  if(el && el.textContent){
    try {
      CATALOG_DATA = JSON.parse(el.textContent.trim());
    } catch(e) {
      // ignore parse error
    }
  }
})();

// ── STATE ──────────────────────────────────────────────────
var talkMap={},activeTalkId=null,SORT_MODE="playlist",isDraggingVideo=false,videoHeight=380,player=null;

// ── INIT ───────────────────────────────────────────────────
function init(){
try{
if(!CATALOG_DATA||!CATALOG_DATA.sections||!CATALOG_DATA.sections.length){document.getElementById("cardGrid").innerHTML='<div class="no-results">Catalog data is empty.</div>';return;}
buildTalkMap(CATALOG_DATA);
var m=document.getElementById("meta");
if(m)m.textContent=CATALOG_DATA.meta.totalSections+" sections  "+CATALOG_DATA.meta.totalPlaylists+" playlists  "+CATALOG_DATA.meta.totalTalks+" talks";
try{if(localStorage.getItem("bhtalks_panel")==="1"){document.getElementById("sidePanel").classList.add("collapsed");document.getElementById("panelToggle").innerHTML="&#9654;";}}catch(e){}
renderView();updateSidePanel();
if(location.hash){var id=location.hash.replace("#","");if(talkMap[id])goToTalk(id);}
}catch(e){console.error(e);}}



function buildTalkMap(data){talkMap={};
for(var si=0;si<data.sections.length;si++){var sec=data.sections[si];
for(var ii=0;ii<sec.items.length;ii++){var item=sec.items[ii];
if(item.type==="playlist"){for(var ti=0;ti<item.talks.length;ti++){talkMap[item.talks[ti].id]=item.talks[ti];}}
else if(item.type==="group"){for(var pi=0;pi<item.playlists.length;pi++){for(var ti=0;ti<item.playlists[pi].talks.length;ti++){talkMap[item.playlists[pi].talks[ti].id]=item.playlists[pi].talks[ti];}}}}}}

function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");}
var navStack=[{type:"home",name:"Home"}],activeMode="playlist",searchQuery="";
var MONTHS=["","January","February","March","April","May","June","July","August","September","October","November","December"];

function getTitleBase(s){return String(s||"").replace(/\s+\d+\s+of\s+\d+/gi,"").replace(/\s+\d+\s*\/\s*\d+/gi,"").replace(/\s+#\d+/gi,"").replace(/\s+Chapter\s+\d+/gi,"").replace(/\s+Part\s+\d+/gi,"").replace(/\s+Talks?[\s-]*\d*/gi,"").replace(/\s+Session\s+\d+/gi,"").replace(/\s+Vol\.?\s*\d+/gi,"").replace(/\s+\d+\s*[-–]\s*\d+/gi,"").replace(/\s+\d+\s*&\s*\d+/gi,"").replace(/\s*\(\d+\)/gi,"").replace(/\s+\d+$/g,"").replace(/^\d+[\s.-]+/g,"").replace(/\s+[IVXLCDM]+$/i,"").replace(/\s*\|[^\|]*$/g,"").replace(/[\s\-\|]+/g," ").trim().toLowerCase();}
var GROUP_COLORS=["#F5DEB3","#C8E6C8","#C8D8F0","#F0E6C8","#E0C8F0","#B8E8D8","#F0C8C8","#D0D0F0","#D8E8C8","#F0D0E0","#D0E0F0","#F0D8C8"];
function getTalkGroupColors(talks){var g={};for(var i=0;i<talks.length;i++){var k=getTitleBase(talks[i].title);if(!g[k])g[k]=[];g[k].push(talks[i]);}
var r={},ci=0;for(var k in g){for(var j=0;j<g[k].length;j++)r[g[k][j].id]=GROUP_COLORS[ci%GROUP_COLORS.length];ci++;}return r;}

function setCardMode(m){
activeMode=m;navStack=[{type:"home",name:"Home"}];
document.querySelectorAll(".sort-btn").forEach(function(b){b.classList.toggle("active",b.dataset.mode===m);});
renderView();}

function renderView(){
if(!CATALOG_DATA)return;
if(searchQuery){renderSearchResults();return;}
var top=navStack[navStack.length-1];
renderBreadcrumb();document.getElementById("cardGrid").className="card-grid";document.getElementById("talkView").classList.remove("active");
if(top.type==="talk"){showTalk(top.id,true);return;}
if(top.type==="home")renderHome();
else if(top.type==="section")renderSectionCards(top.id);
else if(top.type==="playlist")renderTalkCards(top.id);
else if(top.type==="dateYear")renderDateMonthCards(top.id);
else if(top.type==="dateMonth")renderDateTalkCards(top.year,top.month);}

function renderBreadcrumb(){
var h="";var nc=navStack.length;
for(var i=0;i<nc;i++){var n=navStack[i];if(i>0)h+='<span class="sep"> \u203A </span>';
if(i===nc-1)h+=esc(n.name);else h+='<a onclick="navigateTo('+i+')">'+esc(n.name)+'</a>';}
document.getElementById("breadcrumb").innerHTML=h;}

function navigateTo(idx){navStack.splice(idx+1);renderView();}

function renderHome(){
var cg=document.getElementById("cardGrid");cg.className="card-grid";var h="";
if(activeMode==="playlist"){
for(var si=0;si<CATALOG_DATA.sections.length;si++){var sec=CATALOG_DATA.sections[si];var cnt=0;
for(var ii=0;ii<sec.items.length;ii++){var it=sec.items[ii];if(it.type==="playlist")cnt+=it.talks.length;else if(it.type==="group")for(var pi=0;pi<it.playlists.length;pi++)cnt+=it.playlists[pi].talks.length;}
h+='<div class="card section-card" onclick="navigateToSection(\''+sec.id+'\',\''+esc(sec.name)+'\')" style="background-color:'+GROUP_COLORS[si%GROUP_COLORS.length]+'"><div class="card-title">'+esc(sec.name)+'</div><div class="card-count">'+cnt+' talks</div></div>';}}
else if(activeMode==="alpha"){
var all=getAllTalks();all.sort(function(a,b){var ta=(a.talk.title||"").toLowerCase(),tb=(b.talk.title||"").toLowerCase();return ta<tb?-1:ta>tb?1:0;});
var talks=all.map(function(x){return x.talk;});var colors=getTalkGroupColors(talks);
for(var i=0;i<talks.length;i++){var t=talks[i];var c=colors[t.id]||"";
h+='<div class="card talk-card" onclick="goToTalk(\''+t.id+'\')"'+(c?' style="background-color:'+c+'"':'')+'><div class="card-title">'+esc(t.title||"Untitled")+'</div><span class="channel-tag">@'+(t.channel==="smilingswami"?"smilingswami":"satsa8242")+'</span></div>';}}
else if(activeMode==="date"){
var tree={};var all=getAllTalks();
for(var i=0;i<all.length;i++){var t=all[i].talk;var yr=t.uploadDate?t.uploadDate.substring(0,4):"Unknown";if(!tree[yr])tree[yr]=[];tree[yr].push(all[i]);}
var yrs=Object.keys(tree).sort().reverse();
for(var yi=0;yi<yrs.length;yi++)h+='<div class="card section-card" onclick="navigateToDateYear(\''+yrs[yi]+'\')"><div class="card-title">'+(yrs[yi]==="Unknown"?"Unknown Date":yrs[yi])+'</div><div class="card-count">'+tree[yrs[yi]].length+' talks</div></div>';}
cg.innerHTML=h||'<div class="no-results">No talks found</div>';}

function getAllTalks(){var all=[];for(var si=0;si<CATALOG_DATA.sections.length;si++){var sec=CATALOG_DATA.sections[si];for(var ii=0;ii<sec.items.length;ii++){var it=sec.items[ii];if(it.type==="playlist"){for(var ti=0;ti<it.talks.length;ti++)all.push({talk:it.talks[ti],si:si,ii:ii,ti:ti});}else if(it.type==="group"){for(var pi=0;pi<it.playlists.length;pi++){for(var ti=0;ti<it.playlists[pi].talks.length;ti++)all.push({talk:it.playlists[pi].talks[ti],si:si,ii:ii,pi:pi,ti:ti});}}}}return all;}

function navigateToSection(id,n){navStack.push({type:"section",id:id,name:n});renderView();}

function renderSectionCards(sid){
var cg=document.getElementById("cardGrid");cg.className="card-grid";
for(var si=0;si<CATALOG_DATA.sections.length;si++){var sec=CATALOG_DATA.sections[si];if(sec.id!==sid)continue;var h="";
var items=[];for(var ii=0;ii<sec.items.length;ii++)items.push({id:sec.items[ii].id,title:sec.items[ii].name});
var colors=getTalkGroupColors(items);
for(var ii=0;ii<sec.items.length;ii++){var it=sec.items[ii];var c=colors[it.id]||"";
if(it.type==="playlist")h+='<div class="card" onclick="navigateToPlaylist(\''+it.id+'\',\''+esc(it.name)+'\')"'+(c?' style="background-color:'+c+'"':'')+'><div class="card-title">'+esc(it.name)+'</div><div class="card-count">'+it.talks.length+' talks</div></div>';
else if(it.type==="group")h+='<div class="card" onclick="navigateToPlaylist(\''+it.id+'\',\''+esc(it.name)+'\')"'+(c?' style="background-color:'+c+'"':'')+'><div class="card-title">'+esc(it.name)+'</div><div class="card-count">'+(it.playlists.length)+' playlists</div></div>';}
cg.innerHTML=h||'<div class="no-results">No playlists found</div>';break;}}

function navigateToPlaylist(id,n){navStack.push({type:"playlist",id:id,name:n});renderView();}

function findItem(id){for(var si=0;si<CATALOG_DATA.sections.length;si++){var sec=CATALOG_DATA.sections[si];for(var ii=0;ii<sec.items.length;ii++){var it=sec.items[ii];if(it.type==="playlist"&&it.id===id)return it;if(it.type==="group")for(var pi=0;pi<it.playlists.length;pi++)if(it.playlists[pi].id===id)return it.playlists[pi];}}return null;}

function renderTalkCards(pid){
var cg=document.getElementById("cardGrid");cg.className="card-grid talk-grid";var it=findItem(pid);
if(!it||!it.talks){cg.innerHTML='<div class="no-results">No talks found</div>';return;}var h="",colors=getTalkGroupColors(it.talks);
for(var ti=0;ti<it.talks.length;ti++){var t=it.talks[ti];var c=colors[t.id]||"";
h+='<div class="card talk-card" onclick="goToTalk(\''+t.id+'\')"'+(c?' style="background-color:'+c+'"':'')+'><div class="thumb-placeholder"><img src="https://img.youtube.com/vi/'+t.videoId+'/mqdefault.jpg" alt="" onerror="this.style.display=\'none\'" loading="lazy"></div><div class="card-title">'+esc(t.title||"Untitled")+'</div><span class="channel-tag">@'+(t.channel==="smilingswami"?"smilingswami":"satsa8242")+'</span></div>';}
cg.innerHTML=h;}

function navigateToDateYear(y){navStack.push({type:"dateYear",id:y,name:y});renderView();}
function renderDateMonthCards(y){
var cg=document.getElementById("cardGrid");cg.className="card-grid";var h="";var tree={};
var all=getAllTalks();
for(var i=0;i<all.length;i++){var t=all[i].talk;if((t.uploadDate?t.uploadDate.substring(0,4):"Unknown")!==y)continue;var m=t.uploadDate?parseInt(t.uploadDate.substring(4,6),10):0;if(!tree[m])tree[m]=[];tree[m].push(all[i]);}
var ms=Object.keys(tree).sort(function(a,b){return a-b;});
for(var mi=0;mi<ms.length;mi++){var mn=MONTHS[ms[mi]]||"Unknown";h+='<div class="card section-card" onclick="navigateToDateMonth(\''+y+'\',\''+ms[mi]+'\',\''+esc(mn)+'\')"><div class="card-title">'+esc(mn)+'</div><div class="card-count">'+tree[ms[mi]].length+' talks</div></div>';}
cg.innerHTML=h||'<div class="no-results">No talks found</div>';}
function navigateToDateMonth(y,m,n){navStack.push({type:"dateMonth",id:y+"-"+m,name:n,year:y,month:m});renderView();}
function renderDateTalkCards(y,m){
var cg=document.getElementById("cardGrid");cg.className="card-grid talk-grid";var all=getAllTalks();var talks=[];
for(var i=0;i<all.length;i++){var t=all[i].talk;var yr=t.uploadDate?t.uploadDate.substring(0,4):"Unknown";var mo=t.uploadDate?parseInt(t.uploadDate.substring(4,6),10):0;if(yr===y&&mo===parseInt(m,10))talks.push(t);}
var h="",colors=getTalkGroupColors(talks);
for(var i=0;i<talks.length;i++){var t=talks[i];var c=colors[t.id]||"";
h+='<div class="card talk-card" onclick="goToTalk(\''+t.id+'\')"'+(c?' style="background-color:'+c+'"':'')+'><div class="thumb-placeholder"><img src="https://img.youtube.com/vi/'+t.videoId+'/mqdefault.jpg" alt="" onerror="this.style.display=\'none\'" loading="lazy"></div><div class="card-title">'+esc(t.title||"Untitled")+'</div><span class="channel-tag">@'+(t.channel==="smilingswami"?"smilingswami":"satsa8242")+'</span></div>';}
cg.innerHTML=h||'<div class="no-results">No talks found</div>';}

function renderSearchResults(){
var cg=document.getElementById("cardGrid");cg.className="card-grid talk-grid";
var bc=document.getElementById("breadcrumb");
var all=getAllTalks();var results=[];
for(var i=0;i<all.length;i++){var t=all[i].talk;if(t.title&&t.title.toLowerCase().indexOf(searchQuery)>=0)results.push(t);}
var h="",colors=getTalkGroupColors(results);
for(var i=0;i<results.length;i++){var t=results[i];var c=colors[t.id]||"";
h+='<div class="card talk-card" onclick="goToTalk(\''+t.id+'\')"'+(c?' style="background-color:'+c+'"':'')+'><div class="thumb-placeholder"><img src="https://img.youtube.com/vi/'+t.videoId+'/mqdefault.jpg" alt="" onerror="this.style.display=\'none\'" loading="lazy"></div><div class="card-title">'+esc(t.title||"Untitled")+'</div><span class="channel-tag">@'+(t.channel==="smilingswami"?"smilingswami":"satsa8242")+'</span></div>';}
bc.innerHTML='Search results for "'+esc(searchQuery)+'" — '+results.length+' talks';
cg.innerHTML=h||'<div class="no-results">No talks match "'+esc(searchQuery)+'"</div>';}

function goToTalk(id){
var t=talkMap[id];if(!t)return;
navStack.push({type:"talk",id:id,name:t.title});
renderBreadcrumb();document.getElementById("cardGrid").innerHTML="";
document.getElementById("talkView").classList.add("active");
addRecent(t.id,t.title);updateSidePanel();
showTalk(id,true);}

function showTalk(id,fromNav){
var t=talkMap[id];if(!t)return;
closeVideo();
var th=document.getElementById("talkHeader");
var star=isFavourite(id)?'<button class="star-btn" onclick="toggleFav(\''+id+'\')">\u2605</button>':'<button class="star-btn" onclick="toggleFav(\''+id+'\')">\u2606</button>';
var badge='<span style="font-size:11px;background:var(--border-light);padding:2px 8px;border-radius:4px;">@'+(t.channel==="smilingswami"?"smilingswami":"satsa8242")+'</span>';
var thumb='<div class="video-thumb" onclick="toggleVideo(\''+t.videoId+'\')"><img src="https://img.youtube.com/vi/'+t.videoId+'/mqdefault.jpg" onerror="this.style.display=\'none\'"><span class="play-icon"></span></div>';
var ytLink='<button class="watch-btn" onclick="toggleVideo(\''+t.videoId+'\')">\u25B6 Watch</button>';
var ytLink2='<a class="youtube-link" href="https://www.youtube.com/watch?v='+t.videoId+'" target="_blank" rel="noopener">\u25B6 YouTube</a>';
th.innerHTML='<a class="talk-back" onclick="goBackFromTalk()">\u2190 Back to talks</a><h1>'+esc(t.title)+' '+star+'</h1>'+badge+thumb+'<div class="talk-actions">'+ytLink+ytLink2+'</div>';
location.hash=id;}

function goBackFromTalk(){navStack.pop();document.getElementById("talkView").classList.remove("active");renderView();}

function toggleVideo(videoId){
var vp=document.getElementById("videoPane");var dv=document.getElementById("divider");
if(!videoId){alert("No video URL available.");return;}
if(vp.classList.contains("active")){closeVideo();return;}
vp.classList.add("active");dv.classList.add("active");vp.style.height=videoHeight+"px";
if(!player){
var tag=document.createElement("script");tag.src="https://www.youtube.com/iframe_api";
document.getElementsByTagName("script")[0].parentNode.insertBefore(tag,document.getElementsByTagName("script")[0]);
window._pendingVideoId=videoId;
}else{player.loadVideoById(videoId);}
document.querySelectorAll(".watch-btn").forEach(function(b){b.textContent="Close";b.classList.add("watching");});}

function closeVideo(){var vp=document.getElementById("videoPane");var dv=document.getElementById("divider");vp.classList.remove("active");dv.classList.remove("active");if(player)player.stopVideo();document.querySelectorAll(".watch-btn").forEach(function(b){b.textContent="\u25B6 Watch";b.classList.remove("watching");});}
function onYouTubeIframeAPIReady(){var id=window._pendingVideoId||"";if(!id)return;player=new YT.Player("player",{height:"100%",width:"100%",videoId:id,playerVars:{autoplay:1,rel:0}});}
document.getElementById("videoClose").addEventListener("click",closeVideo);

function togglePanel(){
var p=document.getElementById("sidePanel");
var t=document.getElementById("panelToggle");
var c=p.classList.toggle("collapsed");
t.innerHTML=c?"&#9654;":"&#9664;";
t.title=c?"Show panel":"Hide panel";
try{localStorage.setItem("bhtalks_panel",c?"1":"0");}catch(e){}}

function loadFavs(){try{return JSON.parse(localStorage.getItem("bhtalks_favs")||"[]");}catch(e){return [];}}
function saveFavs(f){localStorage.setItem("bhtalks_favs",JSON.stringify(f));}
function isFavourite(id){return loadFavs().indexOf(id)>=0;}
function toggleFav(id){var f=loadFavs();var i=f.indexOf(id);if(i>=0)f.splice(i,1);else f.unshift(id);saveFavs(f);updateSidePanel();showTalk(id,true);}
function loadRecent(){try{return JSON.parse(localStorage.getItem("bhtalks_recent")||"[]");}catch(e){return [];}}
function saveRecent(r){localStorage.setItem("bhtalks_recent",JSON.stringify(r));}
function addRecent(id,title){var r=loadRecent();var i=r.findIndex(function(x){return x.id===id;});if(i>=0)r.splice(i,1);r.unshift({id:id,title:title,ts:Date.now()});if(r.length>100)r.pop();saveRecent(r);}
function updateSidePanel(){renderFavs();renderRecent();}
function renderFavs(){var f=loadFavs();var el=document.getElementById("favList");if(!f.length){el.innerHTML='<div class="panel-empty">No favourites yet</div>';return;}
var h="";for(var i=0;i<f.length;i++){var t=talkMap[f[i]];if(!t)continue;
h+='<div class="panel-card" onclick="goToTalk(\''+t.id+'\')"><div class="thumb"><img src="https://img.youtube.com/vi/'+t.videoId+'/mqdefault.jpg" loading="lazy" onerror="this.innerHTML=\'\'"></div><div class="info"><div class="title">'+esc((t.title||"").substring(0,28))+'</div><span class="chan">@'+(t.channel==="smilingswami"?"smilingswami":"satsa8242")+'</span></div><span class="del-btn" onclick="event.stopPropagation();toggleFav(\''+t.id+'\')">\u2715</span></div>';}
el.innerHTML=h||"<div class='panel-empty'>None</div>";}
function renderRecent(){var r=loadRecent();var el=document.getElementById("recentList");if(!r.length){el.innerHTML='<div class="panel-empty">No recent talks</div>';return;}
var h="";for(var i=0;i<r.length;i++){var t=talkMap[r[i].id];if(!t)continue;
h+='<div class="panel-card" onclick="goToTalk(\''+t.id+'\')"><div class="thumb"><img src="https://img.youtube.com/vi/'+t.videoId+'/mqdefault.jpg" loading="lazy" onerror="this.innerHTML=\'\'"></div><div class="info"><div class="title">'+esc((t.title||"").substring(0,28))+'</div><span class="chan">@'+(t.channel==="smilingswami"?"smilingswami":"satsa8242")+'</span></div></div>';}
el.innerHTML=h||"<div class='panel-empty'>None</div>";}

document.getElementById("search").addEventListener("input",function(){clearTimeout(window._st);window._st=setTimeout(function(){searchQuery=this.value.trim().toLowerCase();renderView();}.bind(this),200);});

window.addEventListener("hashchange",function(){var id=location.hash.replace("#","");if(id&&talkMap[id])goToTalk(id);});

// Resizable video divider
document.getElementById("divider").addEventListener("mousedown",function(e){isDraggingVideo=true;document.body.style.cursor="ns-resize";document.body.style.userSelect="none";});
document.addEventListener("mousemove",function(e){if(!isDraggingVideo)return;var tv=document.getElementById("talkView");var rect=tv.getBoundingClientRect();var y=e.clientY-rect.top;videoHeight=Math.max(100,Math.min(rect.height-150,y-20));document.getElementById("videoPane").style.height=videoHeight+"px";});
document.addEventListener("mouseup",function(){isDraggingVideo=false;document.body.style.cursor="";document.body.style.userSelect="";});

init();
</script>
</body>
</html>"""


# ================================================================
#  Main
# ================================================================

def main():
    print("=== Build Android Catalog ===")

    # Load catalog
    print("  Reading catalog...")
    data, source = load_catalog()
    print(f"  Source: {source}")
    print(f"  Data: {data['meta']['totalSections']} sections, {data['meta']['totalPlaylists']} playlists, {data['meta']['totalTalks']} talks")

    # Strip heavy fields
    print("  Stripping unnecessary fields...")
    data = strip_fields(data)

    # Embed photo
    print("  Embedding photo...")
    b64 = photo_base64()

    # Inject catalog data + photo into HTML template
    print("  Generating BHTalks.html...")
    catalog_json = json.dumps(data, indent=2, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("/*CATALOG_DATA*/", catalog_json).replace("BASE64_PHOTO", b64)

    # Write output
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"  Written: {OUTPUT_FILE} ({size_mb:.1f} MB)")

    # Copy to GitHub folder
    os.makedirs(os.path.dirname(GITHUB_COPY), exist_ok=True)
    shutil.copy2(OUTPUT_FILE, GITHUB_COPY)
    print(f"  Copied: {GITHUB_COPY}")

    # ═══ PWA: Generate icons ═══
    print("  Generating PWA icons...")
    import PIL.Image
    if os.path.exists(PHOTO_PATH):
        img = PIL.Image.open(PHOTO_PATH)
        for dest in ["Be_Happy_Android", "Be_Happy_GitHub"]:
            d = os.path.join(PROJECT_DIR, dest, "icons")
            os.makedirs(d, exist_ok=True)
            for size in [192, 512]:
                resized = img.resize((size, size), PIL.Image.LANCZOS)
                path = os.path.join(d, f"icon-{size}.png")
                resized.save(path)
            print(f"    icons/ for {dest}")
    else:
        print("  WARNING: Swamiji.jpg not found, icons not generated")

    # ═══ PWA: Write manifest.json ═══
    print("  Writing manifest.json...")
    manifest = {
        "name": "Be Happy — Swami Anubhavananda Talks",
        "short_name": "Be Happy",
        "start_url": ".",
        "display": "standalone",
        "background_color": "#FCF9F5",
        "theme_color": "#C76B1E",
        "icons": [
            {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    }
    manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
    for dest in ["Be_Happy_Android", "Be_Happy_GitHub"]:
        p = os.path.join(PROJECT_DIR, dest, "manifest.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write(manifest_json)
        print(f"    {p}")

    # ═══ PWA: Write service worker ═══
    print("  Writing sw.js...")
    cache_version = "bhtalks-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    sw_configs = [
        ("Be_Happy_Android", "BHTalks.html"),
        ("Be_Happy_GitHub", "index.html"),
    ]
    for dest, html_file in sw_configs:
        sw_code = f'var CACHE = "{cache_version}";\nvar ASSETS = ["{html_file}","manifest.json","icons/icon-192.png","icons/icon-512.png"];\nself.addEventListener("install",function(e){{e.waitUntil(caches.open(CACHE).then(function(c){{return c.addAll(ASSETS);}}));}});\nself.addEventListener("fetch",function(e){{e.respondWith(caches.match(e.request).then(function(r){{return r||fetch(e.request);}}));}});'
        p = os.path.join(PROJECT_DIR, dest, "sw.js")
        with open(p, "w", encoding="utf-8") as f:
            f.write(sw_code)
        print(f"    {p}")

    print("Done.")


if __name__ == "__main__":
    main()
