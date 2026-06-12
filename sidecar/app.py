"""Sidecar HTTP API. The UXP panel talks to this over localhost.

POST /analyze: per-camera media paths in, cut map out. Synchronous for now;
job queue + WebSocket progress come with real-length footage in M1.
"""

import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from cutengine.engine import build_cut_map
from director.gateway import suggest
from director.merge import apply_suggestions
from director.segments import TranscriptLine, build_segments, synthetic_transcript
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


# --- Director tier (BYOT) ----------------------------------------------------
# The LLM sees transcript text + segment ids only (hard rule 5). It returns
# decisions keyed to segment_id; we map them to frames. /director produces
# suggestions for the panel's review list; /director/merge applies the
# accepted ones deterministically and returns a fresh, validated cut map.

class DirectorRequest(BaseModel):
    cuts: list[dict]
    total_frames: int
    fps_numerator: int
    fps_denominator: int
    n_cameras: int
    provider: str                       # anthropic | openai | gemini | mock
    api_key: str = ""                   # held in memory only, never logged
    model: str = ""                     # blank = provider default
    # Transcript source. "synthetic" reads a speech-schedule JSON (fixtures);
    # "whisper" (real footage) is not implemented yet and returns 501.
    transcript_source: str = "synthetic"
    schedule_path: str = ""
    transcript: list[dict] | None = None  # or supply lines directly


class MergeRequest(BaseModel):
    cuts: list[dict]
    total_frames: int
    fps_numerator: int
    fps_denominator: int
    accepted: list[dict]
    reaction_s: float = 2.0
    min_shot_s: float = 1.5


def _load_transcript(req: DirectorRequest) -> list[TranscriptLine]:
    if req.transcript:
        return [TranscriptLine(**ln) for ln in req.transcript]
    if req.transcript_source == "synthetic":
        if not req.schedule_path:
            raise HTTPException(400, "synthetic transcript needs schedule_path")
        try:
            with open(req.schedule_path) as f:
                return synthetic_transcript(json.load(f))
        except (OSError, json.JSONDecodeError, KeyError) as e:
            raise HTTPException(422, f"bad schedule file: {e}") from e
    if req.transcript_source == "whisper":
        raise HTTPException(501, "whisper ASR lands with real footage")
    raise HTTPException(400, f"unknown transcript_source {req.transcript_source!r}")


@app.post("/director")
def director(req: DirectorRequest) -> dict:
    transcript = _load_transcript(req)
    segments = build_segments(
        req.cuts, req.total_frames,
        req.fps_numerator, req.fps_denominator, transcript,
    )
    try:
        return suggest(segments, req.n_cameras, req.provider,
                       req.api_key, req.model)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # provider/HTTP errors -> readable panel message
        raise HTTPException(502, f"provider call failed: {e}") from e


@app.post("/director/merge")
def director_merge(req: MergeRequest) -> dict:
    try:
        cut_map, skipped = apply_suggestions(
            req.cuts, req.total_frames,
            req.fps_numerator, req.fps_denominator,
            req.accepted, req.reaction_s, req.min_shot_s,
        )
    except ValueError as e:
        raise HTTPException(422, f"merge produced invalid cut map: {e}") from e
    out = cut_map.to_dict()
    out["skipped"] = skipped
    return out
