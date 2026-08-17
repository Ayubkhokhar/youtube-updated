#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
metadata_generator.py — High-SEO YouTube Metadata Generation Engine.

Follows the exact prompt architecture specified in MASTER_PLAN.md §4b.
Generates:
1. Optimized Title (60-70 chars, rotating across patterns a/b/c/d/e).
2. Comprehensive SEO Description (150-300 words with standalone hook & search paragraph).
3. 15-20 Targeted & Long-Tail Tags.
4. YouTube Category Classification (Education, Science & Technology, or Entertainment).
5. Logs pattern usage to `data/title_pattern_history.json` for CTR & rotation tracking.
"""

import os
import sys
import json
import time
import re
import random
import argparse
from datetime import datetime

# UTF-8 output configuration
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PATTERN_HISTORY_FILE = os.path.join(DATA_DIR, "title_pattern_history.json")

os.makedirs(DATA_DIR, exist_ok=True)

# The 5 proven title patterns from MASTER_PLAN.md §4b
TITLE_PATTERNS = {
    "a": "Curiosity gap: 'The [Topic] Detail Nobody Talks About'",
    "b": "Number/list: '5 [Topic] Facts That Sound Fake (But Aren't)'",
    "c": "Question hook: 'Why Did [Historical Event] Actually Happen?'",
    "d": "Myth-bust: 'The Truth About [Common Belief] Is Not What You Think'",
    "e": "Stakes/scale: 'The [Topic] That Changed Everything'",
}

# The EXACT prompt template from MASTER_PLAN.md §4b
SYSTEM_PROMPT_TEMPLATE = """You are a YouTube SEO specialist for a history/science facts channel targeting a US English-speaking audience. Given the video script below, generate:

1. TITLE (60-70 characters max):
   - Use ONE of these proven patterns, rotate across videos, never repeat the same pattern twice in a row:
     a) Curiosity gap: "The [Topic] Detail Nobody Talks About"
     b) Number/list: "5 [Topic] Facts That Sound Fake (But Aren't)"
     c) Question hook: "Why Did [Historical Event] Actually Happen?"
     d) Myth-bust: "The Truth About [Common Belief] Is Not What You Think"
     e) Stakes/scale: "The [Topic] That Changed Everything"
   - Must accurately reflect the script content — no clickbait that isn't paid off in the video
   - Front-load the specific noun/topic in the first 40 characters (helps both CTR and search)
   - No ALL CAPS, no more than one emoji if any

2. DESCRIPTION (150-300 words):
   - First 2 sentences must work standalone (shown in search/suggested previews) — restate the hook, don't just repeat the title
   - Include 3-5 sentences summarizing what's actually covered (real content summary, not vague teasing)
   - Include a natural-language paragraph with likely search terms a curious viewer would type (not a keyword-stuffed list)
   - End with a one-line channel description + upload schedule note
   - Do NOT use engagement-bait phrases like "like and subscribe" as the primary CTA — one soft mention max

3. TAGS (15-20 tags):
   - Mix of broad (history, science facts) and specific (the exact topic, related figures/events/concepts)
   - Include 2-3 long-tail phrases matching how someone would actually search ("why did X happen", "true story of X")
   - No unrelated trending tags just for reach — must match actual content

4. CATEGORY: classify as one of [Education, Science & Technology, Entertainment] based on content

Output as JSON: {{"title": "...", "description": "...", "tags": [...], "category": "...", "pattern_used": "{preferred_pattern}"}}"""


def load_pattern_history() -> list:
    if os.path.exists(PATTERN_HISTORY_FILE):
        try:
            with open(PATTERN_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("pattern_history", [])
        except Exception:
            pass
    return []


def save_pattern_history(history: list):
    with open(PATTERN_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"pattern_history": history}, f, indent=2, ensure_ascii=False)


def get_next_preferred_pattern() -> str:
    """Returns the next pattern code (a/b/c/d/e) to enforce non-repeating rotation."""
    history = load_pattern_history()
    pattern_keys = ["a", "b", "c", "d", "e"]
    if not history:
        return random.choice(pattern_keys)

    last_pattern = history[-1].get("pattern_used", "")
    available = [p for p in pattern_keys if p != last_pattern]
    return random.choice(available)


def log_pattern_usage(pattern: str, title: str, topic: str):
    history = load_pattern_history()
    history.append({
        "pattern_used": pattern,
        "title": title,
        "topic": topic,
        "timestamp": time.time(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    if len(history) > 500:
        history = history[-500:]
    save_pattern_history(history)


def _generate_mock_metadata(script: dict, topic: str, preferred_pattern: str) -> dict:
    """Generates structured SEO metadata strictly following §4b rules without API calls."""
    clean_topic = topic.strip() or script.get("title", "Historical Discovery")
    
    # Title patterns
    titles_map = {
        "a": f"The {clean_topic} Detail Nobody Talks About",
        "b": f"5 {clean_topic} Facts That Sound Fake (But Aren't)",
        "c": f"Why Did {clean_topic} Actually Happen?",
        "d": f"The Truth About {clean_topic} Is Not What You Think",
        "e": f"The {clean_topic} That Changed Everything",
    }
    title = titles_map.get(preferred_pattern, titles_map["a"])
    if len(title) > 70:
        title = title[:67] + "..."

    # Script summary extraction
    scenes = script.get("scenes", [])
    script_text = " ".join(s.get("narration", "") for s in scenes)
    summary_snippet = script_text[:250] if script_text else f"A deep dive into the fascinating history and science of {clean_topic}."

    description = (
        f"What really happened with {clean_topic}? While most people know the basic story, "
        f"the deeper truth reveals a far more complex and surprising reality.\n\n"
        f"In this video, we explore the crucial details behind {clean_topic}. {summary_snippet} "
        f"From ancient archives to modern scientific breakthroughs, the evidence shows why this event continues to challenge historians and scientists today.\n\n"
        f"For curious minds exploring forgotten history, ancient technology, and unexplained science mysteries, "
        f"understanding the true story of {clean_topic} offers fresh perspective on how historical discoveries shape our world.\n\n"
        f"Quiet Curiosities explores the untold stories of history, science, and the unexplained. New videos uploaded daily."
    )

    tags = [
        "history facts",
        "science facts",
        "educational documentary",
        "ancient history",
        "did you know",
        clean_topic.lower(),
        f"history of {clean_topic.lower()}",
        f"truth about {clean_topic.lower()}",
        f"why did {clean_topic.lower()} happen",
        f"secrets of {clean_topic.lower()}",
        "unexplained mysteries",
        "historical discoveries",
        "science explainer",
        "forgotten history",
        "fascinating facts",
    ]

    category = "Education"
    if any(k in clean_topic.lower() for k in ["space", "quantum", "physics", "science", "biology", "ozone", "computer"]):
        category = "Science & Technology"

    return {
        "title": title,
        "description": description.strip(),
        "tags": tags[:18],
        "category": category,
        "pattern_used": preferred_pattern,
    }


def generate_metadata(script: dict, topic: str = "", mock: bool = False) -> dict:
    """
    Generates YouTube metadata (Title, Description, Tags, Category) for a video script.
    
    Adheres strictly to the prompt engineering in MASTER_PLAN.md §4b.
    """
    preferred_pattern = get_next_preferred_pattern()
    clean_topic = topic or script.get("title", "")

    import config
    config.reload()
    api_key = config.GROQ_API_KEY

    # Use mock fallback if requested or if Groq key is unavailable
    if mock or not api_key or api_key.startswith("gsk_placeholder") or "your_" in api_key:
        metadata = _generate_mock_metadata(script, clean_topic, preferred_pattern)
        log_pattern_usage(metadata.get("pattern_used", preferred_pattern), metadata["title"], clean_topic)
        return metadata

    # Format script for Groq prompt
    script_repr = f"TOPIC: {clean_topic}\n\nSCENES:\n"
    for i, s in enumerate(script.get("scenes", []), 1):
        script_repr += f"Scene {i}: {s.get('narration', '')}\n"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(preferred_pattern=preferred_pattern)

    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Generate YouTube SEO metadata for this script:\n\n{script_repr}"},
            ],
            temperature=0.7,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content.strip()
        data = json.loads(content)

        # Validate fields
        title = data.get("title", f"The Secrets of {clean_topic}")
        description = data.get("description", "")
        tags = data.get("tags", ["history", "science", clean_topic])
        category = data.get("category", "Education")
        pattern = data.get("pattern_used", preferred_pattern)

        # Truncate title if over 70 chars
        if len(title) > 70:
            title = title[:67].rsplit(" ", 1)[0] + "..."

        result = {
            "title": title,
            "description": description,
            "tags": tags,
            "category": category,
            "pattern_used": pattern,
        }

        log_pattern_usage(pattern, title, clean_topic)
        return result

    except Exception as e:
        print(f"[metadata_generator] Groq metadata generation failed, using structured fallback: {e}")
        fallback = _generate_mock_metadata(script, clean_topic, preferred_pattern)
        log_pattern_usage(fallback.get("pattern_used", preferred_pattern), fallback["title"], clean_topic)
        return fallback


def main():
    parser = argparse.ArgumentParser(description="YouTube SEO Metadata Generator CLI.")
    parser.add_argument("--topic", type=str, default="The Antikythera Mechanism", help="Topic to generate metadata for.")
    parser.add_argument("--mock", action="store_true", help="Run with mock/offline generation.")

    args = parser.parse_args()

    dummy_script = {
        "title": args.topic,
        "scenes": [
            {"narration": f"What if the ancient Greeks built a computer 2,000 years before modern technology existed? The Antikythera Mechanism was found in a shipwreck."},
            {"narration": "X-ray scans revealed over thirty precision bronze gears capable of predicting astronomical positions and eclipses decades in advance."},
            {"narration": "Historians now believe classical civilization was far closer to an industrial revolution than previously imagined."},
        ],
    }

    metadata = generate_metadata(dummy_script, topic=args.topic, mock=args.mock)
    print("\n--- Generated YouTube Metadata ---")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
