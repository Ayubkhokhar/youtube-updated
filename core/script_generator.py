# -*- coding: utf-8 -*-
import json
import re
import time
from openai import OpenAI
import config

# Edge-TTS speaks at roughly 155 words/min = 2.6 words/sec at default rate.
_WPS = 2.6   # words per second


def _build_prompt(target, min_words, target_words, scene_count):
    words_per_scene = round(target_words / scene_count)
    scene_dur       = round(target / scene_count)

    return (
        "You are a professional YouTube video scriptwriter. "
        "Write a complete, engaging, well-paced video script.\n\n"

        f"VIDEO TARGET: {target} seconds of spoken narration.\n"
        f"WORD COUNT REQUIREMENT: Total narration across ALL {scene_count} scenes "
        f"must be between {min_words} and {target_words} words.\n\n"

        "WHY WORD COUNT MATTERS:\n"
        f"A narrator speaks at about {round(_WPS * 60)} words per minute.\n"
        f"- {target_words} words / {round(_WPS * 60)} wpm = {target} seconds of speech.\n"
        f"- If you write only {min_words} words = {round(min_words/_WPS)} seconds.\n"
        f"- DO NOT write fewer than {min_words} words total.\n\n"

        f"STRUCTURE: {scene_count} scenes, approximately {words_per_scene} words each, "
        f"approximately {scene_dur} seconds each.\n\n"

        "=== SCENE 1: HOOK (MANDATORY) ===\n"
        "The first line MUST be an irresistible hook. Use one of these proven formats:\n"
        "  - Shocking fact: 'Most people don't know that [surprising fact]...'\n"
        "  - Bold question: 'What if everything you knew about [topic] was wrong?'\n"
        "  - Controversy: 'Here is the uncomfortable truth about [topic] nobody talks about.'\n"
        "  - Story opener: 'Three years ago I discovered something about [topic] that changed everything.'\n"
        "The hook MUST make viewers stop scrolling. This is the single most important line.\n\n"

        f"=== SCENES 2 to {scene_count - 1}: CONTENT ===\n"
        f"Cover the topic thoroughly. Each scene = 2-3 complete sentences, "
        f"approximately {words_per_scene} words. Write full flowing narration as if speaking to camera. "
        "Build curiosity and momentum through each scene.\n\n"

        f"=== SCENE {scene_count}: CLOSING ===\n"
        "End with a strong memorable takeaway AND a direct call-to-action: "
        "'Like this video if you found it useful. Subscribe for more content like this.'\n\n"

        f"WORD COUNT CHECK: Before finalizing, count total words across all {scene_count} scenes. "
        f"If total is less than {min_words} words, you MUST expand each scene to reach {min_words} words minimum.\n\n"

        "Return ONLY valid JSON (no markdown, no extra text):\n"
        "{\n"
        '  "title": "Compelling SEO-friendly video title",\n'
        '  "scenes": [\n'
        '    {\n'
        f'      "narration": "Full narration text for this scene. '
        f'Must be approximately {words_per_scene} words. Write 2-3 complete sentences. '
        f'Do not write a single short sentence.",\n'
        '      "keywords": "2-4 words for stock footage search",\n'
        f'      "duration_sec": {scene_dur},\n'
        '      "text_overlay": {\n'
        '        "text": "Key phrase to display on screen",\n'
        '        "start_sec": 1,\n'
        '        "duration_sec": 3\n'
        '      }\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        "text_overlay is optional - include only for 2-3 most impactful scenes. Omit for others.\n\n"
        f"FINAL REMINDER: Total word count across all {scene_count} scenes must be "
        f"{min_words} to {target_words} words. Count them before responding."
    )


def generate_script(topic, max_retries=3):
    target = config.TOTAL_TARGET_DURATION

    target_words = int(target * _WPS)
    min_words    = int(target * _WPS * 0.80)
    scene_count  = max(3, round(target / 9))

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=config.GROQ_API_KEY,
    )

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                wait = 2 ** attempt
                print(f"[script_generator] Retrying in {wait}s (attempt {attempt + 1})...")
                time.sleep(wait)

            prompt = _build_prompt(target, min_words, target_words, scene_count)

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user",   "content": f"Write a YouTube video script about: {topic}"},
                ],
                temperature=0.75,
                max_tokens=6000,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content.strip()

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group()

            script = json.loads(content)

            if "scenes" not in script or not isinstance(script["scenes"], list):
                raise ValueError("Missing or invalid 'scenes' list in JSON")
            if len(script["scenes"]) < 2:
                raise ValueError(f"Too few scenes: {len(script['scenes'])}")

            for scene in script["scenes"]:
                scene.setdefault("narration", "")
                scene.setdefault("keywords", topic)
                scene.setdefault("duration_sec", round(target / len(script["scenes"])))
                scene["duration_sec"] = max(4, min(20, int(scene["duration_sec"])))

            actual_words = sum(len(s["narration"].split()) for s in script["scenes"])
            est_secs     = round(actual_words / _WPS)

            print(f"[script_generator] Attempt {attempt + 1}: "
                  f"{len(script['scenes'])} scenes, {actual_words} words "
                  f"-> est {est_secs}s (target={target}s, min={min_words} words)")

            if actual_words < min_words and attempt < max_retries:
                shortage = min_words - actual_words
                raise ValueError(
                    f"Word count too low: {actual_words} (need >={min_words}). "
                    f"Short by {shortage} words. Retrying."
                )

            # Trim only if significantly over budget
            if actual_words > target_words * 1.30:
                ratio = target_words / actual_words
                for scene in script["scenes"]:
                    words = scene["narration"].split()
                    keep  = max(10, round(len(words) * ratio))
                    if len(words) > keep:
                        scene["narration"] = " ".join(words[:keep])
                actual_words = sum(len(s["narration"].split()) for s in script["scenes"])

            # Scale scene duration_sec to match actual spoken duration
            actual_duration = actual_words / _WPS
            total_scene_dur = sum(s["duration_sec"] for s in script["scenes"])
            if total_scene_dur > 0:
                scale = actual_duration / total_scene_dur
                for s in script["scenes"]:
                    s["duration_sec"] = max(4, min(20, round(s["duration_sec"] * scale)))

            script.setdefault("title", topic.title())
            return script

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            last_error = e
            print(f"[script_generator] Attempt {attempt + 1} failed: {e}")
        except Exception as e:
            last_error = e
            print(f"[script_generator] Attempt {attempt + 1} unexpected error: {e}")

    raise RuntimeError(
        f"Script generation failed after {max_retries + 1} attempts: {last_error}"
    )
