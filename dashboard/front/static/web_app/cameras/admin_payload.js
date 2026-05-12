import { byId, fieldRawValue, fieldValue } from "../core/dom.js";

export function buildRtspUrl() {
  const brand = fieldValue("camera-admin-brand").toLowerCase();
  const ip = fieldValue("camera-admin-rtsp-ip");
  const port = fieldValue("camera-admin-rtsp-port") || "554";
  const channel = fieldValue("camera-admin-rtsp-channel") || "1";
  const user = fieldValue("camera-admin-stream-user");
  const password = fieldRawValue("camera-admin-stream-password");
  const substream = fieldValue("camera-admin-rtsp-substream") === "true";
  const auth = user || password ? `${encodeURIComponent(user)}:${encodeURIComponent(password)}@` : "";

  if (!ip) return "";
  if (brand === "hikvision") {
    return `rtsp://${auth}${ip}:${port}/Streaming/Channels/${channel}${substream ? "02" : "01"}`;
  }
  if (brand === "dahua") {
    return `rtsp://${auth}${ip}:${port}/cam/realmonitor?channel=${channel}&subtype=${substream ? "1" : "0"}`;
  }
  return `rtsp://${auth}${ip}:${port}/stream1`;
}

export function uniqueCameraCode(name) {
  return String(name || "CAM")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "-")
    .replace(/[^A-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || `CAM-${Date.now()}`;
}

export function buildCameraCreatePayload() {
  const name = fieldValue("camera-admin-name");
  const form = byId("camera-admin-form");
  const editingCameraId = String(form?.dataset?.editingCameraId || "").trim();
  const code = fieldValue("camera-admin-code") || uniqueCameraCode(name);
  const typeCode = fieldValue("camera-admin-type");
  const rboxMode = fieldValue("camera-admin-rbox-mode");
  const substream = fieldValue("camera-admin-rtsp-substream") === "true";
  const activeInput = byId("camera-admin-active");

  return {
    camera_id: editingCameraId,
    nombre: name,
    organizacion_id: fieldValue("camera-admin-organization"),
    tipo_camara_codigo: typeCode,
    protocolo_codigo: "rtsp",
    url_rtsp: buildRtspUrl(),
    ip_camaras_fijas: fieldValue("camera-admin-rtsp-ip"),
    puerto: fieldValue("camera-admin-rtsp-port") || "554",
    canal: fieldValue("camera-admin-rtsp-channel") || "1",
    calidad: substream ? "substream" : "mainstream",
    substream,
    codigo_unico: code,
    marca: fieldValue("camera-admin-brand") || "custom",
    modelo: fieldValue("camera-admin-model"),
    usuario_stream: fieldValue("camera-admin-stream-user"),
    password_stream: fieldRawValue("camera-admin-stream-password"),
    vehiculo_id: fieldValue("camera-admin-vehicle"),
    vehiculo_posicion: fieldValue("camera-admin-vehicle-position"),
    usa_rbox: rboxMode !== "no",
    rbox_id: rboxMode === "existing" ? fieldValue("camera-admin-rbox-select") : "",
    rbox_nombre: rboxMode === "create" ? fieldValue("camera-admin-rbox-create-name") : "",
    rbox_ip_server: rboxMode === "create" ? fieldValue("camera-admin-rbox-create-ip") : "",
    activa: activeInput ? activeInput.checked !== false : true,
  };
}

export function validateCameraCreatePayload(payload) {
  if (!payload.nombre) return "Ingresa un nombre para la camara.";
  if (!payload.organizacion_id) return "Selecciona una organizacion para la camara.";
  if (!payload.tipo_camara_codigo) return "Selecciona el tipo de camara.";
  if (payload.tipo_camara_codigo !== "custom" && !payload.ip_camaras_fijas) {
    return "Ingresa la IP o host de la camara.";
  }
  if (payload.usa_rbox && !payload.rbox_id && !payload.rbox_nombre) {
    return "Selecciona una RBox o escribe el nombre de la nueva RBox.";
  }
  return "";
}
