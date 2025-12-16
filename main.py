# main.py
import os
import uuid
import time
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import FastAPI, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app import settings

HTML_CONTENT = """ full dashboard HTML """
HTML_CONTENT_EMBED = """ embed-friendly HTML """

ROOT = Path(__file__).parent
UPLOAD_DIR = ROOT / "uploads"
RESULT_DIR = ROOT / "results"
METAFILE = ROOT / "results_meta.json"

for d in (UPLOAD_DIR, RESULT_DIR):
    d.mkdir(exist_ok=True)

app = FastAPI(title="Digital Toolbox Backend")

# allow WordPress to access FastAPI (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://acoustics.ids-research.de"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# load/create meta index
if not METAFILE.exists():
    METAFILE.write_text(json.dumps({}))

def add_meta_entry(file_id, filename, status="processing"):
    meta = json.loads(METAFILE.read_text())
    meta[file_id] = {
        "file_id": file_id,
        "filename": filename,
        "status": status,
        "processed_at": None,
        "plots": []
    }
    METAFILE.write_text(json.dumps(meta))

def update_meta(file_id, **kwargs):
    meta = json.loads(METAFILE.read_text())
    if file_id not in meta:
        return
    meta[file_id].update(kwargs)
    METAFILE.write_text(json.dumps(meta))

def cleanup_old_files(max_age_days=7):
    """Delete uploads/results older than max_age_days. Called on each upload to keep disk small."""
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    for folder in (UPLOAD_DIR, RESULT_DIR):
        for p in folder.iterdir():
            try:
                mtime = datetime.utcfromtimestamp(p.stat().st_mtime)
                if mtime < cutoff:
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
            except Exception:
                pass
    # Also purge meta entries whose plots are gone
    meta = json.loads(METAFILE.read_text())
    keep = {}
    for k, v in meta.items():
        any_plot_exists = any((ROOT / p).exists() for p in v.get("plots", []))
        if any_plot_exists:
            keep[k] = v
    METAFILE.write_text(json.dumps(keep))

# Serve root HTML
@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTML_CONTENT

@app.get("/embed", response_class=HTMLResponse)
def dashboard_embed():
    return HTML_CONTENT_EMBED

@app.get("/embed", response_class=HTMLResponse)
def dashboard_embed():
    response = HTMLResponse(HTML_CONTENT_EMBED)
    response.headers["X-Frame-Options"] = "ALLOWALL"
    return response
    
# Paired connectors toggling
@app.get("/toggle_paired")
def toggle_paired(enabled: bool):
    settings.paired_connectors_enabled = enabled
    return {"paired_connectors": enabled}

@app.get("/debug_toggle")
def debug_toggle():
    return {"paired_connectors": settings.paired_connectors_enabled}

# Upload endpoint used by the JS uploader form
@app.post("/upload_html")
async def upload_html(file: UploadFile):
    cleanup_old_files(max_age_days=7)  # tune as needed

    file_id = str(uuid.uuid4())
    saved_name = f"{file_id}_{file.filename}"
    file_path = UPLOAD_DIR / saved_name

    with open(file_path, "wb") as f:
        f.write(await file.read())

    add_meta_entry(file_id, file.filename, status="processing")

    # launch processing script asynchronously (background)
    # Pass file_path and file_id so results are consistent
    subprocess.Popen(["python", str(ROOT / "app" / "process_script.py"), str(file_path), file_id])
    return JSONResponse({"status": "processing", "file_id": file_id})

# Polling endpoint returns status + plot list
@app.get("/status/{file_id}")
def status(file_id: str):
    meta = json.loads(METAFILE.read_text())
    if file_id not in meta:
        return JSONResponse({"status": "not_found"}, status_code=404)
    return JSONResponse(meta[file_id])

# Serve a specific plot (PNG) or other result files
@app.get("/result/{file_id}/{filename}")
def get_result(file_id: str, filename: str):
    path = RESULT_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="image/png")

# Simple history page (JSON)
@app.get("/history")
def history():
    meta = json.loads(METAFILE.read_text())
    # return sorted by processed_at
    items = sorted(meta.values(), key=lambda x: x.get("processed_at") or "", reverse=True)
    return JSONResponse(items)

# Optional: lightweight static content (if you had assets)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------
# Inline HTML content (modern UI + drag/drop + spinner + preview)
# ---------------------------
# HTML_CONTENT = """
# <!doctype html>
# <html>
# <head>
#   <meta charset="utf-8"/>
#   <title>Digital Toolbox Upload</title>
#   <meta name="viewport" content="width=device-width,initial-scale=1"/>
#   <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/basiclightbox@5.0.4/dist/basicLightbox.min.css">
#   <script src="https://cdn.jsdelivr.net/npm/basiclightbox@5.0.4/dist/basicLightbox.min.js"></script>
#   <style>
#     body{font-family:Inter,Arial; background:#f7fafc; padding:24px;}
#     .card{max-width:960px;margin:20px auto;background:white;border-radius:10px;padding:20px;box-shadow:0 6px 20px rgba(0,0,0,0.08);}
#     h1{margin:0 0 12px;font-weight:700}
#     .upload-area{border:2px dashed #cbd5e0;border-radius:8px;padding:30px;text-align:center;color:#4a5568;background:#fff;}
#     .upload-area.dragover{background:#edf2f7;border-color:#63b3ed;}
#     input[type=file]{display:none;}
#     .btn{display:inline-block;padding:10px 18px;background:#2563eb;color:white;border-radius:8px;text-decoration:none;border:none;cursor:pointer;}
#     .meta{margin-top:12px;color:#4a5568;font-size:14px}
#     .spinner{width:48px;height:48px;border:6px solid #e2e8f0;border-top-color:#2563eb;border-radius:50%;animation:spin 1s linear infinite;margin:20px auto;}
#     @keyframes spin{to{transform:rotate(360deg)}}
#     .plots{display:flex;flex-wrap:wrap;gap:12px;margin-top:16px}
#     .plot{width:calc(50% - 6px);min-width:220px;background:#fff;border:1px solid #edf2f7;padding:8px;border-radius:8px;text-align:center}
#     .preview{font-size:13px;color:#475569;margin-top:10px;white-space:pre; font-family:monospace;}
#     .history{margin-top:18px}
#     .history-item{border-top:1px solid #edf2f7;padding:10px 0}
#     .small{font-size:13px;color:#718096}
#   </style>
# </head>
# <body>
#   <div class="card">
#     <h1>Digital Toolbox — Upload & View</h1>
#     <div id="uploader" class="upload-area">
#       <p>Drag & drop an Excel file (.xlsx) here or</p>
#       <button id="pickBtn" class="btn">Choose file</button>
#       <input id="fileInput" type="file" accept=".xlsx" />
#       <div class="meta" id="meta"></div>
#     </div>

#     <div id="statusBox" style="display:none;margin-top:18px;">
#       <div id="spinner" style="display:none;" class="spinner"></div>
#       <div id="msg" class="small"></div>
#       <div id="preview" class="preview"></div>
#       <div class="plots" id="plots"></div>
#     </div>

#     <h3 style="margin-top:26px">Recent results</h3>
#     <div id="history" class="history small"></div>
#   </div>

# <script>
# const uploadArea = document.getElementById('uploader');
# const fileInput = document.getElementById('fileInput');
# const pickBtn = document.getElementById('pickBtn');
# const meta = document.getElementById('meta');
# const statusBox = document.getElementById('statusBox');
# const spinner = document.getElementById('spinner');
# const msg = document.getElementById('msg');
# const preview = document.getElementById('preview');
# const plots = document.getElementById('plots');
# const historyDiv = document.getElementById('history');

# pickBtn.addEventListener('click', ()=> fileInput.click());

# ['dragenter','dragover'].forEach(evt=>{
#   uploadArea.addEventListener(evt, e=>{
#     e.preventDefault(); e.stopPropagation();
#     uploadArea.classList.add('dragover');
#   });
# });
# ['dragleave','drop'].forEach(evt=>{
#   uploadArea.addEventListener(evt, e=>{
#     e.preventDefault(); e.stopPropagation();
#     uploadArea.classList.remove('dragover');
#   });
# });

# uploadArea.addEventListener('drop', async e=>{
#   const file = e.dataTransfer.files[0];
#   if(file) uploadFile(file);
# });

# fileInput.addEventListener('change', e=>{
#   const file = e.target.files[0];
#   if(file) uploadFile(file);
# });

# async function uploadFile(file){
#   meta.innerText = `Selected: ${file.name} (${Math.round(file.size/1024)} KB)`;
#   statusBox.style.display = 'block';
#   spinner.style.display = 'block';
#   msg.textContent = 'Uploading and starting processing...';
#   plots.innerHTML = '';
#   preview.innerHTML = '';

#   const fd = new FormData();
#   fd.append('file', file);

#   const res = await fetch('/upload_html', { method: 'POST', body: fd });
#   if(!res.ok){ msg.textContent = 'Upload failed'; spinner.style.display='none'; return; }
#   const j = await res.json();
#   const id = j.file_id;

#   const maxTries = 60; 
#   let tries = 0;
#   const poll = setInterval(async ()=>{
#     tries += 1;
#     const sres = await fetch(`/status/${id}`);
#     if(sres.status===404){ msg.textContent='Status not found'; clearInterval(poll); spinner.style.display='none'; return; }
#     const info = await sres.json();
#     msg.textContent = `Status: ${info.status}`;

#     // Preview first few rows of Excel (if available)
#     if(info.preview_html){
#       preview.innerHTML = info.preview_html;
#     }

#     if(info.status === 'done' || info.status === 'error'){
#       clearInterval(poll);
#       spinner.style.display = 'none';
#       if(info.status === 'done' && info.plots && info.plots.length){
#         plots.innerHTML = '';
#         for(const p of info.plots){
#           const img = document.createElement('img');
#           img.src = `/result/${id}/${p}`;
#           img.style.maxWidth = '100%';
#           img.style.height = 'auto';
#           img.style.cursor = 'pointer';
#           img.addEventListener('click', ()=>{
#             basicLightbox.create(`<img src="${img.src}" style="width:100%;height:auto;">`).show();
#           });

#           const wrap = document.createElement('div');
#           wrap.className = 'plot';
#           const caption = document.createElement('div');
#           caption.className = 'small';
#           caption.innerText = p;
#           wrap.appendChild(img);
#           wrap.appendChild(caption);
#           plots.appendChild(wrap);
#         }
#       } else if(info.status==='error'){
#         msg.textContent = 'Processing error (check server logs).';
#       } else {
#         msg.textContent = 'No plots found.';
#       }
#       loadHistory();
#     }
#     if(tries > maxTries){
#       clearInterval(poll);
#       spinner.style.display='none';
#       msg.textContent = 'Processing taking too long — try again later.';
#     }
#   }, 2000);
# }

# async function loadHistory(){
#   const res = await fetch('/history');
#   if(!res.ok) return;
#   const arr = await res.json();
#   historyDiv.innerHTML = '';
#   for(const item of arr.slice(0,8)){
#     const el = document.createElement('div');
#     el.className = 'history-item';
#     el.innerHTML = `<div><strong>${item.filename}</strong> — <span class="small">${item.processed_at || 'processing'}</span></div>`;
#     historyDiv.appendChild(el);
#   }
# }

# loadHistory();
# </script>
# </body>
# </html>
# """

HTML_CONTENT = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Digital Toolbox — Multi Upload</title>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/basiclightbox@5.0.4/dist/basicLightbox.min.css">
  <script src="https://cdn.jsdelivr.net/npm/basiclightbox@5.0.4/dist/basicLightbox.min.js"></script>
  <style>
    :root{--card-bg:#fff;--muted:#6b7280;--accent:#2563eb}
    body{font-family:Inter, Arial, sans-serif;background:#f7fafc;padding:20px;margin:0}
    .container{max-width:1100px;margin:18px auto}
    .card{background:var(--card-bg);border-radius:10px;padding:18px;box-shadow:0 6px 20px rgba(2,6,23,0.06);margin-bottom:18px}
    h1{margin:0 0 8px;font-weight:700}
    .upload-area{border:2px dashed #e6eef8;border-radius:10px;padding:26px;text-align:center;color:var(--muted);background:#fff}
    .upload-area.dragover{background:#eef7ff;border-color:var(--accent)}
    input[type=file]{display:none}
    .btn{background:var(--accent);color:#fff;border:none;padding:10px 16px;border-radius:8px;cursor:pointer}
    .meta{margin-top:10px;color:var(--muted)}
    .spinner{width:40px;height:40px;border:6px solid #eef2ff;border-top-color:var(--accent);border-radius:50%;animation:spin 1s linear infinite;margin:12px auto}
    @keyframes spin{to{transform:rotate(360deg)}}
    .files-list{margin-top:14px;display:flex;flex-direction:column;gap:12px}
    .file-card{border:1px solid #eef2f7;border-radius:8px;padding:10px;background:#ffffff}
    .file-header{display:flex;justify-content:space-between;align-items:center;gap:12px}
    .file-title{font-weight:600}
    .status-badge{font-size:13px;color:#fff;padding:6px 10px;border-radius:999px}
    .status-processing{background:#f59e0b}
    .status-done{background:#10b981}
    .status-error{background:#ef4444}
    .file-body{margin-top:10px;display:none}
    .preview{background:#fbfdff;border:1px solid #eef6ff;padding:8px;border-radius:6px;overflow:auto;max-height:220px}
    .plots{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px}
    .plot-thumb{width:180px;border-radius:8px;overflow:hidden;border:1px solid #eef2f7;background:#fff;padding:6px;text-align:center}
    .plot-thumb img{width:100%;height:auto;display:block;border-radius:6px;cursor:pointer}
    .small{font-size:13px;color:var(--muted)}
    .history{margin-top:12px}
    .history-item{border-top:1px solid #f1f5f9;padding:10px 0}
    .collapse-btn{background:transparent;border:none;color:var(--accent);cursor:pointer;font-weight:600}
    .switch {
      position: relative;
      display: inline-block;
      width: 50px;
      height: 24px;
    }
    
    .switch input { 
      display: none;
    }
    
    .slider {
      position: absolute;
      cursor: pointer;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: #ccc;
      transition: .3s;
      border-radius: 24px;
    }
    
    .slider:before {
      position: absolute;
      content: "";
      height: 18px;
      width: 18px;
      left: 3px;
      bottom: 3px;
      background-color: white;
      transition: .3s;
      border-radius: 50%;
    }
    
    input:checked + .slider {
      background-color: #4CAF50;
    }
    
    input:checked + .slider:before {
      transform: translateX(26px);
    }

    /* === Click-to-Zoom Overlay === */
    #zoom-overlay {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(0,0,0,0.8);
      justify-content: center;
      align-items: center;
      z-index: 10000;
    }
    
    #zoom-image {
      max-width: 90%;
      max-height: 90%;
      border-radius: 10px;
    }
    
  </style>
</head>
<body>
  <div id="zoom-overlay">
    <img id="zoom-image">
  </div>

  <div class="container">
    <div class="card">
      <h1>Digital Toolbox — Multi-file Upload </h1>
      <div class="upload-area" id="uploader">
        <p>Drag & drop one or multiple Excel files (.xlsx) here, or</p>
        <button id="pickBtn" class="btn">Choose files</button>
        <input id="fileInput" type="file" accept=".xlsx" multiple />
        <div class="meta" id="meta">Supported: .xlsx</div>
        <label class="switch">
         <input type="checkbox" id="toggle-paired" checked>
         <span class="slider round"></span>
        </label>
        <span id="toggle-text">Paired Connectors: OFF</span>

      </div>

      <div id="statusArea" class="files-list" style="margin-top:14px"></div>

      <div class="card small">
        <strong>Recent history</strong>
        <div id="history" class="history small"></div>
      </div>
    </div>
  </div>

<script>
const pickBtn = document.getElementById('pickBtn');
const fileInput = document.getElementById('fileInput');
const uploader = document.getElementById('uploader');
const statusArea = document.getElementById('statusArea');
const historyDiv = document.getElementById('history');
const meta = document.getElementById('meta');

pickBtn.addEventListener('click', ()=>fileInput.click());

['dragenter','dragover'].forEach(evt=>{
  uploader.addEventListener(evt, e=>{ e.preventDefault(); e.stopPropagation(); uploader.classList.add('dragover'); });
});
['dragleave','drop'].forEach(evt=>{
  uploader.addEventListener(evt, e=>{ e.preventDefault(); e.stopPropagation(); uploader.classList.remove('dragover'); });
});

uploader.addEventListener('drop', async e=>{
  e.preventDefault();
  fileInput.value = "";   // reset the value to upload the same file again
  const files = Array.from(e.dataTransfer.files).filter(f=>f.name.endsWith('.xlsx'));
  if(files.length) startUploads(files);
});

fileInput.addEventListener('change', e=>{
  const files = Array.from(e.target.files).filter(f=>f.name.endsWith('.xlsx'));
  if(files.length) startUploads(files);
});

async function startUploads(files){
  // reset input to accept same file 
  fileInput.value = "";
  meta.textContent = `Uploading ${files.length} file(s)...`;
  const fileEntries = [];
  for(const file of files){
    // create UI card
    const card = document.createElement('div'); card.className='file-card';
    const id = `tmp-${Math.random().toString(36).slice(2,9)}`;
    card.innerHTML = `
      <div class="file-header">
        <div>
          <div class="file-title">${file.name}</div>
          <div class="small">size: ${Math.round(file.size/1024)} KB</div>
        </div>
        <div>
          <span id="badge-${id}" class="status-badge status-processing">Queued</span>
          <button id="toggle-${id}" class="collapse-btn">Open</button>
        </div>
      </div>
      <div id="body-${id}" class="file-body">
        <div id="preview-${id}" class="preview small">Waiting for upload...</div>
        <div id="plots-${id}" class="plots"></div>
      </div>
    `;
    statusArea.prepend(card);

    // upload file
    const fd = new FormData(); fd.append('file', file);
    try{
      const res = await fetch('/upload_html', { method:'POST', body: fd });
      if(!res.ok){ document.getElementById(`badge-${id}`).className='status-badge status-error'; document.getElementById(`badge-${id}`).innerText='Upload failed'; continue;}
      const j = await res.json();
      const file_id = j.file_id;
      document.getElementById(`badge-${id}`).innerText = 'Processing';
      document.getElementById(`badge-${id}`).className='status-badge status-processing';
      fileEntries.push({tmpId:id, file_id, name:file.name});
      attachToggle(id);
    }catch(err){
      document.getElementById(`badge-${id}`).className='status-badge status-error';
      document.getElementById(`badge-${id}`).innerText='Error';
    }
  }

  meta.textContent = 'Polling for processing status...';
  if(fileEntries.length) pollMultiple(fileEntries);
  loadHistory();
}

function attachToggle(id){
  const btn = document.getElementById(`toggle-${id}`);
  const body = document.getElementById(`body-${id}`);
  let opened=false;
  btn.addEventListener('click', ()=>{
    opened = !opened;
    body.style.display = opened ? 'block' : 'none';
    btn.innerText = opened ? 'Close' : 'Open';
  });
}

// Polling multiple files concurrently
function pollMultiple(entries){
  const interval = setInterval(async ()=>{
    for(const entry of entries){
      try{
        const sres = await fetch(`/status/${entry.file_id}`);
        if(!sres.ok) continue;
        const info = await sres.json();
        const badge = document.getElementById(`badge-${entry.tmpId}`);
        const previewBox = document.getElementById(`preview-${entry.tmpId}`);
        const plotsBox = document.getElementById(`plots-${entry.tmpId}`);

        badge.innerText = info.status === 'done' ? 'Done' : (info.status || 'processing');
        badge.className = info.status === 'done' ? 'status-badge status-done' : (info.status==='error' ? 'status-badge status-error' : 'status-badge status-processing');

        if(info.preview_html && previewBox){
          previewBox.innerHTML = info.preview_html;
        }

        // If done — render plots (avoid duplicates)
        if(info.status === 'done' && info.plots && info.plots.length){
          plotsBox.innerHTML = ''; // clear then add
          for(const p of info.plots){
            const wrap = document.createElement('div'); wrap.className='plot-thumb';
            
            // const a = document.createElement('a'); a.href = `/result/${entry.file_id}/${p}`; a.target='_blank';
            // const img = document.createElement('img'); img.src = `/result/${entry.file_id}/${p}`; img.alt=p;
            // img.addEventListener('click', ()=> { basicLightbox.create(`<img src="/result/${entry.file_id}/${p}" style="width:100%;height:auto;">`).show(); });
            // a.appendChild(img);
            // wrap.appendChild(a);

            const img = document.createElement('img');
            img.className = "zoomable";
            img.src = `/result/${entry.file_id}/${p}`;
            img.alt = p;

            wrap.appendChild(img);
            
            const cap = document.createElement('div'); cap.className='small'; cap.innerText = p;
            wrap.appendChild(cap);
            plotsBox.appendChild(wrap);
          }
          // mark processed
          badge.innerText = 'Done';
          badge.className = 'status-badge status-done';
        }
      }catch(e){
        console.log('poll error', e);
      }
    }
    // stop polling when all are done or errored
    const states = entries.map(en=>{
      const b = document.getElementById(`badge-${en.tmpId}`);
      if(!b) return null;
      return b.innerText.toLowerCase();
    });
    const unfinished = states.filter(s=>s && s.match(/processing|queued/));
    if(unfinished.length === 0) clearInterval(interval);
    // refresh history occasionally
    loadHistory();
  }, 2000);
}

// Load history (all previous uploads)
async function loadHistory(){
  try{
    const res = await fetch('/history');
    if(!res.ok) return;
    const arr = await res.json();
    historyDiv.innerHTML = '';
    for(const item of arr){
      const el = document.createElement('div'); el.className='history-item';
      const title = document.createElement('div'); title.innerHTML = `<strong>${item.filename}</strong> — <span class="small">${item.processed_at || 'processing'}</span>`;
      el.appendChild(title);
      if(item.plots && item.plots.length){
        const row = document.createElement('div'); row.style.display='flex'; row.style.flexWrap='wrap'; row.style.gap='8px'; row.style.marginTop='8px';
        for(const p of item.plots){
          // const a = document.createElement('a'); a.href = `/result/${p.split('_')[0]}/${p}`; a.target='_blank';
          // const img = document.createElement('img'); img.src = `/result/${p.split('_')[0]}/${p}`; img.style.maxWidth='140px'; img.style.borderRadius='6px';
          // img.style.border='1px solid #eef2f7';
          // a.appendChild(img);
          // row.appendChild(a);

          const img = document.createElement('img');
          img.className = "zoomable";
          img.src = `/result/${p.split('_')[0]}/${p}`;
          img.style.maxWidth = "140px";
          img.style.borderRadius = "6px";
          img.style.border = "1px solid #eef2f7";

          row.appendChild(img);
        }
        el.appendChild(row);
      }
      historyDiv.appendChild(el);
    }
  }catch(e){ console.log('history load error', e); }
}

// auto-load history on page open
loadHistory();
</script>

<script>
// Set initial state (OFF by default)
const toggle = document.getElementById("toggle-paired");
toggle.checked = false;  // start OFF
document.getElementById("toggle-text").innerText = "Paired Connectors: OFF";

// Add event listener after initial state
toggle.addEventListener("change", function() {
    const isOn = this.checked;
    document.getElementById("toggle-text").innerText =
        isOn ? "Paired Connectors: ON" : "Paired Connectors: OFF";

    // Notify backend
    fetch("/toggle_paired?enabled=" + isOn);
});
</script>


<script>
// === CLICK TO ZOOM ===
document.addEventListener("click", function(e) {
  if (e.target.classList.contains("zoomable")) {
      const overlay = document.getElementById("zoom-overlay");
      const zoomImg = document.getElementById("zoom-image");

      zoomImg.src = e.target.src;
      overlay.style.display = "flex";
  }
});

document.getElementById("zoom-overlay").addEventListener("click", () => {
    document.getElementById("zoom-overlay").style.display = "none";
});
</script>

</body>
</html>
"""

# ---------------------------
# EMBEDDED dashboard (iframe-safe)
# ---------------------------
HTML_CONTENT_EMBED = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <style>
    body {
      margin: 0;
      font-family: Inter, Arial, sans-serif;
      background: #f7fafc;
    }
    .container {
      max-width: 100%;
      padding: 12px;
    }
    h1 { display: none; }
    .upload-area {
      border-radius: 12px;
    }
    .history {
      display: none;
    }
  </style>
</head>
<body>
""" + HTML_CONTENT.split("<body>")[1]

