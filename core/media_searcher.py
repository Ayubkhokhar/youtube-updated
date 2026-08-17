"""
media_searcher.py — Parallel media downloading with a rich clip pool.

Strategy:
  - For every scene, fetch up to 3 video clips AND up to 3 images in parallel
  - All downloads go into a shared "media pool"
  - The video composer then slices the pool into fast 2-4 s cuts for each scene
    instead of looping the same clip over and over
"""
import os
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont
import config

PIXABAY_URL       = "https://pixabay.com/api/"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
PEXELS_URL        = "https://api.pexels.com/v1/search"
PEXELS_VIDEO_URL  = "https://api.pexels.com/videos/search"

# Thread-safe lock for file system writes
_fs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Orientation helpers
# ---------------------------------------------------------------------------

def _api_orientation():
    """Return (pixabay_orient, pexels_orient) strings based on current config."""
    if config.VIDEO_WIDTH > config.VIDEO_HEIGHT:
        return "horizontal", "landscape"
    elif config.VIDEO_WIDTH < config.VIDEO_HEIGHT:
        return "vertical", "portrait"
    else:
        return "horizontal", "square"


# ---------------------------------------------------------------------------
# Video search
# ---------------------------------------------------------------------------

def search_videos_pixabay(query, per_page=5):
    if not config.PIXABAY_API_KEY:
        return []
    pix_orient, _ = _api_orientation()
    params = {
        "key":         config.PIXABAY_API_KEY,
        "q":           query,
        "video_type":  "film",
        "orientation": pix_orient,
        "per_page":    per_page,
        "safesearch":  "true",
    }
    try:
        resp = requests.get(PIXABAY_VIDEO_URL, params=params, timeout=15)
        if resp.status_code == 200:
            urls = []
            target_w = config.VIDEO_WIDTH
            for hit in resp.json().get("hits", []):
                videos = hit.get("videos", {})
                available = []
                for quality in ("medium", "small", "large", "tiny"):
                    v = videos.get(quality)
                    if v and v.get("url"):
                        width = v.get("width") or (
                            1920 if quality == "large"  else
                            1280 if quality == "medium" else
                            960  if quality == "small"  else 640)
                        available.append((width, v["url"]))
                if available:
                    available.sort(key=lambda x: abs(x[0] - target_w))
                    urls.append(available[0][1])
            return urls
    except Exception:
        pass
    return []


def search_videos_pexels(query, per_page=5):
    if not config.PEXELS_API_KEY:
        return []
    _, pex_orient = _api_orientation()
    headers = {"Authorization": config.PEXELS_API_KEY}
    params  = {"query": query, "per_page": per_page, "orientation": pex_orient, "size": "medium"}
    try:
        resp = requests.get(PEXELS_VIDEO_URL, headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            urls = []
            target_w = config.VIDEO_WIDTH
            for vid in resp.json().get("videos", []):
                files = vid.get("video_files", [])
                if files:
                    files_sorted = sorted(files, key=lambda f: abs(f.get("width", 0) - target_w))
                    for f in files_sorted:
                        if f.get("link"):
                            urls.append(f["link"])
                            break
            return urls
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Image search
# ---------------------------------------------------------------------------

def search_images_pixabay(query, per_page=5):
    if not config.PIXABAY_API_KEY:
        return []
    pix_orient, _ = _api_orientation()
    params = {
        "key":         config.PIXABAY_API_KEY,
        "q":           query,
        "image_type":  "photo",
        "orientation": pix_orient,
        "per_page":    per_page,
        "safesearch":  "true",
        "min_width":   1280,
        "min_height":  720,
    }
    try:
        resp = requests.get(PIXABAY_URL, params=params, timeout=15)
        if resp.status_code == 200:
            return [hit["largeImageURL"] for hit in resp.json().get("hits", [])]
    except Exception:
        pass
    return []


def search_images_pexels(query, per_page=5):
    if not config.PEXELS_API_KEY:
        return []
    headers = {"Authorization": config.PEXELS_API_KEY}
    params  = {"query": query, "per_page": per_page, "size": "large"}
    try:
        resp = requests.get(PEXELS_URL, headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            return [photo["src"]["large2x"] for photo in resp.json().get("photos", [])]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download_file(url, filepath, timeout=30):
    try:
        resp = requests.get(url, timeout=timeout, stream=True)
        if resp.status_code == 200:
            with _fs_lock:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            return True
    except Exception:
        pass
    return False


def download_video(url, scene_index, slot=0):
    filepath = os.path.join(config.TEMP_DIR, f"scene_{scene_index:02d}_vid_{slot}.mp4")
    if _download_file(url, filepath, timeout=60):
        if os.path.exists(filepath) and os.path.getsize(filepath) > 50_000:
            return filepath
    return None


def download_image(url, scene_index, slot=0):
    ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    filepath = os.path.join(config.TEMP_DIR, f"scene_{scene_index:02d}_img_{slot}.{ext}")
    if _download_file(url, filepath, timeout=20):
        return filepath
    return None


# ---------------------------------------------------------------------------
# Fallback image generator
# ---------------------------------------------------------------------------

def generate_fallback_image(scene_index, text):
    width, height = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    filepath = os.path.join(config.TEMP_DIR, f"scene_{scene_index:02d}_fallback.jpg")

    from PIL import Image as _Img
    img  = _Img.new("RGB", (width, height), (18, 22, 34))
    draw = ImageDraw.Draw(img)

    font = None
    if os.path.exists(config.FONT_PATH):
        try:
            font = ImageFont.truetype(config.FONT_PATH, max(48, width // 30))
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()

    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > width - 120:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    lines = lines[:5]

    total_h = len(lines) * 72
    y = (height - total_h) // 2
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x + 2, y + 2), ln, fill=(0, 0, 0), font=font)
        draw.text((x, y), ln, fill=(220, 230, 250), font=font)
        y += 72

    draw.rectangle([0, height - 70, width, height], fill=(30, 40, 65))
    draw.text((40, height - 50), "AI Video Generator",
              fill=(88, 166, 255), font=ImageFont.load_default())

    img.save(filepath, quality=90)
    return filepath, "image"


# ---------------------------------------------------------------------------
# Per-scene pool fetcher — downloads MULTIPLE clips + images for each scene
# ---------------------------------------------------------------------------

def fetch_media_pool_for_scene(scene_index, keywords, scene_text, max_videos=3, max_images=3):
    """
    Returns a list of (filepath, media_type) tuples — a rich pool of media
    for this scene. Videos come first, then images.
    Never returns an empty list (falls back to a generated image).
    """
    pref = getattr(config, "MEDIA_PREFERENCE", "video_first")
    pool = []

    # ── Fetch videos ──────────────────────────────────────────────────────
    if pref in ("video_first", "video_only"):
        video_urls = []
        video_urls += search_videos_pixabay(keywords, per_page=max_videos + 1)
        video_urls += search_videos_pexels(keywords, per_page=max_videos + 1)
        # Deduplicate by URL
        seen = set()
        for url in video_urls:
            if url not in seen and len(pool) < max_videos:
                seen.add(url)
                path = download_video(url, scene_index, slot=len(pool))
                if path:
                    pool.append((path, "video"))

    # ── Fetch images (always, unless video_only) ──────────────────────────
    if pref in ("video_first", "image_only"):
        img_urls = []
        img_urls += search_images_pixabay(keywords, per_page=max_images + 1)
        img_urls += search_images_pexels(keywords, per_page=max_images + 1)
        seen_img = set()
        img_count = 0
        for url in img_urls:
            if url not in seen_img and img_count < max_images:
                seen_img.add(url)
                path = download_image(url, scene_index, slot=20 + img_count)
                if path:
                    pool.append((path, "image"))
                    img_count += 1

    if not pool:
        pool.append(generate_fallback_image(scene_index, scene_text))

    return pool


# ---------------------------------------------------------------------------
# Parallel all-scenes fetcher — returns list of pools, one per scene
# ---------------------------------------------------------------------------

def fetch_all_media(scenes, topic, log_cb=None, progress_cb=None, progress_start=12, progress_end=40):
    """
    Download a rich media pool for every scene in parallel.

    Returns: list of pools, where each pool is a list of (filepath, media_type)
             tuples. The video composer picks from the pool for fast cuts.
    """
    scene_count = len(scenes)
    results     = [None] * scene_count
    used_kw     = set()
    kw_lock     = threading.Lock()

    def _fetch_one(idx):
        scene = scenes[idx]
        kw    = scene.get("keywords", topic) or topic
        text  = scene.get("narration", "")

        with kw_lock:
            if kw in used_kw:
                kw = f"{kw} {topic}"
            used_kw.add(kw)

        pool = fetch_media_pool_for_scene(idx, kw, text)
        if log_cb:
            vids = sum(1 for _, mt in pool if mt == "video")
            imgs = sum(1 for _, mt in pool if mt == "image")
            log_cb(f"🎬 Scene {idx + 1}/{scene_count}: {vids} clips, {imgs} images ({kw[:30]})")
        return idx, pool

    max_workers = min(8, scene_count)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, i): i for i in range(scene_count)}
        done_count = 0
        for future in as_completed(futures):
            try:
                idx, pool = future.result()
                results[idx] = pool
            except Exception as e:
                idx = futures[future]
                results[idx] = [generate_fallback_image(idx, scenes[idx].get("narration", ""))]
                if log_cb:
                    log_cb(f"⚠️ Scene {idx + 1} media failed, using fallback: {e}")
            done_count += 1
            if progress_cb:
                pct = progress_start + int((progress_end - progress_start) * done_count / scene_count)
                progress_cb(pct)

    for i, r in enumerate(results):
        if r is None:
            results[i] = [generate_fallback_image(i, scenes[i].get("narration", ""))]

    # Summarise for log
    total_videos = sum(sum(1 for _, mt in pool if mt == "video") for pool in results)
    total_images = sum(sum(1 for _, mt in pool if mt == "image") for pool in results)
    if log_cb:
        log_cb(f"✅ Media pool ready — {total_videos} video clips, {total_images} images across {scene_count} scenes")

    return results
