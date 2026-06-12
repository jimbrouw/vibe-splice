/* panel.js — Vibe Splice M2 panel
 *
 * Ported from adapters/premiere/spike/spike.js. Production-quality: no
 * throwaway probe buttons, no auto-run flags. The spike stays as-is for
 * reference and regression testing.
 *
 * Hard rules honoured (from CLAUDE.md):
 *  - All time values are integer ticks (frameToTickTime). Never float seconds.
 *  - Output always goes to a cloned sequence (cloneToNewSequence).
 *  - E5 guard: assertTimebase() runs before every write.
 *  - No video leaves the machine; sidecar receives audio paths only.
 */

const ppro = require("premierepro");
const uxp  = require("uxp");
const fsp  = uxp.storage.localFileSystem;

// ── Constants ─────────────────────────────────────────────────────────────────
const TICKS_PER_SECOND = 254016000000;
const SIDECAR          = "http://127.0.0.1:8765";

// Mutable — updated from the active sequence's timebase via setRateFromTicks().
let TICKS_PER_FRAME = (TICKS_PER_SECOND / 30000) * 1001; // 29.97 default
let FPS_NUM = 30000;
let FPS_DEN = 1001;

// ── UI element refs ───────────────────────────────────────────────────────────
const $sidecarDot   = document.getElementById("sidecarDot");
const $sidecarLabel = document.getElementById("sidecarLabel");
const $btnStart     = document.getElementById("btnStart");
const $camList      = document.getElementById("camList");
const $btnDetect    = document.getElementById("btnDetect");
const $btnRun       = document.getElementById("btnRun");
const $progressWrap = document.getElementById("progressWrap");
const $progressFill = document.getElementById("progressFill");
const $progressLabel= document.getElementById("progressLabel");
const $openHint     = document.getElementById("openHint");
const $log          = document.getElementById("log");

// ── App state ─────────────────────────────────────────────────────────────────
const state = {
  sidecarOk: false,
  sources: null,    // array from detectSources(), or null
  totalFrames: 0,
  running: false,
};

// ── Logging ───────────────────────────────────────────────────────────────────
let logLines   = [];
let logFile    = null;
let flushTimer = null;

(async () => {
  try {
    const folder = await fsp.getDataFolder();
    logFile = await folder.createFile("panel-log.txt", { overwrite: true });
  } catch (e) {
    console.log("file log unavailable: " + e.message);
  }
})();

function flushLog() {
  if (!logFile) return;
  logFile.write(logLines.join("\n"), { append: false }).catch(() => {});
}

function log(msg, cls) {
  const el = document.createElement("div");
  if (cls) el.className = cls;
  el.textContent = msg;
  $log.appendChild(el);
  $log.scrollTop = $log.scrollHeight;
  console.log(msg);
  logLines.push(msg);
  clearTimeout(flushTimer);
  flushTimer = setTimeout(flushLog, 300);
}

const logOk   = (m) => log("OK  " + m, "ok");
const logErr  = (m) => log("ERR " + m, "err");
const logInfo = (m) => log(m, "info");

// ── Time helpers ──────────────────────────────────────────────────────────────
function gcd(a, b) { while (b) [a, b] = [b, a % b]; return a; }

function setRateFromTicks(tpf) {
  const g = gcd(TICKS_PER_SECOND, tpf);
  FPS_NUM = TICKS_PER_SECOND / g;
  FPS_DEN = tpf / g;
  TICKS_PER_FRAME = tpf;
}

function frameToTickTime(frame) {
  return ppro.TickTime.createWithTicks(String(frame * TICKS_PER_FRAME));
}

function tickTimeToFrame(tt) {
  if (tt.ticks !== undefined) return Number(tt.ticks) / TICKS_PER_FRAME;
  return (tt.seconds * TICKS_PER_SECOND) / TICKS_PER_FRAME;
}

// ── Premiere helpers ──────────────────────────────────────────────────────────
async function getActive() {
  const project = await ppro.Project.getActiveProject();
  if (!project) throw new Error("No active project");
  const sequence = await project.getActiveSequence();
  if (!sequence) throw new Error("No active sequence");
  return { project, sequence };
}

async function execute(project, name, buildActions) {
  return project.lockedAccess(() =>
    project.executeTransaction((compound) => {
      for (const a of buildActions()) compound.addAction(a);
    }, name)
  );
}

async function getVideoTrackItems(sequence, vIndex) {
  const track    = await sequence.getVideoTrack(vIndex);
  const clipType = ppro.Constants?.TrackItemType?.CLIP ?? 1;
  return track.getTrackItems(clipType, false);
}

// E5 guard: refuse sequences whose timebase doesn't match the cut map fps.
// Premiere silently snaps placements to the sequence grid, producing drift.
async function assertTimebase(sequence) {
  const expected = (TICKS_PER_SECOND / FPS_NUM) * FPS_DEN;
  const tb       = await sequence.getTimebase();
  const actual   = Number(tb?.ticks ?? tb);
  logInfo(`timebase: ${actual} ticks/frame (expected ${expected})`);
  if (actual !== expected) {
    throw new Error(
      `timebase mismatch: sequence ${actual} vs footage ${expected} — ` +
      `create the sequence from the footage, not a preset (E5)`
    );
  }
}

// Hard rule 4: never mutate the source sequence. Clone first, find by GUID diff.
async function cloneToNewSequence(project, sequence) {
  async function collectGuids() {
    const guids = new Map();
    const root  = await project.getRootItem();
    async function walk(bin) {
      for (const item of await bin.getItems()) {
        try {
          const clip = ppro.ClipProjectItem.cast(item);
          if (clip && (await clip.isSequence())) {
            const seq = await clip.getSequence();
            if (seq) guids.set(seq.guid.toString(), seq);
          }
        } catch {}
        let f = null;
        if (ppro.FolderItem?.cast) { try { f = ppro.FolderItem.cast(item); } catch {} }
        if (f && typeof f.getItems === "function") await walk(f);
      }
    }
    await walk(root);
    return guids;
  }

  const before = await collectGuids();
  await execute(project, "clone sequence (non-destructive)", () => [
    sequence.createCloneAction(),
  ]);
  const after = await collectGuids();
  for (const [guid, seq] of after) {
    if (!before.has(guid)) {
      logInfo(`writing into clone "${seq.name}" — source untouched`);
      return seq;
    }
  }
  throw new Error("clone ran but no new sequence found");
}

async function clearVideoTrack(project, sequence, vIndex) {
  const editor = await ppro.SequenceEditor.getEditor(sequence);
  const items  = await getVideoTrackItems(sequence, vIndex);
  if (!items.length) return;
  let sel;
  try { sel = ppro.TrackItemSelection.createEmptySelection(sequence); }
  catch { sel = await sequence.getSelection(); }
  for (const ti of items) sel.addItem(ti);
  const mt = ppro.Constants?.MediaType?.VIDEO ?? 1;
  await execute(project, `clear V${vIndex + 1}`, () => [
    editor.createRemoveItemsAction(sel, false, mt, false),
  ]);
}

function buildIntervals(cuts, totalFrames) {
  return cuts.map((cut, i) => ({
    start:  cut.frame,
    end:    i + 1 < cuts.length ? cuts[i + 1].frame : totalFrames,
    camera: cut.camera,
  }));
}

// ── Source detection ──────────────────────────────────────────────────────────
// Reads the active sequence: consecutive single-clip tracks from V1 = cameras;
// the track above the camera stack = assembly target.
async function detectSourcesFromSequence() {
  const { sequence } = await getActive();

  const tb = await sequence.getTimebase();
  setRateFromTicks(Number(tb?.ticks ?? tb));

  const endT       = await sequence.getEndTime();
  const totalFrames = Math.round(Number(endT.ticks) / TICKS_PER_FRAME);
  const trackCount  = await sequence.getVideoTrackCount();

  const sources = [];
  let target = null;

  for (let v = 0; v < trackCount; v++) {
    const items = await getVideoTrackItems(sequence, v);
    if (items.length === 1 && target === null) {
      const ti   = items[0];
      const proj = await ti.getProjectItem();
      const clip = ppro.ClipProjectItem.cast(proj);
      if (await clip.isSequence()) { target = v; continue; }

      const path    = await clip.getMediaFilePath();
      const st      = await ti.getStartTime();
      const ip      = await ti.getInPoint();
      const et      = await ti.getEndTime();
      const offsetFrames = Math.round(
        (Number(st.ticks) - Number(ip.ticks)) / TICKS_PER_FRAME
      );
      const inFrames    = Math.round(Number(ip.ticks) / TICKS_PER_FRAME);
      const mediaEndFrame = inFrames + Math.round(
        (Number(et.ticks) - Number(st.ticks)) / TICKS_PER_FRAME
      );
      sources.push({
        vIndex: v, camera: sources.length + 1,
        name: proj.name, path, offsetFrames, mediaEndFrame,
        projItem: proj,
      });
    } else if (target === null && sources.length) {
      target = v;
    }
  }

  if (sources.length < 2) {
    throw new Error(
      `Only ${sources.length} camera track(s) found — need ≥2 synced single-clip ` +
      `video tracks starting from V1`
    );
  }
  if (target === null) target = sources.length;

  return { sources, target, totalFrames };
}

// ── Apply cut map ─────────────────────────────────────────────────────────────
// For each cut interval:
//   srcIn  = timeline_frame − offsetFrames   (media frame, not timeline frame)
//   srcOut = interval_end  − offsetFrames
// Clamped to [0, mediaEndFrame]; intervals with no media coverage are skipped.
async function applyCutMap(cuts, totalFrames, det, onProgress) {
  const targetTrack = det.target;
  const { project, sequence: source } = await getActive();
  await assertTimebase(source);

  const sequence = await cloneToNewSequence(project, source);

  // Rename the clone: Premiere names clones "X Copy Copy …". The rename
  // lives on the sequence's ProjectItem (createSetNameAction), not Sequence.
  const newName = `${source.name} — Vibe Splice`;
  try {
    const seqItem = await sequence.getProjectItem();
    await execute(project, "rename clone", () => [
      seqItem.createSetNameAction(newName),
    ]);
    logInfo(`clone renamed to "${newName}"`);
  } catch (e) {
    logInfo(`rename failed (${e.message}) — keeping "${sequence.name}"`);
  }

  const editor   = await ppro.SequenceEditor.getEditor(sequence);
  const cams     = det.sources.map((s) => s.projItem);

  await clearVideoTrack(project, sequence, targetTrack);

  const ivs = buildIntervals(cuts, totalFrames);
  for (let idx = 0; idx < ivs.length; idx++) {
    const iv  = ivs[idx];
    const src = det.sources[iv.camera - 1];
    const off = src.offsetFrames;

    let srcIn  = iv.start - off;
    let srcOut = iv.end   - off;
    if (srcIn  < 0)                  { logInfo(`  cam${iv.camera} @${iv.start}: clamp head`); srcIn = 0; }
    if (srcOut > src.mediaEndFrame)  { logInfo(`  cam${iv.camera} @${iv.end}: clamp tail`);  srcOut = src.mediaEndFrame; }
    if (srcIn >= srcOut) {
      logErr(`  cam${iv.camera}: no media for interval ${iv.start}..${iv.end} — skipped`);
      continue;
    }

    onProgress(`Cut ${idx + 1}/${ivs.length}`, (idx + 0.5) / ivs.length);

    const placeT = frameToTickTime(srcIn + off);
    const item   = cams[iv.camera - 1];
    const clip   = ppro.ClipProjectItem.cast(item);

    await execute(project, `src in/out cam${iv.camera} ${srcIn}..${srcOut}`, () => [
      clip.createSetInOutPointsAction(frameToTickTime(srcIn), frameToTickTime(srcOut)),
    ]);
    await execute(project, `overwrite cam${iv.camera} @${srcIn + off}`, () => [
      editor.createOverwriteItemAction(item, placeT, targetTrack, -1),
    ]);
  }

  // Restore project-item in/out points so they're clean for any future operation.
  for (let i = 0; i < cams.length; i++) {
    const clip = ppro.ClipProjectItem.cast(cams[i]);
    await execute(project, `clear in/out cam${i + 1}`, () => [
      clip.createClearInOutPointsAction(),
    ]);
  }

  try {
    if (typeof project.setActiveSequence === "function") {
      await project.setActiveSequence(sequence);
    }
  } catch (e) {
    logErr("setActiveSequence: " + e.message);
  }

  return sequence.name;
}

// ── Sidecar API ───────────────────────────────────────────────────────────────
async function pingHealth() {
  // No AbortSignal.timeout — UXP's fetch may not implement it. Race a timer.
  try {
    const r = await Promise.race([
      fetch(`${SIDECAR}/health`),
      new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 1500)),
    ]);
    return r.ok;
  } catch {
    return false;
  }
}

async function runAnalyze(sources, totalFrames) {
  const resp = await fetch(`${SIDECAR}/analyze`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      audio_paths:    sources.map((s) => s.path),
      offset_frames:  sources.map((s) => s.offsetFrames),
      fps_numerator:  FPS_NUM,
      fps_denominator: FPS_DEN,
      total_frames:   totalFrames,
    }),
  });
  if (!resp.ok) {
    throw new Error(`sidecar ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
  }
  return resp.json();
}

async function openSidecar() {
  // Try to open start.command (macOS) via the file system. The plugin lives at
  // <repo>/panel/ so the start script is at <repo>/sidecar/start.command.
  try {
    const pluginFolder = await fsp.getPluginFolder();
    const nativePath   = pluginFolder.nativePath; // property, not a method (UXP Entry)
    if (!nativePath) throw new Error("plugin folder has no nativePath");
    // Strip last path component to get the repo root.
    const repoRoot  = nativePath.replace(/\/[^/]+\/?$/, "");
    const startPath = `${repoRoot}/sidecar/start.command`;
    await uxp.shell.openPath(startPath);
    logInfo("Opened sidecar/start.command in Terminal — wait a moment then retry.");
  } catch (e) {
    logInfo("Could not auto-open start script: " + e.message);
    logInfo("Start manually:");
    logInfo("  cd <repo>/sidecar");
    logInfo("  ../.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765");
  }
}

// ── Main pipeline ─────────────────────────────────────────────────────────────
async function runPipeline() {
  if (state.running) return;
  state.running = true;
  setRunning(true);
  hideHint();

  try {
    // 1. Detect sources (re-detect every run so changes to the sequence are
    //    picked up without needing a separate Detect button press).
    logInfo("Detecting sources…");
    setProgress("Detecting sources…", null);
    const det = await detectSourcesFromSequence();
    state.sources     = det.sources;
    state.totalFrames = det.totalFrames;
    renderCamList(det.sources);

    for (const s of det.sources) {
      logInfo(`  cam${s.camera} "${s.name}"  offset ${s.offsetFrames}f`);
    }
    logInfo(`  ${det.sources.length} cameras, ${det.totalFrames} frames, target V${det.target + 1}`);

    // 2. Analyze
    logInfo("Sending audio to sidecar…");
    setProgress("Analyzing audio…", null);
    const map = await runAnalyze(det.sources, det.totalFrames);
    logInfo(`Cut map received: ${map.cuts.length} cuts`);

    // 3. Apply
    logInfo(`Applying ${map.cuts.length} cuts to a cloned sequence…`);
    const seqName = await applyCutMap(
      map.cuts,
      map.total_frames,
      det,
      (msg, frac) => setProgress(msg, 0.4 + frac * 0.6)
    );

    setProgress("Done", 1.0);
    logOk(`Applied to "${seqName}". ${map.cuts.length} cuts, zero-drift method A.`);

    // Task 3 — cosmetic gap fix: setActiveSequence makes the clone API-active
    // but does NOT open its timeline in the program monitor. Tell the user.
    showHint(seqName);

  } catch (e) {
    logErr(e.message || String(e));
    setProgress("", 0);
    $progressWrap.style.display = "none";
  } finally {
    state.running = false;
    setRunning(false);
  }
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function setSidecarStatus(ok) {
  state.sidecarOk = ok;
  $sidecarDot.className   = "dot" + (ok ? " online" : "");
  $sidecarLabel.textContent = ok ? "Sidecar online" : "Sidecar offline";
  $sidecarLabel.className   = ok ? "online" : "";
  if (ok) resetStartButton(); // sidecar came up — clear any "Starting…" state
  updateRunButton();
}

let startResetTimer = null;
function resetStartButton() {
  clearTimeout(startResetTimer);
  $btnStart.textContent = "Start";
  $btnStart.disabled = state.running;
}

function renderCamList(sources) {
  if (!sources || !sources.length) {
    $camList.innerHTML = '<div class="cam-placeholder">No sources detected</div>';
    return;
  }
  $camList.innerHTML = sources.map((s) => `
    <div class="cam-row">
      <span class="cam-badge">C${s.camera}</span>
      <span class="cam-name" title="${s.path}">${s.name}</span>
      <span class="cam-offset">${s.offsetFrames}f</span>
    </div>
  `).join("");
}

function updateRunButton() {
  $btnRun.disabled = !(state.sidecarOk && !state.running);
}

function setRunning(running) {
  $btnDetect.disabled = running;
  $btnStart.disabled  = running;
  updateRunButton();
  if (running) {
    $progressWrap.style.display = "block";
  }
}

function setProgress(label, frac) {
  $progressLabel.textContent = label;
  if (frac === null) {
    // indeterminate
    $progressFill.style.width = "";
    $progressFill.classList.add("indeterminate");
  } else {
    $progressFill.classList.remove("indeterminate");
    $progressFill.style.width = Math.round(frac * 100) + "%";
  }
}

// Task 3 — cosmetic gap: surface the open-sequence instruction prominently
// after the pipeline completes. setActiveSequence changes the API-active
// sequence but Premiere's program monitor stays on the original until the
// user double-clicks the new sequence in the Project panel.
function showHint(seqName) {
  $openHint.innerHTML =
    `✓ Done — <strong>${seqName}</strong> is ready.<br>` +
    `Double-click it in the <strong>Project panel</strong> to open the timeline.`;
  $openHint.style.display = "block";
}

function hideHint() {
  $openHint.style.display = "none";
}

// ── Sidecar health poll ───────────────────────────────────────────────────────
// Poll every 3 s. Cache stays warm (< 5 s interval) and the status dot
// updates without user action.
async function pollSidecar() {
  const ok = await pingHealth();
  if (ok !== state.sidecarOk) setSidecarStatus(ok);
}

setInterval(pollSidecar, 3000);
pollSidecar(); // immediate first check

// ── Event handlers ────────────────────────────────────────────────────────────
$btnStart.addEventListener("click", async () => {
  $btnStart.textContent = "Starting…";
  $btnStart.disabled = true;
  // If the sidecar never comes up (blocked permission, missing venv), give
  // the button back after 20 s so the user can retry.
  clearTimeout(startResetTimer);
  startResetTimer = setTimeout(resetStartButton, 20000);
  logInfo("Trying to open sidecar/start.command…");
  await openSidecar();
});

$btnDetect.addEventListener("click", async () => {
  // Queued clicks dispatch even if the button was disabled after the click
  // was generated — state check is the real guard (found in smoke test:
  // a rapid second click ran Detect concurrently with the pipeline and
  // mutated the FPS globals mid-apply).
  if (state.running) return;
  $btnDetect.disabled = true;
  hideHint();
  try {
    logInfo("Detecting sources…");
    const det = await detectSourcesFromSequence();
    state.sources     = det.sources;
    state.totalFrames = det.totalFrames;
    renderCamList(det.sources);
    for (const s of det.sources)
      logOk(`cam${s.camera} "${s.name}"  offset ${s.offsetFrames}f`);
    logInfo(`${det.sources.length} cameras · ${det.totalFrames} frames · target V${det.target + 1}`);
    logInfo(`FPS: ${FPS_NUM}/${FPS_DEN}`);
    updateRunButton();
  } catch (e) {
    logErr(e.message || String(e));
  } finally {
    $btnDetect.disabled = false;
  }
});

$btnRun.addEventListener("click", () => {
  runPipeline().catch((e) => logErr("UNCAUGHT: " + (e?.message ?? String(e))));
});

document.getElementById("btnClearLog").addEventListener("click", () => {
  $log.textContent = "";
  logLines = [];
});

logInfo("Vibe Splice M2 panel loaded.");
logInfo("1. Click Detect Sources to read the active sequence.");
logInfo("2. Start the sidecar if the dot is red.");
logInfo("3. Click Analyze & Apply.");
