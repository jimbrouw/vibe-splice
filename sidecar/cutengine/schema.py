"""The NLE-agnostic cut map contract.

This is the single interchange format between the sidecar (which decides WHEN
to cut and to WHICH camera) and any apply adapter (Premiere now, Resolve in
v2). Authority is the integer frame number at the stated rational frame rate
— never float seconds (BANANAS E1). The Premiere adapter converts each frame
to ticks exactly once: frame * (254016000000 * fps_denominator / fps_numerator).

Wire shape (tests/fixtures/cutmap.json is the reference instance):

{
  "fps_numerator": 30000,
  "fps_denominator": 1001,
  "total_frames": 17982,
  "cuts": [ { "frame": 0, "camera": 1 }, ... ]
}

Rules:
- cuts[0].frame == 0 (something must be on screen from the start)
- frames strictly increasing, all < total_frames
- camera is 1-based
- each entry holds until the next entry's frame (last holds to total_frames)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Cut:
    frame: int
    camera: int


@dataclass
class CutMap:
    fps_numerator: int
    fps_denominator: int
    total_frames: int
    cuts: list[Cut] = field(default_factory=list)

    def validate(self) -> None:
        if self.fps_numerator <= 0 or self.fps_denominator <= 0:
            raise ValueError("fps must be a positive rational")
        if not self.cuts:
            raise ValueError("cut map has no cuts")
        if self.cuts[0].frame != 0:
            raise ValueError("first cut must be at frame 0")
        prev = -1
        for c in self.cuts:
            if c.frame <= prev:
                raise ValueError(f"cut frames must be strictly increasing (at {c.frame})")
            if c.frame >= self.total_frames:
                raise ValueError(f"cut at {c.frame} is past total_frames {self.total_frames}")
            if c.camera < 1:
                raise ValueError(f"camera is 1-based (got {c.camera})")
            prev = c.frame

    def to_dict(self) -> dict:
        return {
            "fps_numerator": self.fps_numerator,
            "fps_denominator": self.fps_denominator,
            "total_frames": self.total_frames,
            "cuts": [{"frame": c.frame, "camera": c.camera} for c in self.cuts],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CutMap":
        m = cls(
            fps_numerator=int(d["fps_numerator"]),
            fps_denominator=int(d["fps_denominator"]),
            total_frames=int(d["total_frames"]),
            cuts=[Cut(int(c["frame"]), int(c["camera"])) for c in d["cuts"]],
        )
        m.validate()
        return m
