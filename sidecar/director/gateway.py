"""BYOT Director gateway: segments in, validated suggestions out.

Providers: anthropic / openai / gemini (BYO API key, called over HTTPS with
httpx) and mock (deterministic, for tests and offline demo). The wire format
to every provider is the same prompt; the response must be a JSON array of
decisions keyed to segment_id. Anything else is dropped, never guessed at.

Hard rule 5: only transcript TEXT leaves the machine. No paths, no media.

LLM output is probabilistic (model, audio quality, accent all move it) — this
layer validates shape, but whether a suggestion is GOOD is the user's call in
the panel's review list. [Inference] expect provider-to-provider variance.
"""

import json
import re

import httpx

from .segments import Segment

DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
}

_SYSTEM = """You are an experienced multi-camera podcast editor reviewing an \
automated cut. Camera N shows speaker N full-time. You receive segments of \
the current cut: which camera is shown, who actually speaks, and what they say.

Suggest ONLY high-confidence improvements of two kinds:
1. "switch" — the shown camera is wrong or weak for a segment (e.g. brief \
interjection won the cut but the main speaker should hold; or a question is \
better held on the asker).
2. "reaction" — during a long single-speaker segment (over ~8s), briefly \
showing a listener adds life. Suggest the listener's camera; the editor \
decides placement.

Respond with a JSON array ONLY, no prose. Each item:
{"segment_id": "...", "action": "switch" | "reaction", "camera": <int>, \
"reason": "<one short sentence>"}
Suggest nothing if the cut is already right — an empty array is a good answer."""


def _segments_payload(segments: list[Segment]) -> str:
    rows = []
    for s in segments:
        rows.append({
            "segment_id": s.segment_id,
            "shown_camera": s.camera,
            "duration_s": s.duration_s,
            "speech": [
                {"speaker": ln.speaker, "text": ln.text} for ln in s.lines
            ],
        })
    return json.dumps(rows, ensure_ascii=False)


def _user_prompt(segments: list[Segment], n_cameras: int) -> str:
    return (
        f"{n_cameras} cameras, camera N = speaker N.\n"
        f"Current cut, in order:\n{_segments_payload(segments)}"
    )


# --- providers ---------------------------------------------------------------

def _call_anthropic(prompt: str, api_key: str, model: str) -> str:
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 2048,
            "system": _SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def _call_openai(prompt: str, api_key: str, model: str) -> str:
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_gemini(prompt: str, api_key: str, model: str) -> str:
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": api_key},
        json={
            "system_instruction": {"parts": [{"text": _SYSTEM}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0},
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_mock(prompt: str, api_key: str, model: str) -> str:
    """Deterministic offline provider. Reads the segments back out of the
    prompt and suggests: a reaction shot on the longest segment >8s, and a
    switch on the first crosstalk segment (2+ speakers) if any."""
    payload = json.loads(prompt[prompt.index("["):])
    out = []
    longest = max(payload, key=lambda s: s["duration_s"], default=None)
    if longest and longest["duration_s"] > 8 and longest["speech"]:
        speaker = longest["speech"][0]["speaker"]
        listener = 1 if speaker != 1 else 2
        out.append({
            "segment_id": longest["segment_id"], "action": "reaction",
            "camera": listener, "reason": "Long take; cut to a listener.",
        })
    for s in payload:
        speakers = {ln["speaker"] for ln in s["speech"]}
        if len(speakers) >= 2:
            dominant = s["speech"][0]["speaker"]
            if dominant != s["shown_camera"]:
                out.append({
                    "segment_id": s["segment_id"], "action": "switch",
                    "camera": dominant,
                    "reason": "Crosstalk; hold the dominant speaker.",
                })
            break
    return json.dumps(out)


_PROVIDERS = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
    "gemini": _call_gemini,
    "mock": _call_mock,
}


# --- response validation ------------------------------------------------------

def _extract_json_array(text: str) -> list:
    """Models wrap JSON in prose or fences despite instructions. Find the array."""
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON array in model response: {text[:200]!r}")
    return json.loads(m.group(0))


def suggest(segments: list[Segment], n_cameras: int, provider: str,
            api_key: str = "", model: str = "") -> list[dict]:
    """Run the Director. Returns validated suggestions enriched with the
    authoritative frame numbers (mapped from segment_id by US, not the LLM).

    Each suggestion: {segment_id, frame, end_frame, old_camera, new_camera,
    action, reason}. Invalid LLM items are dropped and counted, never patched.
    """
    if provider not in _PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}")
    model = model or DEFAULT_MODELS.get(provider, "")
    raw = _PROVIDERS[provider](_user_prompt(segments, n_cameras), api_key, model)
    items = _extract_json_array(raw)

    by_id = {s.segment_id: s for s in segments}
    out: list[dict] = []
    dropped = 0
    for it in items:
        seg = by_id.get(it.get("segment_id"))
        cam = it.get("camera")
        action = it.get("action")
        if (seg is None or action not in ("switch", "reaction")
                or not isinstance(cam, int) or not (1 <= cam <= n_cameras)):
            dropped += 1
            continue
        if action == "switch" and cam == seg.camera:
            dropped += 1  # no-op suggestion
            continue
        out.append({
            "segment_id": seg.segment_id,
            "frame": seg.frame,
            "end_frame": seg.end_frame,
            "old_camera": seg.camera,
            "new_camera": cam,
            "action": action,
            "reason": str(it.get("reason", ""))[:200],
        })
    return {"suggestions": out, "dropped": dropped}
