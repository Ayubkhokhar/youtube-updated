import os
import json
import uuid
import threading
import time
from flask import Flask, render_template, request, jsonify, Response, send_file, redirect, url_for

import config
from core.script_generator import generate_script
from core.media_searcher import fetch_all_media
from core.tts_engine import generate_voiceover
from core.video_composer import compose_video, cleanup_temp
from core.time_estimator import TimeEstimator

# ── In-memory state ──────────────────────────────────────────────────────────
usage = {
    "groq_requests":    0,
    "pixabay_requests": 0,
    "pexels_requests":  0,
    "videos_generated": 0,
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.path.join(config.TEMP_DIR, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

jobs = {}
_jobs_lock = threading.Lock()
MAX_CONCURRENT_JOBS = 2


def _load_usage():
    try:
        if os.path.exists(config.USER_SETTINGS_PATH):
            s = config.load_user_settings()
            return s.get("usage", usage.copy())
    except Exception:
        pass
    return usage.copy()


def _save_usage():
    try:
        s = config.load_user_settings()
        s["usage"] = usage
        config.save_user_settings(s)
    except Exception:
        pass


usage = _load_usage()


def _log(job_id, message):
    with _jobs_lock:
        if job_id in jobs:
            jobs[job_id]["logs"].append(message)


def _progress(job_id, percent):
    with _jobs_lock:
        if job_id in jobs:
            jobs[job_id]["progress"] = percent


def _set_stage(job_id, stage):
    with _jobs_lock:
        if job_id in jobs:
            jobs[job_id]["stage"] = stage


# ── Core build worker ─────────────────────────────────────────────────────────
def build_video(job_id, topic, logo_path):
    start_time = time.time()
    try:
        config.reload()

        current_settings = config.load_user_settings()
        aspect    = current_settings.get("aspect_ratio", config.DEFAULT_ASPECT)
        target_dur = int(current_settings.get("target_duration", config.DEFAULT_DURATION))
        pref      = current_settings.get("media_preference", "video_first")
        zoom      = bool(current_settings.get("enable_zoom", True))

        # Initial AI Prediction
        if job_id in jobs:
            initial_est = TimeEstimator.predict(aspect, target_dur, pref, zoom)
            jobs[job_id]["predicted_time"] = initial_est
            jobs[job_id]["start_time"]     = start_time
            jobs[job_id]["ai_status"]      = "Initial Estimate"

        # ── 1. Generate script ────────────────────────────────────────────
        _set_stage(job_id, "script")
        _log(job_id, "📝 Generating AI script...")
        _progress(job_id, 5)

        script = generate_script(topic)
        usage["groq_requests"] += 1
        scene_count = len(script["scenes"])
        total_words = sum(len(s.get("narration", "").split()) for s in script["scenes"])
        _log(job_id, f"✅ Script: \"{script['title']}\" — {scene_count} scenes, ~{total_words} words")
        _progress(job_id, 12)

        if job_id in jobs:
            refined_est = TimeEstimator.predict(aspect, target_dur, pref, zoom, scene_count=scene_count)
            jobs[job_id]["predicted_time"] = refined_est
            jobs[job_id]["ai_status"]      = "Refined by Script"
            jobs[job_id]["video_title"]    = script.get("title", "")

        # ── 2. Fetch media (parallel) ─────────────────────────────────────
        _set_stage(job_id, "media")
        _log(job_id, f"🎬 Fetching media for {scene_count} scenes in parallel...")
        _progress(job_id, 14)

        media_items = fetch_all_media(
            scenes=script["scenes"],
            topic=topic,
            log_cb=lambda msg: _log(job_id, msg),
            progress_cb=lambda pct: _progress(job_id, pct),
            progress_start=14,
            progress_end=42,
        )

        video_count = sum(sum(1 for _, mt in pool if mt == "video") for pool in media_items)
        image_count = sum(sum(1 for _, mt in pool if mt == "image") for pool in media_items)
        usage["pixabay_requests"] += scene_count
        _log(job_id, f"✅ Media ready — {video_count} clips, {image_count} images across {scene_count} scenes")
        _progress(job_id, 42)

        if job_id in jobs:
            final_est = TimeEstimator.predict(aspect, target_dur, pref, zoom,
                                               scene_count=scene_count, video_clip_count=video_count)
            jobs[job_id]["predicted_time"] = final_est
            jobs[job_id]["ai_status"]      = "Final Precision Estimate"

        # ── 3. Generate voiceover ─────────────────────────────────────────
        _set_stage(job_id, "voice")
        _log(job_id, "🎙️ Generating voiceover with neural TTS...")
        _progress(job_id, 44)

        audio_path, srt_path, timings, actual_duration = generate_voiceover(script["scenes"])
        _log(job_id, f"✅ Voiceover ready — {actual_duration:.1f}s of audio")
        _progress(job_id, 56)

        # ── 4. Compose video ──────────────────────────────────────────────
        _set_stage(job_id, "render")
        _log(job_id, "🎞️ Composing and encoding video (the slow step)...")
        _progress(job_id, 60)

        output_path = compose_video(
            scenes=script["scenes"],
            media_items=media_items,
            srt_path=srt_path,
            voiceover_path=audio_path,
            voiceover_duration=actual_duration,
            logo_path=logo_path,
            title=script.get("title", ""),
            progress_cb=lambda p: _progress(job_id, p),
        )

        usage["videos_generated"] += 1
        _save_usage()
        _progress(job_id, 100)

        total_time = time.time() - start_time
        mins, secs = divmod(int(total_time), 60)
        _log(job_id, f"🎉 Done! Video ready — generated in {mins}m {secs}s")

        _set_stage(job_id, "done")
        with _jobs_lock:
            jobs[job_id]["output"] = os.path.basename(output_path)
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["title"]  = script.get("title", "")
            jobs[job_id]["duration_sec"] = round(actual_duration, 1)

        TimeEstimator.add_run(aspect, target_dur, pref, zoom,
                               scene_count, video_count, total_time)

        # Auto-cleanup job after 20 minutes
        threading.Timer(1200, lambda: jobs.pop(job_id, None)).start()

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        _log(job_id, f"❌ Error: {str(e)}")
        print(tb)
        try:
            with open(os.path.join(config.TEMP_DIR, "error_debug.log"), "w") as f:
                f.write(tb)
        except Exception:
            pass
        with _jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"]  = str(e)
            jobs[job_id]["stage"]  = "error"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    config_status = {
        "groq":    bool(config.GROQ_API_KEY),
        "pixabay": bool(config.PIXABAY_API_KEY),
        "pexels":  bool(config.PEXELS_API_KEY),
    }
    return render_template("index.html", config=config_status)


@app.route("/generate", methods=["POST"])
def generate():
    topic = request.form.get("topic", "").strip()
    if not topic:
        return jsonify({"error": "Topic is required"}), 400

    config.reload()
    if not config.GROQ_API_KEY:
        return jsonify({"error": "GROQ_API_KEY not configured. Go to Settings."}), 400
    if not config.PIXABAY_API_KEY:
        return jsonify({"error": "PIXABAY_API_KEY not configured. Go to Settings."}), 400

    # Concurrent job guard
    with _jobs_lock:
        running = sum(1 for j in jobs.values() if j["status"] == "running")
    if running >= MAX_CONCURRENT_JOBS:
        return jsonify({"error": f"Server busy ({running} videos generating). Please wait."}), 429

    logo      = request.files.get("logo")
    logo_path = None
    if logo and logo.filename:
        ext       = logo.filename.rsplit(".", 1)[-1].lower() if "." in logo.filename else "png"
        logo_path = os.path.join(app.config["UPLOAD_FOLDER"], f"logo_{uuid.uuid4().hex}.{ext}")
        logo.save(logo_path)

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        jobs[job_id] = {
            "status":       "running",
            "stage":        "init",
            "progress":     0,
            "logs":         [],
            "output":       None,
            "error":        None,
            "title":        "",
            "video_title":  "",
            "start_time":   time.time(),
            "predicted_time": 0,
            "ai_status":    "Initializing",
            "duration_sec": 0,
        }

    t = threading.Thread(target=build_video, args=(job_id, topic, logo_path))
    t.daemon = True
    t.start()

    return redirect(url_for("result_page", job_id=job_id))


@app.route("/result/<job_id>")
def result_page(job_id):
    if job_id not in jobs:
        return redirect(url_for("index"))
    return render_template("result.html", job_id=job_id)


@app.route("/progress/<job_id>")
def stream_progress(job_id):
    def generate_events():
        last_log_count = 0
        while True:
            if job_id not in jobs:
                yield f"data: {json.dumps({'status': 'error', 'error': 'Job not found'})}\n\n"
                break
            with _jobs_lock:
                job = dict(jobs[job_id])
            new_logs       = job["logs"][last_log_count:]
            last_log_count = len(job["logs"])
            data = {
                "status":         job["status"],
                "stage":          job.get("stage", ""),
                "progress":       job["progress"],
                "logs":           new_logs,
                "output":         job["output"],
                "error":          job.get("error"),
                "title":          job.get("title", ""),
                "video_title":    job.get("video_title", ""),
                "predicted_time": job.get("predicted_time", 0),
                "elapsed_time":   int(time.time() - job.get("start_time", time.time())),
                "ai_status":      job.get("ai_status", ""),
                "duration_sec":   job.get("duration_sec", 0),
            }
            yield f"data: {json.dumps(data)}\n\n"
            if job["status"] in ("completed", "error"):
                break
            time.sleep(0.5)
    return Response(generate_events(), mimetype="text/event-stream")


@app.route("/download/<filename>")
def download(filename):
    filepath = os.path.join(config.OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    return send_file(filepath, as_attachment=True, mimetype="video/mp4")


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        current = config.load_user_settings()
        aspect  = current.get("aspect_ratio", config.DEFAULT_ASPECT)
        preset  = config.ASPECT_PRESETS.get(aspect, config.ASPECT_PRESETS[config.DEFAULT_ASPECT])
        return jsonify({
            "groq_api_key":      _mask_key(current.get("groq_api_key", "") or os.getenv("GROQ_API_KEY", "")),
            "pixabay_api_key":   _mask_key(current.get("pixabay_api_key", "") or os.getenv("PIXABAY_API_KEY", "")),
            "pexels_api_key":    _mask_key(current.get("pexels_api_key", "") or os.getenv("PEXELS_API_KEY", "")),
            "groq_connected":    bool(config.GROQ_API_KEY),
            "pixabay_connected": bool(config.PIXABAY_API_KEY),
            "pexels_connected":  bool(config.PEXELS_API_KEY),
            "aspect_ratio":      aspect,
            "target_duration":   int(current.get("target_duration", config.DEFAULT_DURATION)),
            "width":             preset["width"],
            "height":            preset["height"],
            "media_preference":  current.get("media_preference", "video_first"),
            "enable_zoom":       bool(current.get("enable_zoom", True)),
            "voice_name":        current.get("voice_name", "en-US-JennyNeural"),
            "bg_music_volume":   float(current.get("bg_music_volume", 0.10)),
            "subtitle_color":    current.get("subtitle_color", "white"),
        })

    data    = request.get_json() or {}
    current = config.load_user_settings()

    for key in ("groq_api_key", "pixabay_api_key", "pexels_api_key"):
        if data.get(key):
            current[key] = data[key]

    if data.get("aspect_ratio") in config.ASPECT_PRESETS:
        current["aspect_ratio"] = data["aspect_ratio"]
    if data.get("target_duration"):
        current["target_duration"] = max(20, min(600, int(data["target_duration"])))

    if data.get("media_preference") in config.VALID_MEDIA_PREFS:
        current["media_preference"] = data["media_preference"]
    if "enable_zoom" in data:
        current["enable_zoom"] = bool(data["enable_zoom"])
    if data.get("voice_name") in config.VALID_VOICES:
        current["voice_name"] = data["voice_name"]
    if "bg_music_volume" in data:
        current["bg_music_volume"] = max(0.0, min(0.5, float(data["bg_music_volume"])))
    if data.get("subtitle_color") in config.VALID_SUBTITLE_COLORS:
        current["subtitle_color"] = data["subtitle_color"]

    config.save_user_settings(current)
    config.reload()
    return jsonify({"ok": True, "message": "Settings saved."})


@app.route("/api/usage")
def api_usage():
    return jsonify(usage)


@app.route("/api/history")
def api_history():
    from core.time_estimator import TimeEstimator
    history = TimeEstimator.load_history()
    # Return the last 10 runs, newest first
    return jsonify(list(reversed(history[-10:])))


def _get_dir_size_mb(path):
    total = 0
    if os.path.exists(path):
        for dp, _, fns in os.walk(path):
            for f in fns:
                fp = os.path.join(dp, f)
                if not os.path.islink(fp):
                    total += os.path.getsize(fp)
    return total / (1024 * 1024)


@app.route("/api/disk_usage")
def api_disk_usage():
    return jsonify({
        "temp_mb":   round(_get_dir_size_mb(config.TEMP_DIR), 2),
        "output_mb": round(_get_dir_size_mb(config.OUTPUT_DIR), 2),
    })


@app.route("/api/clear_cache", methods=["POST"])
def api_clear_cache():
    data       = request.get_json() or {}
    clear_type = data.get("type")

    if clear_type == "temp":
        cleanup_temp()
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        return jsonify({"ok": True, "message": "Temporary cache cleared."})

    if clear_type == "output":
        if os.path.exists(config.OUTPUT_DIR):
            for fn in os.listdir(config.OUTPUT_DIR):
                if fn.endswith(".mp4"):
                    try:
                        os.remove(os.path.join(config.OUTPUT_DIR, fn))
                    except Exception:
                        pass
        return jsonify({"ok": True, "message": "Generated videos cleared."})

    return jsonify({"error": "Invalid clear type"}), 400


@app.route("/api/version")
def api_version():
    return jsonify({"version": config.APP_VERSION})


def _mask_key(key):
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "..." + key[-2:] if len(key) > 4 else key
    return key[:4] + "..." + key[-4:]


if __name__ == "__main__":
    print("=" * 60)
    print(f"  YouTube Automation Tool — v{config.APP_VERSION}")
    print("=" * 60)
    if not config.GROQ_API_KEY:
        print("  [WARNING] GROQ_API_KEY not set — go to /settings")
    if not config.PIXABAY_API_KEY:
        print("  [WARNING] PIXABAY_API_KEY not set — go to /settings")
    print()
    print("  Open: http://localhost:5000")
    print()
    app.run(debug=False, threaded=True, host="0.0.0.0", port=5000)
