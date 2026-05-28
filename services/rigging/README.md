# Rigging Service

Wraps the `rigging_model` inference pipeline and exposes it as a single Python function that the main API can call.

---

## How it connects to the pipeline

```
main.py  (Flask API)
   │
   │  imports
   ▼
services/rigging/rigging_inference.py   ← only file you should edit
   │
   │  subprocess (bash)
   ▼
services/rigging/rigging_model/scripts/inference.sh
   │
   ├─ python inference_utils/mesh_simplify.py   (Step 1 — mesh simplification)
   ├─ python inference.py                        (Step 2 — AR-Rig diffusion)
   └─ python inference_utils/vis_skel.py         (Step 3 — skeleton export)
```

`rigging_inference.py` never imports from `rigging_model` directly. All communication goes through the shell script via **subprocess**, keeping the model code isolated.

---

## Subprocess mechanism

```python
import subprocess
from pathlib import Path

RIGGING_MODEL_DIR = Path(__file__).parent / "rigging_model"

cmd = [
    "bash",
    "scripts/inference.sh",
    "/absolute/path/to/model.glb",  # input — absolute path is safe
    "1",                             # mesh_simplify: 1=yes, 0=no
    "8192",                          # simplify_count: target face count
]

result = subprocess.run(
    cmd,
    cwd=str(RIGGING_MODEL_DIR),   # script resolves all relative paths from here
    capture_output=True,
    text=True,
)
```

Key points:
- `cwd` is set to `rigging_model/` so the shell script's relative paths (`scripts/`, `outputs/`, `ckpt/`) all resolve correctly.
- The input GLB is passed as an **absolute path** — `inference.sh` uses `basename` internally to build the output directory name, so the directory from which main.py runs does not matter.
- `capture_output=True` captures stdout/stderr without printing to console; both are forwarded to the Python logger.

---

## Output layout

After a successful run the shell script writes:

```
rigging_model/outputs/<asset_name>/
├── <asset_name>_simplified.glb       # simplified input mesh
├── <asset_name>_simplified.npz       # intermediate joints + weights
├── <asset_name>_simplified_rig.glb   # ← returned to the caller
└── inference.log                     # full log from all three steps
```

`rig_3d_model()` returns the absolute path to `*_simplified_rig.glb`.

---

## Function signature

```python
from services.rigging.rigging_inference import rig_3d_model

output_glb_path: str = rig_3d_model(
    glb_path       = "/path/to/model.glb",
    mesh_simplify  = 1,      # optional, default 1
    simplify_count = 8192,   # optional, default 8192
)
```

| Parameter       | Type | Default | Description                          |
|-----------------|------|---------|--------------------------------------|
| `glb_path`      | str  | —       | Path to the input `.glb` file        |
| `mesh_simplify` | int  | `1`     | `1` = simplify mesh, `0` = skip      |
| `simplify_count`| int  | `8192`  | Target face count for simplification |

Raises `FileNotFoundError` if the input doesn't exist, `RuntimeError` if inference fails.

---

## Running locally (standalone test)

```bash
cd services/rigging/rigging_model
bash scripts/inference.sh data_examples/spyro_the_dragon.glb 1 8192
```

Or via Python:

```python
from services.rigging.rigging_inference import rig_3d_model
path = rig_3d_model("services/rigging/rigging_model/data_examples/spyro_the_dragon.glb")
print(path)
```

---

## Rules for editing this service

1. **Only edit `rigging_inference.py`** — do not touch anything inside `rigging_model/`.
2. Add logging (`logger.info / logger.warning / logger.error`) to every meaningful step.
3. Pass inputs as absolute paths to avoid CWD-dependent failures.
4. The function must return the absolute path string of the rigged GLB — downstream services depend on this contract.
