"""Deterministic cut engine: per-channel mic activity -> cut map.

Cheap tier, no model. Rules, in order:
1. Per hop, the winner is the active channel; on crosstalk (several active),
   the loudest active channel wins (Director tier may refine this later).
2. On silence, hold the last speaker (never cut to nothing).
3. Shots shorter than min_shot_s are absorbed into the previous shot to avoid
   flicker cutting.
4. Hop decisions convert to integer video frames at the end, once.
"""

import numpy as np

from dsp.vad import HOP_S, detect_activity
from .schema import Cut, CutMap


def channels_to_masks(channel_rms: list[np.ndarray]) -> list[np.ndarray]:
    """Per-channel RMS -> per-channel boolean activity mask (per hop)."""
    n_hops = min(len(r) for r in channel_rms)
    masks = []
    for rms in channel_rms:
        mask = np.zeros(n_hops, dtype=bool)
        for b in detect_activity(rms[:n_hops]):
            mask[b.start_hop : b.end_hop] = True
        masks.append(mask)
    return masks


def decide_per_hop(channel_rms: list[np.ndarray], masks: list[np.ndarray]) -> np.ndarray:
    """Winner camera (1-based) per hop, holding the last speaker on silence."""
    n_hops = len(masks[0])
    rms = np.stack([r[:n_hops] for r in channel_rms])
    act = np.stack(masks)
    winners = np.zeros(n_hops, dtype=np.int32)
    current = 1  # default to camera 1 until someone speaks
    for i in range(n_hops):
        active = np.flatnonzero(act[:, i])
        if len(active) == 1:
            current = int(active[0]) + 1
        elif len(active) > 1:
            current = int(active[np.argmax(rms[active, i])]) + 1
        winners[i] = current
    return winners


def enforce_min_shot(winners: np.ndarray, min_shot_hops: int) -> list[tuple[int, int]]:
    """Collapse per-hop winners to (start_hop, camera) runs, absorbing runs
    shorter than min_shot_hops into the previous shot."""
    runs: list[tuple[int, int]] = []  # (start_hop, camera)
    for i, w in enumerate(winners):
        if not runs or runs[-1][1] != w:
            runs.append((i, int(w)))
    # absorb short runs (except the first) into their predecessor
    out: list[tuple[int, int]] = []
    for j, (start, cam) in enumerate(runs):
        end = runs[j + 1][0] if j + 1 < len(runs) else len(winners)
        if out and end - start < min_shot_hops:
            continue  # predecessor keeps running through this span
        if out and out[-1][1] == cam:
            continue  # same camera after an absorption — extend, no new cut
        out.append((start, cam))
    return out


def hops_to_frames(runs: list[tuple[int, int]], fps_num: int, fps_den: int) -> list[Cut]:
    cuts: list[Cut] = []
    for start_hop, cam in runs:
        t = start_hop * HOP_S
        frame = round(t * fps_num / fps_den)
        if cuts and frame <= cuts[-1].frame:
            continue
        cuts.append(Cut(frame, cam))
    if not cuts or cuts[0].frame != 0:
        first_cam = runs[0][1] if runs else 1
        cuts = [Cut(0, first_cam)] + [c for c in cuts if c.frame > 0]
    return cuts


def build_cut_map(
    channel_rms: list[np.ndarray],
    fps_num: int,
    fps_den: int,
    total_frames: int,
    min_shot_s: float = 1.5,
) -> CutMap:
    masks = channels_to_masks(channel_rms)
    winners = decide_per_hop(channel_rms, masks)
    runs = enforce_min_shot(winners, max(1, int(round(min_shot_s / HOP_S))))
    cuts = hops_to_frames(runs, fps_num, fps_den)
    cuts = [c for c in cuts if c.frame < total_frames]
    m = CutMap(fps_num, fps_den, total_frames, cuts)
    m.validate()
    return m
