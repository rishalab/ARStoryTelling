"""
SHRI Pipeline — JSON Extraction Service
RISHA Lab · IIT Tirupati

Input  : .jpg image of a scanned Hindu scripture page
Output : three JSON dicts (also written to disk for debugging)
  - graph1: 3D model generation
  - graph2: animation generation
  - graph3: scene composition

Usage as module (called by main.py):
    from services.json_extraction.pipeline import run_pipeline
    result = run_pipeline("page.jpg")
    graph1 = result["graph1"]
    graph2 = result["graph2"]
    graph3 = result["graph3"]

Usage as script (for testing):
    python pipeline.py page.jpg
    python pipeline.py page.jpg --output output/
"""

import os
import json
import argparse

from ocr import extract_text
from rule_extractor import extract_candidates
from scaffold_loader import get_index_summary, load_all_for_story
from llm_text_extractor import extract_from_text
from json_generator import generate
from beat_extractor import extract_beats


def run_pipeline(image_path: str, output_dir: str = "output") -> dict:
    """
    Main pipeline function.

    Args:
        image_path: path to .jpg scanned page image
        output_dir: directory to write JSON files (for debugging)

    Returns:
        {
            "graph1": dict,  — 3D model generation
            "graph2": dict,  — animation generation
            "graph3": dict,  — scene composition
            "story_id": str
        }
    """
    print(f"\n{'='*50}")
    print(f"SHRI Pipeline — {os.path.basename(image_path)}")
    print(f"{'='*50}")

    # ── Step 1: OCR ───────────────────────────────────────────────────────────
    print("\n[1/6] OCR...")
    ocr_result = extract_text(image_path)
    print(f"      Method: {ocr_result['method']}")
    print(f"      Text length: {len(ocr_result['raw_text'])} chars")

    # ── Step 2: Rule-based NER ────────────────────────────────────────────────
    print("\n[2/6] Rule-based character extraction...")
    candidate_names = extract_candidates(ocr_result["raw_text"])
    print(f"      Candidates: {candidate_names}")

    # ── Step 3: Scaffold index ────────────────────────────────────────────────
    print("\n[3/6] Loading scaffold index...")
    index_summary = get_index_summary()

    # ── Step 4a: Text LLM ─────────────────────────────────────────────────────
    print("\n[4a/6] Text LLM extraction...")
    text_extraction = extract_from_text(
        ocr_result["raw_text"],
        candidate_names,
        index_summary
    )
    story_id = text_extraction.get("story_id", "unknown")
    print(f"       Story: {story_id}")
    print(f"       Characters: {[c['character_id'] for c in text_extraction.get('characters', [])]}")

    # ── Step 4b: Load scaffold ────────────────────────────────────────────────
    print(f"\n[4b/6] Loading scaffold for: {story_id}...")
    try:
        scaffold_data = load_all_for_story(story_id)
        print(f"       Loaded: {list(scaffold_data['characters'].keys())}")
    except FileNotFoundError:
        print(f"       WARNING: No scaffold for {story_id}")
        scaffold_data = {"story": {}, "characters": {}}

    # ── Step 5: Graph 1 ───────────────────────────────────────────────────────
    print(f"\n[5/6] Building Graph 1...")
    os.makedirs(output_dir, exist_ok=True)
    result  = generate(
        story_id=story_id,
        scaffold_data=scaffold_data,
        text_extraction=text_extraction,
        output_dir=output_dir
    )
    graph1 = json.load(open(result["graph1_path"]))
    print(f"       Characters: {len(graph1.get('characters', []))}")

    # ── Step 6: Graph 2 + Graph 3 ─────────────────────────────────────────────
    print(f"\n[6/6] Extracting beats...")
    story_name = scaffold_data["story"].get("story_name", story_id)
    beats      = extract_beats(
        raw_text=ocr_result["raw_text"],
        story=story_name,
        skandha=text_extraction.get("skandha", ""),
        characters=text_extraction.get("characters", [])
    )

    graph2 = beats["graph2"]
    graph3 = beats["graph3"]

    # Write to disk for debugging
    g2_path = os.path.join(output_dir, "graph2_animation_generation.json")
    g3_path = os.path.join(output_dir, "graph3_scene_composition.json")

    with open(g2_path, "w") as f:
        json.dump(graph2, f, indent=2)
    with open(g3_path, "w") as f:
        json.dump(graph3, f, indent=2)

    print(f"       Animations: {len(graph2.get('animations', []))}")
    print(f"       Scenes: {len(graph3.get('scenes', []))}")

    print(f"\n{'='*50}")
    print("Pipeline complete.")
    print(f"{'='*50}\n")

    return {
        "graph1"  : graph1,
        "graph2"  : graph2,
        "graph3"  : graph3,
        "story_id": story_id
    }


# ── Script mode for testing ───────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SHRI JSON Extraction Pipeline")
    parser.add_argument("image", help="Path to .jpg page image")
    parser.add_argument("--output", default="output", help="Output directory")
    args = parser.parse_args()

    result = run_pipeline(args.image, args.output)
    print(json.dumps({
        "story_id"            : result["story_id"],
        "characters_extracted": len(result["graph1"].get("characters", [])),
        "animations_generated": len(result["graph2"].get("animations", [])),
        "scenes_composed"     : len(result["graph3"].get("scenes", []))
    }, indent=2))