import os
import shutil
import logging
import subprocess
import shlex
from pathlib import Path

logger = logging.getLogger(__name__)

RIGGING_MODEL_DIR = Path(__file__).parent / "rigging_model"
CONDA_ENV = "riganything"


def _conda_base() -> str:
    """Return the conda installation prefix (e.g. ~/miniconda3)."""
    try:
        r = subprocess.run(["conda", "info", "--base"], capture_output=True, text=True, timeout=10)
        base = r.stdout.strip()
        if base:
            return base
    except Exception as e:
        logger.warning("Could not detect conda base: %s", e)
    return os.path.expanduser("~/miniconda3")


def _subprocess_env() -> dict:
    """
    Return an env dict where 'python' resolves to the riganything conda env,
    not the uv .venv that the Flask process runs under.

    The global project uses .venv (via uv run).  Each model folder has its own
    conda env.  When Flask spawns a subprocess, it inherits VIRTUAL_ENV and a
    PATH that starts with .venv/bin — so bare 'python' calls inside
    inference.sh hit the wrong interpreter (no bpy, no torch, etc.).

    Fix: strip all virtualenv / uv vars, then prepend the conda env's bin/
    to PATH so every 'python' call in inference.sh resolves correctly.
    """
    conda_env_bin = str(Path(_conda_base()) / "envs" / CONDA_ENV / "bin")

    env = os.environ.copy()

    # Strip virtualenv vars that make the shell prefer .venv over conda.
    for key in ["VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT", "PYTHONPATH"]:
        env.pop(key, None)
    for key in [k for k in env if k.startswith("UV_")]:
        env.pop(key)

    # Prepend conda env bin — 'python' now resolves to riganything's interpreter.
    env["PATH"] = f"{conda_env_bin}:{env.get('PATH', '/usr/bin:/bin')}"

    logger.info("Subprocess python: %s/python", conda_env_bin)
    return env


def rig_3d_model(glb_path: str, mesh_simplify: int = 1, simplify_count: int = 8192) -> str:
    """
    Run the rigging inference pipeline on a 3D GLB model.

    Calls scripts/inference.sh inside rigging_model via subprocess.Popen,
    using the riganything conda env's Python (not the project's .venv).
    Every log line from the shell script streams to the Python logger in
    real time; inference.log is forwarded after the process exits.

    The shell script runs three steps:
        Step 1 — mesh simplification     (bpy)
        Step 2 — AR-Rig diffusion        (torch + bpy)
        Step 3 — skeleton / rig export   (bpy)

    Args:
        glb_path:        Absolute (or resolvable) path to the input .glb file.
        mesh_simplify:   1 to simplify mesh before inference, 0 to skip.
        simplify_count:  Target face count when simplification is enabled.

    Returns:
        Absolute path to the rigged output file (*_simplified_rig.glb).

    Raises:
        FileNotFoundError: If the input GLB does not exist.
        RuntimeError:      If inference fails or the expected output is missing.
    """
    glb_path = os.path.abspath(glb_path)
    logger.info("rig_3d_model | input=%s  simplify=%s  count=%s", glb_path, mesh_simplify, simplify_count)

    if not os.path.exists(glb_path):
        logger.error("Input file not found: %s", glb_path)
        raise FileNotFoundError(f"Input GLB file not found: {glb_path}")

    asset_stem = Path(glb_path).stem  # e.g. "neo_crispytyph"

    # Clear the output dir so inference.log is fresh and a stale GLB from a
    # previous run cannot mask a new failure.
    output_dir = RIGGING_MODEL_DIR / "outputs" / asset_stem
    if output_dir.exists():
        shutil.rmtree(output_dir)
        logger.info("Cleared stale output dir: %s", output_dir)

    # Run inference.sh directly — no conda activation needed because we inject
    # the conda env's bin/ into PATH via _subprocess_env().
    bash_cmd = (
        f"bash scripts/inference.sh "
        f"{shlex.quote(glb_path)} {mesh_simplify} {simplify_count}"
    )
    logger.info("Script cmd: %s", bash_cmd)
    logger.info("cwd       : %s", RIGGING_MODEL_DIR)
    logger.info("Inference starting — streaming subprocess output below...")

    proc = subprocess.Popen(
        ["bash", "-c", bash_cmd],
        cwd=str(RIGGING_MODEL_DIR),
        env=_subprocess_env(),          # riganything env, not .venv
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,       # merge so we see everything in one stream
        text=True,
        bufsize=1,                      # line-buffered → real-time output
    )

    for line in proc.stdout:
        logger.info("[subprocess] %s", line.rstrip())

    proc.wait()

    # inference.sh redirects Python stdout/stderr to inference.log (>> append).
    # Read it now, forward every line, and scan for known silent failures.
    inference_log = RIGGING_MODEL_DIR / "outputs" / asset_stem / "inference.log"
    log_text = ""
    if inference_log.exists():
        log_text = inference_log.read_text(errors="replace")
        logger.info("--- inference.log start ---")
        for line in log_text.splitlines():
            logger.info("[inference.log] %s", line)
        logger.info("--- inference.log end ---")
    else:
        logger.warning("inference.log not found — all three steps may have failed before writing it")

    if proc.returncode != 0:
        logger.error("Subprocess exited with code %s", proc.returncode)
        raise RuntimeError(f"Rigging inference failed (exit {proc.returncode}). Check logs above.")

    # inference.sh has no errexit — it exits 0 even when Python steps crash.
    # Detect the most common silent failures explicitly.
    if "ModuleNotFoundError: No module named 'bpy'" in log_text:
        conda_bin = str(Path(_conda_base()) / "envs" / CONDA_ENV / "bin" / "python")
        logger.error("bpy not found — wrong Python was used. Expected: %s", conda_bin)
        raise RuntimeError(
            f"bpy not found in the subprocess Python. "
            f"Expected interpreter: {conda_bin}. "
            f"Check that the '{CONDA_ENV}' conda env has bpy installed "
            f"(pip install bpy) and that CONDA_ENV is set correctly."
        )

    if "FileNotFoundError" in log_text and "ckpt/" in log_text:
        ckpt_dir = RIGGING_MODEL_DIR / "ckpt"
        found = [p.name for p in ckpt_dir.glob("*")] if ckpt_dir.exists() else []
        logger.error("Checkpoint missing. Files in ckpt/: %s", found or "none")
        raise RuntimeError(
            f"Model checkpoint not found at ckpt/riganything_ckpt.pt. "
            f"Run: hf download Isabellaliu/RigAnything --local-dir "
            f"{RIGGING_MODEL_DIR / 'ckpt'}"
        )

    output_glb = RIGGING_MODEL_DIR / "outputs" / asset_stem / f"{asset_stem}_simplified_rig.glb"

    if not output_glb.exists():
        logger.error("Expected output not found: %s", output_glb)
        raise RuntimeError(f"Subprocess exited 0 but output file is missing: {output_glb}")

    logger.info("Rigging complete | output=%s", output_glb)
    return str(output_glb)
