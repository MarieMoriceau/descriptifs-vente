import os
import uuid
import threading
import time
import json
import base64
import io
import requests
import pdfplumber
from pypdf import PdfReader
from PIL import Image
from flask import Flask, request, jsonify, render_template_string
import anthropic

# ─── CONFIG ───────────────────────────────────────────────────────────────────
IMGBB_API_KEY       = "be39115664b38075a21de95d2ef95ba1"
GOOGLE_MAPS_API_KEY = "AIzaSyAGE65fo1453M-5CGe162Klk8NjS9K0hJA"
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
GAMMA_API_KEY       = "sk-gamma-KLU47Xtpm0WkqYoQ4DEh0qZSKOOjcZr4hBb0G79m9Rg"
GAMMA_THEME_ID      = "fo87qe3vn58hou1"
GAMMA_TEMPLATE_ID   = "g_uqlvk5ehulo750w"

app = Flask(__name__)
jobs = {}  # job_id -> dict

# ─── HTML TEMPLATE ────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDF → Gamma — Vente | Equation SIE</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 2rem; }
.card { background: white; border-radius: 16px; padding: 2.5rem 2rem; width: 100%; max-width: 560px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); text-align: center; }
.dots { display: flex; justify-content: center; gap: 8px; margin-bottom: 1.5rem; }
.dot { width: 12px; height: 12px; border-radius: 50%; }
.dot-red { background: #e53935; }
.dot-dark { background: #37474f; }
.dot-blue { background: #90a4ae; }
h1 { font-size: 1.6rem; font-weight: 700; color: #1a1a2e; margin-bottom: 0.4rem; }
.subtitle { color: #6b7280; font-size: 0.95rem; margin-bottom: 2rem; }
.info-box { background: #f8f9fa; border-left: 4px solid #e53935; border-radius: 6px; padding: 0.85rem 1rem; margin-bottom: 2rem; text-align: left; }
.info-box p { color: #374151; font-size: 0.9rem; }
.upload-area { border: 2px dashed #d1d5db; border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; cursor: pointer; transition: all 0.2s; }
.upload-area:hover { border-color: #e53935; background: #fff5f5; }
.upload-area input { display: none; }
.upload-label { cursor: pointer; color: #6b7280; font-size: 0.9rem; }
.upload-label span { color: #e53935; font-weight: 600; }
.file-list { text-align: left; margin-bottom: 1rem; font-size: 0.85rem; color: #374151; }
.file-item { padding: 0.3rem 0; border-bottom: 1px solid #f3f4f6; }
.btn { width: 100%; padding: 0.9rem; background: #e53935; color: white; border: none; border-radius: 10px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: background 0.2s; }
.btn:hover { background: #c62828; }
.btn:disabled { background: #9ca3af; cursor: not-allowed; }
.jobs-section { margin-top: 2rem; text-align: left; }
.jobs-title { font-size: 0.85rem; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.75rem; }
.job-item { border: 1px solid #e5e7eb; border-radius: 8px; padding: 0.85rem; margin-bottom: 0.75rem; font-size: 0.85rem; }
.job-item.running { border-color: #93c5fd; background: #f0f4ff; }
.job-item.done { border-color: #86efac; background: #f0fdf4; }
.job-item.error { border-color: #fca5a5; background: #fff5f5; }
.job-filename { font-weight: 600; color: #1a1a2e; margin-bottom: 0.4rem; }
.job-status { color: #6b7280; margin-bottom: 0.4rem; }
.job-logs { font-size: 0.75rem; color: #9ca3af; font-family: monospace; max-height: 80px; overflow-y: auto; background: rgba(0,0,0,0.03); padding: 0.4rem; border-radius: 4px; margin-top: 0.4rem; white-space: pre-wrap; }
.gamma-link { display: inline-block; margin-top: 0.5rem; padding: 0.4rem 0.9rem; background: #16a34a; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 0.82rem; }
.gamma-link:hover { background: #15803d; }
</style>
</head>
<body>
<div class="card">
  <div class="dots">
    <div class="dot dot-red"></div>
    <div class="dot dot-dark"></div>
    <div class="dot dot-blue"></div>
  </div>
  <h1>PDF → Gamma</h1>
  <p class="subtitle">Equation SIE — Produits à la vente</p>
  <div class="info-box">
    <p>📄 Convertir un ou plusieurs descriptifs de vente</p>
  </div>

  <div class="upload-area" id="uploadArea" onclick="document.getElementById('fileInput').click()">
    <input type="file" id="fileInput" accept=".pdf" multiple onchange="handleFiles(this)">
    <label class="upload-label">
      <span>Choisir les PDF</span> ou glisser-déposer ici
    </label>
  </div>
  <div class="file-list" id="fileList"></div>

  <button class="btn" id="submitBtn" onclick="submitFiles()" disabled>
    Lancer la conversion
  </button>

  <div class="jobs-section" id="jobsSection" style="display:none">
    <div class="jobs-title">Conversions en cours</div>
    <div id="jobsList"></div>
  </div>
</div>

<script>
let selectedFiles = [];
let pollingIntervals = {};

function handleFiles(input) {
  selectedFiles = Array.from(input.files);
  const list = document.getElementById('fileList');
  if (selectedFiles.length === 0) {
    list.innerHTML = '';
    document.getElementById('submitBtn').disabled = true;
    return;
  }
  list.innerHTML = selectedFiles.map(f =>
    `<div class="file-item">📄 ${f.name} (${(f.size/1024).toFixed(0)} Ko)</div>`
  ).join('');
  document.getElementById('submitBtn').disabled = false;
}

async function submitFiles() {
  if (selectedFiles.length === 0) return;
  const btn = document.getElementById('submitBtn');
  btn.disabled = true;
  btn.textContent = 'Envoi en cours…';
  document.getElementById('jobsSection').style.display = 'block';

  for (const file of selectedFiles) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const resp = await fetch('/upload', { method: 'POST', body: formData });
      const data = await resp.json();
      if (data.job_id) {
        createJobCard(data.job_id, file.name);
        startPolling(data.job_id);
      }
    } catch(e) {
      console.error('Upload error', e);
    }
  }

  btn.textContent = 'Lancer la conversion';
  btn.disabled = false;
  selectedFiles = [];
  document.getElementById('fileList').innerHTML = '';
  document.getElementById('fileInput').value = '';
}

function createJobCard(jobId, filename) {
  const div = document.createElement('div');
  div.className = 'job-item running';
  div.id = 'job-' + jobId;
  div.innerHTML = `
    <div class="job-filename">📄 ${filename}</div>
    <div class="job-status" id="status-${jobId}">⏳ Démarrage…</div>
    <div class="job-logs" id="logs-${jobId}"></div>
  `;
  document.getElementById('jobsList').prepend(div);
}

function startPolling(jobId) {
  pollingIntervals[jobId] = setInterval(async () => {
    try {
      const resp = await fetch('/status/' + jobId);
      const data = await resp.json();
      updateJobCard(jobId, data);
      if (data.status === 'done' || data.status === 'error') {
        clearInterval(pollingIntervals[jobId]);
      }
    } catch(e) {}
  }, 3000);
}

function updateJobCard(jobId, data) {
  const card = document.getElementById('job-' + jobId);
  const statusEl = document.getElementById('status-' + jobId);
  const logsEl = document.getElementById('logs-' + jobId);
  if (!card) return;

  card.className = 'job-item ' + (data.status === 'done' ? 'done' : data.status === 'error' ? 'error' : 'running');

  const icons = { pending: '⏳', running: '🔄', done: '✅', error: '❌' };
  const labels = { pending: 'En attente', running: 'Traitement…', done: 'Terminé !', error: 'Erreur' };
  statusEl.textContent = (icons[data.status] || '⏳') + ' ' + (data.message || labels[data.status] || data.status);

  if (data.logs && data.logs.length > 0) {
    logsEl.textContent = data.logs.join('\\n');
    logsEl.scrollTop = logsEl.scrollHeight;
  }

  if (data.status === 'done' && data.gamma_url && !document.getElementById('link-' + jobId)) {
    const link = document.createElement('a');
    link.className = 'gamma-link';
    link.id = 'link-' + jobId;
    link.href = data.gamma_url;
    link.target = '_blank';
    link.textContent = '🚀 Ouvrir dans Gamma';
    card.appendChild(link);
  }
}

// Drag & drop
const area = document.getElementById('uploadArea');
area.addEventListener('dragover', e => { e.preventDefault(); area.style.borderColor = '#e53935'; });
area.addEventListener('dragleave', () => { area.style.borderColor = '#d1d5db'; });
area.addEventListener('drop', e => {
  e.preventDefault();
  area.style.borderColor = '#d1d5db';
  const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
  if (files.length) {
    const dt = new DataTransfer();
    files.forEach(f => dt.items.add(f));
    document.getElementById('fileInput').files = dt.files;
    handleFiles(document.getElementById('fileInput'));
  }
});
</script>
</body>
</html>"""


# ─── UTILS ────────────────────────────────────────────────────────────────────

def log(job_id, msg):
    jobs[job_id]["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    print(f"[{job_id[:8]}] {msg}")


def extract_text_pdfplumber(pdf_path):
    """Extract text from all pages except page 0 (confrère logo page)."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            if i == 0:
                continue  # Skip page 0 — logo confrère
            t = page.extract_text()
            if t:
                text += t + "\n"
    return text.strip()


def extract_images_pypdf(pdf_path, max_images=12):
    """
    Extract images via pypdf only — NO rasterisation.
    Memory-safe for Render 512Mo free tier.
    Skips page 0 (confrère logo).
    Filters tiny images (< 100px).
    """
    images = []
    reader = PdfReader(pdf_path)

    for page_num, page in enumerate(reader.pages):
        if page_num == 0:
            continue  # Skip page 0
        if len(images) >= max_images:
            break

        resources = page.get("/Resources")
        if not resources:
            continue
        xobjects = resources.get("/XObject")
        if not xobjects:
            continue

        for name, obj in xobjects.items():
            if len(images) >= max_images:
                break
            try:
                xobj = obj.get_object()
                if xobj.get("/Subtype") != "/Image":
                    continue

                width = int(xobj.get("/Width", 0))
                height = int(xobj.get("/Height", 0))
                if width < 100 or height < 100:
                    continue  # Skip tiny images (logos, icônes, etc.)

                data = xobj.get_data()
                color_space = xobj.get("/ColorSpace", "/DeviceRGB")
                if isinstance(color_space, list):
                    color_space = str(color_space[0])
                else:
                    color_space = str(color_space)

                filter_type = xobj.get("/Filter", "")
                if isinstance(filter_type, list):
                    filter_type = str(filter_type[0])
                else:
                    filter_type = str(filter_type)

                if filter_type == "/DCTDecode":
                    # Already JPEG — use directly
                    img_bytes = data
                else:
                    # Convert via Pillow
                    if color_space == "/DeviceCMYK":
                        img = Image.frombytes("CMYK", (width, height), data)
                        img = img.convert("RGB")
                    elif color_space == "/DeviceGray":
                        img = Image.frombytes("L", (width, height), data)
                        img = img.convert("RGB")
                    else:
                        img = Image.frombytes("RGB", (width, height), data)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=82)
                    img_bytes = buf.getvalue()

                images.append(img_bytes)

            except Exception as e:
                print(f"  [img] skip — {e}")
                continue

    return images


def upload_to_imgbb(image_bytes, job_id):
    """Upload image bytes to imgbb, return public URL or None."""
    try:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY, "image": b64},
            timeout=30
        )
        data = resp.json()
        if data.get("success"):
            return data["data"]["url"]
        else:
            log(job_id, f"imgbb error: {data.get('error', {}).get('message', 'unknown')}")
    except Exception as e:
        log(job_id, f"imgbb upload exception: {e}")
    return None


def get_google_maps_imgbb_url(adresse, code_postal, job_id):
    """Fetch Google Maps static image and upload to imgbb."""
    try:
        full_address = f"{adresse}, {code_postal} Paris, France"
        encoded = requests.utils.quote(full_address)
        map_url = (
            f"https://maps.googleapis.com/maps/api/staticmap"
            f"?center={encoded}&zoom=15&size=600x300&scale=2"
            f"&markers=color:red%7C{encoded}"
            f"&key={GOOGLE_MAPS_API_KEY}"
        )
        resp = requests.get(map_url, timeout=20)
        if resp.status_code == 200:
            url = upload_to_imgbb(resp.content, job_id)
            if url:
                log(job_id, f"✅ Carte Google Maps uploadée")
                return url
    except Exception as e:
        log(job_id, f"Google Maps error: {e}")
    return None


def extract_data_with_claude(text, job_id):
    """
    Use Claude Haiku to extract structured JSON from PDF text.
    Returns dict or None.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = """Tu es un expert en immobilier commercial.
Tu extrais des données structurées depuis des descriptifs de vente immobilière.
Tu réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans backticks, sans commentaires.
Si une information est absente, utilise null."""

    user_prompt = f"""Extrais les informations suivantes du texte ci-dessous et retourne un JSON avec exactement ces clés :

{{
  "adresse": "ex: 55 RUE DE COURCELLES",
  "code_postal": "ex: 75008",
  "surfaces": ["ex: 450 m2"],
  "surfaces_detail": ["ex: 450 m2 (3eme etage)"],
  "prix_vente": "ex: 2 500 000 euros",
  "prix_m2": "ex: 5 555 euros/m2",
  "honoraires": "ex: A la charge de l acquéreur - 4%",
  "disponibilite": "ex: Immediate",
  "transports": ["ex: Metro Monceau ligne 2"],
  "prestations": ["ex: Climatisation", "Fibre optique"],
  "description": "Description courte du bien SANS mentionner le prix",
  "confrere": "ex: CBRE",
  "dpe": "ex: D",
  "regime_fiscal": "ex: Hors TVA"
}}

TEXTE DU DESCRIPTIF :
{text[:6000]}"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt
        )
        raw = message.content[0].text.strip()
        # Clean potential markdown fences
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        return data
    except json.JSONDecodeError as e:
        log(job_id, f"Claude JSON parse error: {e}")
        return None
    except Exception as e:
        log(job_id, f"Claude API error: {e}")
        return None


def build_gamma_prompt(data, photo_urls, map_url):
    """Build the Gamma AI prompt from extracted data."""
    adresse     = data.get("adresse") or "ADRESSE INCONNUE"
    cp          = data.get("code_postal") or ""
    surfaces    = ", ".join(data.get("surfaces") or []) or "Surface NC"
    prix        = data.get("prix_vente") or "Prix NC"
    prix_m2     = data.get("prix_m2") or ""
    honoraires  = data.get("honoraires") or "NC"
    dispo       = data.get("disponibilite") or "NC"
    transports  = "\n".join(f"• {t}" for t in (data.get("transports") or []))
    prestations = "\n".join(f"• {p}" for p in (data.get("prestations") or []))
    description = data.get("description") or ""
    dpe         = data.get("dpe") or "NC"
    fiscal      = data.get("regime_fiscal") or "NC"

    # Paris label
    cp_label = f"{cp} PARIS" if cp else "PARIS"

    # Title for Gamma
    title = f"[RENDER - A RETRAVAILLER] {adresse} — {cp_label} — {surfaces}"

    # Photos block
    photos_block = ""
    if photo_urls:
        photos_block = "PHOTOS DU BIEN :\n" + "\n".join(photo_urls[:10])

    # Map block
    map_block = ""
    if map_url:
        map_block = f"CARTE DE LOCALISATION :\n{map_url}"

    prompt = f"""Crée une présentation de vente immobilière professionnelle avec les informations suivantes.

TITRE DE LA PRÉSENTATION : {title}

ADRESSE : {adresse}
LOCALISATION : {cp_label}
SURFACE : {surfaces}

PRIX DE VENTE : {prix}
PRIX AU M² : {prix_m2}
HONORAIRES : {honoraires}
DISPONIBILITÉ : {dispo}

DESCRIPTION :
{description}

TRANSPORTS :
{transports}

PRESTATIONS & ÉQUIPEMENTS :
{prestations}

{photos_block}

{map_block}

PAGE CONDITIONS (slide dédiée) :
• Prix de vente : {prix}
• Honoraires : {honoraires}
• Régime fiscal : {fiscal}
• DPE : {dpe}

RÈGLES IMPORTANTES :
- Conserver le logo Equation SIE à sa taille originale, ne pas l'agrandir ni le dupliquer
- Ne pas inclure les logos ou mentions des confrères
- Présentation sobre, professionnelle, aux couleurs Equation SIE (rouge #e53935 et sombre #1a1a2e)
- Utiliser les photos fournies pour illustrer les slides
- Afficher la carte de localisation sur la slide dédiée à l'adresse
"""
    return prompt, title


def call_gamma_api(prompt, title, job_id):
    """
    Call Gamma API v1.0 — from-template endpoint (identique au code loc qui fonctionne).
    POST /v1.0/generations/from-template → generationId → poll GET → gammaUrl
    """
    BASE = "https://public-api.gamma.app/v1.0"
    headers = {
        "X-API-KEY": GAMMA_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "gammaId": GAMMA_TEMPLATE_ID,
        "prompt": prompt,
        "themeId": GAMMA_THEME_ID
    }

    log(job_id, "📡 Envoi à l'API Gamma (from-template)…")
    try:
        resp = requests.post(
            f"{BASE}/generations/from-template",
            headers=headers,
            json=payload,
            timeout=60
        )
        log(job_id, f"Gamma POST status: {resp.status_code}")

        if resp.status_code not in (200, 201, 202):
            log(job_id, f"Gamma error: {resp.text[:300]}")
            return None

        generation_id = resp.json().get("generationId")
        if not generation_id:
            log(job_id, f"Pas de generationId: {resp.text[:200]}")
            return None

        log(job_id, f"⏳ Generation démarrée: {generation_id}")

        # Polling toutes les 5s, max 5 minutes (60 tentatives)
        for attempt in range(60):
            time.sleep(5)
            poll = requests.get(
                f"{BASE}/generations/{generation_id}",
                headers={"X-API-KEY": GAMMA_API_KEY},
                timeout=20
            )
            if poll.status_code != 200:
                log(job_id, f"Poll error {poll.status_code}")
                continue

            result = poll.json()
            status = result.get("status", "")
            log(job_id, f"Poll {attempt+1}: {status}")

            if status == "completed":
                gamma_url = result.get("gammaUrl", "")
                if gamma_url:
                    return gamma_url
                log(job_id, f"completed mais pas de gammaUrl: {str(result)[:200]}")
                return None

            if status == "failed":
                log(job_id, f"Generation failed: {str(result)[:200]}")
                return None

        log(job_id, "Timeout après 5 minutes de polling")
        return None

    except requests.Timeout:
        log(job_id, "Gamma API timeout")
        return None
    except Exception as e:
        log(job_id, f"Gamma API exception: {e}")
        return None


# ─── JOB RUNNER ───────────────────────────────────────────────────────────────

def run_job(job_id, pdf_path, filename):
    """Main processing pipeline — runs in a background thread."""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["message"] = "Extraction du texte…"
        log(job_id, f"📄 Démarrage : {filename}")

        # 1. Extract text
        log(job_id, "🔍 Extraction texte (pdfplumber)…")
        text = extract_text_pdfplumber(pdf_path)
        if not text:
            raise ValueError("Aucun texte extrait du PDF")
        log(job_id, f"✅ Texte extrait : {len(text)} caractères")

        # 2. Extract images (pypdf — no rasterisation)
        log(job_id, "🖼️  Extraction images (pypdf)…")
        image_bytes_list = extract_images_pypdf(pdf_path, max_images=12)
        log(job_id, f"✅ {len(image_bytes_list)} image(s) extraite(s)")

        # 3. Upload photos to imgbb
        photo_urls = []
        for i, img_bytes in enumerate(image_bytes_list):
            log(job_id, f"⬆️  Upload photo {i+1}/{len(image_bytes_list)}…")
            url = upload_to_imgbb(img_bytes, job_id)
            if url:
                photo_urls.append(url)
        log(job_id, f"✅ {len(photo_urls)} photo(s) uploadée(s) sur imgbb")

        # 4. Claude Haiku — extract structured data
        jobs[job_id]["message"] = "Analyse par Claude Haiku…"
        log(job_id, "🤖 Claude Haiku — extraction données…")
        data = extract_data_with_claude(text, job_id)
        if not data:
            raise ValueError("Échec extraction données par Claude")
        log(job_id, f"✅ Données extraites : {data.get('adresse', 'adresse NC')} — {data.get('surfaces', ['NC'])}")

        # 5. Google Maps
        log(job_id, "🗺️  Génération carte Google Maps…")
        map_url = get_google_maps_imgbb_url(
            data.get("adresse", ""), data.get("code_postal", "75001"), job_id
        )

        # 6. Build Gamma prompt
        log(job_id, "✍️  Construction du prompt Gamma…")
        prompt, title = build_gamma_prompt(data, photo_urls, map_url)
        log(job_id, f"📝 Titre : {title}")

        # 7. Call Gamma API
        jobs[job_id]["message"] = "Génération Gamma en cours…"
        gamma_url = call_gamma_api(prompt, title, job_id)

        if not gamma_url:
            raise ValueError("Gamma n'a pas retourné d'URL")

        log(job_id, f"🎉 Succès ! URL : {gamma_url}")
        jobs[job_id]["status"]    = "done"
        jobs[job_id]["message"]   = f"Gamma créé : {title}"
        jobs[job_id]["gamma_url"] = gamma_url

    except Exception as e:
        log(job_id, f"❌ ERREUR : {e}")
        jobs[job_id]["status"]  = "error"
        jobs[job_id]["message"] = str(e)

    finally:
        # Cleanup temp file
        try:
            os.remove(pdf_path)
        except Exception:
            pass


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDF only"}), 400

    job_id   = str(uuid.uuid4())
    tmp_path = f"/tmp/{job_id}.pdf"
    f.save(tmp_path)

    jobs[job_id] = {
        "status":    "pending",
        "message":   "En attente…",
        "logs":      [],
        "gamma_url": None,
        "filename":  f.filename
    }

    # Launch background thread
    t = threading.Thread(target=run_job, args=(job_id, tmp_path, f.filename), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status":    job["status"],
        "message":   job["message"],
        "logs":      job["logs"],
        "gamma_url": job["gamma_url"]
    })


@app.route("/health")
def health():
    return jsonify({"ok": True, "jobs": len(jobs)})


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
