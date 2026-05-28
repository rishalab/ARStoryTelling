import os
import logging
import subprocess
import shlex
from pathlib import Path

logger = logging.getLogger(__name__)

MOTION_MODEL_DIR = Path(__file__).parent / "motion_model"
CONDA_ENV = "kimodo"


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
    Return an env dict where 'python' resolves to the kimodo conda env,
    not the uv .venv that the Flask process runs under.

    Strips all virtualenv / uv vars, then prepends the conda env's bin/
    to PATH so every bare 'python' or 'kimodo_gen' resolves correctly.
    """
    conda_env_bin = str(Path(_conda_base()) / "envs" / CONDA_ENV / "bin")
    env = os.environ.copy()
    for key in ["VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT", "PYTHONPATH"]:
        env.pop(key, None)
    for key in [k for k in env if k.startswith("UV_")]:
        env.pop(key)
    env["PATH"] = f"{conda_env_bin}:{env.get('PATH', '/usr/bin:/bin')}"
    logger.info("Subprocess python: %s/python", conda_env_bin)
    return env


def generate_motion(prompt: str, duration: float = 5.0) -> str:
    """
    Generate SMPL motion data (.npz) from a text prompt using the Kimodo model.

    Calls `kimodo_gen <prompt> --duration <s>` via subprocess inside the kimodo
    conda environment. The CLI writes its output to `output.npz` inside the
    model directory (motion_model/).

    Args:
        prompt:   Natural-language description of the desired motion.
        duration: Animation duration in seconds (default 5.0).

    Returns:
        Absolute path to the generated output.npz file.

    Raises:
        RuntimeError: If kimodo_gen exits non-zero or output.npz is not found.
    """
    logger.info("generate_motion | prompt=%r  duration=%.1fs", prompt, duration)

    cmd = f"kimodo_gen {shlex.quote(prompt)} --duration {duration}"
    logger.info("Command : %s", cmd)
    logger.info("cwd     : %s", MOTION_MODEL_DIR)
    logger.info("Motion generation starting — streaming subprocess output...")

    proc = subprocess.Popen(
        ["bash", "-c", cmd],
        cwd=str(MOTION_MODEL_DIR),
        env=_subprocess_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    for line in proc.stdout:
        logger.info("[kimodo] %s", line.rstrip())
    proc.wait()

    if proc.returncode != 0:
        logger.error("kimodo_gen exited with code %s", proc.returncode)
        raise RuntimeError(f"Motion generation failed (exit {proc.returncode}). Check logs above.")

    output_npz = MOTION_MODEL_DIR / "output.npz"
    if not output_npz.exists():
        # Fallback: pick any .npz written into the model dir
        candidates = sorted(MOTION_MODEL_DIR.glob("*.npz"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            logger.error("No .npz found in: %s", MOTION_MODEL_DIR)
            raise RuntimeError(f"kimodo_gen exited 0 but no .npz found in {MOTION_MODEL_DIR}")
        output_npz = candidates[0]
        logger.warning("output.npz not found, using newest .npz: %s", output_npz)

    logger.info("Motion generation complete | output=%s", output_npz)
    return str(output_npz.resolve())
