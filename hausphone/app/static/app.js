/* haus — home automation PWA client */

const SERVER = `${location.protocol}//${location.host}`;
let ws = null;
let wsRetryMs = 1000;
let state = { fan: {}, vera: {}, wemo: {} };
let timerInterval = null;
let deferredInstallPrompt = null;

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
  if (data.vera) Object.assign(state.vera, data.vera);
  if (data.wemo) {
    for (const [k, v] of Object.entries(data.wemo)) {
      state.wemo[k] = Object.assign(state.wemo[k] || {}, v);
    }
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
    const on = !state.vera[deviceKey];
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
  const on = !state.vera.garage;
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
function updateTimers() {
  for (const [name, dev] of Object.entries(state.wemo)) {
    const badge = document.getElementById(`wemo-${name.replace(/_/g, "-")}-timer`);
    if (!badge) continue;
    const rem = dev.timer_remaining;
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
  setToggle(document.getElementById("vera-west-toggle"), v.light_west);
  setToggle(document.getElementById("vera-east-toggle"), v.light_east);
  setToggle(document.getElementById("vera-attic1-toggle"), v.attic1);
  setToggle(document.getElementById("vera-attic2-toggle"), v.attic2);
  setToggle(document.getElementById("vera-ld-floor-toggle"), v.ld_floor);
  setDot(document.getElementById("vera-west-dot"), v.light_west);
  setDot(document.getElementById("vera-east-dot"), v.light_east);
  setDot(document.getElementById("vera-attic1-dot"), v.attic1);
  setDot(document.getElementById("vera-attic2-dot"), v.attic2);
  setDot(document.getElementById("vera-ld-floor-dot"), v.ld_floor);
  setDot(document.getElementById("vera-garage-dot"), v.garage);
  const garageStateEl = document.getElementById("vera-garage-state");
  if (garageStateEl) {
    garageStateEl.textContent = v.garage ? "OPEN" : "CLOSED";
    garageStateEl.classList.toggle("on", !!v.garage);
  }

  const wf = state.wemo.water_feature;
  setToggle(document.getElementById("wemo-water-toggle"), wf?.on);
  setDot(document.getElementById("wemo-water-dot"), wf?.on);
  updateTimers();
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
    for (const [name, dev] of Object.entries(state.wemo)) {
      if (dev.timer_remaining != null && dev.timer_remaining > 0) {
        dev.timer_remaining = Math.max(0, dev.timer_remaining - 1);
      }
    }
    updateTimers();
  }, 1000);
})();
