import os
import logging
import tempfile
import shutil
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template_string

from services.rigging.rigging_inference import rig_3d_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_HTML_VIEWER = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AR Pipeline — Rigging Test</title>
  <script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 860px; margin: 60px auto; padding: 0 24px; color: #222; }
    h1   { font-size: 1.6rem; margin-bottom: 8px; }
    p    { color: #555; margin-top: 0; }
    .row { display: flex; gap: 12px; align-items: center; margin: 20px 0; }
    input[type=file] { flex: 1; }
    button {
      padding: 10px 22px; background: #2563eb; color: #fff;
      border: none; border-radius: 6px; cursor: pointer; font-size: 1rem;
    }
    button:disabled { background: #93c5fd; cursor: default; }
    #status { min-height: 24px; color: #6b7280; font-size: .9rem; }
    #status.error { color: #dc2626; }
    model-viewer {
      width: 100%; height: 520px;
      background: #f3f4f6; border-radius: 10px;
      margin-top: 16px; display: none;
    }
    #download { display: none; margin-top: 10px; }
    a.btn {
      display: inline-block; padding: 8px 18px;
      background: #16a34a; color: #fff; border-radius: 6px; text-decoration: none;
    }
  </style>
</head>
<body>
  <h1>AR Rigging Pipeline — Test UI</h1>
  <p>Upload a <code>.glb</code> file and hit <strong>Rig Model</strong> to run the rigging inference. The rigged model will be displayed inline when ready.</p>
  <div class="row">
    <input type="file" id="glbFile" accept=".glb">
    <button id="rigBtn" onclick="uploadAndRig()">Rig Model</button>
  </div>
  <div id="status"></div>
  <model-viewer id="viewer" auto-rotate camera-controls alt="Rigged 3D model"></model-viewer>
  <div id="download"><a id="dlLink" class="btn" download="rigged_model.glb">Download Rigged GLB</a></div>

  <script>
    async function uploadAndRig() {
      const fileInput = document.getElementById('glbFile');
      const status    = document.getElementById('status');
      const btn       = document.getElementById('rigBtn');
      const viewer    = document.getElementById('viewer');
      const dlDiv     = document.getElementById('download');
      const dlLink    = document.getElementById('dlLink');

      const file = fileInput.files[0];
      if (!file) { alert('Please select a .glb file first.'); return; }

      btn.disabled = true;
      status.className = '';
      status.textContent = 'Uploading and processing... this may take several minutes.';
      viewer.style.display = 'none';
      dlDiv.style.display  = 'none';

      const form = new FormData();
      form.append('model', file);

      try {
        const resp = await fetch('/rig', { method: 'POST', body: form });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ error: resp.statusText }));
          status.className   = 'error';
          status.textContent = 'Error: ' + err.error;
          return;
        }
        const blob = await resp.blob();
        const url  = URL.createObjectURL(blob);

        viewer.src           = url;
        viewer.style.display = 'block';
        dlLink.href          = url;
        dlDiv.style.display  = 'block';
        status.textContent   = 'Done! Rigged model shown below.';
      } catch (e) {
        status.className   = 'error';
        status.textContent = 'Error: ' + e.message;
      } finally {
        btn.disabled = false;
      }
    }
  </script>
</body>
</html>"""


@app.get("/")
def index():
    """HTML test viewer — upload a GLB and see the rigged result inline."""
    logger.info("GET / — serving test UI")
    return render_template_string(_HTML_VIEWER)


@app.post("/rig")
def rig():
    """
    Accept a .glb file, run the rigging pipeline, and return the rigged .glb.

    Form field:
        model (file): the input .glb mesh

    Query params (optional):
        mesh_simplify  (int, default 1): 1=simplify mesh, 0=skip
        simplify_count (int, default 8192): target face count

    Returns:
        200 application/octet-stream — the rigged GLB binary
        400 JSON — if the request is malformed
        500 JSON — if rigging fails
    """
    logger.info("POST /rig — new rigging request")

    if "model" not in request.files:
        logger.warning("Request missing 'model' file field")
        return jsonify({"error": "No model file provided. Use form field name 'model'."}), 400

    file = request.files["model"]
    if not file.filename.lower().endswith(".glb"):
        logger.warning("Unsupported file type: %s", file.filename)
        return jsonify({"error": "Only .glb files are supported."}), 400

    mesh_simplify  = int(request.args.get("mesh_simplify", 1))
    simplify_count = int(request.args.get("simplify_count", 8192))

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


if __name__ == "__main__":
    logger.info("Starting AR StoryTelling Pipeline — Rigging API")
    app.run(host="0.0.0.0", port=5000, debug=True)
