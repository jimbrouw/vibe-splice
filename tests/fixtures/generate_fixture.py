#!/usr/bin/env python3
"""Stand-in 3-camera podcast fixture for the M0 timeline-write spike.

Each "camera" is a 10-minute 720p clip at exactly 30000/1001 fps (NTSC
29.97 — the harshest rate for float-seconds drift) with a burned-in frame
counter, camera label, and timecode. The visible frame number is the ground
truth for drift measurement: after applying a cut map in Premiere, the frame
number visible at each cut must match the cut map exactly.

A white flash is burned into all angles at every 30 s boundary, aligned to a
2 kHz beep in the audio bed, so audio-to-video sync is checkable by eye/ear
anywhere in the timeline.

Frames are rendered with OpenCV and piped to FFmpeg as rawvideo because the
installed FFmpeg builds lack the drawtext filter (no freetype). Piping with
-r 30000/1001 keeps the stream timebase exact.

Replace with real 3-cam footage when available (expected week of 2026-06-15).
Keep the same filenames so the spike panel needs no changes.
"""

import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

FFMPEG = "/opt/homebrew/bin/ffmpeg"
W, H = 1280, 720
FPS_NUM, FPS_DEN = 30000, 1001
DURATION_S = 600
TOTAL_FRAMES = round(DURATION_S * FPS_NUM / FPS_DEN)  # 17982

CAMS = [
    ("cam1", (51, 51, 128)),   # BGR: dark red
    ("cam2", (51, 102, 51)),   # dark green
    ("cam3", (128, 51, 51)),   # dark blue
]

FONT = cv2.FONT_HERSHEY_SIMPLEX


def frame_to_timecode(frame: int) -> str:
    total_ms = frame * FPS_DEN * 1000 // FPS_NUM
    s, ms = divmod(total_ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def put_centered(img, text, y, scale, color, thickness):
    (tw, _), _ = cv2.getTextSize(text, FONT, scale, thickness)
    cv2.putText(img, text, ((W - tw) // 2, y), FONT, scale, color, thickness, cv2.LINE_AA)


def generate_cam(name: str, bgr: tuple, out: Path):
    proc = subprocess.Popen(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
         "-r", f"{FPS_NUM}/{FPS_DEN}", "-i", "-",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
         "-pix_fmt", "yuv420p", str(out)],
        stdin=subprocess.PIPE,
    )
    base = np.full((H, W, 3), bgr, dtype=np.uint8)
    put_centered(base, name.upper(), 140, 4.0, (255, 255, 255), 8)

    flash_frames = set()
    for t in range(0, DURATION_S, 30):
        f0 = round(t * FPS_NUM / FPS_DEN)
        flash_frames.update(range(f0, min(f0 + 3, TOTAL_FRAMES)))  # 3-frame flash

    for f in range(TOTAL_FRAMES):
        if f in flash_frames:
            img = np.full((H, W, 3), 255, dtype=np.uint8)
            put_centered(img, f"FRAME {f}", H // 2 + 30, 3.0, (0, 0, 0), 6)
        else:
            img = base.copy()
            put_centered(img, f"FRAME {f}", H // 2 + 30, 3.0, (0, 255, 255), 6)
            put_centered(img, frame_to_timecode(f), H - 80, 1.5, (255, 255, 255), 3)
        proc.stdin.write(img.tobytes())
        if f % 3000 == 0:
            print(f"  {name}: {f}/{TOTAL_FRAMES}", flush=True)
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        sys.exit(f"ffmpeg failed for {name}")


def generate_audio(out: Path):
    # 440 Hz bed with a 100 ms 2 kHz beep at every 30 s boundary, matching the flash.
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={DURATION_S}",
         "-f", "lavfi", "-i", f"sine=frequency=2000:duration={DURATION_S}",
         "-filter_complex",
         "[0:a]volume=0.15[bed];"
         "[1:a]volume='if(lt(mod(t,30),0.1),1,0)':eval=frame[beep];"
         "[bed][beep]amix=inputs=2:duration=first",
         "-c:a", "pcm_s16le", str(out)],
        check=True,
    )


def main():
    here = Path(__file__).parent
    for name, bgr in CAMS:
        out = here / f"{name}.mp4"
        if out.exists():
            print(f"{out.name} exists, skipping")
            continue
        print(f"Generating {out.name} ...")
        generate_cam(name, bgr, out)
    audio = here / "audio_bed.wav"
    if not audio.exists():
        print("Generating audio_bed.wav ...")
        generate_audio(audio)
    print("Done.")


if __name__ == "__main__":
    main()
