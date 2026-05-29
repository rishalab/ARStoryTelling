"""
Module: Beat Extractor
SHRI Project · RISHA Lab · IIT Tirupati

Takes OCR text directly from pipeline.
Produces:
  Graph 2 — individual animations to generate (action + duration only)
  Graph 3 — scene composition (which animation plays when + spatial positions)

Both graphs fully LLM-driven for beat division, duration, positions.
Rule-based only for character identification and verb extraction
which feeds as context to the LLM.

Standalone test:
  python beat_extractor.py
  python beat_extractor.py --file page_text.txt
"""

import json
import re
import os
import argparse
from groq import Groq


import os
from dotenv import load_dotenv
load_dotenv()
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL   = "llama-3.3-70b-versatile"


# ── Rule-based: character identification ─────────────────────────────────────
def extract_characters_simple(text: str) -> list:
    TITLES = ["Lord", "King", "Queen", "Prince", "Princess",
              "Sage", "Rishi", "Muni", "Demon", "Saint"]
    STOP   = {"The","This","That","When","While","Once","Long","After",
               "Before","But","And","So","He","She","They","His","Her",
               "Their","Lord","King","Dear","Your","My","By","You","In",
               "On","At","To","For","Of","With","From","An","A","Today",
               "All","Although","Nevertheless","Everyone","Please"}
    found  = set()

    for title in TITLES:
        pattern = re.compile(rf"\b{title}\s+([A-Z][a-zA-Z]+)\b")
        for match in pattern.findall(text):
            found.add(match)

    from collections import Counter
    counts = Counter(re.findall(r"\b([A-Z][a-zA-Z]{2,})\b", text))
    for word, count in counts.items():
        if count >= 2 and word not in STOP:
            found.add(word)

    return [name.lower().replace(" ", "_") for name in sorted(found)]


# ── Rule-based: verb extraction ───────────────────────────────────────────────
def extract_verbs(text: str) -> list:
    pattern = re.compile(
        r"\b(walked|ran|approached|moved|entered|came|stepped|stopped|turned|"
        r"looked|heard|saw|stood|watched|asked|said|spoke|told|replied|praised|"
        r"warned|offered|gave|took|washed|poured|welcomed|greeted|bowed|raised|"
        r"pointed|placed|held|lifted|nodded|grew|expanded|transformed|became)\b",
        re.IGNORECASE
    )
    return list(set(pattern.findall(text)))


# ── LLM: full beat extraction + scene composition ────────────────────────────
def extract_beats_llm(raw_text: str, character_ids: list, verbs: list) -> dict:
    """
    Single LLM call that produces both Graph 2 and Graph 3.
    """
    characters_str = ", ".join(character_ids) if character_ids else "unknown"
    verbs_str      = ", ".join(verbs) if verbs else "none detected"

    prompt = f"""You are an animation director for a Hindu scripture AR system.

Page text:
\"\"\"{raw_text}\"\"\"

Character IDs (use these exactly as-is): {characters_str}
Action verbs found: {verbs_str}

Produce two JSON objects:

1. graph2 — list of all individual animations to generate.
   Each entry is ONE animation file with just the action and duration.
   Action must be HumanML3D style: "a person walks forward slowly"
   No character names in action description.

2. graph3 — scene composition.
   Which animation file plays when.
   Spatial position of each character per scene (can change between scenes).
   Position is relative to center of book surface (SLAM detected plane).
   facing: "positive_x" or "negative_x"
   Characters facing each other should have opposite facing directions.
   Simultaneous = true when two characters act at the same time.

Return ONLY this JSON structure, no explanation, no markdown:

{{
  "graph2": {{
    "animations": [
      {{
        "animation_id": "<character_id>_anim_1",
        "character_id": "<character_id>",
        "action": "<HumanML3D style motion phrase>",
        "duration_seconds": <number>
      }}
    ]
  }},
  "graph3": {{
    "scenes": [
      {{
        "scene_id": "scene_1",
        "characters": [
          {{
            "character_id": "<character_id>",
            "position": [<x>, 0, <z>],
            "facing": "<positive_x|negative_x>",
            "glb_file": "<character_id>.glb"
          }}
        ],
        "timeline": [
          {{
            "start_time": <seconds>,
            "end_time": <seconds>,
            "character_id": "<character_id>",
            "animation_id": "<animation_id from graph2>",
            "simultaneous": <true|false>
          }}
        ]
      }}
    ]
  }}
}}"""

    client   = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role"   : "system",
                "content": "You are an animation beat extractor for Hindu scripture AR. Return only valid JSON, no markdown, no explanation."
            },
            {
                "role"   : "user",
                "content": prompt
            }
        ],
        temperature=0.1,
        max_tokens=2000
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}\nResponse: {raw}")


# ── Main function called by pipeline ─────────────────────────────────────────
def extract_beats(
    raw_text  : str,
    story     : str  = "",
    skandha   : str  = "",
    characters: list = None
) -> dict:
    """
    Main entry point. Called directly by pipeline.py with OCR text.

    Args:
        raw_text:   OCR extracted text from page (from ocr.py)
        story:      story name from scaffold
        skandha:    skandha number from scaffold
        characters: list of character dicts from llm_text_extractor
                    (each has a "character_id" key matched to scaffold)

    Returns:
        {
            "graph2": graph2_dict,
            "graph3": graph3_dict
        }
    """
    character_ids = [c["character_id"] for c in (characters or [])]
    verbs         = extract_verbs(raw_text)
    print(f"  Character IDs: {character_ids}")
    print(f"  Verbs found  : {verbs}")

    print("  [beat_extractor] Calling LLM for beat division and scene composition...")
    result = extract_beats_llm(raw_text, character_ids, verbs)

    # Add story metadata
    result["graph2"]["graph"]   = "animation_generation"
    result["graph2"]["story"]   = story
    result["graph2"]["skandha"] = skandha

    result["graph3"]["graph"]              = "scene_composition"
    result["graph3"]["story"]              = story
    result["graph3"]["skandha"]            = skandha
    result["graph3"]["coordinate_system"]  = "book_surface_center"

    return result


# ── Standalone test runner ────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SHRI Beat Extractor — standalone test"
    )
    parser.add_argument("--file",    help="Path to text file")
    parser.add_argument("--story",   default="", help="Story name")
    parser.add_argument("--skandha", default="", help="Skandha number")
    parser.add_argument("--out",     default="output", help="Output directory")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            raw_text = f.read()
    else:
        # Built-in sample for quick test
        raw_text = """
        Lord Vamana started walking towards the sacrificial arena of the
        King of asuras, Bali. When he reached the spot, the priests stood up
        and welcomed the young brahmana boy. King Bali became very happy to
        see Vamana and instantly developed deep devotion to the Lord. Bali
        unhesitatingly washed Lord Vamana's lotus feet and placed the water
        on his head. Bali praised Vamana and said, My dear brahmana, I
        heartily welcome You. Please ask me for whatever You want. Lord
        Vamana was very pleased and said, I only want three steps of land.
        """
        print("No file provided — using built-in sample text.\n")

    print("\n" + "="*50)
    print("SHRI Beat Extractor — standalone test")
    print("="*50 + "\n")

    result = extract_beats(raw_text, args.story, args.skandha)

    print("\nGraph 2 — Animation Generation:")
    print(json.dumps(result["graph2"], indent=2))

    print("\nGraph 3 — Scene Composition:")
    print(json.dumps(result["graph3"], indent=2))

    # Save output files
    os.makedirs(args.out, exist_ok=True)
    g2_path = os.path.join(args.out, "graph2_animation_generation.json")
    g3_path = os.path.join(args.out, "graph3_scene_composition.json")

    with open(g2_path, "w") as f:
        json.dump(result["graph2"], f, indent=2)
    with open(g3_path, "w") as f:
        json.dump(result["graph3"], f, indent=2)

    print(f"\nSaved: {g2_path}")
    print(f"Saved: {g3_path}")