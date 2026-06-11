"""Sidecar HTTP API. The UXP panel talks to this over localhost.

POST /analyze: per-camera media paths in, cut map out. Synchronous for now;
job queue + WebSocket progress come with real-length footage in M1.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from cutengine.engine import build_cut_map
from dsp.extract import extract_mono
from dsp.vad import HOP_S, rms_per_hop

app = FastAPI(title="vibe-splice sidecar", version="0.1.0")


class AnalyzeRequest(BaseModel):
    # One audio source per camera, index-aligned: camera N = audio_paths[N-1].
    audio_paths: list[str]
    fps_numerator: int
    fps_denominator: int
    total_frames: int
    min_shot_s: float = 1.5


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": app.version}


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    if len(req.audio_paths) < 2:
        raise HTTPException(400, "need at least 2 camera audio sources")
    try:
        channel_rms = [rms_per_hop(extract_mono(p), 16000, HOP_S) for p in req.audio_paths]
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
