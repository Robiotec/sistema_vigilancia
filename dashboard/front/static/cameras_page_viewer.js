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

  // Per-camera inference VIEW state (local only, no DB update)
  const inferenceViewState = new Map();

  function inferenceViewPreviewUrl(cameraName) {
    const t = new URL("/api/camera-preview-frame", window.location.origin);
    t.searchParams.set("camera_name", cameraName);
    t.searchParams.set("inference", "1");
    return `${t.pathname}${t.search}`;
  }

  function normalViewPreviewUrl(cameraName) {
    const t = new URL("/api/camera-preview-frame", window.location.origin);
    t.searchParams.set("camera_name", cameraName);
    return `${t.pathname}${t.search}`;
  }

  const INFERENCE_UNAVAILABLE_SRCDOC = [
    "<!doctype html><html><head><meta charset='utf-8'>",
    "<style>html,body{height:100%;margin:0;background:#050709;color:#d7dee8;",
    "font:700 13px/1.5 system-ui,sans-serif;display:grid;place-items:center;",
    "text-align:center;padding:16px;box-sizing:border-box}</style></head>",
    "<body>El video de Inferencia no está habilitado para está cámara</body></html>",
  ].join("");

  async function checkInferenceStreamAvailable(cameraName) {
    try {
      const resp = await fetch(
        `/api/camera-viewer-url?camera_name=${encodeURIComponent(cameraName)}&inference=1`,
        { credentials: "same-origin", headers: { Accept: "application/json" } },
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
    } else {
      btn.classList.remove("is-active", "is-unavailable", "is-loading");
      btn.setAttribute("aria-pressed", "false");
      btn.setAttribute("aria-label", "Activar la inferencia");
      btn.title = "Activar la inferencia";
      if (label) label.textContent = "Activar inferencia";
    }
  }

  async function handleInferenceViewToggle(btn, frame, cameraName) {
    const currentlyActive = Boolean(inferenceViewState.get(cameraName));
    if (currentlyActive) {
      inferenceViewState.set(cameraName, false);
      syncInferenceViewBtn(btn, "normal");
      frame.removeAttribute("srcdoc");
      frame.src = normalViewPreviewUrl(cameraName);
      return;
    }
    btn.classList.add("is-loading");
    btn.disabled = true;
    const available = await checkInferenceStreamAvailable(cameraName);
    btn.disabled = false;
    btn.classList.remove("is-loading");
    inferenceViewState.set(cameraName, true);
    if (!available) {
      frame.srcdoc = INFERENCE_UNAVAILABLE_SRCDOC;
      syncInferenceViewBtn(btn, "unavailable");
    } else {
      frame.removeAttribute("srcdoc");
      frame.src = inferenceViewPreviewUrl(cameraName);
      syncInferenceViewBtn(btn, "active");
    }
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

  function cameraEventHtml(item, key) {
    const cropPath = String(item.crop_path || "").trim();
    const videoPath = String(item.video_path || "").trim();
    const imageUrl = cropPath ? `/api/camera-event-crop?path=${encodeURIComponent(cropPath)}` : "";
    const videoUrl = videoPath ? `/api/camera-event-video?path=${encodeURIComponent(videoPath)}` : "";
    const imageAlt = item.event_type === "person" ? "Foto de rostro de visitante" : "Foto de placa detectada";
    const rows = Array.isArray(item.rows) ? item.rows : [];
    const modalRowsHtml = rows.map((row) => `
      <strong>${escapeHtml(row.label)}:</strong>
      <span>${escapeHtml(row.value)}</span>
    `).join("");
    const rowDuration = cameraEventRowValue(rows, ["duration", "duración", "duracion"]);
    const timestampLabel = cameraEventRowValue(rows, ["timestamp", "fecha", "hora"]) || formatTimestamp(item.timestamp);
    const durationLabel = rowDuration ? formatDuration(rowDuration.replace(/\s*s\.?$/i, "")) : "Sin duración";
    const timestampNumber = Number(item.timestamp);
    const timestampDatetime = Number.isFinite(timestampNumber) && timestampNumber > 0
      ? new Date(timestampNumber * 1000).toISOString()
      : "";
    const mediaHtml = videoUrl
      ? `<video class="face-preview-video event-card__thumb" muted preload="metadata" playsinline><source src="${videoUrl}" type="video/mp4" /></video>`
      : imageUrl
        ? `<img class="face-preview-image event-card__thumb" src="${imageUrl}" alt="${escapeHtml(imageAlt)}" loading="lazy" />`
        : `<span class="face-preview-avatar event-card__thumb">${escapeHtml(String(item.event_type || "?").slice(0, 2).toUpperCase())}</span>`;
    return `
      <article
        class="face-preview-item event-card"
        data-camera-event-key="${escapeHtml(key)}"
        data-camera-event-type="${escapeHtml(item.event_type || "")}"
        ${videoUrl ? `data-camera-event-video-url="${escapeHtml(videoUrl)}" data-camera-event-title="${escapeHtml(item.display_title || "Video detectado")}" data-camera-event-meta="${escapeHtml(modalRowsHtml)}" role="button" tabindex="0"` : ""}
      >
        ${mediaHtml}
        <div class="face-preview-copy event-card__content">
          <time class="event-card__time" datetime="${escapeHtml(timestampDatetime)}">
            ${escapeHtml(timestampLabel)}
          </time>
          <span class="event-card__duration">Duración: ${escapeHtml(durationLabel)}</span>
        </div>
      </article>
    `;
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

  function bindEventVideoModal() {
    const feed = document.getElementById("camera-events-feed");
    const modal = document.getElementById("event-video-modal");
    if (!feed || !modal) return;
    feed.addEventListener("click", (event) => {
      const card = event.target instanceof Element
        ? event.target.closest("[data-camera-event-video-url]")
        : null;
      if (!card) return;
      openEventVideoModal(card);
    });
    feed.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const card = event.target instanceof Element
        ? event.target.closest("[data-camera-event-video-url]")
        : null;
      if (!card) return;
      event.preventDefault();
      openEventVideoModal(card);
    });
    ["event-video-modal-backdrop", "event-video-close"].forEach((id) => {
      const button = document.getElementById(id);
      if (button) button.addEventListener("click", closeEventVideoModal);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modal.hidden) {
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
      syncCameraEvents(items);
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
    const camera = cameraByName(cameraName);
    if (camera && (camera.inference_type || camera.tipo_inferencia)) {
      return uiInferenceTypeFromDb(camera.inference_type || camera.tipo_inferencia);
    }
    const state = loadInferenceTypes();
    return normalizeInferenceType(state[String(cameraName || "").trim()]);
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
    activeLabel.textContent = normalizedName
      ? `${String(cameraByName(normalizedName).display_name || normalizedName).toUpperCase()} · ${inferenceTypes[normalizedType]}`
      : "Selecciona una cámara";
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
    bindEventVideoModal();

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
  });
})();
