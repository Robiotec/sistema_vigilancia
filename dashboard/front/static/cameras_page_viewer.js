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
    ppt: "DETECCIÓN DE PPT",
    hands_helmet: "DETECCIÓN MANOS CASCO",
  };
  let activeCameraName = "";
  let cameraEventsRequestToken = 0;
  let cameraEventsRefreshTimer = 0;

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

  function renderCameraEvents(items, { emptyMessage = "No hay eventos recientes para esta cámara." } = {}) {
    const feed = document.getElementById("camera-events-feed");
    if (!feed) return;
    const events = Array.isArray(items) ? items : [];
    if (!events.length) {
      feed.innerHTML = `
        <article class="face-preview-item face-preview-empty">
          <div class="face-preview-copy">
            <strong>Sin eventos</strong>
            <span>${escapeHtml(emptyMessage)}</span>
          </div>
        </article>
      `;
      return;
    }

    feed.innerHTML = events.map((item) => {
      const cropPath = String(item.crop_path || "").trim();
      const imageUrl = cropPath ? `/api/camera-event-crop?path=${encodeURIComponent(cropPath)}` : "";
      const imageAlt = item.event_type === "person" ? "Foto de rostro de visitante" : "Foto de placa detectada";
      const rows = Array.isArray(item.rows) ? item.rows : [];
      const rowsHtml = rows.map((row) => `
        <strong>${escapeHtml(row.label)}:</strong>
        <span>${escapeHtml(row.value)}</span>
      `).join("");
      return `
        <article class="face-preview-item" data-camera-event-type="${escapeHtml(item.event_type || "")}">
          ${imageUrl
            ? `<img class="face-preview-image" src="${imageUrl}" alt="${escapeHtml(imageAlt)}" loading="lazy" />`
            : `<span class="face-preview-avatar">${escapeHtml(String(item.event_type || "?").slice(0, 2).toUpperCase())}</span>`}
          <div class="face-preview-copy">
            <strong>${escapeHtml(item.display_title || "Evento detectado")}</strong>
            <span>${escapeHtml(formatTimestamp(item.timestamp))}</span>
            ${rowsHtml}
          </div>
        </article>
      `;
    }).join("");
  }

  async function loadCameraEvents(cameraName) {
    const normalizedName = String(cameraName || "").trim();
    const feed = document.getElementById("camera-events-feed");
    if (!feed) return;
    if (!normalizedName) {
      renderCameraEvents([], { emptyMessage: "Selecciona una cámara para cargar resultados recientes de personas y placas." });
      return;
    }

    const requestToken = ++cameraEventsRequestToken;
    renderCameraEvents([], { emptyMessage: "Cargando eventos..." });
    try {
      const response = await fetch(`/api/camera-events?camera_name=${encodeURIComponent(normalizedName)}&limit=8`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (requestToken !== cameraEventsRequestToken) return;
      const items = Array.isArray(payload) ? payload : Array.isArray(payload.items) ? payload.items : [];
      renderCameraEvents(items);
    } catch (error) {
      if (requestToken !== cameraEventsRequestToken) return;
      renderCameraEvents([], { emptyMessage: "No se pudieron cargar los eventos de esta cámara." });
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
    }, 3000);
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

  function inferenceTypeForCamera(cameraName) {
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

    if (!cameraId) return;
    try {
      await fetch(`/api/cameras/${encodeURIComponent(cameraId)}/inference`, {
        method: "PATCH",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ hacer_inferencia: nextEnabled }),
      });
    } catch (error) {}
  }

  function setInferenceState(cameraName, enabled) {
    const normalizedName = String(cameraName || "").trim();
    if (!normalizedName) return;
    const state = loadInferenceState();
    state[normalizedName] = Boolean(enabled);
    saveInferenceState(state);
    syncInferenceButtons(normalizedName, Boolean(enabled));
  }

  async function persistCameraInference(cameraName, enabled) {
    const normalizedName = String(cameraName || "").trim();
    const camera = cameraByName(normalizedName);
    const cameraId = String((camera && (camera.camera_id || camera.id || camera.source_id)) || "").trim();
    setInferenceState(normalizedName, enabled);
    if (!cameraId) return;
    try {
      await fetch(`/api/cameras/${encodeURIComponent(cameraId)}/inference`, {
        method: "PATCH",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ hacer_inferencia: Boolean(enabled) }),
      });
    } catch (error) {}
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
    frame.src = largeViewerUrl(normalizedName, resolvedInferenceType);
    frame.title = `Visor ${label}`;
    frame.loading = "eager";
    frame.allow = "autoplay; fullscreen; picture-in-picture";
    frame.referrerPolicy = "strict-origin-when-cross-origin";
    frame.setAttribute("allowfullscreen", "");

    const shell = document.createElement("section");
    shell.className = "camera-card cameras-page-large-card is-active is-web-viewer";
    shell.setAttribute("aria-label", `Vista ampliada ${label}`);
    shell.appendChild(frame);

    primaryView.replaceChildren(shell);
    primaryView.classList.remove("is-empty");
    activeCameraName = normalizedName;
    syncInferenceToolbar(normalizedName, resolvedInferenceType);
    void loadCameraEvents(normalizedName);
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
    renderCamera(activeCameraName, { inferenceType: nextType });
    await persistCameraInference(activeCameraName, nextType !== "none");
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
    renderCameraEvents([], { emptyMessage: "Selecciona una cámara para cargar resultados recientes de personas y placas." });

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
