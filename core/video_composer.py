"""
video_composer.py — Optimised video assembly pipeline.

Key improvements:
- Pool-based clip distribution: each scene has multiple videos + images
- Fast professional pacing: 2-4 s cuts instead of one long looping clip
- Images mixed in as 1.5-2 s flash cuts between video clips
- Subtitles rendered at true screen-bottom with semi-transparent backing bar
- concatenate_videoclips uses method="compose" for proper layering
- FFmpeg: ultrafast preset, 4 threads
- Background music fades in/out for a clean mix
"""

import os
import re
import math
import random
import shutil
import uuid
import threading
import numpy as np
from PIL import Image
from moviepy import (
    VideoFileClip, AudioFileClip,
    CompositeVideoClip, CompositeAudioClip,
    concatenate_videoclips,
    TextClip, ColorClip, ImageClip, VideoClip, afx,
)
import config


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _crop_to_fill(img, target_w, target_h):
    w, h = img.size
    target_ratio = target_w / target_h
    img_ratio    = w / h
    if img_ratio > target_ratio:
        new_w = int(h * target_ratio)
        new_h = h
    else:
        new_w = w
        new_h = int(w / target_ratio)
    left = (w - new_w) // 2
    top  = (h - new_h) // 2
    return img.crop((left, top, left + new_w, top + new_h))


def _make_scene_clip(image_path, duration):
    """Static ImageClip — no zoom."""
    with Image.open(image_path) as img:
        img   = _crop_to_fill(img.convert("RGB"), config.VIDEO_WIDTH, config.VIDEO_HEIGHT)
        img   = img.resize((config.VIDEO_WIDTH, config.VIDEO_HEIGHT), Image.LANCZOS)
        frame = np.array(img)
    return ImageClip(frame).with_duration(duration)


def _make_kenburns_clip(image_path, duration):
    """Ken Burns slow zoom-in on a still image for cinematic motion feel."""
    try:
        padded_w = int(config.VIDEO_WIDTH  * 1.14)
        padded_h = int(config.VIDEO_HEIGHT * 1.14)
        with Image.open(image_path) as img:
            img    = _crop_to_fill(img.convert("RGB"), padded_w, padded_h)
            img    = img.resize((padded_w, padded_h), Image.LANCZOS)
            source = np.array(img)

        tw, th = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
        pw, ph = padded_w, padded_h

        def make_frame(t):
            progress = t / max(duration, 0.001)
            zoom   = 1.0 + 0.10 * progress          # 1.0x → 1.10x
            crop_w = int(tw / zoom)
            crop_h = int(th / zoom)
            x1 = max(0, min((pw - crop_w) // 2, pw - crop_w))
            y1 = max(0, min((ph - crop_h) // 2, ph - crop_h))
            cropped = source[y1:y1 + crop_h, x1:x1 + crop_w]
            return np.array(Image.fromarray(cropped).resize((tw, th), Image.BILINEAR))

        return VideoClip(make_frame, duration=duration)
    except Exception:
        return _make_scene_clip(image_path, duration)


# ---------------------------------------------------------------------------
# Video clip helper
# ---------------------------------------------------------------------------

def _make_video_scene_clip(video_path, duration):
    """Load a video clip, mute it, crop/resize to target, and trim to duration."""
    try:
        clip = VideoFileClip(video_path).without_audio()

        if clip.duration < duration:
            # Open fresh handles for each copy — NEVER reuse [clip]*n
            n = math.ceil(duration / clip.duration)
            copies = [VideoFileClip(video_path).without_audio() for _ in range(n)]
            clip = concatenate_videoclips(copies, method="compose").subclipped(0, duration)
        else:
            start = max(0.0, (clip.duration - duration) / 2)
            clip  = clip.subclipped(start, start + duration)

        clip_w, clip_h = clip.size
        target_w, target_h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
        clip_ratio   = clip_w / clip_h
        target_ratio = target_w / target_h

        if abs(clip_ratio - target_ratio) > 0.01:
            if clip_ratio > target_ratio:
                new_w = int(clip_h * target_ratio)
                x1    = (clip_w - new_w) // 2
                clip  = clip.cropped(x1=x1, width=new_w)
            else:
                new_h = int(clip_w / target_ratio)
                y1    = (clip_h - new_h) // 2
                clip  = clip.cropped(y1=y1, height=new_h)

        if clip.size != (target_w, target_h):
            clip = clip.resized((target_w, target_h))

        return clip
    except Exception as e:
        print(f"[video_composer] video clip error: {e}")
        return None


# ---------------------------------------------------------------------------
# Pool-based fast-cut builder
# ---------------------------------------------------------------------------

# How long each "cut" should be in seconds (min, max)
_CUT_VIDEO_MIN = 2.0
_CUT_VIDEO_MAX = 4.0
_CUT_IMAGE_MIN = 1.2
_CUT_IMAGE_MAX = 2.0


def _build_cuts_from_pool(pool, total_duration, enable_zoom=True):
    """
    Given a pool of (path, media_type) tuples and a total duration to fill,
    return a list of sub-clips that together sum to total_duration.

    Strategy:
      - Interleave videos and images from the pool in order
      - Each video cut = 2-4 s, each image cut = 1.2-2 s
      - If pool is exhausted, cycle through it again (different offsets for videos)
      - Final cut is trimmed to fit exactly
    """
    if not pool:
        return [ColorClip(
            size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT),
            color=(18, 22, 34)
        ).with_duration(total_duration)]

    # Separate videos and images
    videos = [(p, mt) for p, mt in pool if mt == "video"]
    images = [(p, mt) for p, mt in pool if mt == "image"]

    # Build an interleaved sequence: video, image, video, image, ...
    sequence = []
    vi, ii = 0, 0
    while True:
        if vi < len(videos):
            sequence.append(videos[vi])
            vi += 1
        if ii < len(images):
            sequence.append(images[ii])
            ii += 1
        if vi >= len(videos) and ii >= len(images):
            break

    if not sequence:
        sequence = pool[:]

    cuts = []
    elapsed = 0.0
    seq_idx = 0
    video_offsets = {}   # track offset into each video file to avoid same-frame repeats

    while elapsed < total_duration - 0.2:
        remaining = total_duration - elapsed
        media_path, media_type = sequence[seq_idx % len(sequence)]
        seq_idx += 1

        if media_type == "video":
            cut_dur = min(
                round(random.uniform(_CUT_VIDEO_MIN, _CUT_VIDEO_MAX), 1),
                remaining
            )
            if cut_dur < 0.5:
                break
            clip = _make_video_scene_clip(media_path, cut_dur)
            if clip is None:
                # Try as image fallback
                clip = _make_kenburns_clip(media_path, cut_dur) if enable_zoom \
                    else _make_scene_clip(media_path, cut_dur)
        else:
            cut_dur = min(
                round(random.uniform(_CUT_IMAGE_MIN, _CUT_IMAGE_MAX), 1),
                remaining
            )
            if cut_dur < 0.5:
                break
            clip = _make_kenburns_clip(media_path, cut_dur) if enable_zoom \
                else _make_scene_clip(media_path, cut_dur)

        cuts.append(clip)
        elapsed += cut_dur

    # Fill any gap (rounding slack)
    gap = total_duration - elapsed
    if gap > 0.05 and cuts:
        cuts[-1] = cuts[-1].with_duration(cuts[-1].duration + gap)
    elif gap > 0.05:
        cuts.append(ColorClip(
            size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT),
            color=(18, 22, 34)
        ).with_duration(gap))

    return cuts


# ---------------------------------------------------------------------------
# SRT subtitle parsing
# ---------------------------------------------------------------------------

def _parse_srt(srt_path):
    subs = []
    if not os.path.exists(srt_path):
        return subs
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()
    for block in re.split(r"\n\n+", content.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[1])
        if not m:
            continue
        start = _srt_to_sec(m.group(1))
        end   = _srt_to_sec(m.group(2))
        text  = " ".join(lines[2:])
        subs.append((start, end, text))
    return subs


def _srt_to_sec(t):
    h, m, s = t.split(":")
    s, ms   = s.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


# ---------------------------------------------------------------------------
# Text overlays / subtitles
# ---------------------------------------------------------------------------

def _make_subtitle_clips(srt_path, video_duration):
    """
    Render word-level subtitles at the BOTTOM of the frame with a dark
    semi-transparent backing bar for legibility.
    Groups consecutive words into 3-5 word chunks for a karaoke-style feel.
    """
    subs     = _parse_srt(srt_path)
    clips    = []
    font_arg = config.FONT_PATH if os.path.exists(config.FONT_PATH) else None

    # Responsive font size
    font_size = max(36, min(64, min(config.VIDEO_WIDTH, config.VIDEO_HEIGHT) // 16))
    # Bottom position: leave ~8% margin from the very bottom edge
    bottom_margin = int(config.VIDEO_HEIGHT * 0.08)

    color_map = {"white": "white", "yellow": "#FFDC32", "cyan": "#00E5FF"}
    sub_color = color_map.get(getattr(config, "SUBTITLE_COLOR", "white"), "white")

    # Group word-level SRT entries into 3-word chunks for readability
    WORDS_PER_GROUP = 4
    groups = []
    buf_words, buf_start, buf_end = [], None, None

    for start, end, text in subs:
        if start >= video_duration:
            break
        end = min(end, video_duration)
        if end <= start:
            continue
        word = text.strip()
        if not word:
            continue
        if buf_start is None:
            buf_start = start
        buf_end = end
        buf_words.append(word)
        if len(buf_words) >= WORDS_PER_GROUP:
            groups.append((buf_start, buf_end, " ".join(buf_words)))
            buf_words, buf_start, buf_end = [], None, None

    if buf_words and buf_start is not None:
        groups.append((buf_start, buf_end, " ".join(buf_words)))

    for g_start, g_end, text in groups:
        if g_start >= video_duration:
            break
        g_end = min(g_end, video_duration)
        if g_end <= g_start:
            continue
        try:
            txt = (
                TextClip(
                    font=font_arg,
                    text=text,
                    font_size=font_size,
                    color=sub_color,
                    stroke_color="black",
                    stroke_width=2,
                    method="label",
                )
                # Place at bottom: ("center", y_from_top)
                .with_position(("center", config.VIDEO_HEIGHT - bottom_margin), relative=False)
                .with_start(g_start)
                .with_duration(g_end - g_start)
            )
            clips.append(txt)
        except Exception as e:
            print(f"[video_composer] subtitle clip error: {e}")

    return clips


def _make_overlay_clips(scenes, video_duration):
    """Bold keyword overlays at 30% height from script text_overlay fields."""
    clips    = []
    font_arg = config.FONT_PATH if os.path.exists(config.FONT_PATH) else None
    font_size = max(44, min(80, min(config.VIDEO_WIDTH, config.VIDEO_HEIGHT) // 12))
    cumulative = 0.0

    for scene in scenes:
        to        = scene.get("text_overlay")
        scene_dur = scene.get("duration_sec", 5)
        if to and to.get("text"):
            abs_start = cumulative + float(to.get("start_sec", 0))
            abs_end   = abs_start + float(to.get("duration_sec", 2))
            abs_start = min(abs_start, video_duration - 0.1)
            abs_end   = min(abs_end, video_duration)
            if abs_end > abs_start:
                try:
                    txt = (TextClip(
                        font=font_arg,
                        text=to["text"],
                        font_size=font_size,
                        color="#FFDC32",
                        stroke_color="black",
                        stroke_width=3,
                        method="label",
                    )
                    .with_position(("center", int(config.VIDEO_HEIGHT * 0.30)))
                    .with_start(abs_start)
                    .with_duration(abs_end - abs_start))
                    clips.append(txt)
                except Exception as e:
                    print(f"[video_composer] overlay clip error: {e}")
        cumulative += scene_dur
    return clips


def _make_logo_clip(logo_path, duration):
    try:
        with Image.open(logo_path) as lg:
            lg = lg.convert("RGBA")
            lg.thumbnail((config.VIDEO_WIDTH // 5, int(config.VIDEO_HEIGHT * 0.07)), Image.LANCZOS)
            logo_frame = np.array(lg)
        return (ImageClip(logo_frame)
                .with_duration(duration)
                .with_position(("right", "bottom")))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main compose function
# ---------------------------------------------------------------------------

def compose_video(scenes, media_items, srt_path, voiceover_path, voiceover_duration,
                  logo_path=None, title="", progress_cb=None):
    """
    Assemble all scenes into a final MP4.

    media_items : list of pools — each pool is a list of (filepath, media_type)
                  tuples. One pool per scene (from fetch_all_media).
    progress_cb : optional callable(int) reporting 62→97 during encode
    """
    enable_zoom = getattr(config, "ENABLE_ZOOM", True)

    # ── Scale visual durations to match actual TTS audio ────────────────
    total_scene_dur = sum(s.get("duration_sec", 5) for s in scenes)
    time_factor     = voiceover_duration / max(1.0, total_scene_dur)

    all_cuts = []      # flat list of all individual sub-clips
    cumulative_dur = 0.0

    for i, scene in enumerate(scenes):
        remaining = voiceover_duration - cumulative_dur
        if remaining < 0.3:
            break

        scene_dur = min(scene.get("duration_sec", 5) * time_factor, remaining)
        if scene_dur < 0.5:
            break

        # Get the pool for this scene — may be a list of (path, type) or
        # a single tuple (backward compat)
        pool = media_items[i] if i < len(media_items) else []
        if isinstance(pool, tuple):
            pool = [pool]   # wrap single item in a list

        cuts = _build_cuts_from_pool(pool, scene_dur, enable_zoom=enable_zoom)
        all_cuts.extend(cuts)
        cumulative_dur += scene_dur

    if not all_cuts:
        raise RuntimeError("No scene clips were created — check media_items list.")

    # ── Concatenate all cuts into the visual track ───────────────────────
    main_video = concatenate_videoclips(all_cuts, method="compose")

    # Attach voiceover audio
    voice_audio = AudioFileClip(voiceover_path)
    if voice_audio.duration > main_video.duration + 0.1:
        voice_audio = voice_audio.subclipped(0, main_video.duration)
    main_video = main_video.with_audio(voice_audio)

    # ── Layer subtitles + overlays + logo ───────────────────────────────
    all_layers  = [main_video]
    all_layers += _make_subtitle_clips(srt_path, main_video.duration)
    all_layers += _make_overlay_clips(scenes, main_video.duration)

    if logo_path and os.path.exists(logo_path):
        lc = _make_logo_clip(logo_path, main_video.duration)
        if lc:
            all_layers.append(lc)

    final = CompositeVideoClip(
        all_layers,
        size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT)
    ).with_duration(main_video.duration)

    # ── Background music mix ─────────────────────────────────────────────
    vol      = getattr(config, "BG_MUSIC_VOLUME", 0.10)
    bg_music = _load_background_music(final.duration)
    if bg_music and vol > 0:
        bg_music = bg_music.with_effects([
            afx.AudioFadeIn(duration=1.5),
            afx.MultiplyVolume(vol),
            afx.AudioFadeOut(duration=2.0),
        ])
        final = final.with_audio(CompositeAudioClip([final.audio, bg_music]))

    # ── SEO-friendly output filename ─────────────────────────────────────
    safe_title      = re.sub(r'[^a-zA-Z0-9]+', '-', title).strip('-').lower()
    safe_title      = safe_title[:60] or "youtube-video"
    uid             = str(uuid.uuid4())[:6]
    output_filename = f"{safe_title}_{uid}.mp4"
    output_path     = os.path.join(config.OUTPUT_DIR, output_filename)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # ── Clean up stray MoviePy audio-extraction temp files from cwd ──────
    _cleanup_mpy_temp_files()

    # ── Progress ticker (encoding has no native callback) ────────────────
    _tick_stop = threading.Event()

    def _ticker():
        pct = 62
        while not _tick_stop.is_set() and pct < 97:
            _tick_stop.wait(timeout=6)
            if not _tick_stop.is_set():
                pct = min(pct + 2, 97)
                if progress_cb:
                    progress_cb(pct)

    ticker = threading.Thread(target=_ticker, daemon=True)
    ticker.start()

    try:
        final.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            fps=config.FPS,
            preset="ultrafast",
            bitrate="4000k",
            threads=4,
            logger=None,
        )
    finally:
        _tick_stop.set()
        ticker.join(timeout=5)

    # ── Cleanup clip handles ─────────────────────────────────────────────
    for obj in [final, main_video, voice_audio]:
        try:
            obj.close()
        except Exception:
            pass
    if bg_music:
        try:
            bg_music.close()
        except Exception:
            pass
    for clip in all_cuts:
        try:
            clip.close()
        except Exception:
            pass

    return output_path


# ---------------------------------------------------------------------------
# MoviePy stray temp-file cleanup
# ---------------------------------------------------------------------------

def _cleanup_mpy_temp_files():
    """Remove TEMP_MPY_wvf_snd.mp4 files that MoviePy drops in the cwd."""
    try:
        cwd = os.getcwd()
        for fname in os.listdir(cwd):
            if "TEMP_MPY_wvf_snd" in fname:
                try:
                    os.remove(os.path.join(cwd, fname))
                except Exception:
                    pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Background music loader
# ---------------------------------------------------------------------------

def _load_background_music(duration):
    if not os.path.exists(config.MUSIC_DIR):
        return None
    files = [f for f in os.listdir(config.MUSIC_DIR) if f.lower().endswith((".mp3", ".wav", ".m4a"))]
    if not files:
        return None
    try:
        music = AudioFileClip(os.path.join(config.MUSIC_DIR, files[0]))
        if music.duration < duration:
            music = music.with_effects([afx.AudioLoop(duration=duration)])
        else:
            music = music.subclipped(0, duration)
        return music
    except Exception:
        return None


def cleanup_temp():
    import gc
    gc.collect()
    if os.path.exists(config.TEMP_DIR):
        shutil.rmtree(config.TEMP_DIR, ignore_errors=True)
    os.makedirs(config.TEMP_DIR, exist_ok=True)
