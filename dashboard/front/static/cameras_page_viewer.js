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
