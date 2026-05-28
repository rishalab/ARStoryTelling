import os
import logging
import subprocess
import tempfile
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

RIGGING_MODEL_DIR = Path(__file__).parent / "rigging_model"


def rig_3d_model(glb_path: str, mesh_simplify: int = 1, simplify_count: int = 8192) -> str:
    """
    Run the rigging inference pipeline on a 3D GLB model.

    Internally calls `scripts/inference.sh` inside rigging_model via subprocess.
    The shell script runs mesh simplification, AR-Rig diffusion inference, and
    skeleton visualization in sequence, writing all artifacts under:
        rigging_model/outputs/<asset_name>/

    Args:
        glb_path:        Absolute (or resolvable) path to the input .glb file.
        mesh_simplify:   1 to simplify mesh before inference, 0 to skip.
        simplify_count:  Target face count when simplification is enabled.

    Returns:
        Absolute path to the rigged output file (*_simplified_rig.glb).

    Raises:
        FileNotFoundError: If the input GLB does not exist.
        RuntimeError:      If the inference subprocess exits with a non-zero code,
                           or if the expected output file is missing after the run.
    """
    glb_path = os.path.abspath(glb_path)
    logger.info("rig_3d_model called | input=%s simplify=%s count=%s", glb_path, mesh_simplify, simplify_count)

    if not os.path.exists(glb_path):
        logger.error("Input file not found: %s", glb_path)
        raise FileNotFoundError(f"Input GLB file not found: {glb_path}")

    asset_stem = Path(glb_path).stem  # e.g. "spyro_the_dragon"

    # The shell script resolves DATA_NAME from the basename, so an absolute path is safe.
    cmd = [
        "bash",
        "scripts/inference.sh",
        glb_path,
        str(mesh_simplify),
        str(simplify_count),
    ]

    logger.info("Subprocess command: %s | cwd=%s", " ".join(cmd), RIGGING_MODEL_DIR)

    result = subprocess.run(
        cmd,
        cwd=str(RIGGING_MODEL_DIR),
        capture_output=True,
        text=True,
    )

    logger.debug("stdout:\n%s", result.stdout)
    if result.stderr:
        logger.warning("stderr:\n%s", result.stderr)

    if result.returncode != 0:
        logger.error("Inference script failed (returncode=%s)", result.returncode)
        raise RuntimeError(
            f"Rigging inference failed (exit {result.returncode}):\n{result.stderr}"
        )

    # inference.sh writes: outputs/<stem>/<stem>_simplified_rig.glb
    output_glb = RIGGING_MODEL_DIR / "outputs" / asset_stem / f"{asset_stem}_simplified_rig.glb"

    if not output_glb.exists():
        logger.error("Expected output not found after inference: %s", output_glb)
        raise RuntimeError(f"Rigging completed but output file missing: {output_glb}")

    logger.info("Rigging complete | output=%s", output_glb)
    return str(output_glb)
