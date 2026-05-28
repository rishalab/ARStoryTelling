# kimodo_motion Service

Wraps the Kimodo text-to-motion model and the bone-retargeting step, exposing them as Python functions the main API wires into the full pipeline.

---

## How it connects to the pipeline

```
main.py  (Flask API)
   │
   │  imports
   ├──► services/kimodo_motion/motion_inference.py   ← generates .npz from text
   │       │
   │       │  subprocess (bash, kimodo conda env)
   │       ▼
   │    motion_model/   (kimodo_gen CLI — writes output.npz here)
   │
   └──► services/kimodo_motion/retarget.py           ← maps .npz onto rigged .glb
            │
            │  direct Python import (pygltflib + numpy, no subprocess needed)
            ▼
         animated .glb  (GLB with embedded GLTF animation track)
```

`motion_inference.py` never imports from `motion_model/` directly — all
communication with the model goes through the `kimodo_gen` CLI via **subprocess**.

`retarget.py` is pure Python (pygltflib + numpy) and is imported directly.

---

## Subprocess mechanism — `generate_motion`

```python
import subprocess, shlex

cmd = f"kimodo_gen {shlex.quote(prompt)} --duration {duration}"

proc = subprocess.Popen(
    ["bash", "-c", cmd],
    cwd=str(MOTION_MODEL_DIR),   # kimodo writes output.npz here
    env=_subprocess_env(),        # kimodo conda env's bin/ prepended to PATH
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)
```

Key points:
- `cwd` is set to `motion_model/` so `kimodo_gen` writes `output.npz` there.
- The Flask process runs under `.venv`; `_subprocess_env()` strips all virtualenv
  vars and prepends the `kimodo` conda env's `bin/` so the correct interpreter
  and CLI are used.
- Subprocess stdout/stderr are streamed line-by-line to the Python logger.

---

## Output layout — `generate_motion`

```
motion_model/
└── output.npz          ← returned to the caller (absolute path)
```

The `.npz` contains:

| Key               | Shape                      | Description                          |
|-------------------|----------------------------|--------------------------------------|
| `local_rot_mats`  | `(n_frames, n_joints, 3, 3)` | Per-joint local rotation matrices   |
| `root_positions`  | `(n_frames, 3)`            | Root joint world positions           |

---

## Bone retargeting — `blend_animation` (retarget.py)

Solves the scale mismatch between RigAnything bone translations (30 000–120 000
units) and mesh vertices (0–1.5 units):

1. Detects scale factor `S = max_bone_translation / max_mesh_coord`.
2. Divides all bone node translations by `S`.
3. Divides the translation column of every inverse bind matrix (IBM) by `S`.
4. Converts `local_rot_mats` rotation matrices → quaternions.
5. Normalises rotations relative to frame 0 (T-pose anchor).
6. Writes a new GLTF `Animation` track with `LINEAR` interpolated quaternion
   samplers and saves the result as a self-contained `.glb`.

---

## Full pipeline sequence

```
input.glb  ──► rig_3d_model()     ──► rigged.glb ──┐
                                                     ├──► blend_animation() ──► animated.glb
text prompt ──► generate_motion() ──► output.npz  ──┘
```

`POST /animate` in `main.py` chains all three steps automatically.

---

## Function signatures

```python
# motion_inference.py
def generate_motion(prompt: str, duration: float = 5.0) -> str:
    """Returns absolute path to motion_model/output.npz."""

# retarget.py
def blend_animation(
    glb_path: str,
    npz_path: str,
    out_path: str,
    fps: int = 30,
    joint_indices: list = None,
    animation_name: str = "NPZ_Animation",
) -> None:
    """Writes animated .glb to out_path."""
```

---

## Input / Output contract

### `generate_motion`

| Parameter  | Type    | Default | Description                          |
|------------|---------|---------|--------------------------------------|
| `prompt`   | `str`   | —       | Natural-language motion description  |
| `duration` | `float` | `5.0`   | Animation duration in seconds        |

Returns: absolute path to `output.npz`.
Raises: `RuntimeError` if `kimodo_gen` fails or no `.npz` is produced.

### `blend_animation`

| Parameter        | Type    | Default           | Description                               |
|------------------|---------|-------------------|-------------------------------------------|
| `glb_path`       | `str`   | —                 | Rigged `.glb` from RigAnything            |
| `npz_path`       | `str`   | —                 | Kimodo-generated `.npz`                   |
| `out_path`       | `str`   | —                 | Destination path for the animated `.glb`  |
| `fps`            | `int`   | `30`              | Frames per second                         |
| `joint_indices`  | `list`  | `None` (0..N-1)   | NPZ joint indices to map onto GLB bones   |
| `animation_name` | `str`   | `"NPZ_Animation"` | Name of the embedded GLTF animation track |

Returns: nothing (file written to `out_path`).
Raises: `SystemExit` / `RuntimeError` if GLB has no skin or NPZ is malformed.

---

## Dependencies

```bash
# kimodo conda env  (for generate_motion)
conda create -n kimodo python=3.10
conda activate kimodo
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install "kimodo[all] @ git+https://github.com/nv-tlabs/kimodo.git"

# project .venv  (for blend_animation / retarget.py)
pip install pygltflib numpy
```

---

## Rules for editing this service

1. **Only edit `motion_inference.py` and `retarget.py`** — do not touch anything
   inside `motion_model/`.
2. Add logging (`logger.info / logger.warning / logger.error`) to every
   meaningful step in `motion_inference.py`.
3. Use `subprocess.Popen` with line-buffered streaming so logs are visible in
   real time.
4. `generate_motion` must return the absolute path string of the `.npz` — the
   retarget step depends on this contract.
