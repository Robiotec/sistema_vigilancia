import { byId, closest } from "../core/dom.js";
import { setFeedback } from "../core/feedback.js";
import { buildCameraCreatePayload, validateCameraCreatePayload } from "./admin_payload.js";

const FEEDBACK_ID = "camera-admin-feedback";

function isStandaloneRboxMode() {
  return byId("camera-admin-form")?.classList?.contains("is-rbox-mode") === true;
}

async function readError(response) {
  try {
    const payload = await response.json();
    return payload.detail || payload.error || JSON.stringify(payload);
  } catch (error) {
    return `HTTP ${response.status}`;
  }
}

async function submitCameraCreate(event) {
  const submit = byId("camera-admin-submit");
  if (!submit || submit.disabled) return;
  if (window.__ROBIOTEC_CAMERA_ADMIN_SUBMITTING__) return;
  if (isStandaloneRboxMode()) return;

  event.preventDefault();
  event.stopPropagation();

  const payload = buildCameraCreatePayload();
  const validationMessage = validateCameraCreatePayload(payload);
  if (validationMessage) {
    setFeedback(FEEDBACK_ID, validationMessage, "error");
    return;
  }

  const originalLabel = submit.textContent;
  const isEditing = Boolean(String(payload.camera_id || "").trim());
  window.__ROBIOTEC_CAMERA_ADMIN_SUBMITTING__ = true;
  submit.disabled = true;
  submit.textContent = isEditing ? "Guardando..." : "Creando...";
  setFeedback(
    FEEDBACK_ID,
    isEditing ? "Actualizando camara en la base de datos..." : "Creando camara en la base de datos...",
    "info",
  );

  try {
    const response = await fetch(isEditing ? `/api/cameras/${encodeURIComponent(payload.camera_id)}` : "/api/cameras", {
      method: isEditing ? "PUT" : "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (response.status === 401) {
      window.location.assign("/login");
      return;
    }
    if (!response.ok) {
      throw new Error(await readError(response));
    }

    setFeedback(FEEDBACK_ID, isEditing ? "Camara actualizada correctamente." : "Camara creada correctamente.", "success");
    window.setTimeout(() => window.location.reload(), 700);
  } catch (error) {
    setFeedback(FEEDBACK_ID, `No se pudo guardar la camara: ${error.message || error}`, "error");
  } finally {
    window.__ROBIOTEC_CAMERA_ADMIN_SUBMITTING__ = false;
    submit.disabled = false;
    submit.textContent = originalLabel || (isEditing ? "Guardar cambios" : "Crear camara");
  }
}

if (!window.__ROBIOTEC_CAMERA_ADMIN_FALLBACK_BOUND__) {
  window.__ROBIOTEC_CAMERA_ADMIN_FALLBACK_BOUND__ = true;
  document.addEventListener(
    "click",
    (event) => {
      const button = closest(event.target, "#camera-admin-submit");
      if (!button) return;
      if (window.__ROBIOTEC_CAMERA_ADMIN_SUBMITTING__) return;
      if (isStandaloneRboxMode()) return;

      event.preventDefault();
      event.stopImmediatePropagation();
      void submitCameraCreate(event);
    },
    true,
  );

  const form = byId("camera-admin-form");
  if (form) {
    form.addEventListener(
      "submit",
      (event) => {
        if (isStandaloneRboxMode()) return;
      event.preventDefault();
      event.stopImmediatePropagation();
        void submitCameraCreate(event);
      },
      true,
    );
  }
}
