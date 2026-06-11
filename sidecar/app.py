"""Sidecar HTTP API. The UXP panel talks to this over localhost.

POST /analyze: per-camera media paths in, cut map out. Synchronous for now;
job queue + WebSocket progress come with real-length footage in M1.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from cutengine.engine import build_cut_map
from dsp.extract import extract_mono
from dsp.vad import HOP_S, align_to_timeline, rms_per_hop

app = FastAPI(title="vibe-splice sidecar", version="0.1.0")


class AnalyzeRequest(BaseModel):
    # One audio source per camera, index-aligned: camera N = audio_paths[N-1].
    # Audio may be camera-embedded or separately recorded — any FFmpeg-decodable
    # file. offset_frames[N] is where that file's t=0 sits on the timeline
    # (positive: audio starts after timeline frame 0; negative: audio started
    # rolling before the cameras). Defaults to all-zero (already aligned).
    audio_paths: list[str]
    fps_numerator: int
    fps_denominator: int
    total_frames: int
    min_shot_s: float = 1.5
    offset_frames: list[int] | None = None


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": app.version}


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    if len(req.audio_paths) < 2:
        raise HTTPException(400, "need at least 2 camera audio sources")
    offsets = req.offset_frames or [0] * len(req.audio_paths)
    if len(offsets) != len(req.audio_paths):
        raise HTTPException(400, "offset_frames must match audio_paths length")
    try:
        channel_rms = [
            align_to_timeline(
                rms_per_hop(extract_mono(p), 16000, HOP_S),
                off, req.fps_numerator, req.fps_denominator,
            )
            for p, off in zip(req.audio_paths, offsets)
        ]
    except RuntimeError as e:
        raise HTTPException(422, str(e)) from e
    cut_map = build_cut_map(
        channel_rms,
        req.fps_numerator,
        req.fps_denominator,
        req.total_frames,
        req.min_shot_s,
    )
    return cut_map.to_dict()
