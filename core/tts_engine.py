"""
tts_engine.py — Robust TTS with retry logic and voice speed optimisation.
Generates a full voiceover MP3 + word-level SRT subtitle file for the script.
"""
import asyncio
import os
import time
import config


def _get_voice():
    return getattr(config, "VOICE_NAME", "en-US-JennyNeural")


def generate_voiceover(scenes, max_retries: int = 3):
    """
    Concatenate all scene narrations into one text block, synthesise speech,
    generate an SRT file, and return:
        (audio_path, srt_path, timings, actual_duration_seconds)
    """
    full_text = " ".join(scene.get("narration", "").strip() for scene in scenes)
    full_text  = full_text.strip()

    if not full_text:
        raise ValueError("No narration text found in scenes.")

    audio_path = os.path.join(config.TEMP_DIR, "full_voiceover.mp3")
    srt_path   = os.path.join(config.TEMP_DIR, "subtitles.srt")

    # Try edge-tts with retries
    success = False
    for attempt in range(max_retries):
        if _try_edge_tts(full_text, audio_path, srt_path):
            success = True
            break
        wait = 2 ** attempt
        print(f"[tts_engine] edge-tts attempt {attempt + 1} failed, retrying in {wait}s...")
        time.sleep(wait)

    # Fallback to gTTS if edge-tts keeps failing
    if not success:
        print("[tts_engine] edge-tts exhausted, trying gTTS fallback...")
        success = _try_gtts(full_text, audio_path, srt_path, scenes)

    if not success:
        raise RuntimeError("All TTS backends failed. Check your internet connection.")

    # Measure the actual audio duration
    actual_duration = _measure_audio_duration(audio_path)
    if actual_duration <= 0:
        # Last-resort estimate: 150 words per minute
        word_count = len(full_text.split())
        actual_duration = (word_count / 150) * 60

    # Build timing list (used by the composer for scene alignment)
    timings = []
    current_time = 0.0
    for i, scene in enumerate(scenes):
        timings.append({
            "scene_index": i,
            "start_sec":   current_time,
            "duration_sec": scene.get("duration_sec", 10),
            "text":         scene.get("narration", ""),
        })
        current_time += scene.get("duration_sec", 10)

    return audio_path, srt_path, timings, actual_duration


def _measure_audio_duration(audio_path: str) -> float:
    """Return the duration of an MP3 file in seconds using moviepy."""
    try:
        from moviepy import AudioFileClip as _AFC
        clip = _AFC(audio_path)
        dur  = clip.duration
        clip.close()
        return float(dur)
    except Exception:
        return 0.0


def _try_edge_tts(text: str, audio_path: str, srt_path: str) -> bool:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_edge_tts_generate(text, audio_path, srt_path))
        finally:
            loop.close()
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
            return True
    except Exception as e:
        print(f"[tts_engine] edge-tts error: {e}")
    return False


async def _edge_tts_generate(text: str, audio_path: str, srt_path: str):
    import edge_tts
    voice = _get_voice()

    # Save audio
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(audio_path)

    # Generate word-level SRT
    communicate2 = edge_tts.Communicate(text, voice)
    srt_lines = []
    idx = 1
    async for chunk in communicate2.stream():
        if chunk["type"] == "WordBoundary":
            start = chunk["offset"] / 1e7
            end   = start + chunk["duration"] / 1e7
            word  = chunk.get("text", "").strip()
            if word:
                srt_lines.append(str(idx))
                srt_lines.append(f"{_fmt_srt(start)} --> {_fmt_srt(end)}")
                srt_lines.append(word)
                srt_lines.append("")
                idx += 1

    # Sentence-level fallback if word boundaries weren't returned
    if idx == 1:
        communicate3 = edge_tts.Communicate(text, voice)
        async for chunk in communicate3.stream():
            if chunk["type"] == "Sentence":
                start    = chunk["offset"] / 1e7
                end      = (chunk["offset"] + chunk["duration"]) / 1e7
                sentence = chunk.get("text", "").strip()
                if sentence:
                    srt_lines.append(str(idx))
                    srt_lines.append(f"{_fmt_srt(start)} --> {_fmt_srt(end)}")
                    srt_lines.append(sentence)
                    srt_lines.append("")
                    idx += 1

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))


def _try_gtts(text: str, audio_path: str, srt_path: str, scenes: list) -> bool:
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="en", slow=False)
        tts.save(audio_path)

        # Build a basic SRT from scene timing estimates
        srt_lines = []
        current_time = 0.0
        for i, scene in enumerate(scenes):
            dur = scene.get("duration_sec", 10)
            srt_lines.append(str(i + 1))
            srt_lines.append(f"{_fmt_srt(current_time)} --> {_fmt_srt(current_time + dur)}")
            srt_lines.append(scene.get("narration", ""))
            srt_lines.append("")
            current_time += dur

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))
        return True
    except Exception as e:
        print(f"[tts_engine] gTTS error: {e}")
    return False


def _fmt_srt(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
