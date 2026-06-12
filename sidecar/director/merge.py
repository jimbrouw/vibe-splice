"""Apply ACCEPTED Director suggestions to a cut map. Pure, deterministic.

The user reviewed the suggestions in the panel; this maps the accepted ones
back onto the integer-frame cut map. The LLM is long gone by now — frames
here come from the segments we built, never from model output.

switch   — recolour one segment: cuts[i].camera = new_camera.
reaction — insert a brief cutaway INSIDE the segment, then return:
           starts 40% into the segment, lasts reaction_s, and only happens
           if both the cutaway and the remaining shoulders respect
           min_shot_s. Too-short segments are skipped, not squeezed.
"""

from cutengine.schema import Cut, CutMap


def apply_suggestions(cuts: list[dict], total_frames: int,
                      fps_numerator: int, fps_denominator: int,
                      accepted: list[dict],
                      reaction_s: float = 2.0,
                      min_shot_s: float = 1.5) -> CutMap:
    fps = fps_numerator / fps_denominator
    min_shot = max(1, round(min_shot_s * fps))
    reaction = max(1, round(reaction_s * fps))

    work = [{"frame": c["frame"], "camera": c["camera"]} for c in cuts]
    by_frame = {c["frame"]: c for c in work}
    skipped = 0

    for sug in accepted:
        seg = by_frame.get(sug["frame"])
        if seg is None:  # cut map changed since suggestions were made
            skipped += 1
            continue
        if sug["action"] == "switch":
            seg["camera"] = sug["new_camera"]
        elif sug["action"] == "reaction":
            start, end = sug["frame"], sug["end_frame"]
            r0 = start + round((end - start) * 0.4)
            r1 = r0 + reaction
            # both shoulders and the cutaway must respect min-shot
            if r0 - start < min_shot or end - r1 < min_shot or r1 - r0 < min_shot:
                skipped += 1
                continue
            work.append({"frame": r0, "camera": sug["new_camera"]})
            work.append({"frame": r1, "camera": seg["camera"]})
        else:
            skipped += 1

    work.sort(key=lambda c: c["frame"])
    # collapse duplicate frames (last writer wins) and same-camera runs
    dedup: list[dict] = []
    for c in work:
        if dedup and dedup[-1]["frame"] == c["frame"]:
            dedup[-1] = c
            continue
        dedup.append(c)
    collapsed: list[Cut] = []
    for c in dedup:
        if collapsed and collapsed[-1].camera == c["camera"]:
            continue
        collapsed.append(Cut(frame=c["frame"], camera=c["camera"]))

    cut_map = CutMap(
        fps_numerator=fps_numerator,
        fps_denominator=fps_denominator,
        total_frames=total_frames,
        cuts=collapsed,
    )
    cut_map.validate()
    return cut_map, skipped
