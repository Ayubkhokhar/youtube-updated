"""Generate default assets (intro, outro, background music)."""
import os
from config import ASSETS_DIR, INTRO_PATH, OUTRO_PATH, MUSIC_DIR, VIDEO_WIDTH, VIDEO_HEIGHT, FPS
from moviepy import ColorClip, TextClip, CompositeVideoClip


def generate_intro():
    if os.path.exists(INTRO_PATH):
        print("Intro already exists")
        return

    print("Generating intro video...")
    bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(15, 20, 35))
    text1 = TextClip(
        text="Your Video",
        font_size=72,
        color="white",
        stroke_color="black",
        stroke_width=3,
        method="label",
    ).with_position("center").with_start(0).with_duration(4)

    text2 = TextClip(
        text="Starts Now",
        font_size=48,
        color="#58a6ff",
        stroke_color="black",
        stroke_width=2,
        method="label",
    ).with_position(("center", VIDEO_HEIGHT // 2 + 60)).with_start(1.5).with_duration(2.5)

    intro = CompositeVideoClip([bg, text1, text2], size=(VIDEO_WIDTH, VIDEO_HEIGHT)).with_duration(4)
    intro.write_videofile(INTRO_PATH, fps=FPS, codec="libx264", audio_codec="aac", preset="ultrafast")
    intro.close()
    print("Intro generated")


def generate_outro():
    if os.path.exists(OUTRO_PATH):
        print("Outro already exists")
        return

    print("Generating outro video...")
    bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(10, 15, 30))
    thanks = TextClip(
        text="Thanks for Watching!",
        font_size=64,
        color="white",
        stroke_color="black",
        stroke_width=3,
        method="label",
    ).with_position(("center", VIDEO_HEIGHT // 2 - 60)).with_start(0).with_duration(5)

    sub = TextClip(
        text="Subscribe for more content",
        font_size=36,
        color="#3fb950",
        stroke_color="black",
        stroke_width=2,
        method="label",
    ).with_position(("center", VIDEO_HEIGHT // 2 + 40)).with_start(1.5).with_duration(3.5)

    outro = CompositeVideoClip([bg, thanks, sub], size=(VIDEO_WIDTH, VIDEO_HEIGHT)).with_duration(5)
    outro.write_videofile(OUTRO_PATH, fps=FPS, codec="libx264", audio_codec="aac", preset="ultrafast")
    outro.close()
    print("Outro generated")


def generate_background_music_placeholder():
    if os.listdir(MUSIC_DIR):
        print("Music files already exist")
        return

    print("Generating background music placeholder...")
    import wave
    import struct
    import math

    path = os.path.join(MUSIC_DIR, "background.wav")
    sample_rate = 44100
    duration = 30
    n_samples = sample_rate * duration

    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            t = i / sample_rate
            value = int(16000 * math.sin(2 * math.pi * 220 * t) * 0.3)
            value += int(16000 * math.sin(2 * math.pi * 330 * t) * 0.15)
            value += int(16000 * math.sin(2 * math.pi * 440 * t) * 0.08)
            value = max(-32768, min(32767, value))
            wf.writeframes(struct.pack("<h", value))

    print("Background music placeholder generated")


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)

    generate_intro()
    generate_outro()
    generate_background_music_placeholder()

    print("\nAssets setup complete!")
    print(f"  Intro: {'Ready' if os.path.exists(INTRO_PATH) else 'Not available'}")
    print(f"  Outro: {'Ready' if os.path.exists(OUTRO_PATH) else 'Not available'}")
    print(f"  Music: {'Ready' if any(os.listdir(MUSIC_DIR)) else 'Not available'}")


if __name__ == "__main__":
    main()
