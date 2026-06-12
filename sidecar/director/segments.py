"""Build Director segments: the ONLY view of the timeline the LLM ever sees.

BYOT contract (CLAUDE.md): the Director never owns timecodes. Each segment
carries a segment_id; the LLM returns decisions keyed to segment_id, and
deterministic code here maps them back to the integer frames the DSP already
computed. Frames stay authoritative end-to-end.

A segment is one interval of the base cut map (cut N holds until cut N+1),
enriched with who is speaking (from the transcript) and what they said.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TranscriptLine:
    """One utterance. Times in seconds within the timeline, speaker 1-based."""
    start_s: float
    end_s: float
    speaker: int
    text: str


@dataclass(frozen=True)
class Segment:
    segment_id: str          # "seg-0007" — opaque to the LLM
    frame: int               # cut frame (authoritative, never sent for editing)
    end_frame: int
    camera: int              # proposed angle from the DSP base map
    duration_s: float
    lines: list[TranscriptLine] = field(default_factory=list)

    def speakers(self) -> list[int]:
        seen: list[int] = []
        for ln in self.lines:
            if ln.speaker not in seen:
                seen.append(ln.speaker)
        return seen


def build_segments(cuts: list[dict], total_frames: int,
                   fps_numerator: int, fps_denominator: int,
                   transcript: list[TranscriptLine]) -> list[Segment]:
    """Intersect the base cut map with transcript lines.

    A transcript line belongs to every segment it overlaps, so the LLM sees
    crosstalk as two speakers inside one segment.
    """
    spf = fps_denominator / fps_numerator  # seconds per frame
    segments: list[Segment] = []
    for i, cut in enumerate(cuts):
        start = cut["frame"]
        end = cuts[i + 1]["frame"] if i + 1 < len(cuts) else total_frames
        t0, t1 = start * spf, end * spf
        lines = [ln for ln in transcript if ln.start_s < t1 and ln.end_s > t0]
        segments.append(Segment(
            segment_id=f"seg-{i:04d}",
            frame=start,
            end_frame=end,
            camera=cut["camera"],
            duration_s=round(t1 - t0, 3),
            lines=lines,
        ))
    return segments


# --- synthetic transcript (fixtures have noise bursts, not speech) ----------
# Real footage uses Whisper behind the same TranscriptLine interface. Until
# then, speech_schedule.json (the fixture ground truth) plus canned podcast
# text exercises the entire Director chain deterministically.

_CANNED = [
    "So the thing nobody tells you about shipping early is the feedback hurts.",
    "Right, and that's exactly the point — you want it to hurt sooner.",
    "Ha, yeah. We learned that the expensive way on the last launch.",
    "Can I push back on that a little? I think timing mattered more than polish.",
    "That's fair. Although the data we saw afterwards told a different story.",
    "Wait, really? I'd love to see that breakdown.",
    "I'll share it after the show. The short version: retention was flat.",
    "Which honestly surprised everyone in the room that day.",
]


def synthetic_transcript(schedule: list[dict]) -> list[TranscriptLine]:
    """speech_schedule.json entries -> TranscriptLine list with canned text."""
    out: list[TranscriptLine] = []
    for i, seg in enumerate(schedule):
        out.append(TranscriptLine(
            start_s=float(seg["start_s"]),
            end_s=float(seg["end_s"]),
            speaker=int(seg["speaker"]),
            text=_CANNED[i % len(_CANNED)],
        ))
    return out
