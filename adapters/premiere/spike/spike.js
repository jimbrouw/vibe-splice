/* M0 timeline-write spike. Throwaway probe code — heavy logging, no product
 * structure. Every Premiere action call is wrapped because they throw
 * "Script Action failed to execute" on bad params with no detail.
 *
 * Time discipline (hard rule #2): every edit point is built ONCE as a
 * TickTime snapped to a frame boundary. Integer tick math where possible:
 * Premiere's tick rate is 254016000000/s, so at 30000/1001 fps one frame is
 * exactly 254016000000 / 30000 * 1001 = 8475667200 ticks. No float seconds
 * ever enter the write path. [Unverified] which TickTime constructors the
 * live API exposes — button 0 probes this first.
 */

const ppro = require("premierepro");

// ---------- cut map (mirror of /tests/fixtures/cutmap.json — keep in sync) ----------
const FPS_NUM = 30000;
const FPS_DEN = 1001;
const TOTAL_FRAMES = 17982;
const CUTS = [
  { frame: 0,     camera: 1 },
  { frame: 450,   camera: 2 },   // checkpoint: early
  { frame: 1200,  camera: 3 },
  { frame: 2400,  camera: 1 },
  { frame: 4500,  camera: 2 },
  { frame: 6300,  camera: 3 },
  { frame: 8991,  camera: 1 },   // checkpoint: middle
  { frame: 10500, camera: 2 },
  { frame: 12000, camera: 3 },
  { frame: 14100, camera: 1 },
  { frame: 16200, camera: 2 },
  { frame: 17500, camera: 3 },   // checkpoint: late
];

const TICKS_PER_SECOND = 254016000000;
const TICKS_PER_FRAME = (TICKS_PER_SECOND / FPS_NUM) * FPS_DEN; // 8475667200, exact integer

// ---------- logging ----------
// Mirrors every log line to spike-log.txt in the plugin data folder so the
// session driving this spike can read results without scraping the panel UI.
const logEl = document.getElementById("log");
const fsp = require("uxp").storage.localFileSystem;
let logLines = [];
let logFile = null;
async function initLogFile() {
  try {
    const folder = await fsp.getDataFolder();
    logFile = await folder.createFile("spike-log.txt", { overwrite: true });
    const native = await folder.getNativePath?.();
    if (native) console.log("spike-log at: " + native);
  } catch (e) {
    console.log("file log unavailable: " + e.message);
  }
}
initLogFile();
let flushTimer = null;
function flushLog() {
  if (!logFile) return;
  logFile.write(logLines.join("\n"), { append: false }).catch(() => {});
}
function log(msg, cls) {
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = msg;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
  console.log(msg);
  logLines.push(msg);
  clearTimeout(flushTimer);
  flushTimer = setTimeout(flushLog, 300);
}
const ok = (m) => log("OK  " + m, "ok");
const err = (m) => log("ERR " + m, "err");
const info = (m) => log(m, "info");

// ---------- time helpers ----------
function frameToTickTime(frame) {
  const ticks = frame * TICKS_PER_FRAME; // < 2^53 for any plausible timeline
  if (typeof ppro.TickTime.createWithTicks === "function") {
    return ppro.TickTime.createWithTicks(String(ticks));
  }
  // Fallback: seconds derived from integer ticks, divided once. Logged so the
  // spike report records which path was live.
  log("frameToTickTime fallback: createWithSeconds (createWithTicks missing)");
  return ppro.TickTime.createWithSeconds(ticks / TICKS_PER_SECOND);
}

function tickTimeToFrame(tickTime) {
  // ticks may be exposed as .ticks (string) or .seconds (number). Probe both.
  if (tickTime.ticks !== undefined) return Number(tickTime.ticks) / TICKS_PER_FRAME;
  return (tickTime.seconds * TICKS_PER_SECOND) / TICKS_PER_FRAME;
}

// ---------- fragile-call wrapper ----------
async function safe(label, fn, params) {
  log("→ " + label + (params ? " " + JSON.stringify(params) : ""));
  try {
    const r = await fn();
    ok(label);
    return r;
  } catch (e) {
    err(label + ": " + (e && e.message ? e.message : String(e)));
    throw e;
  }
}

// ---------- project / sequence access ----------
async function getActive() {
  const project = await ppro.Project.getActiveProject();
  if (!project) throw new Error("No active project");
  const sequence = await project.getActiveSequence();
  if (!sequence) throw new Error("No active sequence");
  return { project, sequence };
}

async function findProjectItem(project, name) {
  const root = await project.getRootItem();
  async function walk(bin, depth) {
    const items = await bin.getItems();
    for (const item of items) {
      log(`  ${"  ".repeat(depth)}item: "${item.name}" (${item.constructor?.name})`);
      if (item.name === name) return item;
      let asFolder = null;
      if (typeof item.getItems === "function") asFolder = item;
      else if (ppro.FolderItem?.cast) {
        try { asFolder = ppro.FolderItem.cast(item); } catch { /* not a bin */ }
      }
      if (asFolder && typeof asFolder.getItems === "function") {
        const found = await walk(asFolder, depth + 1).catch(() => null);
        if (found) return found;
      }
    }
    return null;
  }
  const found = await walk(root, 0);
  if (!found) throw new Error(`Project item "${name}" not found anywhere in project — import the fixtures first`);
  return found;
}

// Execute actions inside a locked transaction. [Unverified] exact signature —
// this is the pattern from uxp-premiere-pro-samples; button 0 probes it.
async function execute(project, name, buildActions) {
  return safe(`transaction "${name}"`, () =>
    project.lockedAccess(() =>
      project.executeTransaction((compound) => {
        for (const a of buildActions()) compound.addAction(a);
      }, name)
    )
  );
}

async function getVideoTrackItems(sequence, vIndex) {
  const track = await sequence.getVideoTrack(vIndex);
  const clipType = ppro.Constants?.TrackItemType?.CLIP ?? 1;
  const items = await track.getTrackItems(clipType, false);
  return items;
}

// ---------- 0. probe ----------
async function probe() {
  info("=== API surface probe ===");
  info("ppro keys: " + Object.keys(ppro).join(", "));
  info("TickTime statics: " + Object.getOwnPropertyNames(ppro.TickTime).join(", "));
  if (ppro.Constants) info("Constants keys: " + Object.keys(ppro.Constants).join(", "));
  const { project, sequence } = await getActive();
  info("project: " + project.name);
  info("sequence: " + sequence.name);
  info("sequence proto: " + Object.getOwnPropertyNames(Object.getPrototypeOf(sequence)).join(", "));
  const editor = await ppro.SequenceEditor.getEditor(sequence);
  info("SequenceEditor proto: " + Object.getOwnPropertyNames(Object.getPrototypeOf(editor)).join(", "));
  const t = frameToTickTime(450);
  info("TickTime(frame 450) instance props: " + Object.getOwnPropertyNames(Object.getPrototypeOf(t)).join(", "));
  info("frame 450 → ticks expected 3814050240000, roundtrip frame: " + tickTimeToFrame(t));
  const items = await getVideoTrackItems(sequence, 0);
  info("V1 track items: " + items.length);
  if (items.length) {
    const ti = items[0];
    info("trackItem proto: " + Object.getOwnPropertyNames(Object.getPrototypeOf(ti)).join(", "));
  }
  const cam1 = await findNoLog(project, "cam1.mp4");
  if (cam1) {
    info("cam1 projectItem proto: " + Object.getOwnPropertyNames(Object.getPrototypeOf(cam1)).join(", "));
    if (ppro.ClipProjectItem?.cast) {
      try {
        const clip = ppro.ClipProjectItem.cast(cam1);
        info("ClipProjectItem proto: " + Object.getOwnPropertyNames(Object.getPrototypeOf(clip)).join(", "));
      } catch (e) { info("ClipProjectItem.cast failed: " + e.message); }
    }
  }
  info("TrackItemSelection statics: " + Object.getOwnPropertyNames(ppro.TrackItemSelection).join(", "));
}

async function findNoLog(project, name) {
  const root = await project.getRootItem();
  async function walk(bin) {
    for (const item of await bin.getItems()) {
      if (item.name === name) return item;
      let f = null;
      if (typeof item.getItems === "function") f = item;
      else if (ppro.FolderItem?.cast) { try { f = ppro.FolderItem.cast(item); } catch {} }
      if (f) { const r = await walk(f).catch(() => null); if (r) return r; }
    }
    return null;
  }
  return walk(root);
}

// ---------- 1. build synced test sequence ----------
async function buildTestSequence() {
  info("=== Build 3-cam stacked sequence ===");
  const { project, sequence } = await getActive();
  const editor = await ppro.SequenceEditor.getEditor(sequence);
  const t0 = frameToTickTime(0);

  const cams = [];
  for (let i = 1; i <= 3; i++) cams.push(await findProjectItem(project, `cam${i}.mp4`));
  const audio = await findProjectItem(project, "audio_bed.wav");

  // Cameras stacked on V1..V3 (vIndex 0..2), no audio from cams (aIndex -1
  // [Unverified] whether -1 suppresses audio — probe will tell). Audio bed on A1.
  for (let i = 0; i < 3; i++) {
    await execute(project, `place cam${i + 1} on V${i + 1}`, () => [
      editor.createOverwriteItemAction(cams[i], t0, i, -1),
    ]);
  }
  await execute(project, "place audio bed on A1", () => [
    editor.createOverwriteItemAction(audio, t0, -1, 0),
  ]);
  ok("stacked sequence built — eyeball it: cam1/2/3 on V1/V2/V3, bed on A1, all starting at 0");
}

// ---------- 2. split primitive ----------
// Candidate: clone the trackItem in place, trim original to end at the
// boundary, trim clone to start at it. If this holds frame-exactly it powers
// methods B and C.
async function splitTrackItemAt(project, sequence, vIndex, frame) {
  const editor = await ppro.SequenceEditor.getEditor(sequence);
  const cutT = frameToTickTime(frame);

  let items = await getVideoTrackItems(sequence, vIndex);
  const target = items.find(
    (ti) => tickTimeToFrame(ti.getStartTime ? ti.getStartTime() : ti.startTime) <= frame
  );
  // For the spike sequence every track has one item spanning the timeline, so
  // items[0] is the target; the find() is belt-and-braces for re-runs.
  const orig = target || items[0];

  // Clone in place on the same track.
  await execute(project, `clone V${vIndex + 1} item`, () => [
    editor.createCloneTrackItemAction(orig, frameToTickTime(0), 0, 0, true, false),
  ]);

  // Re-query: which item is the clone is [Unverified]; assume last in list.
  items = await getVideoTrackItems(sequence, vIndex);
  const a = items[0];
  const b = items[items.length - 1];

  await execute(project, `trim original to end at frame ${frame}`, () => [
    a.createSetEndAction(cutT),
  ]);
  await execute(project, `trim clone to start at frame ${frame}`, () => [
    b.createSetStartAction(cutT),
    b.createSetInPointAction(cutT), // keep source in sync with position so content matches time
  ]);
  return frame;
}

async function testSplitPrimitive() {
  info("=== Split primitive test: split V1 at frame 450 ===");
  const { project, sequence } = await getActive();
  await splitTrackItemAt(project, sequence, 0, 450);
  const items = await getVideoTrackItems(sequence, 0);
  info(`V1 now has ${items.length} items:`);
  for (const ti of items) {
    const s = tickTimeToFrame(await ti.getStartTime());
    const e = tickTimeToFrame(await ti.getEndTime());
    info(`  item: start frame ${s}, end frame ${e}`);
  }
  info("Expected: two items, boundary exactly at 450. Check the displayed FRAME number at the playhead.");
}

// ---------- intervals from cut map ----------
let appliedCuts = CUTS; // verify compares V4 against whatever was last applied

function intervals(cuts, totalFrames) {
  const out = [];
  for (let i = 0; i < cuts.length; i++) {
    out.push({
      start: cuts[i].frame,
      end: i + 1 < cuts.length ? cuts[i + 1].frame : totalFrames,
      camera: cuts[i].camera,
    });
  }
  return out;
}

// ---------- clear a video track ----------
async function clearVideoTrack(project, sequence, vIndex) {
  const editor = await ppro.SequenceEditor.getEditor(sequence);
  const items = await getVideoTrackItems(sequence, vIndex);
  if (!items.length) return;
  let sel;
  try {
    sel = ppro.TrackItemSelection.createEmptySelection(sequence);
    info("createEmptySelection(sequence) worked");
  } catch (e) {
    err("createEmptySelection(sequence): " + e.message + " — trying via sequence.getSelection()");
    sel = await sequence.getSelection();
  }
  info("selection proto: " + Object.getOwnPropertyNames(Object.getPrototypeOf(sel)).join(", "));
  for (const ti of items) {
    try { sel.addItem(ti); }
    catch (e) { err("sel.addItem(ti): " + e.message); throw e; }
  }
  const mt = ppro.Constants?.MediaType?.VIDEO ?? 1;
  await execute(project, `clear V${vIndex + 1} (${items.length} items)`, () => [
    editor.createRemoveItemsAction(sel, false, mt, false),
  ]);
}

// ---------- 3a. Method A: segmented overwrite onto V4 ----------
// 3-point-edit model: set source in/out on the ClipProjectItem first, then
// overwrite-place at the interval start. Found in the first run: trimming a
// placed item with createSetInPointAction MOVES it and lands off-frame by a
// 29.97/30 factor — never trim source after placement.
async function methodA() {
  return applyCutMap(CUTS, TOTAL_FRAMES, "Method A (hardcoded cut map)");
}

async function applyCutMap(cuts, totalFrames, label) {
  info(`=== Apply onto V4: ${label}, ${cuts.length} cuts ===`);
  const { project, sequence } = await getActive();
  const editor = await ppro.SequenceEditor.getEditor(sequence);

  const cams = [];
  for (let i = 1; i <= 3; i++) cams.push(await findProjectItem(project, `cam${i}.mp4`));

  await clearVideoTrack(project, sequence, 3);

  for (const iv of intervals(cuts, totalFrames)) {
    const startT = frameToTickTime(iv.start);
    const endT = frameToTickTime(iv.end);
    const item = cams[iv.camera - 1];
    const clip = ppro.ClipProjectItem.cast(item);
    await execute(project, `A: source in/out ${iv.start}..${iv.end} on cam${iv.camera}`, () => [
      clip.createSetInOutPointsAction(startT, endT),
    ]);
    await execute(project, `A: overwrite cam${iv.camera} at frame ${iv.start}`, () => [
      editor.createOverwriteItemAction(item, startT, 3, -1),
    ]);
  }
  for (let i = 0; i < 3; i++) {
    const clip = ppro.ClipProjectItem.cast(cams[i]);
    await execute(project, `A: clear in/out on cam${i + 1}`, () => [
      clip.createClearInOutPointsAction(),
    ]);
  }
  appliedCuts = cuts;
  ok(`${label}: applied to V4. Run verify.`);
}

// ---------- 6. full pipeline: sidecar analyze -> apply ----------
const SIDECAR = "http://127.0.0.1:8765";
const FIXTURES = "/Users/standard/Developer/Vibe-splice/tests/fixtures";

async function runPipeline() {
  info("=== Full pipeline: sidecar /analyze -> Method A apply ===");
  let resp;
  try {
    resp = await fetch(`${SIDECAR}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audio_paths: [1, 2, 3].map((n) => `${FIXTURES}/cam${n}.mp4`),
        fps_numerator: FPS_NUM,
        fps_denominator: FPS_DEN,
        total_frames: TOTAL_FRAMES,
      }),
    });
  } catch (e) {
    err(`sidecar unreachable at ${SIDECAR} — is uvicorn running? (${e.message})`);
    return;
  }
  if (!resp.ok) {
    err(`sidecar ${resp.status}: ${(await resp.text()).slice(0, 300)}`);
    return;
  }
  const map = await resp.json();
  info(`cut map received: ${map.cuts.length} cuts over ${map.total_frames} frames`);
  for (const c of map.cuts) info(`  frame ${c.frame} -> cam${c.camera}`);
  await applyCutMap(map.cuts, map.total_frames, "sidecar VAD cut map");
  await verify();
}

// ---------- 3b. Method B: stacked + disable ----------
async function methodB() {
  info("=== Method B: stacked + disable ===");
  const { project, sequence } = await getActive();

  // Segment all three tracks at every switch point.
  const boundaries = CUTS.slice(1).map((c) => c.frame);
  for (let v = 0; v < 3; v++) {
    for (const f of boundaries) {
      await splitTrackItemAt(project, sequence, v, f);
    }
  }

  // Disable every segment that is not the chosen camera for its interval.
  for (let v = 0; v < 3; v++) {
    const items = await getVideoTrackItems(sequence, v);
    for (const ti of items) {
      const s = tickTimeToFrame(await ti.getStartTime());
      const iv = intervals().find((x) => x.start <= s && s < x.end);
      const enabled = iv && iv.camera === v + 1;
      await execute(project, `B: V${v + 1} segment @${s} → ${enabled ? "ENABLED" : "disabled"}`, () => [
        ti.createSetDisabledAction(!enabled),
      ]);
    }
  }
  ok("Method B applied. Exactly one camera should be enabled per interval. Run verify.");
}

// ---------- 3c. Method C: stacked + remove ----------
async function methodC() {
  info("=== Method C: stacked + remove (destructive to the spike sequence) ===");
  const { project, sequence } = await getActive();
  const editor = await ppro.SequenceEditor.getEditor(sequence);

  const boundaries = CUTS.slice(1).map((c) => c.frame);
  for (let v = 0; v < 3; v++) {
    for (const f of boundaries) {
      await splitTrackItemAt(project, sequence, v, f);
    }
  }

  for (let v = 0; v < 3; v++) {
    const items = await getVideoTrackItems(sequence, v);
    for (const ti of items) {
      const s = tickTimeToFrame(await ti.getStartTime());
      const iv = intervals().find((x) => x.start <= s && s < x.end);
      if (iv && iv.camera === v + 1) continue; // keep the chosen angle
      // [Unverified] how to build a TrackItemSelection for one item — probe
      // exposes the type. Placeholder per samples:
      const selection = await ppro.TrackItemSelection.createEmptySelection?.() ?? null;
      if (!selection) {
        err("TrackItemSelection factory not found — record in BANANAS and use probe output");
        return;
      }
      selection.addItem(ti);
      await execute(project, `C: remove V${v + 1} segment @${s}`, () => [
        editor.createRemoveItemsAction(selection, false, 1, false), // no ripple
      ]);
    }
  }
  ok("Method C applied. Run verify.");
}

// ---------- 4. verify drift ----------
async function verify() {
  info("=== Drift verification against cut map ===");
  const { sequence } = await getActive();
  let worst = 0;
  for (let v = 0; v < 4; v++) {
    let items;
    try {
      items = await getVideoTrackItems(sequence, v);
    } catch {
      continue; // track may not exist (e.g. no V4 unless Method A ran)
    }
    for (const ti of items) {
      const st = await ti.getStartTime();
      const et = await ti.getEndTime();
      const ip = await ti.getInPoint?.();
      const s = tickTimeToFrame(st);
      const e = tickTimeToFrame(et);
      const sErr = Math.abs(s - Math.round(s));
      const eErr = Math.abs(e - Math.round(e));
      worst = Math.max(worst, sErr, eErr);
      info(
        `V${v + 1} item ${s.toFixed(4)}..${e.toFixed(4)} ` +
        `startTicks=${st.ticks} mod=${Number(st.ticks) % TICKS_PER_FRAME} ` +
        `inTicks=${ip ? ip.ticks : "?"}`
      );
    }
  }
  info(`Worst sub-frame error: ${worst.toExponential(3)} frames`);
  // V4 must contain exactly the applied cut map: one segment per cut.
  try {
    const v4 = await getVideoTrackItems(sequence, 3);
    const starts = [];
    for (const ti of v4) starts.push(Math.round(tickTimeToFrame(await ti.getStartTime())));
    starts.sort((a, b) => a - b);
    const expected = appliedCuts.map((c) => c.frame);
    const match =
      starts.length === expected.length && starts.every((f, i) => f === expected[i]);
    if (match) ok(`V4 matches applied cut map exactly (${starts.length} segments)`);
    else {
      err(`V4 mismatch. expected starts: ${expected.join(",")}`);
      err(`             actual starts: ${starts.join(",")}`);
    }
  } catch (e) {
    err("V4 comparison failed: " + e.message);
  }
  info("API readback is necessary but not sufficient: also step the playhead to");
  info("frames 450 / 8991 / 17500 and confirm the burned-in FRAME number matches");
  info("and the 30s flash stays aligned with the beep late in the timeline.");
}

// ---------- 5. cycle playhead through checkpoints ----------
const CHECKPOINTS = [450, 8991, 17500];
let cpIndex = 0;
async function gotoNextCheckpoint() {
  const { sequence } = await getActive();
  const f = CHECKPOINTS[cpIndex % CHECKPOINTS.length];
  cpIndex++;
  await sequence.setPlayerPosition(frameToTickTime(f));
  info(`playhead set to frame ${f} — program monitor must show FRAME ${f}`);
}

// ---------- wiring ----------
function bind(id, fn) {
  document.getElementById(id).addEventListener("click", () =>
    fn().catch((e) => err("UNCAUGHT: " + (e && e.message ? e.message : String(e))))
  );
}
bind("btnProbe", probe);
bind("btnBuild", buildTestSequence);
bind("btnSplit", testSplitPrimitive);
bind("btnMethodA", methodA);
bind("btnMethodB", methodB);
bind("btnMethodC", methodC);
bind("btnVerify", verify);
bind("btnCheckpoint", gotoNextCheckpoint);
bind("btnPipeline", runPipeline);
document.getElementById("btnClear").addEventListener("click", () => (logEl.textContent = ""));

info("M0 spike panel loaded. Run 0 (probe) first; paste its output back into the session.");

// One-shot auto-run for driving the pipeline without UI access. Set to false
// after use — throwaway spike convenience, not product behaviour.
const AUTO_RUN_PIPELINE = false;
if (AUTO_RUN_PIPELINE) {
  setTimeout(() => runPipeline().catch((e) => err("UNCAUGHT: " + e.message)), 1500);
}
