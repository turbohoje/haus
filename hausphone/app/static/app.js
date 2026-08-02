/* haus — home automation PWA client */

const SERVER = `${location.protocol}//${location.host}`;
let ws = null;
let wsRetryMs = 1000;
let state = { fan: {}, zwave: {}, wemo: {}, attic_timers: null, locks: {} };
let timerInterval = null;
let deferredInstallPrompt = null;

// ── Settings (per-device prefs in localStorage) ───────────────────────────
const APP_VERSION = document.getElementById("app-version").textContent.trim();
const PREFS_KEY = "haus-prefs";
// Bumped only when the prefs shape changes — deliberately independent of
// APP_VERSION so a routine deploy doesn't wipe toggles and card order.
const PREFS_SCHEMA = 2;
const ELEMENTS = [
  { key: "camera",        label: "Camera", pinned: true },  // always first; not orderable
  { key: "door_locks",    label: "Door Locks" },
  { key: "m_fan_light",   label: "M.Fan / M.Light" },
  { key: "lights_e_w",    label: "Lght E / Lght W" },
  { key: "attics",        label: "Attic1 / Attic2" },
  { key: "ld_floor",      label: "LD Floor" },
  { key: "water_feature", label: "Water Feature" },
  { key: "l_fire",        label: "Living Fire" },
  { key: "m_fire",        label: "Master Fire" },
  { key: "garage",        label: "Garage" },
];
const ORDERABLE = ELEMENTS.filter(el => !el.pinned);

function defaultPrefs() {
  const elements = {};
  for (const el of ELEMENTS) elements[el.key] = true;
  return {
    schema: PREFS_SCHEMA,
    version: APP_VERSION,
    elements,
    order: ORDERABLE.map(el => el.key),
  };
}

function loadPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return defaultPrefs();
    const parsed = JSON.parse(raw);
    // Abandon prefs only when their shape changes — not on every app version.
    if (parsed.schema !== PREFS_SCHEMA) return defaultPrefs();
    parsed.version = APP_VERSION;
    // Backfill any new elements added after prefs were saved.
    for (const el of ELEMENTS) {
      if (!(el.key in parsed.elements)) parsed.elements[el.key] = true;
    }
    // Drop retired keys from the saved order; new ones land at the bottom.
    const order = (parsed.order || []).filter(k => ORDERABLE.some(el => el.key === k));
    for (const el of ORDERABLE) {
      if (!order.includes(el.key)) order.push(el.key);
    }
    parsed.order = order;
    return parsed;
  } catch {
    return defaultPrefs();
  }
}

function savePrefs(p) {
  localStorage.setItem(PREFS_KEY, JSON.stringify(p));
}

function applyPrefs(p) {
  // Re-append cards in pref order (camera is outside #controls, so it stays put).
  const controls = document.getElementById("controls");
  for (const key of p.order) {
    const node = controls.querySelector(`[data-element="${key}"]`);
    if (node) controls.appendChild(node);
  }
  for (const el of ELEMENTS) {
    const node = document.querySelector(`[data-element="${el.key}"]`);
    if (!node) continue;
    node.style.display = p.elements[el.key] ? "" : "none";
  }
}

function settingsRow(el, p) {
  const row = document.createElement("div");
  row.className = el.pinned ? "settings-row pinned" : "settings-row";
  row.dataset.prefKey = el.key;
  row.innerHTML = `
    <span class="settings-handle" aria-hidden="true">${el.pinned ? "" : "&#9776;"}</span>
    <span class="settings-label"></span>
    <label class="settings-switch">
      <input type="checkbox" ${p.elements[el.key] ? "checked" : ""}>
      <span class="settings-switch-slider"></span>
    </label>`;
  row.querySelector(".settings-label").textContent = el.label;
  row.querySelector("input").addEventListener("change", e => {
    p.elements[el.key] = e.target.checked;
    savePrefs(p);
    applyPrefs(p);
  });
  if (!el.pinned) {
    row.querySelector(".settings-handle")
       .addEventListener("pointerdown", e => startDrag(e, row, p));
  }
  return row;
}

function renderSettings(p) {
  const pinned = document.getElementById("settings-pinned");
  const list = document.getElementById("settings-list");
  pinned.innerHTML = "";
  list.innerHTML = "";
  for (const el of ELEMENTS) {
    if (el.pinned) pinned.appendChild(settingsRow(el, p));
  }
  for (const key of p.order) {
    const el = ORDERABLE.find(e => e.key === key);
    if (el) list.appendChild(settingsRow(el, p));
  }
}

// ── Drag-to-reorder ───────────────────────────────────────────────────────
// Rows are swapped in the DOM as the finger crosses a neighbour's midpoint;
// `startY` is rebased by the same distance each swap so the dragged row keeps
// tracking the finger. Order is persisted on release.
let drag = null;

function startDrag(e, row, p) {
  if (!document.getElementById("settings-body").classList.contains("reordering")) return;
  e.preventDefault();
  const handle = e.currentTarget;
  handle.setPointerCapture(e.pointerId);
  handle.addEventListener("pointermove", dragMove);
  handle.addEventListener("pointerup", endDrag);
  handle.addEventListener("pointercancel", endDrag);
  drag = { row, handle, startY: e.clientY, prefs: p };
  row.classList.add("dragging");
}

function dragMove(e) {
  if (!drag) return;
  const row = drag.row;
  const list = row.parentElement;
  let dy = e.clientY - drag.startY;

  // offsetTop is layout-based, so the row's own transform doesn't skew it.
  const next = row.nextElementSibling;
  const nextShift = next ? next.offsetTop - row.offsetTop : 0;
  if (next && dy > nextShift / 2) {
    list.insertBefore(next, row);
    drag.startY += nextShift;
    dy -= nextShift;
  } else {
    const prev = row.previousElementSibling;
    const prevShift = prev ? row.offsetTop - prev.offsetTop : 0;
    if (prev && dy < -prevShift / 2) {
      list.insertBefore(row, prev);
      drag.startY -= prevShift;
      dy += prevShift;
    }
  }
  row.style.transform = `translateY(${dy}px)`;
}

function endDrag(e) {
  if (!drag) return;
  const { row, handle, prefs } = drag;
  handle.removeEventListener("pointermove", dragMove);
  handle.removeEventListener("pointerup", endDrag);
  handle.removeEventListener("pointercancel", endDrag);
  if (handle.hasPointerCapture(e.pointerId)) handle.releasePointerCapture(e.pointerId);
  row.classList.remove("dragging");
  row.style.transform = "";
  drag = null;

  prefs.order = [...document.getElementById("settings-list").children]
    .map(r => r.dataset.prefKey);
  savePrefs(prefs);
  applyPrefs(prefs);
}

const _prefs = loadPrefs();
savePrefs(_prefs);  // ensures version stamp is current
applyPrefs(_prefs);
renderSettings(_prefs);

function setReorderMode(on) {
  document.getElementById("settings-body").classList.toggle("reordering", on);
  const btn = document.getElementById("settings-reorder");
  btn.setAttribute("aria-pressed", String(on));
  btn.textContent = on ? "Done" : "Reorder";
}

document.getElementById("settings-gear")?.addEventListener("click", () => {
  document.getElementById("settings-overlay").classList.add("visible");
});
document.getElementById("settings-close")?.addEventListener("click", () => {
  document.getElementById("settings-overlay").classList.remove("visible");
  setReorderMode(false);
});
document.getElementById("settings-reorder")?.addEventListener("click", () => {
  setReorderMode(!document.getElementById("settings-body").classList.contains("reordering"));
});

// ── DOM refs ──────────────────────────────────────────────────────────────
const img          = document.getElementById("live-image");
const offlineBanner = document.getElementById("offline-banner");
const installBar   = document.getElementById("install-bar");
const installBtn   = document.getElementById("install-btn");

// ── Service Worker ────────────────────────────────────────────────────────
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(console.warn);
}

// ── Cert install prompt ───────────────────────────────────────────────────
const certBar = document.getElementById("cert-bar");
const certDismiss = document.getElementById("cert-dismiss");

if (location.protocol === "https:" && !localStorage.getItem("cert-dismissed")) {
  certBar.classList.add("visible");
}

certDismiss?.addEventListener("click", () => {
  localStorage.setItem("cert-dismissed", "1");
  certBar.classList.remove("visible");
});

// ── PWA install prompt ────────────────────────────────────────────────────
window.addEventListener("beforeinstallprompt", e => {
  e.preventDefault();
  deferredInstallPrompt = e;
  if (!window.matchMedia("(display-mode: standalone)").matches) {
    installBar.classList.add("visible");
  }
});

installBtn?.addEventListener("click", async () => {
  if (!deferredInstallPrompt) return;
  deferredInstallPrompt.prompt();
  const { outcome } = await deferredInstallPrompt.userChoice;
  if (outcome === "accepted") installBar.classList.remove("visible");
  deferredInstallPrompt = null;
});

// iOS Safari: show manual add-to-home-screen hint
const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
const isStandalone = window.matchMedia("(display-mode: standalone)").matches;
if (isIos && !isStandalone && !deferredInstallPrompt) {
  const bar = installBar;
  bar.querySelector("#install-text").textContent =
    'Install: tap Share then “Add to Home Screen”';
  bar.classList.add("visible");
  document.getElementById("install-btn").style.display = "none";
}

// ── Connectivity check ────────────────────────────────────────────────────
async function checkConnectivity() {
  try {
    const r = await fetch("/api/state", { signal: AbortSignal.timeout(3000) });
    if (r.ok) {
      offlineBanner.classList.remove("visible");
      return true;
    }
  } catch (_) {}
  offlineBanner.classList.add("visible");
  return false;
}

// ── WebSocket ─────────────────────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    wsRetryMs = 1000;
    offlineBanner.classList.remove("visible");
  };

  ws.onmessage = e => {
    const msg = JSON.parse(e.data);
    if (msg.type === "image_refresh") {
      img.src = "/image?t=" + Date.now();
    } else if (msg.type === "state") {
      mergeState(msg.data);
      renderAll();
    }
  };

  ws.onclose = () => {
    ws = null;
    checkConnectivity();
    setTimeout(connectWS, wsRetryMs);
    wsRetryMs = Math.min(wsRetryMs * 1.5, 15000);
  };

  ws.onerror = () => ws?.close();
}

// ── State management ──────────────────────────────────────────────────────
function mergeState(data) {
  if (data.fan)  Object.assign(state.fan,  data.fan);
  if (data.zwave) {
    for (const [k, v] of Object.entries(data.zwave)) {
      state.zwave[k] = Object.assign(state.zwave[k] || {}, v);
    }
  }
  if (data.wemo) {
    for (const [k, v] of Object.entries(data.wemo)) {
      state.wemo[k] = Object.assign(state.wemo[k] || {}, v);
    }
  }
  if (data.locks) {
    for (const [k, v] of Object.entries(data.locks)) {
      state.locks[k] = Object.assign(state.locks[k] || {}, v);
    }
  }
  if (data.attic_timers) {
    state.attic_timers = data.attic_timers;
  }
}

// ── API helpers ───────────────────────────────────────────────────────────
async function post(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ── Render helpers ────────────────────────────────────────────────────────
function setToggle(btn, on) {
  btn.classList.toggle("on", !!on);
  btn.textContent = on ? "ON" : "OFF";
}

function setSlider(slider, valEl, pct) {
  if (pct == null) return;
  slider.value = pct;
  valEl.textContent = pct + "%";
}

function setDot(dot, on) {
  dot.classList.toggle("on", !!on);
}

// ── Fan ───────────────────────────────────────────────────────────────────
const fanBtn        = document.getElementById("fan-toggle");
const fanLightBtn   = document.getElementById("fanlight-toggle");
const fanExpand     = document.getElementById("fan-expand");
const fanDetail     = document.getElementById("fan-detail");
const fanSpeedSlider = document.getElementById("fan-speed");
const fanSpeedVal   = document.getElementById("fan-speed-val");
const fanBrightSlider = document.getElementById("fan-bright");
const fanBrightVal  = document.getElementById("fan-bright-val");

fanBtn?.addEventListener("click", async () => {
  const on = !state.fan.fan_on;
  fanBtn.disabled = true;
  try { mergeState({ fan: await post("/api/fan/power", { on }) }); renderAll(); }
  catch(e) { console.error(e); }
  finally { fanBtn.disabled = false; }
});

fanLightBtn?.addEventListener("click", async () => {
  const on = !state.fan.light_on;
  fanLightBtn.disabled = true;
  try { mergeState({ fan: await post("/api/light/power", { on }) }); renderAll(); }
  catch(e) { console.error(e); }
  finally { fanLightBtn.disabled = false; }
});

fanExpand?.addEventListener("click", () => {
  fanDetail.classList.toggle("open");
  fanExpand.classList.toggle("open");
});

const fanLightExpand  = document.getElementById("fanlight-expand");
const fanLightDetail  = document.getElementById("fanlight-detail");
fanLightExpand?.addEventListener("click", () => {
  fanLightDetail.classList.toggle("open");
  fanLightExpand.classList.toggle("open");
});

fanSpeedSlider?.addEventListener("change", async () => {
  const pct = parseInt(fanSpeedSlider.value);
  fanSpeedVal.textContent = pct + "%";
  try { mergeState({ fan: await post("/api/fan/speed", { percent: pct }) }); renderAll(); }
  catch(e) { console.error(e); }
});
fanSpeedSlider?.addEventListener("input", () => {
  fanSpeedVal.textContent = fanSpeedSlider.value + "%";
});

fanBrightSlider?.addEventListener("change", async () => {
  const pct = parseInt(fanBrightSlider.value);
  fanBrightVal.textContent = pct + "%";
  try { mergeState({ fan: await post("/api/light/brightness", { percent: pct }) }); renderAll(); }
  catch(e) { console.error(e); }
});
fanBrightSlider?.addEventListener("input", () => {
  fanBrightVal.textContent = fanBrightSlider.value + "%";
});

// ── Zwave lights ───────────────────────────────────────────────────────────
function bindZwave(deviceKey, btnId) {
  const btn = document.getElementById(btnId);
  btn?.addEventListener("click", async () => {
    const on = !state.zwave[deviceKey]?.on;
    btn.disabled = true;
    try { mergeState({ zwave: await post(`/api/zwave/${deviceKey}/power`, { on }) }); renderAll(); }
    catch(e) { console.error(e); }
    finally { btn.disabled = false; }
  });
}
bindZwave("light_west", "zwave-west-toggle");
bindZwave("light_east", "zwave-east-toggle");
bindZwave("attic1", "zwave-attic1-toggle");
bindZwave("attic2", "zwave-attic2-toggle");
bindZwave("ld_floor", "zwave-ld-floor-toggle");
bindZwave("l_fire", "zwave-l-fire-toggle");
bindZwave("m_fire", "zwave-m-fire-toggle");

// ── Garage door (slide to activate) ───────────────────────────────────────
const garageSlide = document.getElementById("garage-slide");
const garageWrap  = garageSlide?.parentElement;
const ARM_THRESHOLD = 90;
let garageFiring = false;

function resetGarageSlide() {
  if (!garageSlide) return;
  garageSlide.value = 0;
  garageWrap.classList.remove("armed");
}

garageSlide?.addEventListener("input", () => {
  const v = parseInt(garageSlide.value);
  garageWrap.classList.toggle("armed", v >= ARM_THRESHOLD);
});

async function fireGarage() {
  if (garageFiring) return;
  garageFiring = true;
  const on = !state.zwave.garage?.on;
  try {
    mergeState({ zwave: await post("/api/zwave/garage/power", { on }) });
    renderAll();
  } catch (e) {
    console.error(e);
  } finally {
    garageFiring = false;
    resetGarageSlide();
  }
}

// `change` fires on release for range inputs across desktop and mobile;
// covers the case where the user lets go and the value sticks at >=90.
garageSlide?.addEventListener("change", () => {
  if (parseInt(garageSlide.value) >= ARM_THRESHOLD) {
    fireGarage();
  } else {
    resetGarageSlide();
  }
});

// ── Door locks ─────────────────────────────────────────────────────────────
const LOCK_ICON = { locked: "\u{1F512}", unlocked: "\u{1F513}", unknown: "❓" };
const LOCK_WORD = { locked: "LOCKED", unlocked: "UNLOCKED", unknown: "UNKNOWN" };

const locksGrid        = document.getElementById("locks-grid");
const lockPicker       = document.getElementById("lock-picker");
const locksExpand      = document.getElementById("locks-expand");
const locksDetail      = document.getElementById("locks-detail");
const lockSlideWrap    = document.getElementById("lock-slide-wrap");
const lockSlide        = document.getElementById("lock-slide");
const lockActuateLabel = document.getElementById("lock-actuate-label");
const locksSummary     = document.getElementById("locks-summary");
const locksDot         = document.getElementById("locks-dot");

const LOCK_ARM_THRESHOLD = 90;
let selectedLock = null;
let lockFiring = false;
let locksBuilt = false;

locksExpand?.addEventListener("click", () => {
  locksDetail.classList.toggle("open");
  locksExpand.classList.toggle("open");
});

// Build the per-door chips (status) + picker buttons once, when state arrives.
function buildLocksUI() {
  const keys = Object.keys(state.locks);
  if (locksBuilt || keys.length === 0) return;
  locksGrid.innerHTML = "";
  lockPicker.innerHTML = "";
  for (const key of keys) {
    const label = state.locks[key].label || key;

    const chip = document.createElement("div");
    chip.className = "lock-chip";
    chip.dataset.lock = key;
    chip.innerHTML =
      '<span class="lock-chip-icon"></span>' +
      '<span class="lock-chip-name"></span>' +
      '<span class="lock-chip-state"></span>';
    chip.querySelector(".lock-chip-name").textContent = label;
    locksGrid.appendChild(chip);

    const pick = document.createElement("button");
    pick.className = "lock-pick";
    pick.dataset.lock = key;
    pick.textContent = label;
    pick.addEventListener("click", () => selectLock(key));
    lockPicker.appendChild(pick);
  }
  locksBuilt = true;
}

function selectLock(key) {
  selectedLock = key;
  lockPicker.querySelectorAll(".lock-pick").forEach(b => {
    b.classList.toggle("selected", b.dataset.lock === key);
  });
  lockSlideWrap.hidden = false;
  resetLockSlide();
  updateLockActuateLabel();
}

function updateLockActuateLabel() {
  if (!selectedLock) {
    lockActuateLabel.textContent = "Select a door above";
    return;
  }
  const l = state.locks[selectedLock];
  const name = l?.label || selectedLock;
  const status = l?.status || "unknown";
  const action = status === "locked" ? "slide to unlock" : "slide to lock";
  lockActuateLabel.textContent = `${name} is ${LOCK_WORD[status]} · ${action}`;
}

function resetLockSlide() {
  if (!lockSlide) return;
  lockSlide.value = 0;
  lockSlideWrap.classList.remove("armed");
}

lockSlide?.addEventListener("input", () => {
  lockSlideWrap.classList.toggle("armed", parseInt(lockSlide.value) >= LOCK_ARM_THRESHOLD);
});

async function fireLock() {
  if (!selectedLock || lockFiring) return;
  lockFiring = true;
  const cur = state.locks[selectedLock]?.status;
  // slide toggles: locked -> unlock; unlocked/unknown -> lock (securing is the safe default)
  const locked = cur !== "locked";
  try {
    mergeState({ locks: await post(`/api/lock/${selectedLock}`, { locked }) });
    renderAll();
  } catch (e) {
    console.error(e);
  } finally {
    lockFiring = false;
    resetLockSlide();
  }
}

// `change` fires on release for range inputs; fire if the user let go past the arm point.
lockSlide?.addEventListener("change", () => {
  if (parseInt(lockSlide.value) >= LOCK_ARM_THRESHOLD) fireLock();
  else resetLockSlide();
});

function renderLocks() {
  buildLocksUI();
  const locks = state.locks;
  let unlocked = 0, unknown = 0, total = 0;
  for (const [key, l] of Object.entries(locks)) {
    total++;
    const status = l.status || "unknown";
    if (status === "unlocked") unlocked++;
    else if (status !== "locked") unknown++;
    const chip = locksGrid.querySelector(`.lock-chip[data-lock="${key}"]`);
    if (chip) {
      chip.classList.remove("locked", "unlocked", "unknown");
      chip.classList.add(status);
      chip.querySelector(".lock-chip-icon").textContent = LOCK_ICON[status];
      chip.querySelector(".lock-chip-state").textContent = LOCK_WORD[status];
    }
  }
  const alert = unlocked + unknown > 0;
  if (locksSummary) {
    if (!total) {
      locksSummary.textContent = "";
    } else if (!alert) {
      locksSummary.textContent = "All secured";
    } else {
      const parts = [];
      if (unlocked) parts.push(`${unlocked} unlocked`);
      if (unknown) parts.push(`${unknown} unknown`);
      locksSummary.textContent = parts.join(" · ");
    }
    locksSummary.classList.toggle("alert", alert);
  }
  if (locksDot) {
    locksDot.classList.toggle("on", total > 0 && !alert);
    locksDot.classList.toggle("alert", alert);
  }
  updateLockActuateLabel();
}

// ── WeMo ──────────────────────────────────────────────────────────────────
function bindWemo(deviceName, btnId, badgeId) {
  const btn   = document.getElementById(btnId);
  const badge = document.getElementById(badgeId);
  btn?.addEventListener("click", async () => {
    const on = !state.wemo[deviceName]?.on;
    btn.disabled = true;
    try { mergeState({ wemo: await post(`/api/wemo/${deviceName}/power`, { on }) }); renderAll(); }
    catch(e) { console.error(e); }
    finally { btn.disabled = false; }
  });
}
bindWemo("water_feature", "wemo-water-toggle", "wemo-water-timer");

// ── Timer countdown display ───────────────────────────────────────────────
function renderTimerBadge(badgeId, rem) {
  const badge = document.getElementById(badgeId);
  if (!badge) return;
  if (rem != null && rem > 0) {
    const h = Math.floor(rem / 3600);
    const m = Math.floor((rem % 3600) / 60);
    const s = rem % 60;
    badge.textContent = h > 0
      ? `auto-off ${h}h ${m}m`
      : `auto-off ${m}m ${s.toString().padStart(2,"0")}s`;
    badge.classList.add("visible");
  } else {
    badge.classList.remove("visible");
  }
}

function updateTimers() {
  for (const [name, dev] of Object.entries(state.wemo)) {
    renderTimerBadge(`wemo-${name.replace(/_/g, "-")}-timer`, dev?.timer_remaining);
  }
  for (const [name, dev] of Object.entries(state.zwave)) {
    renderTimerBadge(`zwave-${name.replace(/_/g, "-")}-timer`, dev?.timer_remaining);
  }
}

// ── Attic timers (delay-on + off-timer) ───────────────────────────────────
const atticExpand = document.getElementById("attic-expand");
const atticDetail = document.getElementById("attic-detail");
const atticDelayOnAttic1 = document.getElementById("attic-delay-on-attic1");
const atticDelayOnAttic2 = document.getElementById("attic-delay-on-attic2");
const atticDelayOnSlider = document.getElementById("attic-delay-on-slider");
const atticDelayOnVal = document.getElementById("attic-delay-on-val");
const atticDelayOnRemaining = document.getElementById("attic-delay-on-remaining");
const atticOffTimerEnable = document.getElementById("attic-off-timer-enable");
const atticOffTimerSlider = document.getElementById("attic-off-timer-slider");
const atticOffTimerVal = document.getElementById("attic-off-timer-val");
const atticOffTimerRemaining = document.getElementById("attic-off-timer-remaining");

atticExpand?.addEventListener("click", () => {
  atticDetail.classList.toggle("open");
  atticExpand.classList.toggle("open");
});

function formatMinutes(min) {
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

function formatRemaining(sec) {
  if (sec == null) return "";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return h > 0
    ? `${h}h ${m}m ${s.toString().padStart(2,"0")}s`
    : `${m}m ${s.toString().padStart(2,"0")}s`;
}

function readDelayOnFans() {
  const fans = [];
  if (atticDelayOnAttic1.checked) fans.push("attic1");
  if (atticDelayOnAttic2.checked) fans.push("attic2");
  return fans;
}

async function postAtticDelayOn(armed, fans, durationSeconds) {
  try {
    const r = await post("/api/attic/delay-on", {
      armed, fans, duration_seconds: durationSeconds,
    });
    state.attic_timers = Object.assign(state.attic_timers || {}, r);
    renderAtticTimers();
  } catch (e) { console.error(e); }
}

async function postAtticOffTimer(armed, durationSeconds) {
  try {
    const r = await post("/api/attic/off-timer", {
      armed, duration_seconds: durationSeconds,
    });
    state.attic_timers = Object.assign(state.attic_timers || {}, r);
    renderAtticTimers();
  } catch (e) { console.error(e); }
}

atticDelayOnSlider?.addEventListener("input", () => {
  atticDelayOnVal.textContent = formatMinutes(parseInt(atticDelayOnSlider.value));
});
atticDelayOnSlider?.addEventListener("change", () => {
  const fans = readDelayOnFans();
  if (fans.length === 0) return;  // nothing selected; ignore
  const seconds = parseInt(atticDelayOnSlider.value) * 60;
  postAtticDelayOn(true, fans, seconds);
});

function onDelayOnFansChanged() {
  const fans = readDelayOnFans();
  const armed = state.attic_timers?.delay_on?.armed;
  if (fans.length === 0) {
    if (armed) postAtticDelayOn(false, [], 0);
    return;
  }
  if (armed) {
    // Re-arm with current slider duration; fresh countdown.
    const seconds = parseInt(atticDelayOnSlider.value) * 60;
    postAtticDelayOn(true, fans, seconds);
  }
  // Otherwise: not armed yet — wait for slider release.
}
atticDelayOnAttic1?.addEventListener("change", onDelayOnFansChanged);
atticDelayOnAttic2?.addEventListener("change", onDelayOnFansChanged);

atticOffTimerSlider?.addEventListener("input", () => {
  atticOffTimerVal.textContent = formatMinutes(parseInt(atticOffTimerSlider.value));
});
atticOffTimerSlider?.addEventListener("change", () => {
  if (!atticOffTimerEnable.checked) return;
  const seconds = parseInt(atticOffTimerSlider.value) * 60;
  postAtticOffTimer(true, seconds);
});
atticOffTimerEnable?.addEventListener("change", () => {
  if (atticOffTimerEnable.checked) {
    const seconds = parseInt(atticOffTimerSlider.value) * 60;
    postAtticOffTimer(true, seconds);
  } else {
    postAtticOffTimer(false, 0);
  }
});

function renderAtticTimers() {
  const t = state.attic_timers;
  if (!t) return;

  const d = t.delay_on;
  if (d) {
    if (d.armed) {
      atticDelayOnAttic1.checked = d.fans.includes("attic1");
      atticDelayOnAttic2.checked = d.fans.includes("attic2");
      const min = Math.max(1, Math.round((d.duration_seconds || 0) / 60));
      atticDelayOnSlider.value = min;
      atticDelayOnVal.textContent = formatMinutes(min);
    } else if (state._delayOnPrevArmed) {
      // Timer just fired (or got disarmed remotely): clear the per-fan UI so
      // stale checkmarks don't linger. We do NOT clobber checkboxes during
      // pre-arm config (when prev was already false).
      atticDelayOnAttic1.checked = false;
      atticDelayOnAttic2.checked = false;
    }
    atticDelayOnRemaining.textContent = d.armed ? formatRemaining(d.remaining) : "";
    state._delayOnPrevArmed = d.armed;
  }

  const o = t.off_timer;
  if (o) {
    if (o.armed) {
      atticOffTimerEnable.checked = true;
      const min = Math.max(1, Math.round((o.duration_seconds || 0) / 60));
      atticOffTimerSlider.value = min;
      atticOffTimerVal.textContent = formatMinutes(min);
    } else {
      atticOffTimerEnable.checked = false;
    }
    atticOffTimerRemaining.textContent = o.armed ? formatRemaining(o.remaining) : "";
  }
}

// ── Render all ────────────────────────────────────────────────────────────
function renderAll() {
  const f = state.fan;
  setToggle(fanBtn, f.fan_on);
  setToggle(fanLightBtn, f.light_on);
  setDot(document.getElementById("fan-dot"), f.fan_on);
  setDot(document.getElementById("fanlight-dot"), f.light_on);
  setSlider(fanSpeedSlider, fanSpeedVal, f.fan_speed);
  setSlider(fanBrightSlider, fanBrightVal, f.light_brightness);

  const v = state.zwave;
  setToggle(document.getElementById("zwave-west-toggle"), v.light_west?.on);
  setToggle(document.getElementById("zwave-east-toggle"), v.light_east?.on);
  setToggle(document.getElementById("zwave-attic1-toggle"), v.attic1?.on);
  setToggle(document.getElementById("zwave-attic2-toggle"), v.attic2?.on);
  setToggle(document.getElementById("zwave-ld-floor-toggle"), v.ld_floor?.on);
  setToggle(document.getElementById("zwave-l-fire-toggle"), v.l_fire?.on);
  setToggle(document.getElementById("zwave-m-fire-toggle"), v.m_fire?.on);
  setDot(document.getElementById("zwave-west-dot"), v.light_west?.on);
  setDot(document.getElementById("zwave-east-dot"), v.light_east?.on);
  setDot(document.getElementById("zwave-attic1-dot"), v.attic1?.on);
  setDot(document.getElementById("zwave-attic2-dot"), v.attic2?.on);
  setDot(document.getElementById("zwave-ld-floor-dot"), v.ld_floor?.on);
  setDot(document.getElementById("zwave-l-fire-dot"), v.l_fire?.on);
  setDot(document.getElementById("zwave-m-fire-dot"), v.m_fire?.on);
  setDot(document.getElementById("zwave-garage-dot"), v.garage?.on);
  const garageStateEl = document.getElementById("zwave-garage-state");
  if (garageStateEl) {
    garageStateEl.textContent = v.garage?.on ? "OPEN" : "CLOSED";
    garageStateEl.classList.toggle("on", !!v.garage?.on);
  }

  const wf = state.wemo.water_feature;
  setToggle(document.getElementById("wemo-water-toggle"), wf?.on);
  setDot(document.getElementById("wemo-water-dot"), wf?.on);
  updateTimers();
  renderAtticTimers();
  renderLocks();
}

// ── Init ──────────────────────────────────────────────────────────────────
(async () => {
  const online = await checkConnectivity();
  if (online) {
    const data = await fetch("/api/state").then(r => r.json()).catch(() => ({}));
    mergeState(data);
    renderAll();
  }
  connectWS();

  // Timer display refreshes every second
  setInterval(() => {
    for (const dev of Object.values(state.wemo)) {
      if (dev?.timer_remaining != null && dev.timer_remaining > 0) {
        dev.timer_remaining = Math.max(0, dev.timer_remaining - 1);
      }
    }
    for (const dev of Object.values(state.zwave)) {
      if (dev?.timer_remaining != null && dev.timer_remaining > 0) {
        dev.timer_remaining = Math.max(0, dev.timer_remaining - 1);
      }
    }
    const at = state.attic_timers;
    if (at?.delay_on?.armed && at.delay_on.remaining > 0) {
      at.delay_on.remaining = Math.max(0, at.delay_on.remaining - 1);
    }
    if (at?.off_timer?.armed && at.off_timer.remaining > 0) {
      at.off_timer.remaining = Math.max(0, at.off_timer.remaining - 1);
    }
    updateTimers();
    renderAtticTimers();
  }, 1000);
})();
