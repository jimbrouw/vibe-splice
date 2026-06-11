"""Energy-gate voice activity detection. Cheap tier: pure DSP, no model.

One mic per person (the 80% case): "who is talking" is per-channel activity.
RMS energy in short hops, a noise-floor-relative threshold, and hysteresis
(separate open/close thresholds plus minimum durations) to avoid flicker.

Output is activity blocks in HOP units; the cut engine converts hops to video
frames. Float seconds never leave this module.
"""

from dataclasses import dataclass

import numpy as np

HOP_S = 0.05  # 50 ms analysis hop — fine enough to localise speech onsets


@dataclass(frozen=True)
class ActivityBlock:
    start_hop: int
    end_hop: int  # exclusive


def rms_per_hop(samples: np.ndarray, sample_rate: int, hop_s: float = HOP_S) -> np.ndarray:
    """Mono float samples -> RMS per hop."""
    hop = int(round(sample_rate * hop_s))
    n = len(samples) // hop
    if n == 0:
        return np.zeros(0)
    x = samples[: n * hop].reshape(n, hop).astype(np.float64)
    return np.sqrt((x * x).mean(axis=1))


def detect_activity(
    rms: np.ndarray,
    open_ratio: float = 4.0,
    close_ratio: float = 2.0,
    min_active_hops: int = 4,   # 200 ms — shorter bursts are noise
    min_gap_hops: int = 6,      # 300 ms — shorter silences don't close a block
) -> list[ActivityBlock]:
    """Hysteresis gate over per-hop RMS, thresholds relative to the noise floor.

    The noise floor is the 20th percentile of RMS (assumes a speaker is silent
    most of the time on their own mic, true for podcast mics).
    """
    if len(rms) == 0:
        return []
    floor = max(np.percentile(rms, 20), 1e-8)
    open_t = floor * open_ratio
    close_t = floor * close_ratio

    blocks: list[ActivityBlock] = []
    active = False
    start = 0
    gap = 0
    for i, v in enumerate(rms):
        if not active:
            if v >= open_t:
                active, start, gap = True, i, 0
        else:
            if v >= close_t:
                gap = 0
            else:
                gap += 1
                if gap >= min_gap_hops:
                    end = i - gap + 1
                    if end - start >= min_active_hops:
                        blocks.append(ActivityBlock(start, end))
                    active = False
    if active:
        end = len(rms) - gap if gap else len(rms)
        if end - start >= min_active_hops:
            blocks.append(ActivityBlock(start, end))
    return blocks
