#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
shorts_extractor.py — Auto-extract vertical 9:16 YouTube Shorts from long-form videos.

Follows MASTER_PLAN.md §4d:
- Extracts 2-4 high-retention segments (30-60s) from long-form video output.
- Re-formats to 9:16 vertical (1080x1920).
- Generates optimized Shorts metadata with #Shorts hashtags.
- Prepares clips for scheduled multi-upload without repeating full generation costs.
"""

import os
import sys
import re
import json
import uuid
import argparse
from moviepy import (
    VideoFileClip, CompositeVideoClip, TextClip,
    ColorClip, ImageClip
)

# UTF-8 output configuration
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config

SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920


def _parse_srt_segment(srt_path: str, start_time: float, end_time: float) -> list:
    """Extract and re-index subtitles falling within [start_time, end_time]."""
    if not srt_path or not os.path.exists(srt_path):
        return []

    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    subs = []
    for block in re.split(r"\n\n+", content.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[1])
        if not m:
            continue
        s_sec = _srt_str_to_sec(m.group(1))
        e_sec = _srt_str_to_sec(m.group(2))
        text = " ".join(lines[2:]).strip()

        # Check overlap
        if e_sec > start_time and s_sec < end_time:
            rel_start = max(0.0, s_sec - start_time)
            rel_end = min(end_time - start_time, e_sec - start_time)
            if rel_end > rel_start and text:
                subs.append((rel_start, rel_end, text))

    return subs


def _srt_str_to_sec(t: str) -> float:
    h, m, s = t.split(":")
    s, ms = s.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _make_shorts_subtitle_clips(subs: list, duration: float) -> list:
    """Large, vibrant subtitles formatted for vertical mobile viewing."""
    clips = []
    font_arg = config.FONT_PATH if os.path.exists(config.FONT_PATH) else None
    font_size = 56  # prominent for vertical screens

    # Group into 2-3 words for fast-paced vertical viewing
    WORDS_PER_GROUP = 3
    groups = []
    buf_words, buf_start, buf_end = [], None, None

    for s_start, s_end, text in subs:
        if s_start >= duration:
            break
        s_end = min(s_end, duration)
        if buf_start is None:
            buf_start = s_start
        buf_end = s_end
        buf_words.append(text)
        if len(buf_words) >= WORDS_PER_GROUP:
            groups.append((buf_start, buf_end, " ".join(buf_words)))
            buf_words, buf_start, buf_end = [], None, None

    if buf_words and buf_start is not None:
        groups.append((buf_start, buf_end, " ".join(buf_words)))

    for g_start, g_end, text in groups:
        if g_start >= duration:
            break
        g_end = min(g_end, duration)
        if g_end <= g_start:
            continue
        try:
            txt = (
                TextClip(
                    font=font_arg,
                    text=text.upper(),
                    font_size=font_size,
                    color="#FFDC32",
                    stroke_color="black",
                    stroke_width=4,
                    method="label",
                )
                .with_position(("center", int(SHORTS_HEIGHT * 0.65)))
                .with_start(g_start)
                .with_duration(g_end - g_start)
            )
            clips.append(txt)
        except Exception as e:
            print(f"[shorts_extractor] Subtitle clip error: {e}")

    return clips


def _identify_segments(scenes: list, total_duration: float, max_shorts: int = 3) -> list:
    """
    Identifies high-impact candidate time windows [start, end, title_hook] from script scenes.
    """
    segments = []
    if not scenes:
        # Fallback split into 30s chunks
        chunk_dur = min(40.0, total_duration)
        segments.append((0.0, chunk_dur, "Shocking Historical Fact"))
        if total_duration > 60:
            segments.append((chunk_dur, min(total_duration, chunk_dur + 40.0), "The Untold Mystery"))
        return segments

    # 1. Hook Short (First scenes totaling 30-45s)
    cum_dur = 0.0
    hook_end = 0.0
    for scene in scenes:
        dur = scene.get("duration_sec", 8)
        if cum_dur + dur <= 50.0:
            cum_dur += dur
            hook_end = cum_dur
        else:
            break
    if hook_end >= 20.0:
        hook_title = scenes[0].get("text_overlay", {}).get("text") or "The Hidden Fact Nobody Knows"
        segments.append((0.0, min(total_duration, hook_end), hook_title))

    # 2. Middle Climax Short
    if len(scenes) >= 4 and total_duration >= 70.0:
        mid_idx = len(scenes) // 2
        mid_start = sum(s.get("duration_sec", 8) for s in scenes[:mid_idx])
        mid_dur = sum(s.get("duration_sec", 8) for s in scenes[mid_idx:mid_idx + 3])
        mid_end = min(total_duration, mid_start + min(45.0, max(25.0, mid_dur)))
        if mid_end - mid_start >= 20.0:
            mid_title = scenes[mid_idx].get("text_overlay", {}).get("text") or "What Scientists Just Discovered"
            segments.append((mid_start, mid_end, mid_title))

    # Limit to max requested shorts
    return segments[:max_shorts]


def extract_shorts(
    video_path: str,
    script: dict = None,
    srt_path: str = None,
    output_dir: str = None,
    max_shorts: int = 3,
    dry_run: bool = False,
) -> list:
    """
    Extracts 2-4 vertical Shorts (1080x1920) from long-form video.
    Returns a list of dicts with short metadata and video filepaths.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Source video not found: {video_path}")

    if not output_dir:
        output_dir = os.path.join(config.OUTPUT_DIR, "shorts")
    os.makedirs(output_dir, exist_ok=True)

    src_clip = VideoFileClip(video_path)
    total_duration = src_clip.duration
    scenes = script.get("scenes", []) if script else []

    candidate_segments = _identify_segments(scenes, total_duration, max_shorts=max_shorts)
    extracted_shorts = []

    base_topic = script.get("title", "Mystery") if script else "History Facts"

    for idx, (start_t, end_t, segment_hook) in enumerate(candidate_segments, 1):
        seg_duration = end_t - start_t
        uid = str(uuid.uuid4())[:5]
        safe_name = re.sub(r'[^a-zA-Z0-9]+', '-', segment_hook).strip('-').lower()[:30]
        out_filename = f"short_{idx}_{safe_name}_{uid}.mp4"
        out_filepath = os.path.join(output_dir, out_filename)

        # Metadata for this Short
        short_title = f"{segment_hook[:55]} #Shorts"
        short_desc = (
            f"{segment_hook}. Did you know this fascinating detail about {base_topic}?\n\n"
            f"Watch the full story on our channel! Subscribe for daily history & science facts.\n\n"
            f"#Shorts #History #Science #Facts #DidYouKnow"
        )
        short_tags = ["Shorts", "YouTubeShorts", "History", "Science", "DidYouKnow", "Facts", base_topic.lower()]

        item_meta = {
            "index": idx,
            "title": short_title,
            "description": short_desc,
            "tags": short_tags,
            "category": "Education",
            "start_time_sec": round(start_t, 2),
            "end_time_sec": round(end_t, 2),
            "duration_sec": round(seg_duration, 2),
            "video_path": out_filepath if not dry_run else None,
            "status": "ready" if not dry_run else "dry_run",
        }

        if dry_run:
            print(f"🟡 [shorts_extractor] Dry run: Identified Short {idx} ({start_t:.1f}s - {end_t:.1f}s, {seg_duration:.1f}s): {short_title}")
            extracted_shorts.append(item_meta)
            continue

        print(f"🎬 [shorts_extractor] Extracting Short {idx}/{len(candidate_segments)} ({start_t:.1f}s - {end_t:.1f}s)...")

        # Extract subclip
        sub = src_clip.subclipped(start_t, end_t)

        # Re-center and crop/scale to 1080x1920 (9:16)
        sw, sh = sub.size
        target_w, target_h = SHORTS_WIDTH, SHORTS_HEIGHT
        src_ratio = sw / sh
        target_ratio = target_w / target_h

        if abs(src_ratio - target_ratio) > 0.01:
            if src_ratio > target_ratio:
                new_w = int(sh * target_ratio)
                x1 = (sw - new_w) // 2
                sub_cropped = sub.cropped(x1=x1, width=new_w)
            else:
                new_h = int(sw / target_ratio)
                y1 = (sh - new_h) // 2
                sub_cropped = sub.cropped(y1=y1, height=new_h)
            sub_916 = sub_cropped.resized((target_w, target_h))
        else:
            sub_916 = sub.resized((target_w, target_h))

        # Add vertical burned-in subtitles if srt exists
        layers = [sub_916]
        if srt_path and os.path.exists(srt_path):
            segment_subs = _parse_srt_segment(srt_path, start_t, end_t)
            sub_clips = _make_shorts_subtitle_clips(segment_subs, seg_duration)
            layers.extend(sub_clips)

        final_short = CompositeVideoClip(layers, size=(target_w, target_h)).with_duration(seg_duration)

        # Write output video
        final_short.write_videofile(
            out_filepath,
            codec="libx264",
            audio_codec="aac",
            fps=config.FPS,
            preset="ultrafast",
            bitrate="4000k",
            threads=4,
            logger=None,
        )

        # Cleanup handles
        for c in [final_short, sub_916, sub]:
            try:
                c.close()
            except Exception:
                pass

        print(f"✅ Short {idx} successfully created: {out_filepath}")
        extracted_shorts.append(item_meta)

    src_clip.close()
    return extracted_shorts


def main():
    parser = argparse.ArgumentParser(description="YouTube Shorts Extractor CLI.")
    parser.add_argument("--video", type=str, required=True, help="Path to input long-form MP4.")
    parser.add_argument("--srt", type=str, default=None, help="Path to subtitles SRT file.")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for shorts.")
    parser.add_argument("--max", type=int, default=3, help="Max number of shorts to extract.")
    parser.add_argument("--dry-run", action="store_true", help="Identify candidate segments without rendering video.")

    args = parser.parse_args()

    dummy_script = {
        "title": "The Secrets of Ancient Alexandria",
        "scenes": [
            {"duration_sec": 12, "text_overlay": {"text": "The Lost Knowledge"}},
            {"duration_sec": 15, "text_overlay": {"text": "Over 500,000 Scrolls"}},
            {"duration_sec": 15, "text_overlay": {"text": "The Real Destruction"}},
        ],
    }

    results = extract_shorts(
        video_path=args.video,
        script=dummy_script,
        srt_path=args.srt,
        output_dir=args.output_dir,
        max_shorts=args.max,
        dry_run=args.dry_run,
    )

    print("\n--- Extracted Shorts Metadata ---")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
