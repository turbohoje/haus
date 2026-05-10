/* haus — home automation PWA client */

const SERVER = `${location.protocol}//${location.host}`;
let ws = null;
let wsRetryMs = 1000;
let state = { fan: {}, vera: {}, wemo: {}, attic_timers: null };
let timerInterval = null;
let deferredInstallPrompt = null;

// ── Settings (per-device prefs in localStorage) ───────────────────────────
const APP_VERSION = document.getElementById("app-version").textContent.trim();
const PREFS_KEY = "haus-prefs";
const ELEMENTS = [
  { key: "camera",        label: "Camera" },
  { key: "m_fan_light",   label: "M.Fan / M.Light" },
  { key: "lights_e_w",    label: "Lght E / Lght W" },
  { key: "attics",        label: "Attic1 / Attic2" },
  { key: "ld_floor",      label: "LD Floor" },
  { key: "water_feature", label: "Water Feature" },
  { key: "l_fire",        label: "Living Fire" },
  { key: "m_fire",        label: "Master Fire" },
  { key: "garage",        label: "Garage" },
];

function defaultPrefs() {
  const elements = {};
  for (const el of ELEMENTS) elements[el.key] = true;
  return { version: APP_VERSION, elements };
}

function loadPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return defaultPrefs();
    const parsed = JSON.parse(raw);
    // Abandon prefs on version change — breaking changes are not migrated yet.
    if (parsed.version !== APP_VERSION) return defaultPrefs();
    // Backfill any new elements added after prefs were saved.
    for (const el of ELEMENTS) {
      if (!(el.key in parsed.elements)) parsed.elements[el.key] = true;
    }
    return parsed;
  } catch {
    return defaultPrefs();
  }
}

function savePrefs(p) {
  localStorage.setItem(PREFS_KEY, JSON.stringify(p));
}

function applyPrefs(p) {
  for (const el of ELEMENTS) {
    const node = document.querySelector(`[data-element="${el.key}"]`);
    if (!node) continue;
    node.style.display = p.elements[el.key] ? "" : "none";
  }
}

function renderSettings(p) {
  const list = document.getElementById("settings-list");
  list.innerHTML = "";
  for (const el of ELEMENTS) {
    const row = document.createElement("div");
    row.className = "settings-row";
    const checked = p.elements[el.key] ? "checked" : "";
    row.innerHTML = `
      <span class="settings-label"></span>
      <label class="settings-switch">
        <input type="checkbox" data-pref-key="${el.key}" ${checked}>
        <span class="settings-switch-slider"></span>
      </label>`;
    row.querySelector(".settings-label").textContent = el.label;
    list.appendChild(row);
  }
  list.querySelectorAll('input[type="checkbox"]').forEach(input => {
    input.addEventListener("change", () => {
      p.elements[input.dataset.prefKey] = input.checked;
      savePrefs(p);
      applyPrefs(p);
    });
  });
}

const _prefs = loadPrefs();
savePrefs(_prefs);  // ensures version stamp is current
applyPrefs(_prefs);
renderSettings(_prefs);

document.getElementById("settings-gear")?.addEventListener("click", () => {
  document.getElementById("settings-overlay").classList.add("visible");
});
document.getElementById("settings-close")?.addEventListener("click", () => {
  document.getElementById("settings-overlay").classList.remove("visible");
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
  if (data.vera) {
    for (const [k, v] of Object.entries(data.vera)) {
      state.vera[k] = Object.assign(state.vera[k] || {}, v);
    }
  }
  if (data.wemo) {
    for (const [k, v] of Object.entries(data.wemo)) {
      state.wemo[k] = Object.assign(state.wemo[k] || {}, v);
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

// ── Vera lights ───────────────────────────────────────────────────────────
function bindVera(deviceKey, btnId) {
  const btn = document.getElementById(btnId);
  btn?.addEventListener("click", async () => {
    const on = !state.vera[deviceKey]?.on;
    btn.disabled = true;
    try { mergeState({ vera: await post(`/api/vera/${deviceKey}/power`, { on }) }); renderAll(); }
    catch(e) { console.error(e); }
    finally { btn.disabled = false; }
  });
}
bindVera("light_west", "vera-west-toggle");
bindVera("light_east", "vera-east-toggle");
bindVera("attic1", "vera-attic1-toggle");
bindVera("attic2", "vera-attic2-toggle");
bindVera("ld_floor", "vera-ld-floor-toggle");
bindVera("l_fire", "vera-l-fire-toggle");
bindVera("m_fire", "vera-m-fire-toggle");

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
  const on = !state.vera.garage?.on;
  try {
    mergeState({ vera: await post("/api/vera/garage/power", { on }) });
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
  for (const [name, dev] of Object.entries(state.vera)) {
    renderTimerBadge(`vera-${name.replace(/_/g, "-")}-timer`, dev?.timer_remaining);
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

  const v = state.vera;
  setToggle(document.getElementById("vera-west-toggle"), v.light_west?.on);
  setToggle(document.getElementById("vera-east-toggle"), v.light_east?.on);
  setToggle(document.getElementById("vera-attic1-toggle"), v.attic1?.on);
  setToggle(document.getElementById("vera-attic2-toggle"), v.attic2?.on);
  setToggle(document.getElementById("vera-ld-floor-toggle"), v.ld_floor?.on);
  setToggle(document.getElementById("vera-l-fire-toggle"), v.l_fire?.on);
  setToggle(document.getElementById("vera-m-fire-toggle"), v.m_fire?.on);
  setDot(document.getElementById("vera-west-dot"), v.light_west?.on);
  setDot(document.getElementById("vera-east-dot"), v.light_east?.on);
  setDot(document.getElementById("vera-attic1-dot"), v.attic1?.on);
  setDot(document.getElementById("vera-attic2-dot"), v.attic2?.on);
  setDot(document.getElementById("vera-ld-floor-dot"), v.ld_floor?.on);
  setDot(document.getElementById("vera-l-fire-dot"), v.l_fire?.on);
  setDot(document.getElementById("vera-m-fire-dot"), v.m_fire?.on);
  setDot(document.getElementById("vera-garage-dot"), v.garage?.on);
  const garageStateEl = document.getElementById("vera-garage-state");
  if (garageStateEl) {
    garageStateEl.textContent = v.garage?.on ? "OPEN" : "CLOSED";
    garageStateEl.classList.toggle("on", !!v.garage?.on);
  }

  const wf = state.wemo.water_feature;
  setToggle(document.getElementById("wemo-water-toggle"), wf?.on);
  setDot(document.getElementById("wemo-water-dot"), wf?.on);
  updateTimers();
  renderAtticTimers();
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
    for (const dev of Object.values(state.vera)) {
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
