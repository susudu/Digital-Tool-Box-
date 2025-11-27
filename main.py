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

ROOT = Path(__file__).parent
UPLOAD_DIR = ROOT / "uploads"
RESULT_DIR = ROOT / "results"
METAFILE = ROOT / "results_meta.json"

for d in (UPLOAD_DIR, RESULT_DIR):
    d.mkdir(exist_ok=True)

app = FastAPI(title="Digital Toolbox Backend")

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
def index():
    return HTML_CONTENT  # defined below

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
HTML_CONTENT = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Digital Toolbox Upload</title>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <style>
    body{font-family:Inter,Arial; background:#f7fafc; padding:24px;}
    .card{max-width:960px;margin:20px auto;background:white;border-radius:10px;padding:20px;box-shadow:0 6px 20px rgba(0,0,0,0.08);}
    h1{margin:0 0 12px;font-weight:700}
    .upload-area{border:2px dashed #cbd5e0;border-radius:8px;padding:30px;text-align:center;color:#4a5568;background:#fff;}
    .upload-area.dragover{background:#edf2f7;border-color:#63b3ed;}
    input[type=file]{display:none;}
    .btn{display:inline-block;padding:10px 18px;background:#2563eb;color:white;border-radius:8px;text-decoration:none;border:none;cursor:pointer;}
    .meta{margin-top:12px;color:#4a5568;font-size:14px}
    .spinner{width:48px;height:48px;border:6px solid #e2e8f0;border-top-color:#2563eb;border-radius:50%;animation:spin 1s linear infinite;margin:20px auto;}
    @keyframes spin{to{transform:rotate(360deg)}}
    .plots{display:flex;flex-wrap:wrap;gap:12px;margin-top:16px}
    .plot{width:calc(50% - 6px);min-width:220px;background:#fff;border:1px solid #edf2f7;padding:8px;border-radius:8px;text-align:center}
    .preview{font-size:13px;color:#475569;margin-top:10px}
    .history{margin-top:18px}
    .history-item{border-top:1px solid #edf2f7;padding:10px 0}
    .small{font-size:13px;color:#718096}
  </style>
</head>
<body>
  <div class="card">
    <h1>Digital Toolbox — Upload & View</h1>
    <div id="uploader" class="upload-area">
      <p>Drag & drop an Excel file (.xlsx) here or</p>
      <button id="pickBtn" class="btn">Choose file</button>
      <input id="fileInput" type="file" accept=".xlsx" />
      <div class="meta" id="meta"></div>
    </div>

    <div id="statusBox" style="display:none;margin-top:18px;">
      <div id="spinner" style="display:none;" class="spinner"></div>
      <div id="msg" class="small"></div>
      <div id="preview" class="preview"></div>
      <div class="plots" id="plots"></div>
    </div>

    <h3 style="margin-top:26px">Recent results</h3>
    <div id="history" class="history small"></div>
  </div>

<script>
const uploadArea = document.getElementById('uploader');
const fileInput = document.getElementById('fileInput');
const pickBtn = document.getElementById('pickBtn');
const meta = document.getElementById('meta');
const statusBox = document.getElementById('statusBox');
const spinner = document.getElementById('spinner');
const msg = document.getElementById('msg');
const preview = document.getElementById('preview');
const plots = document.getElementById('plots');
const historyDiv = document.getElementById('history');

pickBtn.addEventListener('click', ()=> fileInput.click());

['dragenter','dragover'].forEach(evt=>{
  uploadArea.addEventListener(evt, (e)=>{ e.preventDefault(); e.stopPropagation(); uploadArea.classList.add('dragover'); });
});
['dragleave','drop'].forEach(evt=>{
  uploadArea.addEventListener(evt, (e)=>{ e.preventDefault(); e.stopPropagation(); uploadArea.classList.remove('dragover'); });
});

uploadArea.addEventListener('drop', async (e)=>{
  const file = e.dataTransfer.files[0];
  if(file) uploadFile(file);
});

fileInput.addEventListener('change', (e)=> {
  const file = e.target.files[0];
  if(file) uploadFile(file);
});

async function uploadFile(file){
  meta.innerText = `Selected: ${file.name} (${Math.round(file.size/1024)} KB)`;
  statusBox.style.display = 'block';
  spinner.style.display = 'block';
  msg.textContent = 'Uploading and starting processing...';
  plots.innerHTML = '';
  preview.innerHTML = '';

  const fd = new FormData();
  fd.append('file', file);

  const res = await fetch('/upload_html', { method: 'POST', body: fd });
  if(!res.ok){ msg.textContent = 'Upload failed'; spinner.style.display='none'; return; }
  const j = await res.json();
  const id = j.file_id;

  // poll status endpoint until status = done or timeout
  const maxTries = 60; // 60 * 2s = 2 minutes
  let tries = 0;
  const poll = setInterval(async ()=>{
    tries += 1;
    const sres = await fetch(`/status/${id}`);
    if(sres.status===404){ msg.textContent='Status not found'; clearInterval(poll); spinner.style.display='none'; return; }
    const info = await sres.json();
    msg.textContent = `Status: ${info.status}`;
    if(info.preview_html){
      preview.innerHTML = info.preview_html; // small HTML preview (safe)
    }
    if(info.status === 'done' || info.status === 'error'){
      clearInterval(poll);
      spinner.style.display = 'none';
      if(info.status === 'done' && info.plots && info.plots.length){
        plots.innerHTML = '';
        for(const p of info.plots){
          const img = document.createElement('img');
          img.src = `/result/${id}/${p}`;
          img.style.maxWidth = '100%';
          img.style.height = 'auto';
          const wrap = document.createElement('div');
          wrap.className = 'plot';
          const caption = document.createElement('div');
          caption.className = 'small';
          caption.innerText = p;
          wrap.appendChild(img);
          wrap.appendChild(caption);
          plots.appendChild(wrap);
        }
      } else if(info.status==='error'){
        msg.textContent = 'Processing error (check server logs).';
      } else {
        msg.textContent = 'No plots found.';
      }
      // Refresh history
      loadHistory();
    } else {
      // still processing
      // optional: add rotating dots
    }
    if(tries > maxTries){
      clearInterval(poll);
      spinner.style.display='none';
      msg.textContent = 'Processing taking too long — try again later.';
    }
  }, 2000);
}

// simple history loader
async function loadHistory(){
  const res = await fetch('/history');
  if(!res.ok) return;
  const arr = await res.json();
  historyDiv.innerHTML = '';
  for(const item of arr.slice(0,8)){
    const el = document.createElement('div');
    el.className = 'history-item';
    el.innerHTML = `<div><strong>${item.filename}</strong> — <span class="small">${item.processed_at || 'processing'}</span></div>`;
    historyDiv.appendChild(el);
  }
}

loadHistory();
</script>
</body>
</html>
"""
