import argparse
import subprocess
from pathlib import Path
import shutil
import sys
import time

SERVICE_ROOT = Path(__file__).resolve().parent
TRIPOSR = SERVICE_ROOT / "TripoSR"


def convert_obj_to_glb(obj_path: Path, glb_path: Path):
    import trimesh
    mesh = trimesh.load(obj_path, force="mesh")
    mesh.export(glb_path)
    print(f"Converted OBJ to GLB: {glb_path}")


def generate_glb(input_image: str, asset_name: str | None = None):
    input_path = Path(input_image)

    if not input_path.is_absolute():
        input_path = ROOT / input_path

    if not input_path.exists():
        raise FileNotFoundError(f"Input image not found: {input_path}")

    if asset_name is None:
        asset_name = input_path.stem

    job_id = f"{asset_name}_{int(time.time())}"

    out_dir = ROOT / "outputs" / "jobs" / job_id
    final_dir = ROOT / "outputs" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            sys.executable,
            str(TRIPOSR / "run.py"),
            str(input_path),
            "--output-dir",
            str(out_dir),
        ],
        cwd=str(TRIPOSR),
        check=True,
    )

    final_glb = final_dir / f"{job_id}.glb"

    glbs = list(out_dir.rglob("*.glb"))
    if glbs:
        shutil.copy(glbs[0], final_glb)
        print(f"GLB ready: {final_glb}")
        return final_glb

    objs = list(out_dir.rglob("*.obj"))
    if objs:
        convert_obj_to_glb(objs[0], final_glb)
        print(f"GLB ready: {final_glb}")
        return final_glb

    raise FileNotFoundError(f"No GLB or OBJ found in {out_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate GLB from any 2D image using TripoSR")
    parser.add_argument("--input", "-i", required=True, help="Path to input image")
    parser.add_argument("--name", "-n", default=None, help="Asset/model name")
    args = parser.parse_args()

    generate_glb(args.input, args.name)