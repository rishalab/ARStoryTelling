import os
import logging
import tempfile
import shutil
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template_string

from services.rigging.rigging_inference import rig_3d_model, RIGGING_MODEL_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── HTML test viewer ──────────────────────────────────────────────────────────
_HTML_VIEWER = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AR Pipeline — Rigging Test</title>
  <script type="module" src="https://ajax.googleapis.com/ajax/libs/model-viewer/3.5.0/model-viewer.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body {
      font-family: system-ui, sans-serif;
      max-width: 900px; margin: 50px auto; padding: 0 24px; color: #1a1a1a;
    }
    h1   { font-size: 1.7rem; margin-bottom: 6px; }
    p    { color: #555; margin: 0 0 20px; }
    .card {
      background: #f8f9fa; border: 1px solid #dee2e6;
      border-radius: 10px; padding: 20px; margin-bottom: 20px;
    }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    input[type=file] { flex: 1; min-width: 200px; }
    button {
      padding: 10px 26px; background: #2563eb; color: #fff;
      border: none; border-radius: 6px; cursor: pointer; font-size: 1rem;
      white-space: nowrap;
    }
    button:disabled { background: #93c5fd; cursor: default; }
    #status {
      min-height: 24px; margin-top: 14px;
      font-size: .9rem; color: #374151; font-family: monospace;
    }
    #status.error { color: #dc2626; }
    #status.ok    { color: #16a34a; }
    .spinner {
      display: inline-block; width: 14px; height: 14px;
      border: 2px solid #93c5fd; border-top-color: #2563eb;
      border-radius: 50%; animation: spin .7s linear infinite;
      vertical-align: middle; margin-right: 6px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    model-viewer {
      width: 100%; height: 540px;
      background: #e5e7eb; border-radius: 10px; display: none;
    }
    .dl-row { margin-top: 12px; display: none; }
    a.btn-dl {
      display: inline-block; padding: 8px 18px;
      background: #16a34a; color: #fff;
      border-radius: 6px; text-decoration: none; font-size: .9rem;
    }
    .hint { font-size: .82rem; color: #6b7280; margin-top: 8px; }
  </style>
</head>
<body>
  <h1>AR Rigging Pipeline — Test Viewer</h1>
  <p>Upload a <code>.glb</code> mesh, run rigging, and inspect the result directly in this page. Inference takes a few minutes — the log streams to the terminal.</p>

  <div class="card">
    <div class="row">
      <input type="file" id="glbFile" accept=".glb">
      <button id="rigBtn" onclick="uploadAndRig()">Rig Model</button>
    </div>
    <div id="status"></div>
    <p class="hint">Optional params: mesh_simplify (1/0) and simplify_count can be appended as URL query params.</p>
  </div>

  <model-viewer
    id="viewer"
    auto-rotate
    camera-controls
    shadow-intensity="1"
    alt="Rigged 3D model"
    ar
  ></model-viewer>

  <div class="dl-row" id="dlRow">
    <a id="dlLink" class="btn-dl" download="rigged_model.glb">⬇ Download Rigged GLB</a>
    <span class="hint" style="margin-left:12px">Import into Blender to inspect bones and weights.</span>
  </div>

  <script>
    const setStatus = (msg, cls = '') => {
      const el = document.getElementById('status');
      el.className = cls;
      el.innerHTML = msg;
    };

    async function uploadAndRig() {
      const fileInput = document.getElementById('glbFile');
      const btn       = document.getElementById('rigBtn');
      const viewer    = document.getElementById('viewer');
      const dlRow     = document.getElementById('dlRow');
      const dlLink    = document.getElementById('dlLink');

      const file = fileInput.files[0];
      if (!file) { alert('Please select a .glb file first.'); return; }

      btn.disabled = true;
      viewer.style.display = 'none';
      dlRow.style.display  = 'none';

      setStatus('<span class="spinner"></span>Uploading model…');

      const form = new FormData();
      form.append('model', file);

      // pass optional query params from URL if present
      const search = new URLSearchParams(window.location.search);
      const params = new URLSearchParams();
      if (search.has('mesh_simplify'))  params.set('mesh_simplify',  search.get('mesh_simplify'));
      if (search.has('simplify_count')) params.set('simplify_count', search.get('simplify_count'));
      const qs = params.toString() ? '?' + params.toString() : '';

      setStatus('<span class="spinner"></span>Running rigging inference… (this takes several minutes — watch the terminal for live logs)');

      try {
        const resp = await fetch('/rig' + qs, { method: 'POST', body: form });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ error: resp.statusText }));
          setStatus('Error: ' + err.error, 'error');
          return;
        }

        const blob = await resp.blob();
        const url  = URL.createObjectURL(blob);

        viewer.src           = url;
        viewer.style.display = 'block';
        dlLink.href          = url;
        dlRow.style.display  = 'block';

        setStatus('✓ Rigging complete — rotate the model below to inspect it.', 'ok');
      } catch (e) {
        setStatus('Error: ' + e.message, 'error');
      } finally {
        btn.disabled = false;
      }
    }
  </script>
</body>
</html>"""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    """HTML test viewer."""
    logger.info("GET / — serving test UI")
    return render_template_string(_HTML_VIEWER)


@app.post("/rig")
def rig():
    """
    Accept a .glb file, run the rigging pipeline, and return the rigged .glb.

    Form field:
        model (file): the input .glb mesh

    Query params (optional):
        mesh_simplify  (int, default 1): 1 = simplify mesh before inference, 0 = skip
        simplify_count (int, default 8192): target face count for simplification

    Returns:
        200 application/octet-stream — rigged GLB binary
        400 JSON — malformed request
        500 JSON — inference error
    """
    logger.info("POST /rig — new rigging request from %s", request.remote_addr)

    if "model" not in request.files:
        logger.warning("Missing 'model' file field in request")
        return jsonify({"error": "No model file provided. Use form field name 'model'."}), 400

    file = request.files["model"]
    if not file.filename.lower().endswith(".glb"):
        logger.warning("Unsupported file type: %s", file.filename)
        return jsonify({"error": "Only .glb files are supported."}), 400

    try:
        mesh_simplify  = int(request.args.get("mesh_simplify", 1))
        simplify_count = int(request.args.get("simplify_count", 8192))
    except ValueError as e:
        return jsonify({"error": f"Invalid query param: {e}"}), 400

    # Save upload to a temp dir using the original filename so the asset stem is clean.
    tmpdir = tempfile.mkdtemp(prefix="rig_upload_")
    try:
        upload_path = Path(tmpdir) / file.filename
        file.save(str(upload_path))
        logger.info("Saved upload to %s", upload_path)

        output_path = rig_3d_model(
            str(upload_path),
            mesh_simplify=mesh_simplify,
            simplify_count=simplify_count,
        )

        logger.info("Sending rigged model: %s", output_path)
        return send_file(
            output_path,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name="rigged_model.glb",
        )

    except FileNotFoundError as e:
        logger.error("File not found: %s", e)
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        logger.error("Rigging runtime error: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.exception("Unexpected error during rigging")
        return jsonify({"error": f"Unexpected error: {e}"}), 500
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        logger.debug("Cleaned up temp dir: %s", tmpdir)


@app.get("/outputs/<path:filename>")
def serve_output(filename: str):
    """
    Serve a previously rigged GLB directly by its path under rigging_model/outputs/.

    Example: GET /outputs/spyro_the_dragon/spyro_the_dragon_simplified_rig.glb

    Useful for viewing a cached result in the browser without re-uploading.
    """
    full_path = RIGGING_MODEL_DIR / "outputs" / filename
    logger.info("GET /outputs/%s", filename)

    if not full_path.exists() or not full_path.is_file():
        logger.warning("Output file not found: %s", full_path)
        return jsonify({"error": f"File not found: {filename}"}), 404

    # Prevent directory traversal
    try:
        full_path.resolve().relative_to((RIGGING_MODEL_DIR / "outputs").resolve())
    except ValueError:
        logger.error("Directory traversal attempt: %s", filename)
        return jsonify({"error": "Invalid path"}), 400

    return send_file(str(full_path), mimetype="application/octet-stream")


if __name__ == "__main__":
    logger.info("Starting AR StoryTelling Pipeline — Rigging API")
    app.run(host="0.0.0.0", port=5000, debug=True)
