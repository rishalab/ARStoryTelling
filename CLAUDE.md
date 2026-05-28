# AR StoryTelling Pipeline — Claude Rules

## Editing rules

1. **Never touch model directories.** Do not edit any file inside `services/<service>/rigging_model/` or any `*_model/` subdirectory. Only edit the top-level inference file for each service (e.g. `services/rigging/rigging_inference.py`).

2. **Add sufficient logging everywhere.** Every inference function must log at entry (`logger.info`), at key steps (`logger.info` / `logger.debug`), on warnings (`logger.warning`), and on errors (`logger.error` / `logger.exception`). Use `logging.getLogger(__name__)` — do not use `print`.

3. **Subprocess is the interface to model code.** Each `*_inference.py` calls its model's shell script via `subprocess.run(...)` with `cwd` set to the model directory. Never import from model directories directly.

4. **main.py is the API orchestrator only.** It imports inference functions from `services/*/` and wires them into Flask routes. Business logic and subprocess calls belong in the service inference files, not in `main.py`.

5. **Always pass absolute paths to inference functions.** Resolve with `os.path.abspath()` before calling subprocess so the model's relative paths (`outputs/`, `scripts/`, `ckpt/`) resolve correctly from their own `cwd`.

6. **README files per service.** Each service under `services/<name>/` must have a `README.md` explaining: (a) how subprocess is used, (b) input/output contract, (c) the function signature. Do not modify the top-level `README.md`.

7. **Temporary files must be cleaned up.** Any temp directory created during an API request must be removed in a `finally` block using `shutil.rmtree(..., ignore_errors=True)`.

## Project structure

```
AR_StoryTelling_Pipeline/
├── main.py                          ← Flask API — edit here for routes/pipeline wiring
├── CLAUDE.md
├── README.md                        ← do not touch
└── services/
    ├── rigging/
    │   ├── rigging_inference.py     ← edit here (subprocess wrapper)
    │   ├── README.md                ← edit here (service docs)
    │   └── rigging_model/           ← DO NOT TOUCH
    ├── kimodo_motion/
    │   ├── motion_inference.py      ← edit here
    │   └── kimodo_motion_model/     ← DO NOT TOUCH
    └── extraction/
        ├── extraction_inference.py  ← edit here
        └── extraction_model/        ← DO NOT TOUCH
```

## Inference function contract

Every service inference function must follow this pattern:

```python
def <verb>_3d_model(input_path: str, **kwargs) -> str:
    """Docstring with Args / Returns / Raises."""
    input_path = os.path.abspath(input_path)
    logger.info("...")
    # subprocess call with cwd=MODEL_DIR
    # validate output exists
    return str(output_path)  # absolute path
```
