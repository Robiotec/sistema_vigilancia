(() => {
  const config = window.__WEB_APP_CONFIG__ || {};
  const cameras = Array.isArray(config.cameras) ? config.cameras : [];
  const inferenceStorageKey = "robiotec.camera_inference_state";
  const inferenceTypeStorageKey = "robiotec.camera_inference_type";
  const inferenceTypes = {
    none: "SIN INFERENCIA",
    plates: "DETECCIÓN DE PLACAS",
    faces: "DETECCIÓN DE ROSTROS",
    access: "DETECCIÓN DE ACCESO",
    hands_helmet: "DETECCIÓN MANOS CASCO",
  };
  const inferenceTypeToDb = {
    none: "inactiva",
    plates: "placa",
    faces: "rostro",
    access: "zona",
    hands_helmet: "movimiento",
  };
  const inferenceTypeFromDb = {
    inactiva: "none",
    placas: "plates",
    placa: "plates",
    rostros: "faces",
    rostro: "faces",
    zonas: "access",
    zona: "access",
    movimientos: "hands_helmet",
    movimiento: "hands_helmet",
  };
  // === Inference view toggle styles ===
  (function () {
    if (document.getElementById("camera-infer-view-styles")) return;
    const s = document.createElement("style");
    s.id = "camera-infer-view-styles";
    s.textContent = `
.camera-infer-view-btn{position:absolute;top:8px;left:8px;z-index:2;display:inline-flex;align-items:center;gap:0;max-width:41px;overflow:hidden;white-space:nowrap;padding:3px 7px;border-radius:5px;border:1px solid rgba(255,255,255,.14);background:rgba(6,8,16,.72);color:rgba(255,255,255,.85);font:700 10px/1 system-ui,sans-serif;letter-spacing:.06em;cursor:pointer;pointer-events:auto;transition:max-width .24s ease,background .2s ease,border-color .2s ease,box-shadow .2s ease,color .2s ease}
.camera-infer-view-btn:hover,.camera-infer-view-btn:focus-visible{max-width:190px;gap:7px;background:linear-gradient(135deg,rgba(235,133,37,.96),rgba(255,184,74,.9));border-color:rgba(255,205,120,.75);color:#fff;box-shadow:0 12px 28px rgba(235,133,37,.28),0 4px 14px rgba(0,0,0,.3)}
.camera-infer-view-btn.is-active{background:linear-gradient(135deg,rgba(235,133,37,.92),rgba(255,174,55,.78));border-color:rgba(255,196,92,.62);color:#fff;box-shadow:0 0 0 1px rgba(255,255,255,.08) inset,0 8px 18px rgba(235,133,37,.24)}
.camera-infer-view-btn.is-active:hover,.camera-infer-view-btn.is-active:focus-visible{background:linear-gradient(135deg,rgba(235,133,37,1),rgba(255,210,94,.94));border-color:rgba(255,221,145,.86)}
.camera-infer-view-btn.is-unavailable{background:rgba(140,20,20,.78);border-color:rgba(220,80,80,.4);color:#fff}
.camera-infer-view-btn.is-loading{opacity:.55;cursor:wait}
.camera-infer-view-icon{position:relative;flex:0 0 25px;width:25px;height:25px}
.camera-infer-view-icon svg{position:absolute;inset:0;width:25px;height:25px;transition:opacity .18s ease,transform .24s ease}
.camera-infer-eye-open{opacity:0;transform:scale(.82) translateY(1px)}
.camera-infer-eye-closed{opacity:1;transform:scale(1)}
.camera-infer-view-btn.is-active .camera-infer-eye-open{opacity:1;transform:scale(1) translateY(0)}
.camera-infer-view-btn.is-active .camera-infer-eye-closed{opacity:0;transform:scaleY(.35) translateY(2px)}
.camera-infer-view-btn:hover .camera-infer-eye-open,.camera-infer-view-btn:focus-visible .camera-infer-eye-open{opacity:1;transform:scale(1) translateY(0)}
.camera-infer-view-btn:hover .camera-infer-eye-closed,.camera-infer-view-btn:focus-visible .camera-infer-eye-closed{opacity:0;transform:scaleY(.35) translateY(2px)}
.camera-infer-view-label{display:inline-block;max-width:0;opacity:0;transform:translateX(-8px);overflow:hidden;transition:max-width .24s ease,opacity .18s ease,transform .24s ease}
.camera-infer-view-btn:hover .camera-infer-view-label,.camera-infer-view-btn:focus-visible .camera-infer-view-label{max-width:132px;opacity:1;transform:translateX(0)}
.cameras-page-large-card{position:relative}
.cameras-page-large-card .camera-infer-view-btn{top:14px;left:14px;max-width:49px;padding:6px 12px;font-size:11px;border-radius:8px}
.cameras-page-large-card .camera-infer-view-btn:hover,.cameras-page-large-card .camera-infer-view-btn:focus-visible{max-width:216px}
.page-cameras .camera-pill-shell .camera-infer-view-btn{top:20px;left:20px}`;
    document.head.appendChild(s);
  })();

  // === Event card type styles ===
  (function () {
    if (document.getElementById("camera-event-card-styles")) return;
    const s = document.createElement("style");
    s.id = "camera-event-card-styles";
    s.textContent = `
/* ── base badge ── */
.event-card__badge{display:inline-flex;align-items:center;gap:4px;padding:2px 7px;border-radius:20px;font:700 9px/1.4 system-ui,sans-serif;letter-spacing:.07em;text-transform:uppercase;margin-bottom:5px;width:fit-content}
.event-card__badge svg{width:10px;height:10px;flex:0 0 auto}
/* ── plate – layout vertical ── */
.event-card--plate{flex-direction:column;align-items:stretch;gap:8px;border-color:rgba(59,130,246,.28);box-shadow:0 0 0 1px rgba(59,130,246,.08) inset,0 8px 22px rgba(0,0,0,.14)}
.event-card--plate:hover,.event-card--plate:focus-visible{border-color:rgba(59,130,246,.55);background:linear-gradient(180deg,rgba(59,130,246,.1),rgba(37,99,235,.04)),rgba(255,255,255,.02);box-shadow:0 0 0 1px rgba(59,130,246,.1) inset,0 0 22px rgba(59,130,246,.15),0 14px 30px rgba(0,0,0,.24)}
.event-card--plate .event-card__badge{background:rgba(59,130,246,.18);color:#93c5fd;border:1px solid rgba(59,130,246,.3)}
.event-card--plate__top{display:flex;gap:10px;align-items:flex-start}
.event-card--plate__img{width:72px;height:72px;flex:0 0 72px;object-fit:cover;border-radius:8px;border:1px solid rgba(255,255,255,.08);background:#111827}
.event-card--plate__img-placeholder{width:72px;height:72px;flex:0 0 72px;border-radius:8px;border:1px solid rgba(59,130,246,.18);background:rgba(59,130,246,.08);display:flex;align-items:center;justify-content:center;font:700 10px/1 system-ui,sans-serif;color:rgba(147,197,253,.5);letter-spacing:.05em}
.event-card--plate__main{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}
.event-card--plate__num{font:800 16px/1.2 monospace,system-ui;color:#bfdbfe;letter-spacing:.07em}
.event-card--plate__vehicle{font:500 10px/1.5 system-ui,sans-serif;color:rgba(148,163,184,.75);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.event-card--plate__time{font:400 9px/1.4 system-ui,sans-serif;color:rgba(148,163,184,.45);margin-top:2px}
/* alert flags */
.event-card--plate__flags{display:flex;flex-wrap:wrap;gap:4px}
.ec-flag{display:inline-flex;align-items:center;gap:3px;padding:2px 6px;border-radius:4px;font:700 8px/1.4 system-ui,sans-serif;letter-spacing:.05em;text-transform:uppercase}
.ec-flag--danger{background:rgba(239,68,68,.2);color:#fca5a5;border:1px solid rgba(239,68,68,.35)}
.ec-flag--warn{background:rgba(245,158,11,.18);color:#fcd34d;border:1px solid rgba(245,158,11,.3)}
.ec-flag--ok{background:rgba(16,185,129,.14);color:#6ee7b7;border:1px solid rgba(16,185,129,.25)}
.ec-flag--neutral{background:rgba(148,163,184,.1);color:rgba(148,163,184,.7);border:1px solid rgba(148,163,184,.18)}
/* detail grid */
.event-card--plate__grid{display:grid;grid-template-columns:1fr 1fr;gap:2px 8px;border-top:1px solid rgba(59,130,246,.1);padding-top:6px}
.event-card--plate__grid dt{font:600 8.5px/1.5 system-ui,sans-serif;color:rgba(148,163,184,.5);text-transform:uppercase;letter-spacing:.05em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.event-card--plate__grid dd{font:500 9.5px/1.5 system-ui,sans-serif;color:rgba(203,213,225,.8);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0}
/* ── person – layout vertical ── */
.event-card--person{flex-direction:column;align-items:stretch;gap:8px;border-color:rgba(16,185,129,.25);box-shadow:0 0 0 1px rgba(16,185,129,.07) inset,0 8px 22px rgba(0,0,0,.14)}
.event-card--person:hover,.event-card--person:focus-visible{border-color:rgba(16,185,129,.5);background:linear-gradient(180deg,rgba(16,185,129,.1),rgba(5,150,105,.04)),rgba(255,255,255,.03);box-shadow:0 0 0 1px rgba(16,185,129,.1) inset,0 0 22px rgba(16,185,129,.16),0 14px 30px rgba(0,0,0,.24)}
.event-card--person .event-card__badge{background:rgba(16,185,129,.18);color:#6ee7b7;border:1px solid rgba(16,185,129,.3)}
.event-card--person__top{display:flex;gap:10px;align-items:flex-start}
.event-card--person__img{width:72px;height:72px;flex:0 0 72px;object-fit:cover;border-radius:8px;border:1px solid rgba(255,255,255,.08);background:#111827}
.event-card--person__img-placeholder{width:72px;height:72px;flex:0 0 72px;border-radius:8px;border:1px solid rgba(16,185,129,.18);background:rgba(16,185,129,.07);display:flex;align-items:center;justify-content:center;font:700 10px/1 system-ui,sans-serif;color:rgba(110,231,183,.5);letter-spacing:.05em}
.event-card--person__main{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}
.event-card--person__name{font:700 13px/1.3 system-ui,sans-serif;color:#d1fae5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.event-card--person__time{font:400 9px/1.4 system-ui,sans-serif;color:rgba(148,163,184,.45);margin-top:2px}
.event-card--person__grid{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;border-top:1px solid rgba(16,185,129,.1);padding-top:6px}
.event-card--person__grid dt{font:600 8.5px/1.5 system-ui,sans-serif;color:rgba(148,163,184,.5);text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}
.event-card--person__grid dd{font:500 9.5px/1.5 system-ui,sans-serif;color:rgba(203,213,225,.8);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0}
/* ── motion ── */
.event-card--motion{border-color:rgba(245,158,11,.25);box-shadow:0 0 0 1px rgba(245,158,11,.07) inset,0 8px 22px rgba(0,0,0,.14)}
.event-card--motion:hover,.event-card--motion:focus-visible{border-color:rgba(245,158,11,.5);background:linear-gradient(180deg,rgba(245,158,11,.1),rgba(217,119,6,.04)),rgba(255,255,255,.03);box-shadow:0 0 0 1px rgba(245,158,11,.1) inset,0 0 22px rgba(245,158,11,.16),0 14px 30px rgba(0,0,0,.24)}
.event-card--motion .event-card__badge{background:rgba(245,158,11,.18);color:#fcd34d;border:1px solid rgba(245,158,11,.3)}
.event-card--motion .event-card__title{font:700 12px/1.3 system-ui,sans-serif;color:#fef3c7;margin-bottom:2px}
.event-card--motion .event-card__sub{font:500 10px/1.4 system-ui,sans-serif;color:rgba(148,163,184,.7)}
.event-card--motion .event-card__time{font:500 10px/1.4 system-ui,sans-serif;color:rgba(148,163,184,.55);margin-top:4px}
/* ── zone ── */
.event-card--zone{border-color:rgba(139,92,246,.25);box-shadow:0 0 0 1px rgba(139,92,246,.07) inset,0 8px 22px rgba(0,0,0,.14)}
.event-card--zone:hover,.event-card--zone:focus-visible{border-color:rgba(139,92,246,.5);background:linear-gradient(180deg,rgba(139,92,246,.1),rgba(109,40,217,.04)),rgba(255,255,255,.03);box-shadow:0 0 0 1px rgba(139,92,246,.1) inset,0 0 22px rgba(139,92,246,.16),0 14px 30px rgba(0,0,0,.24)}
.event-card--zone .event-card__badge{background:rgba(139,92,246,.18);color:#c4b5fd;border:1px solid rgba(139,92,246,.3)}
.event-card--zone .event-card__title{font:700 12px/1.3 system-ui,sans-serif;color:#ede9fe;margin-bottom:2px}
.event-card--zone .event-card__sub{font:500 10px/1.4 system-ui,sans-serif;color:rgba(148,163,184,.7)}
.event-card--zone .event-card__time{font:500 10px/1.4 system-ui,sans-serif;color:rgba(148,163,184,.55);margin-top:4px}`;
    document.head.appendChild(s);
  })();

  // Per-camera inference VIEW state (local only, no DB update)
  const inferenceViewState = new Map();
  const inferencePollingTimers = new Map();
  const INFERENCE_POLL_INTERVAL_MS = 2000;
  const INFERENCE_POLL_MAX_ATTEMPTS = 12;

  function inferenceViewPreviewUrl(cameraName, inferenceType = null) {
    const t = new URL("/api/camera-preview-frame", window.location.origin);
    t.searchParams.set("camera_name", cameraName);
    t.searchParams.set("inference", "1");
    const normalizedType = normalizeInferenceType(inferenceType || inferenceTypeForCamera(cameraName));
    if (normalizedType !== "none") {
      t.searchParams.set("inference_type", normalizedType);
    }
    t.searchParams.set("_", String(Date.now()));
    return `${t.pathname}${t.search}`;
  }

  function normalViewPreviewUrl(cameraName) {
    const t = new URL("/api/camera-preview-frame", window.location.origin);
    t.searchParams.set("camera_name", cameraName);
    return `${t.pathname}${t.search}`;
  }

const INFERENCE_UNAVAILABLE_SRCDOC = [
  "<!doctype html>",
  "<html>",
  "<head>",
  "<meta charset='utf-8'>",
  "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
  "<style>",
  "html, body {",
  "  height: 100%;",
  "  margin: 0;",
  "  background: #0b0f14;",
  "  color: #e5e7eb;",
  "  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;",
  "  display: flex;",
  "  align-items: center;",
  "  justify-content: center;",
  "}",
  ".container {",
  "  max-width: 560px;",
  "  padding: 28px 24px;",
  "  text-align: center;",
  "  background: #111827;",
  "  border: 1px solid rgba(255,255,255,0.06);",
  "  border-radius: 10px;",
  "  box-shadow: 0 10px 25px rgba(0,0,0,0.4);",
  "}",
  ".title {",
  "  font-size: 22px;",
  "  font-weight: 600;",
  "  color: #f9fafb;",
  "  margin-bottom: 10px;",
  "  letter-spacing: 0.3px;",
  "}",
  ".divider {",
  "  width: 32px;",
  "  height: 2px;",
  "  background: #374151;",
  "  margin: 0 auto 16px auto;",
  "  border-radius: 2px;",
  "}",
  ".message {",
  "  font-size: 18px;",
  "  line-height: 1.6;",
  "  color: #9ca3af;",
  "}",
  "</style>",
  "</head>",
  "<body>",
  "<div class='container'>",
  "  <div class='title'>Inferencia no disponible</div>",
  "  <div class='divider'></div>",
  "  <div class='message'>",
  "    El video de inferencia no está habilitado para esta cámara.<br>",
  "    Por favor, inténtelo nuevamente más tarde.",
  "  </div>",
  "</div>",
  "</body>",
  "</html>",
].join("");

const INFERENCE_LOADING_SRCDOC = [
  "<!doctype html>",
  "<html><head><meta charset='utf-8'>",
  "<style>",
  "html,body{height:100%;margin:0;background:#0b0f14;display:flex;align-items:center;justify-content:center}",
  ".wrap{display:flex;flex-direction:column;align-items:center;gap:14px}",
  ".ring{width:38px;height:38px;border-radius:50%;border:3px solid rgba(235,133,37,.18);border-top-color:rgba(235,133,37,.9);animation:spin .75s linear infinite}",
  "@keyframes spin{to{transform:rotate(360deg)}}",
  ".lbl{font:700 11px/1 system-ui,sans-serif;letter-spacing:.08em;color:rgba(255,255,255,.38);text-transform:uppercase}",
  "</style></head>",
  "<body><div class='wrap'>",
  "<div class='ring'></div>",
  "<span class='lbl'>Iniciando inferencia…</span>",
  "</div></body></html>",
].join("");

  async function checkInferenceStreamAvailable(cameraName, inferenceType = null) {
    try {
      const target = new URL("/api/camera-viewer-url", window.location.origin);
      target.searchParams.set("camera_name", cameraName);
      target.searchParams.set("inference", "1");
      const normalizedType = normalizeInferenceType(inferenceType || inferenceTypeForCamera(cameraName));
      if (normalizedType !== "none") {
        target.searchParams.set("inference_type", normalizedType);
      }
      target.searchParams.set("_", String(Date.now()));
      const resp = await fetch(
        `${target.pathname}${target.search}`,
        { cache: "no-store", credentials: "same-origin", headers: { Accept: "application/json" } },
      );
      const data = await resp.json();
      return Boolean(data && data.online === true && !data.error);
    } catch {
      return false;
    }
  }

  function syncInferenceViewBtn(btn, state) {
    const label = btn.querySelector(".camera-infer-view-label");
    if (state === "active") {
      btn.classList.add("is-active");
      btn.classList.remove("is-unavailable", "is-loading");
      btn.setAttribute("aria-pressed", "true");
      btn.setAttribute("aria-label", "Volver a vista normal");
      btn.title = "Volver a vista normal";
      if (label) label.textContent = "Vista normal";
    } else if (state === "unavailable") {
      btn.classList.add("is-active", "is-unavailable");
      btn.classList.remove("is-loading");
      btn.setAttribute("aria-pressed", "true");
      btn.setAttribute("aria-label", "Inferencia no disponible, volver a vista normal");
      btn.title = "Inferencia no disponible, clic para volver a vista normal";
      if (label) label.textContent = "No disponible";
    } else if (state === "loading") {
      btn.classList.add("is-active", "is-loading");
      btn.classList.remove("is-unavailable");
      btn.setAttribute("aria-pressed", "true");
      btn.setAttribute("aria-label", "Iniciando inferencia");
      btn.title = "Iniciando inferencia";
      if (label) label.textContent = "Cargando…";
    } else {
      btn.classList.remove("is-active", "is-unavailable", "is-loading");
      btn.setAttribute("aria-pressed", "false");
      btn.setAttribute("aria-label", "Activar la inferencia");
      btn.title = "Activar la inferencia";
      if (label) label.textContent = "Activar inferencia";
    }
  }

  function stopInferencePolling(cameraName) {
    const timerId = inferencePollingTimers.get(cameraName);
    if (timerId != null) {
      clearInterval(timerId);
      inferencePollingTimers.delete(cameraName);
    }
  }

  function startInferencePolling(cameraName, btn, frame) {
    stopInferencePolling(cameraName);
    let attempts = 0;
    const timerId = setInterval(async () => {
      if (!inferenceViewState.get(cameraName)) {
        stopInferencePolling(cameraName);
        return;
      }
      attempts += 1;
      const inferenceType = inferenceTypeForCamera(cameraName);
      const available = await checkInferenceStreamAvailable(cameraName, inferenceType);
      if (!inferenceViewState.get(cameraName)) {
        stopInferencePolling(cameraName);
        return;
      }
      if (available && frame.srcdoc) {
        frame.removeAttribute("srcdoc");
        frame.src = inferenceViewPreviewUrl(cameraName, inferenceType);
        syncInferenceViewBtn(btn, "active");
      } else if (!available && !frame.srcdoc) {
        frame.srcdoc = INFERENCE_LOADING_SRCDOC;
        syncInferenceViewBtn(btn, "loading");
      }
      if (!available && attempts >= INFERENCE_POLL_MAX_ATTEMPTS) {
        inferenceViewState.set(cameraName, false);
        stopInferencePolling(cameraName);
        syncInferenceViewBtn(btn, "normal");
        frame.removeAttribute("srcdoc");
        frame.src = normalViewPreviewUrl(cameraName);
      }
    }, INFERENCE_POLL_INTERVAL_MS);
    inferencePollingTimers.set(cameraName, timerId);
  }

  async function activateInferenceView(btn, frame, cameraName, inferenceType = null) {
    const resolvedInferenceType = normalizeInferenceType(inferenceType || inferenceTypeForCamera(cameraName));
    btn.classList.add("is-loading");
    btn.disabled = true;
    const available = await checkInferenceStreamAvailable(cameraName, resolvedInferenceType);
    btn.disabled = false;
    btn.classList.remove("is-loading");
    inferenceViewState.set(cameraName, true);
    if (!available) {
      frame.srcdoc = INFERENCE_LOADING_SRCDOC;
      syncInferenceViewBtn(btn, "loading");
    } else {
      frame.removeAttribute("srcdoc");
      frame.src = inferenceViewPreviewUrl(cameraName, resolvedInferenceType);
      syncInferenceViewBtn(btn, "active");
    }
    startInferencePolling(cameraName, btn, frame);
  }

  async function handleInferenceViewToggle(btn, frame, cameraName) {
    const currentlyActive = Boolean(inferenceViewState.get(cameraName));
    if (currentlyActive) {
      inferenceViewState.set(cameraName, false);
      stopInferencePolling(cameraName);
      syncInferenceViewBtn(btn, "normal");
      frame.removeAttribute("srcdoc");
      frame.src = normalViewPreviewUrl(cameraName);
      return;
    }
    await activateInferenceView(btn, frame, cameraName);
  }

  const INFER_BTN_SVG =
    '<span class="camera-infer-view-icon" aria-hidden="true">' +
    '<svg class="camera-infer-eye-closed" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" focusable="false">' +
    '<path d="M4 14.5c2.2-2.1 4.8-3.1 8-3.1s5.8 1 8 3.1"/>' +
    '<path d="M7 17l1.4-2.1"/>' +
    '<path d="M12 18v-2.6"/>' +
    '<path d="M17 17l-1.4-2.1"/>' +
    "</svg>" +
    '<svg class="camera-infer-eye-open" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" focusable="false">' +
    '<path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/>' +
    '<circle cx="12" cy="12" r="3"/>' +
    "</svg>" +
    "</span>";

  function createInferenceViewBtn(cameraName, frame) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "camera-infer-view-btn";
    btn.setAttribute("aria-pressed", "false");
    btn.setAttribute("aria-label", "Activar la inferencia");
    btn.title = "Activar la inferencia";
    btn.innerHTML = `${INFER_BTN_SVG}<span class="camera-infer-view-label">Activar inferencia</span>`;
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      void handleInferenceViewToggle(btn, frame, cameraName);
    });
    return btn;
  }

  let activeCameraName = "";
  let cameraEventsRequestToken = 0;
  let cameraEventsRefreshTimer = 0;
  const cameraEventsRefreshMs = 2000;

  function ready(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }
    callback();
  }

  function cameraNameFromTrigger(trigger) {
    if (!(trigger instanceof Element)) return "";
    const rawName = String(trigger.getAttribute("data-camera-name") || "").trim();
    if (rawName) return rawName;
    if (trigger instanceof HTMLAnchorElement) {
      try {
        return String(new URL(trigger.href, window.location.href).searchParams.get("camera") || "").trim();
      } catch (error) {}
    }
    return "";
  }

  function cameraByName(cameraName) {
    const normalizedName = String(cameraName || "").trim();
    return cameras.find((camera) => camera && camera.name === normalizedName) || { name: normalizedName };
  }

  function formatTimestamp(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return "Sin fecha";
    try {
      return new Date(numeric * 1000).toLocaleString("es-EC", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (error) {
      return String(value);
    }
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function cameraEventKey(item) {
    return [
      item.source_file,
      item.crop_path,
      item.video_path,
      item.timestamp,
      item.event_type,
      item.plate,
      item.person_id,
      item.track_id,
    ].map((value) => String(value || "").trim()).join("|");
  }

  function deduplicatePlateEvents(items) {
    const seenPlates = new Set();
    return items.filter((item) => {
      if (String(item.event_type || "").trim() !== "plate") return true;
      const plate = String(item.plate || "").trim();
      if (!plate || seenPlates.has(plate)) return false;
      seenPlates.add(plate);
      return true;
    });
  }

  function cameraEventRowValue(rows, labels) {
    const wanted = labels.map((label) => String(label).trim().toLowerCase());
    const match = rows.find((row) => wanted.includes(String(row && row.label || "").trim().toLowerCase()));
    return match ? String(match.value ?? "").trim() : "";
  }

  function formatDuration(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) {
      return String(value || "Sin duración");
    }
    const totalSeconds = Math.round(numeric);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function _eventTimestampDatetime(item) {
    const n = Number(item.timestamp);
    return Number.isFinite(n) && n > 0 ? new Date(n * 1000).toISOString() : "";
  }

  function _eventModalRows(rows) {
    return rows.map((row) => {
      const v = String(row.value || "").trim().toUpperCase();
      const isAlert = (v === "SI") && ["reportado robado", "multas pendientes", "prenda comercial", "prenda industrial",
        "prohibición enajenar", "remarcado motor", "remarcado chasis", "reserva dominio"].includes(String(row.label || "").toLowerCase().trim());
      const valStyle = isAlert ? ' style="color:#fca5a5;font-weight:800"' : "";
      return `<strong>${escapeHtml(row.label)}:</strong><span${valStyle}>${escapeHtml(row.value)}</span>`;
    }).join("");
  }

  const _PLATE_ALERT_FIELDS = new Set([
    "reportado robado", "multas pendientes", "prenda comercial", "prenda industrial",
    "prohibición enajenar", "remarcado motor", "remarcado chasis", "reserva dominio",
  ]);

  function _plateModalHtml(rows) {
    return rows.map((row) => {
      const lbl = String(row.label || "").trim();
      const val = String(row.value || "").trim();
      const isEmpty = !val || val === "Sin dato";
      const isAlert = !isEmpty && val.toUpperCase() === "SI" && _PLATE_ALERT_FIELDS.has(lbl.toLowerCase());
      const cardStyle = isAlert
        ? "background:rgba(239,68,68,.13);border:1px solid rgba(239,68,68,.3)"
        : "background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07)";
      const valColor = isAlert
        ? "color:#fca5a5;font-weight:800"
        : isEmpty
          ? "color:rgba(148,163,184,.35)"
          : "color:rgba(248,250,252,.92)";
      return `<div style="padding:9px 11px;border-radius:8px;${cardStyle}">` +
        `<div style="font:900 10px/1.18 system-ui,sans-serif;color:rgba(148,163,184,.68);text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(lbl)}</div>` +
        `<div style="font:800 15.5px/1.50 system-ui,sans-serif;${valColor};overflow-wrap:anywhere">${escapeHtml(val || "—")}</div>` +
        `</div>`;
    }).join("");
  }

  function _flagHtml(label, value) {
    const v = String(value || "").trim().toUpperCase();
    const cls = v === "SI" ? "ec-flag--danger" : v === "NO" ? "ec-flag--ok" : "ec-flag--neutral";
    return `<span class="ec-flag ${cls}">${escapeHtml(label)}: ${escapeHtml(v || "—")}</span>`;
  }

  function cameraEventHtmlPlate(item, key) {
    const rows      = Array.isArray(item.rows) ? item.rows : [];
    const rv        = (lbl) => cameraEventRowValue(rows, Array.isArray(lbl) ? lbl : [lbl]);
    const imageUrl  = item.crop_path ? `/api/camera-event-crop?path=${encodeURIComponent(String(item.crop_path))}` : "";
    const plate     = String(item.plate || rv(["placa"]) || "—").trim();
    const marca     = rv(["marca"]) || "";
    const modelo    = rv(["modelo"]) || "";
    const robado    = rv(["reportado robado"]) || "";
    const multas    = rv(["multas pendientes"]) || "";
    const datetime  = _eventTimestampDatetime(item);
    const tsLabel   = formatTimestamp(item.timestamp);
    const modalMeta = _plateModalHtml(rows);
    const interactiveAttrs = imageUrl
      ? `data-camera-event-image-url="${escapeHtml(imageUrl)}" data-camera-event-title="${escapeHtml("Placa " + plate)}" data-camera-event-primary="${escapeHtml(plate)}" data-camera-event-meta="${escapeHtml(modalMeta)}" data-camera-event-meta-layout="plate-grid" role="button" tabindex="0"`
      : "";
    const thumbHtml = imageUrl
      ? `<img class="face-preview-image event-card__thumb" src="${escapeHtml(imageUrl)}" alt="Placa ${escapeHtml(plate)}" loading="lazy" />`
      : `<span class="face-preview-avatar event-card__thumb" style="font-size:10px;color:rgba(147,197,253,.6)">PLC</span>`;
    const vehicleLine = [marca, modelo].filter(Boolean).join("\n");
    return `
      <article class="face-preview-item event-card event-card--plate" data-camera-event-key="${escapeHtml(key)}" data-camera-event-type="plate" ${interactiveAttrs}>
        ${thumbHtml}
        <div class="face-preview-copy event-card__content">
          <span class="event-card__badge">PLACA</span>
          <strong style="font:800 15px/1.2 monospace,system-ui;color:#fff;letter-spacing:.05em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(plate)}</strong>
          ${marca  ? `<span style="font:600 12px/1.3 system-ui;color:rgba(203,213,225,.9);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(marca)}</span>` : ""}
          ${modelo ? `<span style="font:500 11px/1.3 system-ui;color:rgba(148,163,184,.8);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(modelo)}</span>` : ""}
          <div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:2px">
            ${_flagHtml("Multas", multas)}
            ${_flagHtml("Reportado", robado)}
          </div>
          <time style="font:400 10px/1.4 system-ui;color:rgba(148,163,184,.5);margin-top:1px" datetime="${escapeHtml(datetime)}">${escapeHtml(tsLabel)}</time>
        </div>
      </article>`;
  }

  function cameraEventHtmlPerson(item, key) {
    const rows      = Array.isArray(item.rows) ? item.rows : [];
    const rv        = (lbl) => cameraEventRowValue(rows, Array.isArray(lbl) ? lbl : [lbl]);
    const imageUrl  = item.crop_path ? `/api/camera-event-crop?path=${encodeURIComponent(String(item.crop_path))}` : "";
    const name      = String(item.person_name || rv(["nombre"]) || "Visitante").trim();
    const cedula    = String(item.person_id || rv(["cédula", "cedula", "Cedula"]) || "").trim();
    const datetime  = _eventTimestampDatetime(item);
    const tsLabel   = formatTimestamp(item.timestamp);
    const modalRows = _eventModalRows(rows);
    const interactiveAttrs = imageUrl
      ? `data-camera-event-image-url="${escapeHtml(imageUrl)}" data-camera-event-title="${escapeHtml(name)}" data-camera-event-primary="${escapeHtml(name)}" data-camera-event-meta="${escapeHtml(modalRows)}" role="button" tabindex="0"`
      : "";
    const thumbHtml = imageUrl
      ? `<img class="face-preview-image event-card__thumb" src="${escapeHtml(imageUrl)}" alt="Foto de ${escapeHtml(name)}" loading="lazy" />`
      : `<span class="face-preview-avatar event-card__thumb" style="font-size:10px;color:rgba(110,231,183,.6)">PRS</span>`;
    return `
      <article class="face-preview-item event-card event-card--person" data-camera-event-key="${escapeHtml(key)}" data-camera-event-type="person" ${interactiveAttrs}>
        ${thumbHtml}
        <div class="face-preview-copy event-card__content">
          <span class="event-card__badge"><svg viewBox="0 0 10 10" fill="none"><circle cx="5" cy="3.5" r="2" stroke="currentColor" stroke-width="1"/><path d="M1.5 9c0-1.93 1.567-3.5 3.5-3.5S8.5 7.07 8.5 9" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>PERSONA</span>
          <strong style="font:700 14px/1.3 system-ui;color:#d1fae5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(name)}</strong>
          ${cedula ? `<span style="font:500 11px/1.4 system-ui;color:rgba(148,163,184,.8)">ID: ${escapeHtml(cedula)}</span>` : ""}
          <time style="font:400 10px/1.4 system-ui;color:rgba(148,163,184,.5);margin-top:1px" datetime="${escapeHtml(datetime)}">${escapeHtml(tsLabel)}</time>
        </div>
      </article>`;
  }

  function cameraEventHtmlMotion(item, key) {
    const rows = Array.isArray(item.rows) ? item.rows : [];
    const videoUrl = item.video_path ? `/api/camera-event-video?path=${encodeURIComponent(String(item.video_path))}` : "";
    const rowDuration = cameraEventRowValue(rows, ["duration", "duración", "duracion"]);
    const durationLabel = rowDuration ? formatDuration(rowDuration.replace(/\s*s\.?$/i, "")) : "Sin duración";
    const timestampLabel = cameraEventRowValue(rows, ["timestamp", "fecha", "hora"]) || formatTimestamp(item.timestamp);
    const datetime = _eventTimestampDatetime(item);
    const modalRows = _eventModalRows(rows);
    const interactiveAttrs = videoUrl
      ? `data-camera-event-video-url="${escapeHtml(videoUrl)}" data-camera-event-title="Movimiento detectado" data-camera-event-meta="${escapeHtml(modalRows)}" role="button" tabindex="0"`
      : "";
    const thumbHtml = videoUrl
      ? `<video class="face-preview-video event-card__thumb" muted preload="metadata" playsinline><source src="${escapeHtml(videoUrl)}" type="video/mp4" /></video>`
      : `<span class="face-preview-avatar event-card__thumb" style="font-size:9px">MOV</span>`;
    return `
      <article class="face-preview-item event-card event-card--motion" data-camera-event-key="${escapeHtml(key)}" data-camera-event-type="clips_movimiento" ${interactiveAttrs}>
        ${thumbHtml}
        <div class="face-preview-copy event-card__content" style="gap:0;overflow:hidden">
          <span class="event-card__badge"><svg viewBox="0 0 10 10" fill="none"><path d="M2 5h6M5 2l3 3-3 3" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"/></svg>MOVIMIENTO</span>
          <span class="event-card__title">Movimiento detectado</span>
          <span class="event-card__sub">Duración: ${escapeHtml(durationLabel)}</span>
          <time class="event-card__time" datetime="${escapeHtml(datetime)}">${escapeHtml(timestampLabel)}</time>
        </div>
      </article>`;
  }

  function cameraEventHtmlZone(item, key) {
    const rows = Array.isArray(item.rows) ? item.rows : [];
    const videoUrl = item.video_path ? `/api/camera-event-video?path=${encodeURIComponent(String(item.video_path))}` : "";
    const rowDuration = cameraEventRowValue(rows, ["duration", "duración", "duracion"]);
    const durationLabel = rowDuration ? formatDuration(rowDuration.replace(/\s*s\.?$/i, "")) : "Sin duración";
    const timestampLabel = cameraEventRowValue(rows, ["timestamp", "fecha", "hora"]) || formatTimestamp(item.timestamp);
    const datetime = _eventTimestampDatetime(item);
    const modalRows = _eventModalRows(rows);
    const interactiveAttrs = videoUrl
      ? `data-camera-event-video-url="${escapeHtml(videoUrl)}" data-camera-event-title="Alerta de zona" data-camera-event-meta="${escapeHtml(modalRows)}" role="button" tabindex="0"`
      : "";
    const thumbHtml = videoUrl
      ? `<video class="face-preview-video event-card__thumb" muted preload="metadata" playsinline><source src="${escapeHtml(videoUrl)}" type="video/mp4" /></video>`
      : `<span class="face-preview-avatar event-card__thumb" style="font-size:9px">ZNA</span>`;
    return `
      <article class="face-preview-item event-card event-card--zone" data-camera-event-key="${escapeHtml(key)}" data-camera-event-type="clips_zona" ${interactiveAttrs}>
        ${thumbHtml}
        <div class="face-preview-copy event-card__content" style="gap:0;overflow:hidden">
          <span class="event-card__badge"><svg viewBox="0 0 10 10" fill="none"><polygon points="5,1 9,9 1,9" stroke="currentColor" stroke-width="1" fill="none" stroke-linejoin="round"/><line x1="5" y1="4" x2="5" y2="6.5" stroke="currentColor" stroke-width="1" stroke-linecap="round"/><circle cx="5" cy="7.8" r=".5" fill="currentColor"/></svg>ZONA</span>
          <span class="event-card__title">Alerta de zona</span>
          <span class="event-card__sub">Duración: ${escapeHtml(durationLabel)}</span>
          <time class="event-card__time" datetime="${escapeHtml(datetime)}">${escapeHtml(timestampLabel)}</time>
        </div>
      </article>`;
  }

  function cameraEventHtml(item, key) {
    const type = String(item.event_type || "").trim();
    if (type === "plate") return cameraEventHtmlPlate(item, key);
    if (type === "person") return cameraEventHtmlPerson(item, key);
    if (type === "clips_movimiento") return cameraEventHtmlMotion(item, key);
    if (type === "clips_zona") return cameraEventHtmlZone(item, key);
    // fallback genérico para tipos desconocidos
    const rows = Array.isArray(item.rows) ? item.rows : [];
    const cropPath = String(item.crop_path || "").trim();
    const videoPath = String(item.video_path || "").trim();
    const imageUrl = cropPath ? `/api/camera-event-crop?path=${encodeURIComponent(cropPath)}` : "";
    const videoUrl = videoPath ? `/api/camera-event-video?path=${encodeURIComponent(videoPath)}` : "";
    const eventTitle = String(item.display_title || (videoUrl ? "Video detectado" : "Evento detectado")).trim();
    const eventPrimary = String(item.plate || item.person_name || item.person_id || item.cam_id || eventTitle).trim();
    const modalRows = _eventModalRows(rows);
    const interactiveAttrs = videoUrl
      ? `data-camera-event-video-url="${escapeHtml(videoUrl)}" data-camera-event-title="${escapeHtml(eventTitle)}" data-camera-event-meta="${escapeHtml(modalRows)}" role="button" tabindex="0"`
      : imageUrl
        ? `data-camera-event-image-url="${escapeHtml(imageUrl)}" data-camera-event-title="${escapeHtml(eventTitle)}" data-camera-event-primary="${escapeHtml(eventPrimary)}" data-camera-event-meta="${escapeHtml(modalRows)}" role="button" tabindex="0"`
        : "";
    const rowDuration = cameraEventRowValue(rows, ["duration", "duración", "duracion"]);
    const timestampLabel = cameraEventRowValue(rows, ["timestamp", "fecha", "hora"]) || formatTimestamp(item.timestamp);
    const durationLabel = rowDuration ? formatDuration(rowDuration.replace(/\s*s\.?$/i, "")) : "Sin duración";
    const timestampDatetime = _eventTimestampDatetime(item);
    const mediaHtml = videoUrl
      ? `<video class="face-preview-video event-card__thumb" muted preload="metadata" playsinline><source src="${videoUrl}" type="video/mp4" /></video>`
      : imageUrl
        ? `<img class="face-preview-image event-card__thumb" src="${imageUrl}" alt="Evento detectado" loading="lazy" />`
        : `<span class="face-preview-avatar event-card__thumb">${escapeHtml(String(type || "?").slice(0, 2).toUpperCase())}</span>`;
    return `
      <article class="face-preview-item event-card" data-camera-event-key="${escapeHtml(key)}" data-camera-event-type="${escapeHtml(type)}" ${interactiveAttrs}>
        ${mediaHtml}
        <div class="face-preview-copy event-card__content">
          <time class="event-card__time" datetime="${escapeHtml(timestampDatetime)}">${escapeHtml(timestampLabel)}</time>
          <span class="event-card__duration">Duración: ${escapeHtml(durationLabel)}</span>
        </div>
      </article>`;
  }

  function openEventImageModal(card) {
    const modal = document.getElementById("plate-file-modal");
    const title = document.getElementById("plate-file-modal-title");
    const primary = document.getElementById("plate-file-plate");
    const content = document.getElementById("plate-file-content");
    if (!modal || !content) return;
    const imageUrl = String(card.getAttribute("data-camera-event-image-url") || "").trim();
    if (!imageUrl) return;
    const label = String(card.getAttribute("data-camera-event-title") || "Evento detectado").trim();
    const primaryValue = String(card.getAttribute("data-camera-event-primary") || label).trim();
    const metaHtml = card.getAttribute("data-camera-event-meta") || "";
    const metaLayout = card.getAttribute("data-camera-event-meta-layout") || "";
    if (title) title.textContent = label;
    if (primary) primary.textContent = primaryValue;
    const metaSection = metaLayout === "plate-grid"
      ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:1.25rem">${metaHtml || ""}</div>`
      : `<div class="event-detail-meta">${metaHtml || "<span>Sin información adicional.</span>"}</div>`;
    content.innerHTML = `
      <section class="plate-file-section">
        <span class="plate-file-section-title">Imagen</span>
        <img class="event-detail-image" src="${escapeHtml(imageUrl)}" alt="${escapeHtml(label)}" />
      </section>
      <section class="plate-file-section">
        <span class="plate-file-section-title">Información</span>
        ${metaSection}
      </section>
    `;
    modal.classList.add("is-event-detail");
    modal.hidden = false;
    document.body.classList.add("is-modal-open");
  }

  function closeEventVideoModal() {
    const modal = document.getElementById("event-video-modal");
    const player = document.getElementById("event-video-player");
    const meta = document.getElementById("event-video-meta");
    if (!modal || !(player instanceof HTMLVideoElement)) return;
    player.pause();
    player.removeAttribute("src");
    player.innerHTML = "";
    player.load();
    if (meta) meta.innerHTML = "";
    modal.hidden = true;
    document.body.classList.remove("is-modal-open");
  }

  function openEventVideoModal(card) {
    const modal = document.getElementById("event-video-modal");
    const player = document.getElementById("event-video-player");
    const title = document.getElementById("event-video-modal-title");
    const meta = document.getElementById("event-video-meta");
    if (!modal || !(player instanceof HTMLVideoElement)) return;
    const videoUrl = String(card.getAttribute("data-camera-event-video-url") || "").trim();
    if (!videoUrl) return;
    const label = String(card.getAttribute("data-camera-event-title") || "Video detectado").trim();
    if (title) title.textContent = label;
    if (meta) meta.innerHTML = card.getAttribute("data-camera-event-meta") || "";
    player.innerHTML = `<source src="${escapeHtml(videoUrl)}" type="video/mp4" />`;
    modal.hidden = false;
    document.body.classList.add("is-modal-open");
    player.load();
    void player.play().catch(() => {});
  }

  function bindEventModals() {
    const feed = document.getElementById("camera-events-feed");
    const videoModal = document.getElementById("event-video-modal");
    if (!feed) return;
    feed.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target : null;
      const videoCard = target ? target.closest("[data-camera-event-video-url]") : null;
      if (videoCard) {
        openEventVideoModal(videoCard);
        return;
      }
      const imageCard = target
        ? target.closest("[data-camera-event-image-url]")
        : null;
      if (!imageCard) return;
      openEventImageModal(imageCard);
    });
    feed.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const target = event.target instanceof Element ? event.target : null;
      const videoCard = target ? target.closest("[data-camera-event-video-url]") : null;
      if (videoCard) {
        event.preventDefault();
        openEventVideoModal(videoCard);
        return;
      }
      const imageCard = target
        ? target.closest("[data-camera-event-image-url]")
        : null;
      if (!imageCard) return;
      event.preventDefault();
      openEventImageModal(imageCard);
    });
    ["event-video-modal-backdrop", "event-video-close"].forEach((id) => {
      const button = document.getElementById(id);
      if (button) button.addEventListener("click", closeEventVideoModal);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (videoModal && !videoModal.hidden) {
        closeEventVideoModal();
      }
    });
  }

  function createCameraEventNode(item, key) {
    const template = document.createElement("template");
    template.innerHTML = cameraEventHtml(item, key).trim();
    return template.content.firstElementChild;
  }

  function renderCameraEvents(items, { emptyMessage = "No hay eventos recientes para esta cámara." } = {}) {
    const feed = document.getElementById("camera-events-feed");
    if (!feed) return;
    const events = Array.isArray(items) ? items : [];
    if (!events.length) {
      feed.innerHTML = `
        <article class="face-preview-item face-preview-empty event-card event-card--empty">
          <div class="face-preview-copy event-card__content">
            <strong>Sin eventos</strong>
            <span>${escapeHtml(emptyMessage)}</span>
          </div>
        </article>
      `;
      return;
    }

    feed.innerHTML = events.map((item) => cameraEventHtml(item, cameraEventKey(item))).join("");
  }

  function syncCameraEvents(items) {
    const feed = document.getElementById("camera-events-feed");
    if (!feed) return;
    const events = Array.isArray(items) ? items : [];
    if (!events.length) {
      if (!feed.querySelector("[data-camera-event-key]")) {
        renderCameraEvents([]);
      }
      return;
    }

    feed.querySelectorAll(".face-preview-empty").forEach((item) => item.remove());
    const existingByKey = new Map();
    feed.querySelectorAll("[data-camera-event-key]").forEach((item) => {
      existingByKey.set(item.getAttribute("data-camera-event-key") || "", item);
    });

    const activeKeys = new Set();
    events.forEach((item, index) => {
      const key = cameraEventKey(item);
      activeKeys.add(key);
      let node = existingByKey.get(key);
      if (!node) {
        node = createCameraEventNode(item, key);
      }
      if (!node) return;
      const currentAtIndex = feed.children[index] || null;
      if (currentAtIndex !== node) {
        feed.insertBefore(node, currentAtIndex);
      }
    });

    feed.querySelectorAll("[data-camera-event-key]").forEach((item) => {
      if (!activeKeys.has(item.getAttribute("data-camera-event-key") || "")) {
        item.remove();
      }
    });
  }

  async function loadCameraEvents(cameraName, { reset = false } = {}) {
    const normalizedName = String(cameraName || "").trim();
    const feed = document.getElementById("camera-events-feed");
    if (!feed) return;
    if (!normalizedName) {
      renderCameraEvents([], { emptyMessage: "Selecciona una cámara para cargar resultados recientes de personas, placas y videos." });
      return;
    }

    const requestToken = ++cameraEventsRequestToken;
    if (reset || !feed.querySelector("[data-camera-event-key]")) {
      renderCameraEvents([], { emptyMessage: "Cargando eventos..." });
    }
    try {
      const response = await fetch(`/api/camera-events?camera_name=${encodeURIComponent(normalizedName)}&limit=8`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (requestToken !== cameraEventsRequestToken) return;
      const items = Array.isArray(payload) ? payload : Array.isArray(payload.items) ? payload.items : [];
      syncCameraEvents(deduplicatePlateEvents(items));
    } catch (error) {
      if (requestToken !== cameraEventsRequestToken) return;
      if (reset || !feed.querySelector("[data-camera-event-key]")) {
        renderCameraEvents([], { emptyMessage: "No se pudieron cargar los eventos de esta cámara." });
      }
    }
  }

  function scheduleCameraEventsRefresh(cameraName) {
    if (cameraEventsRefreshTimer) {
      window.clearTimeout(cameraEventsRefreshTimer);
      cameraEventsRefreshTimer = 0;
    }
    const normalizedName = String(cameraName || "").trim();
    if (!normalizedName) return;
    cameraEventsRefreshTimer = window.setTimeout(() => {
      cameraEventsRefreshTimer = 0;
      void loadCameraEvents(normalizedName).finally(() => {
        if (activeCameraName === normalizedName) {
          scheduleCameraEventsRefresh(normalizedName);
        }
      });
    }, cameraEventsRefreshMs);
  }

  function loadInferenceState() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(inferenceStorageKey) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (error) {
      return {};
    }
  }

  function saveInferenceState(state) {
    try {
      window.localStorage.setItem(inferenceStorageKey, JSON.stringify(state || {}));
    } catch (error) {}
  }

  function loadInferenceTypes() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(inferenceTypeStorageKey) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (error) {
      return {};
    }
  }

  function saveInferenceTypes(state) {
    try {
      window.localStorage.setItem(inferenceTypeStorageKey, JSON.stringify(state || {}));
    } catch (error) {}
  }

  function normalizeInferenceType(value) {
    const normalized = String(value || "").trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(inferenceTypes, normalized) ? normalized : "none";
  }

  function dbInferenceTypeForUi(value) {
    return inferenceTypeToDb[normalizeInferenceType(value)] || "inactiva";
  }

  function uiInferenceTypeFromDb(value) {
    const normalized = String(value || "").trim().toLowerCase();
    return inferenceTypeFromDb[normalized] || "none";
  }

  function inferenceTypeForCamera(cameraName) {
    const normalizedName = String(cameraName || "").trim();
    const state = loadInferenceTypes();
    if (Object.prototype.hasOwnProperty.call(state, normalizedName)) {
      return normalizeInferenceType(state[normalizedName]);
    }
    const camera = cameraByName(cameraName);
    if (camera && (camera.inference_type || camera.tipo_inferencia)) {
      return uiInferenceTypeFromDb(camera.inference_type || camera.tipo_inferencia);
    }
    return "none";
  }

  function saveInferenceTypeForCamera(cameraName, inferenceType) {
    const normalizedName = String(cameraName || "").trim();
    if (!normalizedName) return;
    const state = loadInferenceTypes();
    state[normalizedName] = normalizeInferenceType(inferenceType);
    saveInferenceTypes(state);
  }

  function isInferenceEnabled(cameraName) {
    const camera = cameraByName(cameraName);
    const state = loadInferenceState();
    if (Object.prototype.hasOwnProperty.call(state, cameraName)) {
      return Boolean(state[cameraName]);
    }
    return Boolean(camera && camera.hacer_inferencia === true);
  }

  function syncInferenceButtons(cameraName, enabled) {
    const normalizedName = String(cameraName || "").trim();
    document.querySelectorAll(`[data-camera-inference-name="${CSS.escape(normalizedName)}"]`).forEach((button) => {
      button.classList.toggle("is-enabled", enabled);
      button.classList.remove("is-updating");
      button.disabled = false;
      button.setAttribute("aria-pressed", enabled ? "true" : "false");
      button.setAttribute("aria-label", `${enabled ? "Desactivar" : "Activar"} inferencia en ${normalizedName}`);
      button.title = enabled ? "Inferencia activa" : "Inferencia inactiva";
    });
  }

  async function toggleInference(button) {
    const cameraName = String(button && button.getAttribute("data-camera-inference-name") || "").trim();
    if (!cameraName) return;
    const cameraId = String(button.getAttribute("data-camera-inference-id") || "").trim();
    const nextEnabled = !isInferenceEnabled(cameraName);
    button.classList.add("is-updating");
    button.disabled = true;

    const state = loadInferenceState();
    state[cameraName] = nextEnabled;
    saveInferenceState(state);
    syncInferenceButtons(cameraName, nextEnabled);

    // Switch the pill preview iframe between normal and inference stream
    const pillFrame = button.closest(".camera-pill-shell")
      ? button.closest(".camera-pill-shell").querySelector(".camera-pill-frame")
      : null;
    if (pillFrame) {
      if (nextEnabled) {
        checkInferenceStreamAvailable(cameraName).then((available) => {
          inferenceViewState.set(cameraName, true);
          if (!available) {
            pillFrame.srcdoc = INFERENCE_UNAVAILABLE_SRCDOC;
          } else {
            pillFrame.removeAttribute("srcdoc");
            pillFrame.src = inferenceViewPreviewUrl(cameraName);
          }
        });
      } else {
        inferenceViewState.set(cameraName, false);
        pillFrame.removeAttribute("srcdoc");
        pillFrame.src = normalViewPreviewUrl(cameraName);
      }
    }

    if (!cameraId) return;
    try {
      await fetch(`/api/cameras/${encodeURIComponent(cameraId)}/inference`, {
        method: "PATCH",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          hacer_inferencia: nextEnabled,
          camera_name: cameraName,
          inference_type: nextEnabled ? dbInferenceTypeForUi(inferenceTypeForCamera(cameraName)) : "inactiva",
        }),
      });
    } catch (error) {}

    if (cameraName === activeCameraName) {
      renderCamera(cameraName, { persistUrl: false });
    }
  }

  function setInferenceState(cameraName, enabled) {
    const normalizedName = String(cameraName || "").trim();
    if (!normalizedName) return;
    const state = loadInferenceState();
    state[normalizedName] = Boolean(enabled);
    saveInferenceState(state);
    syncInferenceButtons(normalizedName, Boolean(enabled));
  }

  async function persistCameraInference(cameraName, inferenceType) {
    const normalizedName = String(cameraName || "").trim();
    const camera = cameraByName(normalizedName);
    const normalizedType = normalizeInferenceType(inferenceType);
    const enabled = normalizedType !== "none";
    setInferenceState(normalizedName, enabled);
    try {
      const response = await fetch("/api/camera-inference-by-name", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          hacer_inferencia: Boolean(enabled),
          camera_name: normalizedName,
          inference_type: dbInferenceTypeForUi(normalizedType),
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error((payload && (payload.detail || payload.error)) || "camera_inference_update_failed");
      }
      const updatedCamera = payload && typeof payload.camera === "object" ? payload.camera : null;
      if (camera) {
        camera.hacer_inferencia = updatedCamera ? Boolean(updatedCamera.hacer_inferencia) : Boolean(enabled);
        camera.inference_type = updatedCamera && updatedCamera.inference_type
          ? updatedCamera.inference_type
          : dbInferenceTypeForUi(normalizedType);
        camera.tipo_inferencia = camera.inference_type;
      }
    } catch (error) {
      const activeLabel = document.getElementById("camera-inference-active");
      if (activeLabel) {
        activeLabel.textContent = `${normalizedName.toUpperCase()} · NO SE PUDO GUARDAR`;
      }
      throw error;
    }
  }

  function largeViewerUrl(cameraName, inferenceType = "none") {
    const target = new URL("/api/camera-preview-frame", window.location.origin);
    target.searchParams.set("camera_name", cameraName);
    const normalizedType = normalizeInferenceType(inferenceType);
    if (normalizedType !== "none") {
      target.searchParams.set("inference", "1");
      target.searchParams.set("inference_type", normalizedType);
    }
    return `${target.pathname}${target.search}`;
  }

  function syncInferenceToolbar(cameraName, inferenceType = "none") {
    const toolbar = document.getElementById("camera-inference-toolbar");
    const select = document.getElementById("camera-inference-type");
    const loadButton = document.getElementById("camera-inference-load");
    const activeLabel = document.getElementById("camera-inference-active");
    const normalizedName = String(cameraName || "").trim();
    const normalizedType = normalizeInferenceType(inferenceType);
    if (!toolbar || !select || !loadButton || !activeLabel) return;

    select.value = normalizedType;
    select.disabled = !normalizedName;
    loadButton.disabled = !normalizedName;
    toolbar.dataset.inferenceType = normalizedType;
    document.body.dataset.cameraInferenceType = normalizedType;
    if (!normalizedName) {
      activeLabel.textContent = "Selecciona una cámara";
      return;
    }
    const cameraLabel = String(cameraByName(normalizedName).display_name || normalizedName).toUpperCase();
    if (normalizedType !== "none") {
      activeLabel.textContent = "";
      activeLabel.append(document.createTextNode(`${cameraLabel} · `));
      const inferenceLabel = document.createElement("span");
      inferenceLabel.className = "camera-inference-selected";
      inferenceLabel.textContent = inferenceTypes[normalizedType];
      activeLabel.append(inferenceLabel);
      return;
    }
    activeLabel.textContent = "";
    activeLabel.append(document.createTextNode(`${cameraLabel} · `));
    const noInferenceLabel = document.createElement("span");
    noInferenceLabel.className = "camera-inference-no-inference";
    noInferenceLabel.textContent = inferenceTypes[normalizedType];
    activeLabel.append(noInferenceLabel);
  }

  function setUrlCamera(cameraName) {
    if (!window.history || typeof window.history.replaceState !== "function") return;
    try {
      const target = new URL(window.location.href);
      target.searchParams.set("camera", cameraName);
      window.history.replaceState(null, "", target.toString());
    } catch (error) {}
  }

  function renderCamera(cameraName, { persistUrl = true, inferenceType = null } = {}) {
    const switcher = document.getElementById("camera-switcher");
    const primaryView = document.getElementById("primary-view");
    if (!switcher || !primaryView) return;

    const normalizedName = String(cameraName || "").trim();
    if (!normalizedName) return;

    const camera = cameraByName(normalizedName);
    const label = String(camera.display_name || camera.name || normalizedName).trim();
    const resolvedInferenceType = normalizeInferenceType(inferenceType || inferenceTypeForCamera(normalizedName));
    const currentFrame = primaryView.querySelector(".cameras-page-large-frame");
    if (activeCameraName === normalizedName && currentFrame && !inferenceViewState.get(normalizedName)) {
      syncInferenceToolbar(normalizedName, resolvedInferenceType);
      switcher.querySelectorAll("[data-camera-name], .camera-pill[href]").forEach((item) => {
        item.classList.toggle("is-active", cameraNameFromTrigger(item) === normalizedName);
      });
      if (persistUrl) {
        setUrlCamera(normalizedName);
      }
      return;
    }
    if (activeCameraName && activeCameraName !== normalizedName) {
      stopInferencePolling(activeCameraName);
      inferenceViewState.delete(activeCameraName);
    }

    const frame = document.createElement("iframe");
    frame.className = "camera-web-frame cameras-page-large-frame";
    frame.src = largeViewerUrl(normalizedName, "none");
    frame.title = `Visor ${label}`;
    frame.loading = "eager";
    frame.allow = "autoplay; fullscreen; picture-in-picture";
    frame.referrerPolicy = "strict-origin-when-cross-origin";
    frame.setAttribute("allowfullscreen", "");

    const shell = document.createElement("section");
    shell.className = "camera-card cameras-page-large-card is-active is-web-viewer";
    shell.setAttribute("aria-label", `Vista ampliada ${label}`);
    shell.appendChild(frame);
    inferenceViewState.delete(normalizedName);
    shell.appendChild(createInferenceViewBtn(normalizedName, frame));

    primaryView.replaceChildren(shell);
    primaryView.classList.remove("is-empty");
    activeCameraName = normalizedName;
    syncInferenceToolbar(normalizedName, resolvedInferenceType);
    void loadCameraEvents(normalizedName, { reset: true });
    scheduleCameraEventsRefresh(normalizedName);
    switcher.querySelectorAll("[data-camera-name], .camera-pill[href]").forEach((item) => {
      item.classList.toggle("is-active", cameraNameFromTrigger(item) === normalizedName);
    });
    if (persistUrl) {
      setUrlCamera(normalizedName);
    }
  }

  window.__ROBIOTEC_CAMERA_PAGE_VIEWER_OPEN__ = (cameraName) => {
    renderCamera(cameraName);
    return false;
  };

  async function loadSelectedInference() {
    const select = document.getElementById("camera-inference-type");
    if (!select || !activeCameraName) return;
    const nextType = normalizeInferenceType(select.value);
    saveInferenceTypeForCamera(activeCameraName, nextType);
    try {
      await persistCameraInference(activeCameraName, nextType);
      syncInferenceToolbar(activeCameraName, nextType);
      const primaryView = document.getElementById("primary-view");
      const btn = primaryView && primaryView.querySelector(".camera-infer-view-btn");
      const frame = primaryView && primaryView.querySelector(".cameras-page-large-frame");
      if (btn && frame) {
        const currentlyActive = Boolean(inferenceViewState.get(activeCameraName));
        if (nextType !== "none" && !currentlyActive) {
          void activateInferenceView(btn, frame, activeCameraName, nextType);
        } else if (nextType !== "none" && currentlyActive) {
          stopInferencePolling(activeCameraName);
          frame.srcdoc = INFERENCE_LOADING_SRCDOC;
          syncInferenceViewBtn(btn, "loading");
          void activateInferenceView(btn, frame, activeCameraName, nextType);
        } else if (nextType === "none" && currentlyActive) {
          void handleInferenceViewToggle(btn, frame, activeCameraName);
        }
      }
    } catch (error) {
      saveInferenceTypeForCamera(activeCameraName, inferenceTypeForCamera(activeCameraName));
    }
  }

  function requestedCameraName() {
    try {
      return String(new URL(window.location.href).searchParams.get("camera") || "").trim();
    } catch (error) {
      return "";
    }
  }

  ready(() => {
    const switcher = document.getElementById("camera-switcher");
    if (!switcher) return;

    switcher.querySelectorAll("[data-camera-inference-name]").forEach((button) => {
      const cameraName = String(button.getAttribute("data-camera-inference-name") || "").trim();
      if (cameraName) {
        syncInferenceButtons(cameraName, isInferenceEnabled(cameraName));
      }
    });

    const inferenceLoad = document.getElementById("camera-inference-load");
    if (inferenceLoad) {
      inferenceLoad.addEventListener("click", () => {
        void loadSelectedInference();
      });
    }

    const inferenceTypeSelect = document.getElementById("camera-inference-type");
    if (inferenceTypeSelect) {
      inferenceTypeSelect.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        void loadSelectedInference();
      });
    }
    syncInferenceToolbar("", "none");
    renderCameraEvents([], { emptyMessage: "Selecciona una cámara para cargar resultados recientes de personas, placas y videos." });
    bindEventModals();

    switcher.addEventListener("click", (event) => {
      const inferenceButton = event.target instanceof Element
        ? event.target.closest("[data-camera-inference-name]")
        : null;
      if (inferenceButton) {
        event.preventDefault();
        event.stopImmediatePropagation();
        void toggleInference(inferenceButton);
        return;
      }
      const trigger = event.target instanceof Element
        ? event.target.closest("[data-camera-name], .camera-pill[href]")
        : null;
      const cameraName = cameraNameFromTrigger(trigger);
      if (!cameraName) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      renderCamera(cameraName);
    }, true);

    switcher.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const trigger = event.target instanceof Element
        ? event.target.closest("[data-camera-name], .camera-pill[href]")
        : null;
      const cameraName = cameraNameFromTrigger(trigger);
      if (!cameraName) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      renderCamera(cameraName);
    }, true);

    const initialCameraName = requestedCameraName();
    if (initialCameraName) {
      renderCamera(initialCameraName, { persistUrl: false });
    }

    startSnapshotRefresh();
  });

  const SNAPSHOT_REFRESH_MS = 60000;
  const visibleSnapshotImages = new WeakSet();

  function refreshSnapshots() {
    document.querySelectorAll(".camera-pill-snapshot[data-snapshot-url]").forEach((img) => {
      const base = img.getAttribute("data-snapshot-url");
      if (!base) return;
      if (document.visibilityState === "hidden") return;
      if (!visibleSnapshotImages.has(img)) return;
      const fresh = new Image();
      fresh.onload = () => {
        img.src = fresh.src;
        img.classList.remove("is-error");
      };
      fresh.onerror = () => {
        img.classList.add("is-error");
      };
      fresh.src = `${base}&_t=${Date.now()}`;
    });
  }

  function startSnapshotRefresh() {
    const snapshotImages = document.querySelectorAll(".camera-pill-snapshot[data-snapshot-url]");
    const observer = "IntersectionObserver" in window
      ? new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            visibleSnapshotImages.add(entry.target);
          } else {
            visibleSnapshotImages.delete(entry.target);
          }
        });
      }, { root: document.querySelector(".camera-switcher") || null, threshold: 0.08 })
      : null;
    snapshotImages.forEach((img) => {
      img.addEventListener("error", () => img.classList.add("is-error"), { once: false });
      img.addEventListener("load", () => img.classList.remove("is-error", "is-loading"), { once: false });
      if (observer) {
        observer.observe(img);
      } else {
        visibleSnapshotImages.add(img);
      }
    });
    setInterval(refreshSnapshots, SNAPSHOT_REFRESH_MS);
  }
})();
