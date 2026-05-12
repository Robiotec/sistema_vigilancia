const API_BASE_URL = window.ROBIOTEC_CONFIG?.apiBaseUrl || "http://127.0.0.1:8003";

const state = {
  token: localStorage.getItem("robiotec.jwt") || "",
  user: null,
  route: "overview",
  selectedStream: "",
  streamStatus: null,
  streamToken: null,
  resources: {},
  loadingResource: "",
  formFeedback: "",
};

const modules = [
  { id: "overview", label: "Dashboard", icon: "⌂", detail: "Resumen operativo" },
  { id: "streams", label: "Video", icon: "⌖", detail: "Streams en vivo" },
  { id: "companies", label: "Empresas", icon: "▦", detail: "Clientes y grupos" },
  { id: "users", label: "Usuarios", icon: "◎", detail: "Accesos y roles" },
  { id: "areas", label: "Areas", icon: "⌑", detail: "Zonas de trabajo" },
  { id: "cameras", label: "Camaras", icon: "▣", detail: "Dispositivos fijos" },
  { id: "rboxes", label: "R-Box", icon: "▤", detail: "Nodos de campo" },
  { id: "vehicles", label: "Vehiculos", icon: "◇", detail: "Flota terrestre" },
  { id: "drones", label: "Drones", icon: "△", detail: "Aeronaves" },
  { id: "stream-paths", label: "Paths", icon: "↗", detail: "Permisos MediaMTX" },
];

const resourceLabels = {
  companies: "Empresas",
  users: "Usuarios",
  areas: "Areas",
  cameras: "Camaras",
  rboxes: "R-Box",
  vehicles: "Vehiculos",
  drones: "Drones",
  "stream-paths": "Stream paths",
};

const resourceFields = {
  companies: [
    { name: "name", label: "Nombre", type: "text", required: true },
    { name: "active", label: "Activo", type: "checkbox", defaultValue: true },
  ],
  users: [
    { name: "username", label: "Usuario", type: "text", required: true },
    { name: "password", label: "Contrasena", type: "password", required: true },
    { name: "email", label: "Email", type: "email" },
    { name: "company_id", label: "Empresa", type: "select", resource: "companies", optional: true },
    {
      name: "role_names",
      label: "Rol",
      type: "select",
      options: ["viewer", "operator", "area_admin", "company_admin", "master"],
      defaultValue: "viewer",
    },
    { name: "active", label: "Activo", type: "checkbox", defaultValue: true },
  ],
  areas: [
    { name: "company_id", label: "Empresa", type: "select", resource: "companies", required: true },
    { name: "name", label: "Nombre", type: "text", required: true },
    { name: "active", label: "Activo", type: "checkbox", defaultValue: true },
  ],
  cameras: [
    { name: "company_id", label: "Empresa", type: "select", resource: "companies", required: true },
    { name: "area_id", label: "Area", type: "select", resource: "areas", optional: true },
    { name: "name", label: "Nombre", type: "text", required: true },
    { name: "brand", label: "Marca", type: "text", required: true },
    { name: "model", label: "Modelo", type: "text" },
    { name: "rtsp_url", label: "RTSP interno", type: "text" },
    { name: "active", label: "Activo", type: "checkbox", defaultValue: true },
    { name: "can_publish", label: "Puede publicar", type: "checkbox", defaultValue: true },
  ],
  rboxes: [
    { name: "company_id", label: "Empresa", type: "select", resource: "companies", required: true },
    { name: "area_id", label: "Area", type: "select", resource: "areas", optional: true },
    { name: "name", label: "Nombre", type: "text", required: true },
    { name: "serial", label: "Serial", type: "text", required: true },
    { name: "active", label: "Activo", type: "checkbox", defaultValue: true },
  ],
  vehicles: [
    { name: "company_id", label: "Empresa", type: "select", resource: "companies", required: true },
    { name: "area_id", label: "Area", type: "select", resource: "areas", optional: true },
    { name: "name", label: "Nombre", type: "text", required: true },
    { name: "plate", label: "Placa", type: "text" },
    { name: "active", label: "Activo", type: "checkbox", defaultValue: true },
    { name: "can_publish", label: "Puede publicar", type: "checkbox", defaultValue: true },
  ],
  drones: [
    { name: "company_id", label: "Empresa", type: "select", resource: "companies", required: true },
    { name: "area_id", label: "Area", type: "select", resource: "areas", optional: true },
    { name: "name", label: "Nombre", type: "text", required: true },
    { name: "provider", label: "Proveedor", type: "text", defaultValue: "robiotec" },
    { name: "unique_code", label: "Codigo unico", type: "text" },
    { name: "active", label: "Activo", type: "checkbox", defaultValue: true },
    { name: "can_publish", label: "Puede publicar", type: "checkbox", defaultValue: true },
  ],
  "stream-paths": [
    { name: "company_id", label: "Empresa", type: "select", resource: "companies", required: true },
    { name: "area_id", label: "Area", type: "select", resource: "areas", optional: true },
    { name: "path", label: "Path", type: "text", placeholder: "empresa/area/camara-01", required: true },
    { name: "resource_type", label: "Tipo", type: "select", options: ["camera", "vehicle", "drone"] },
    { name: "resource_id", label: "ID recurso", type: "text", required: true },
    { name: "active", label: "Activo", type: "checkbox", defaultValue: true },
    { name: "can_publish", label: "Puede publicar", type: "checkbox", defaultValue: true },
  ],
};

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) throw new Error(payload?.detail || "Solicitud rechazada por la API");
  return payload;
}

function setToken(token) {
  state.token = token;
  localStorage.setItem("robiotec.jwt", token);
}

function logout() {
  state.token = "";
  state.user = null;
  state.resources = {};
  localStorage.removeItem("robiotec.jwt");
  renderLogin();
}

async function bootstrap() {
  if (!state.token) return renderLogin();
  try {
    state.user = await api("/auth/me");
    render();
    loadInitialData();
  } catch {
    logout();
  }
}

function renderLogin() {
  document.body.className = "page-login";
  document.querySelector("#app").innerHTML = `
    <main class="login-shell">
      <section class="login-hero" aria-label="Resumen de plataforma">
        <div class="login-hero-top">
          <div class="login-mark"><img src="/static/assets/logoSimplificadoC.png" alt="" /></div>
          <div class="login-brand">
            <img src="/static/assets/LoogoBlanco.png" alt="ROBIOTEC" />
            <span>Security</span>
          </div>
        </div>

        <div class="login-copy">
          <span class="login-kicker">Ingreso seguro</span>
          <h1>Video, telemetria y control desde una sola consola</h1>
          <p>Un centro operativo sobrio para vigilar camaras, dispositivos y accesos sin perder contexto.</p>
        </div>

        <div class="login-glance-grid">
          <article><span>Supervision</span><strong>Streams autorizados</strong><p>Acceso con tokens temporales y paths controlados.</p></article>
          <article><span>Telemetria</span><strong>Flota y drones</strong><p>Informacion lista para operaciones en una sola VM.</p></article>
          <article><span>Control</span><strong>Roles y areas</strong><p>Permisos por usuario, empresa, area y recurso.</p></article>
        </div>

        <div class="login-hero-band">
          <span>Monitoreo visual</span>
          <span>Estado de mision</span>
          <span>Respuesta operativa</span>
        </div>
      </section>
      <section class="login-panel" aria-label="Formulario de acceso">
        <div class="login-panel-badge"><img src="/static/assets/logoSimplificadoC.png" alt="" /></div>
        <p class="eyebrow">Acceso operativo</p>
        <h2>Inicia sesion</h2>
        <p class="login-panel-copy">Ingresa con tus credenciales para continuar al centro de mando.</p>
        <form id="login-form" class="login-form">
          <label><span>Usuario</span><input name="username" autocomplete="username" value="robiotec" /></label>
          <label><span>Contrasena</span><input name="password" type="password" autocomplete="current-password" /></label>
          <p id="login-feedback" class="feedback"></p>
          <button type="submit">Entrar al sistema</button>
        </form>
        <div class="login-alt-grid">
          <article><strong>Supervisor</strong><p>Vision global, coordinacion y seguimiento.</p></article>
          <article><strong>Operador</strong><p>Visualizacion y respuesta en campo.</p></article>
        </div>
      </section>
    </main>
  `;

  document.querySelector("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const feedback = document.querySelector("#login-feedback");
    feedback.textContent = "Validando credenciales...";
    try {
      const payload = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username"),
          password: form.get("password"),
        }),
      });
      setToken(payload.access_token);
      await bootstrap();
    } catch (error) {
      feedback.textContent = error.message;
    }
  });
}

function render() {
  if (!state.token || !state.user) return renderLogin();
  document.body.className = "page-dashboard";
  document.querySelector("#app").innerHTML = `
    <div class="app-shell">
      <aside class="app-sidebar">
        <div class="sidebar-header">
          <div class="sidebar-brand">
            <span><img src="/static/assets/logoSimplificadoC.png" alt="" /></span>
            <div><strong>ROBIOTEC</strong><small>Security Console</small></div>
          </div>
          <p>Monitoreo visual, telemetria y eventos desde un unico punto de control.</p>
        </div>
        <nav aria-label="Navegacion principal">${modules.map(navButton).join("")}</nav>
        <div class="sidebar-footer">
          <span>Usuario activo</span>
          <strong>${escapeHtml(state.user.username)}</strong>
        </div>
        <button class="sidebar-logout" id="logout-button">Salir</button>
      </aside>
      <main class="app-main">
        <header class="top">
          <div>
            <p class="eyebrow">Centro de Mando</p>
            <h1>${resourceLabels[state.route] || "Consola de Control"}</h1>
          </div>
          <div class="user-pill"><span>${escapeHtml(state.user.username)}</span><strong>${escapeHtml(state.user.roles.join(", ") || "sin rol")}</strong></div>
        </header>
        <section class="wrap">${renderRoute()}</section>
      </main>
    </div>
  `;

  document.querySelector("#logout-button").addEventListener("click", logout);
  document.querySelectorAll("[data-route]").forEach((button) => {
    button.addEventListener("click", () => {
      state.route = button.dataset.route;
      state.streamStatus = null;
      state.streamToken = null;
      state.formFeedback = "";
      render();
      hydrateRoute();
    });
  });

  if (state.route === "streams") bindStreamTools();
  if (resourceLabels[state.route] && state.route !== "streams") bindCrud(state.route);
}

function hydrateRoute() {
  if (resourceLabels[state.route] && state.route !== "streams") {
    loadResource(state.route);
    loadDependencies(state.route);
  }
  if (state.route === "streams") bindStreamTools();
  if (state.route === "overview") loadInitialData();
}

function navButton(item) {
  const active = state.route === item.id ? "is-active" : "";
  return `
    <button class="sidebar-link ${active}" data-route="${item.id}" type="button">
      <span class="sidebar-icon">${item.icon}</span>
      <span class="sidebar-link-copy"><b>${item.label}</b><small>${item.detail}</small></span>
    </button>
  `;
}

function renderRoute() {
  if (state.route === "overview") return renderOverview();
  if (state.route === "streams") return renderStreams();
  return renderCrud(state.route);
}

function renderOverview() {
  const counts = {
    streams: (state.resources["stream-paths"] || []).length,
    vehicles: (state.resources.vehicles || []).length,
    drones: (state.resources.drones || []).length,
    cameras: (state.resources.cameras || []).length,
  };
  return `
    <section class="ops-grid">
      ${[
        ["Streams", counts.streams, "paths autorizados"],
        ["Camaras", counts.cameras, "registradas"],
        ["Vehiculos", counts.vehicles, "en flota"],
        ["Drones", counts.drones, "habilitados"],
      ].map(([label, value, note]) => `<article class="ops-card"><span>${label}</span><strong>${value}</strong><p>${note}</p></article>`).join("")}
    </section>
    <section class="command-grid">
      <article class="workbench">
        <div class="section-head"><p class="eyebrow">Situacion de Campo</p><h2>Mapa operativo</h2></div>
        <div class="map-mock">
          <span class="node n1"></span><span class="node n2"></span><span class="node n3"></span>
          <div class="map-core"><strong>ROBIOTEC</strong><span>VM activa</span></div>
          <div class="map-route r1"></div><div class="map-route r2"></div>
        </div>
      </article>
      <article class="workbench">
        <div class="section-head"><p class="eyebrow">Operacion</p><h2>Estado del sistema</h2></div>
        <div class="system-list">
          ${renderSystemRow("API central", "Conectada")}
          ${renderSystemRow("Usuario", state.user.roles.join(", ") || "Sin rol")}
          ${renderSystemRow("Registros", `${Object.values(counts).reduce((a, b) => a + b, 0)} cargados`)}
          ${renderSystemRow("Video", "Validacion por path")}
        </div>
        <div class="mission-strip">
          <span>API</span>
          <span>MediaMTX</span>
          <span>Dashboard</span>
        </div>
      </article>
    </section>
  `;
}

function renderSystemRow(label, value) {
  return `<div class="system-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderStreams() {
  const status = state.streamStatus;
  return `
    <section class="camera-stage">
      <aside class="camera-selector-panel">
        <p class="eyebrow">Stream path</p>
        <h2>Validar video</h2>
        <p class="panel-copy">Solicita estado y token del stream sin exponer URLs RTSP reales al navegador.</p>
        <label class="field"><span>Path autorizado</span><input id="stream-path-input" value="${escapeAttribute(state.selectedStream)}" placeholder="empresa/area/camara-01" /></label>
        <button class="primary-button" id="check-stream">Consultar estado</button>
        <button class="ghost-button" id="request-token">Solicitar token</button>
        <div class="camera-mini-list">
          ${(state.resources["stream-paths"] || []).slice(0, 5).map((item) => `
            <button type="button" data-stream-pick="${escapeAttribute(item.path)}">
              <span>${escapeHtml(item.path)}</span><small>${escapeHtml(item.resource_type || "stream")}</small>
            </button>
          `).join("") || `<p>No hay paths cargados todavia.</p>`}
        </div>
      </aside>
      <section class="viewer-shell">
        <div class="primary-view ${status?.online ? "is-online" : ""}">
          <div class="viewer-grid"></div>
          <div>
            <span class="live-dot"></span>
            <h2>${status ? (status.online ? "Video disponible" : "Video no disponible") : "Sin stream seleccionado"}</h2>
            <p>${escapeHtml(status?.message || "Consulta primero el estado del path contra la API central.")}</p>
            ${state.streamToken ? `<code>${escapeHtml(state.streamToken.viewer_url)}</code>` : ""}
          </div>
        </div>
      </section>
    </section>
  `;
}

function bindStreamTools() {
  const input = document.querySelector("#stream-path-input");
  document.querySelector("#check-stream").addEventListener("click", async () => {
    state.selectedStream = input.value.trim();
    try {
      state.streamStatus = await api(`/streams/${encodePath(state.selectedStream)}/status`);
    } catch (error) {
      state.streamStatus = { online: false, message: error.message };
    }
    render();
  });
  document.querySelector("#request-token").addEventListener("click", async () => {
    state.selectedStream = input.value.trim();
    try {
      state.streamToken = await api(`/stream/token/${encodePath(state.selectedStream)}`, { method: "POST" });
    } catch (error) {
      state.streamToken = null;
      state.streamStatus = { online: false, message: error.message };
    }
    render();
  });
  document.querySelectorAll("[data-stream-pick]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedStream = button.dataset.streamPick || "";
      state.streamStatus = null;
      state.streamToken = null;
      render();
    });
  });
}

function encodePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

function renderCrud(resource) {
  return `
    <section class="crud-grid">
      <form class="editor-panel" id="resource-form">
        <div class="section-head">
          <div><p class="eyebrow">Nuevo registro</p><h2>${resourceLabels[resource]}</h2></div>
        </div>
        <div class="form-grid">${resourceFields[resource].map(renderField).join("")}</div>
        <p id="form-feedback" class="feedback">${escapeHtml(state.formFeedback)}</p>
        <button class="primary-button" type="submit">Guardar</button>
      </form>
      <section class="page-section-shell">
        <div class="section-head">
          <div><p class="eyebrow">Administracion</p><h2>${resourceLabels[resource]}</h2></div>
          <button class="ghost-button compact-button" id="refresh-resource" type="button">Actualizar</button>
        </div>
        <div class="table-shell">
          <table>
            <thead><tr><th>Nombre</th><th>Detalle</th><th>Estado</th><th></th></tr></thead>
            <tbody id="resource-body">${renderRows(resource)}</tbody>
          </table>
        </div>
      </section>
    </section>
  `;
}

function renderField(field) {
  if (field.type === "checkbox") {
    return `
      <label class="check-field">
        <input name="${field.name}" type="checkbox" ${field.defaultValue !== false ? "checked" : ""} />
        <span>${field.label}</span>
      </label>
    `;
  }
  if (field.type === "select") {
    return `
      <label class="field">
        <span>${field.label}</span>
        <select name="${field.name}" ${field.required ? "required" : ""}>
          ${field.optional ? `<option value="">Sin asignar</option>` : ""}
          ${selectOptions(field)}
        </select>
      </label>
    `;
  }
  return `
    <label class="field">
      <span>${field.label}</span>
      <input name="${field.name}" type="${field.type}" ${field.required ? "required" : ""} value="${escapeAttribute(field.defaultValue || "")}" placeholder="${escapeAttribute(field.placeholder || "")}" />
    </label>
  `;
}

function selectOptions(field) {
  if (field.options) {
    return field.options
      .map((value) => `<option value="${escapeAttribute(value)}" ${value === field.defaultValue ? "selected" : ""}>${escapeHtml(value)}</option>`)
      .join("");
  }
  return (state.resources[field.resource] || [])
    .map((item) => `<option value="${escapeAttribute(item.id)}">${escapeHtml(item.name || item.username || item.path || item.serial || item.id)}</option>`)
    .join("");
}

function renderRows(resource) {
  if (state.loadingResource === resource) return `<tr><td colspan="4">Cargando datos...</td></tr>`;
  const items = state.resources[resource] || [];
  if (!items.length) return `<tr><td colspan="4">Sin registros todavia.</td></tr>`;
  return items.map((item) => `
    <tr>
      <td>${escapeHtml(item.name || item.username || item.path || item.serial || "Registro")}</td>
      <td>${renderItemDetail(resource, item)}</td>
      <td><span class="status ${item.active === false ? "off" : "on"}">${item.active === false ? "Inactivo" : "Activo"}</span></td>
      <td><button class="danger-button" data-delete-id="${escapeAttribute(item.id)}" type="button">Eliminar</button></td>
    </tr>
  `).join("");
}

function renderItemDetail(resource, item) {
  const detailByResource = {
    companies: item.id,
    users: item.email || item.company_id || item.id,
    areas: item.company_id,
    cameras: item.brand ? `${item.brand}${item.model ? ` ${item.model}` : ""}` : item.id,
    rboxes: item.serial || item.id,
    vehicles: item.plate || item.company_id,
    drones: item.unique_code || item.provider || item.id,
    "stream-paths": `${item.resource_type || ""} ${item.resource_id || ""}`.trim() || item.id,
  };
  return `<code>${escapeHtml(detailByResource[resource] || item.id)}</code>`;
}

async function loadInitialData() {
  await Promise.all(Object.keys(resourceLabels).map((resource) => loadResource(resource, false)));
  if (state.route === "overview") render();
}

async function loadDependencies(resource) {
  const dependencies = [...new Set(resourceFields[resource].filter((field) => field.resource).map((field) => field.resource))];
  await Promise.all(dependencies.map((dependency) => loadResource(dependency, false)));
  if (state.route === resource) render();
}

async function loadResource(resource, shouldRender = true) {
  state.loadingResource = resource;
  if (shouldRender && state.route === resource) render();
  try {
    state.resources[resource] = await api(`/${resource}`);
  } catch (error) {
    state.resources[resource] = [];
    state.formFeedback = error.message;
  } finally {
    state.loadingResource = "";
  }
  if (shouldRender && state.route === resource) renderAndBindCrud(resource);
}

function renderAndBindCrud(resource) {
  render();
  bindCrud(resource);
}

function bindCrud(resource) {
  const form = document.querySelector("#resource-form");
  const refreshButton = document.querySelector("#refresh-resource");
  if (!form || !refreshButton) return;

  refreshButton.addEventListener("click", () => loadResource(resource));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formPayload(resource, new FormData(form));
    state.formFeedback = "Guardando...";
    renderAndBindCrud(resource);
    try {
      await api(`/${resource}`, { method: "POST", body: JSON.stringify(payload) });
      state.formFeedback = "Registro guardado.";
      await loadResource(resource);
    } catch (error) {
      state.formFeedback = error.message;
      renderAndBindCrud(resource);
    }
  });

  document.querySelectorAll("[data-delete-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api(`/${resource}/${button.dataset.deleteId}`, { method: "DELETE" });
        state.formFeedback = "Registro eliminado.";
        await loadResource(resource);
      } catch (error) {
        state.formFeedback = error.message;
        renderAndBindCrud(resource);
      }
    });
  });
}

function formPayload(resource, form) {
  return resourceFields[resource].reduce((payload, field) => {
    if (field.type === "checkbox") {
      payload[field.name] = form.get(field.name) === "on";
      return payload;
    }
    let value = String(form.get(field.name) || "").trim();
    if (!value && field.optional) value = null;
    if (!value && !field.required) value = null;
    payload[field.name] = field.name === "role_names" ? [value] : value;
    return payload;
  }, {});
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

bootstrap();
