import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { ModalController } from "../shared/modal";
import { ToastBus } from "../shared/toast";

type CompanyItem = {
  id: string;
  name: string;
};

type GeofenceType = "polygon" | "circle";

type GeofenceGeometry = {
  type?: string;
  coordinate_order?: string;
  coordinates?: unknown;
  center?: { lat?: number; lon?: number; lng?: number };
  radius_m?: number;
  radius?: number;
  color?: string;
  style?: { color?: string; fillColor?: string };
};

type GeofenceItem = {
  id: string;
  company_id: string;
  company_name: string;
  name: string;
  type: GeofenceType;
  geofence_type: GeofenceType;
  geometry: GeofenceGeometry;
  color: string | null;
  active: boolean;
  description: string;
  updated_at: string | null;
};

type GeofenceAlert = {
  id: string;
  vehicle_name: string;
  plate: string;
  geofence_name: string;
  event_type: string;
  gps_at: string | null;
  recorded_at: string | null;
  processed: boolean;
};

type GeofenceOverview = {
  geofences: GeofenceItem[];
  alerts: GeofenceAlert[];
  companies: CompanyItem[];
  summary: {
    geofences: number;
    active: number;
    inactive: number;
    pending_alerts: number;
    scope: string;
    updated_at: string;
  };
};

type SaveResponse = {
  ok: boolean;
  geofence: GeofenceItem;
};

type AlertResponse = {
  ok: boolean;
  alert: GeofenceAlert;
};

type FieldSpec = {
  name: string;
  label: string;
  type?: "text" | "number" | "textarea" | "select" | "checkbox" | "color";
  required?: boolean;
  options?: Array<{ value: string; label: string }>;
};

export class GeofenceAdminPage {
  private data: GeofenceOverview = {
    geofences: [],
    alerts: [],
    companies: [],
    summary: { geofences: 0, active: 0, inactive: 0, pending_alerts: 0, scope: "", updated_at: "" }
  };
  private modal?: ModalController;
  private form?: HTMLFormElement;
  private editingId = "";

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.root.replaceChildren(createElement("div", { className: "rb-loading" }, "Cargando geocercas..."));
    await this.load();
    this.render();
  }

  private async load(): Promise<void> {
    this.data = await this.api.get<GeofenceOverview>("/api/v1/geofences/overview/");
  }

  private render(): void {
    const modalElement = this.modalElement();
    this.root.replaceChildren(
      createElement("div", { className: "rb-admin-header" }, [
        createElement("div", {}, [
          createElement("span", { className: "rb-kicker" }, "Telemetría"),
          createElement("h1", { className: "h4 mb-1" }, "Geocercas"),
          createElement("p", { className: "rb-muted mb-0" }, "Zonas operativas y eventos de entrada o salida.")
        ]),
        createElement("div", { className: "rb-admin-actions" }, [
          createElement("button", {
            className: "btn btn-outline-light",
            attrs: { type: "button" },
            onClick: () => void this.loadAndRender()
          }, "Actualizar"),
          createElement("button", {
            className: "btn btn-danger",
            attrs: { type: "button" },
            onClick: () => this.openCreate()
          }, "Nueva geocerca")
        ])
      ]),
      this.summaryBand(),
      createElement("div", { className: "rb-geofence-layout" }, [
        this.panel("Geocercas", String(this.data.geofences.length), this.geofenceList()),
        this.panel("Alertas recientes", String(this.data.alerts.length), this.alertList())
      ]),
      modalElement
    );
    this.modal = new ModalController(modalElement);
  }

  private summaryBand(): HTMLElement {
    return createElement("section", { className: "rb-access-summary" }, [
      this.summaryCard("Total", String(this.data.summary.geofences || this.data.geofences.length)),
      this.summaryCard("Activas", String(this.data.summary.active || 0)),
      this.summaryCard("Inactivas", String(this.data.summary.inactive || 0)),
      this.summaryCard("Alertas pendientes", String(this.data.summary.pending_alerts || 0))
    ]);
  }

  private summaryCard(label: string, value: string): HTMLElement {
    return createElement("article", { className: "rb-access-card" }, [
      createElement("span", {}, label),
      createElement("strong", {}, value)
    ]);
  }

  private panel(title: string, count: string, content: HTMLElement): HTMLElement {
    return createElement("section", { className: "rb-panel rb-device-panel" }, [
      createElement("div", { className: "rb-panel-heading" }, [
        createElement("h2", { className: "h5 mb-0" }, title),
        createElement("span", { className: "rb-count" }, count)
      ]),
      content
    ]);
  }

  private geofenceList(): HTMLElement {
    if (!this.data.geofences.length) {
      return createElement("p", { className: "rb-muted mb-0" }, "Sin geocercas registradas.");
    }
    return createElement("div", { className: "rb-device-list" }, this.data.geofences.map((geofence) => {
      const color = this.geofenceColor(geofence);
      const swatch = createElement("span", { className: "rb-geofence-swatch" });
      swatch.style.backgroundColor = color;
      const meta = [
        geofence.company_name,
        this.typeLabel(geofence.geofence_type || geofence.type),
        this.shapeMeta(geofence),
        geofence.active ? "activa" : "inactiva"
      ].filter(Boolean).join(" · ");
      return createElement("button", {
        className: "rb-device-row rb-geofence-row",
        attrs: { type: "button" },
        onClick: () => this.openEdit(geofence.id)
      }, [
        createElement("span", { className: "rb-geofence-row-title" }, [
          swatch,
          createElement("span", { className: "rb-device-title" }, geofence.name)
        ]),
        createElement("span", { className: "rb-device-meta" }, meta)
      ]);
    }));
  }

  private alertList(): HTMLElement {
    if (!this.data.alerts.length) {
      return createElement("p", { className: "rb-muted mb-0" }, "Sin alertas de geocerca.");
    }
    return createElement("div", { className: "rb-geofence-alert-list" }, this.data.alerts.map((alert) => {
      const title = [
        alert.plate || alert.vehicle_name || "Vehículo",
        this.eventLabel(alert.event_type),
        alert.geofence_name
      ].filter(Boolean).join(" · ");
      const action = createElement("button", {
        className: alert.processed ? "btn btn-outline-light btn-sm" : "btn btn-danger btn-sm",
        attrs: { type: "button" },
        onClick: () => void this.toggleAlert(alert)
      }, alert.processed ? "Reabrir" : "Procesar");
      return createElement("article", { className: "rb-geofence-alert-row" }, [
        createElement("div", {}, [
          createElement("strong", {}, title),
          createElement("span", { className: "rb-device-meta" }, this.formatDate(alert.gps_at || alert.recorded_at))
        ]),
        action
      ]);
    }));
  }

  private modalElement(): HTMLElement {
    const form = createElement("form", { className: "modal-body rb-device-form rb-geofence-form" }) as HTMLFormElement;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.submit();
    });
    this.form = form;

    return createElement("div", { className: "modal fade", attrs: { tabindex: "-1", "aria-hidden": "true" } }, [
      createElement("div", { className: "modal-dialog modal-dialog-centered modal-lg" }, [
        createElement("div", { className: "modal-content rb-modal-content" }, [
          createElement("div", { className: "modal-header" }, [
            createElement("h2", { className: "modal-title h5", attrs: { "data-modal-title": "true" } }, "Editar geocerca"),
            createElement("button", { className: "btn-close btn-close-white", attrs: { type: "button", "data-bs-dismiss": "modal", "aria-label": "Cerrar" } })
          ]),
          form,
          createElement("div", { className: "modal-footer" }, [
            createElement("button", {
              className: "btn btn-outline-danger me-auto",
              attrs: { type: "button", "data-delete-button": "true" },
              onClick: () => void this.remove()
            }, "Eliminar"),
            createElement("button", { className: "btn btn-outline-light", attrs: { type: "button", "data-bs-dismiss": "modal" } }, "Cancelar"),
            createElement("button", {
              className: "btn btn-danger",
              attrs: { type: "button" },
              onClick: () => this.form?.requestSubmit()
            }, "Guardar")
          ])
        ])
      ])
    ]);
  }

  private openCreate(): void {
    this.editingId = "";
    this.fillForm();
    this.modal?.setTitle("Nueva geocerca");
    this.setDeleteVisible(false);
    this.modal?.open();
  }

  private openEdit(id: string): void {
    const item = this.data.geofences.find((geofence) => geofence.id === id);
    if (!item) return;
    this.editingId = id;
    this.fillForm(item);
    this.modal?.setTitle(`Editar ${item.name}`);
    this.setDeleteVisible(true);
    this.modal?.open();
  }

  private fillForm(item?: GeofenceItem): void {
    if (!this.form) return;
    this.form.replaceChildren(createElement("div", { className: "row g-3" }, this.fields().map((field) => this.fieldControl(field, item))));
  }

  private fields(): FieldSpec[] {
    return [
      { name: "company_id", label: "Organización", type: "select", required: true, options: this.companyOptions() },
      { name: "name", label: "Nombre", required: true },
      { name: "geofence_type", label: "Tipo", type: "select", required: true, options: this.typeOptions() },
      { name: "color", label: "Color", type: "color" },
      { name: "coordinates", label: "Coordenadas", type: "textarea" },
      { name: "lat", label: "Latitud centro", type: "number" },
      { name: "lon", label: "Longitud centro", type: "number" },
      { name: "radius_m", label: "Radio metros", type: "number" },
      { name: "description", label: "Descripción", type: "textarea" },
      { name: "active", label: "Activa", type: "checkbox" }
    ];
  }

  private fieldControl(field: FieldSpec, item?: GeofenceItem): HTMLElement {
    const wrapper = createElement("div", {
      className: field.type === "checkbox" ? "col-12 col-md-6 rb-check-wrap" : "col-12 col-md-6"
    });
    const value = this.fieldValue(field.name, item);
    const id = `geofence-${field.name}`;

    if (field.type === "checkbox") {
      const input = createElement("input", { className: "form-check-input", attrs: { type: "checkbox", name: field.name, id } }) as HTMLInputElement;
      input.checked = value !== false;
      wrapper.append(createElement("div", { className: "form-check form-switch" }, [
        input,
        createElement("label", { className: "form-check-label", attrs: { for: id } }, field.label)
      ]));
      return wrapper;
    }

    wrapper.append(createElement("label", { className: "form-label", attrs: { for: id } }, field.label));
    if (field.type === "select") {
      const select = createElement("select", { className: "form-select", attrs: { name: field.name, id } }) as HTMLSelectElement;
      if (!field.required) {
        select.append(createElement("option", { attrs: { value: "" } }, "Sin asignar"));
      }
      for (const option of field.options ?? []) {
        const optionElement = createElement("option", { attrs: { value: option.value } }, option.label) as HTMLOptionElement;
        optionElement.selected = option.value === String(value ?? "");
        select.append(optionElement);
      }
      wrapper.append(select);
      return wrapper;
    }

    if (field.type === "textarea") {
      const textarea = createElement("textarea", { className: "form-control", attrs: { name: field.name, id, rows: "4" } }) as HTMLTextAreaElement;
      textarea.value = String(value ?? "");
      wrapper.append(textarea);
      return wrapper;
    }

    const input = createElement("input", {
      className: "form-control",
      attrs: { type: field.type ?? "text", name: field.name, id, step: field.type === "number" ? "any" : "1" }
    }) as HTMLInputElement;
    input.value = String(value ?? "");
    wrapper.append(input);
    return wrapper;
  }

  private async submit(): Promise<void> {
    const payload = this.readPayload();
    if (!payload) return;
    try {
      const url = this.editingId ? `/api/v1/geofences/geofences/${this.editingId}/` : "/api/v1/geofences/geofences/";
      if (this.editingId) {
        await this.api.put<SaveResponse>(url, payload);
      } else {
        await this.api.post<SaveResponse>(url, payload);
      }
      this.toastBus.success("Geocerca guardada.");
      this.modal?.close();
      await this.load();
      this.render();
    } catch {
      this.toastBus.error("No se pudo guardar la geocerca.");
    }
  }

  private async remove(): Promise<void> {
    if (!this.editingId) return;
    try {
      await this.api.delete(`/api/v1/geofences/geofences/${this.editingId}/`);
      this.toastBus.success("Geocerca eliminada.");
      this.modal?.close();
      await this.load();
      this.render();
    } catch {
      this.toastBus.error("No se pudo eliminar la geocerca.");
    }
  }

  private readPayload(): Record<string, unknown> | null {
    if (!this.form) return null;
    const get = (name: string): string => {
      const control = this.form?.elements.namedItem(name);
      if (control instanceof HTMLInputElement || control instanceof HTMLSelectElement || control instanceof HTMLTextAreaElement) {
        return control.value.trim();
      }
      return "";
    };
    const activeControl = this.form.elements.namedItem("active");
    const type = (get("geofence_type") || "polygon") as GeofenceType;
    const color = this.normalizeColor(get("color"));
    const payload: Record<string, unknown> = {
      company_id: get("company_id"),
      name: get("name"),
      type,
      geofence_type: type,
      color,
      active: activeControl instanceof HTMLInputElement ? activeControl.checked : true,
      description: get("description")
    };

    if (type === "circle") {
      const lat = Number(get("lat"));
      const lon = Number(get("lon"));
      const radius = Number(get("radius_m"));
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(radius) || radius <= 0) {
        this.toastBus.info("Completa centro y radio de la geocerca.");
        return null;
      }
      payload.lat = lat;
      payload.lon = lon;
      payload.radius_m = radius;
      payload.geometry = {
        type: "Circle",
        center: { lat, lon },
        radius_m: radius,
        color,
        style: { color, fillColor: color }
      };
      return payload;
    }

    const coordinates = this.parseCoordinates(get("coordinates"));
    if (coordinates.length < 3) {
      this.toastBus.info("Ingresa al menos tres coordenadas.");
      return null;
    }
    payload.geometry = {
      type: "Polygon",
      coordinate_order: "latlon",
      coordinates,
      color,
      style: { color, fillColor: color }
    };
    return payload;
  }

  private async toggleAlert(alert: GeofenceAlert): Promise<void> {
    try {
      await this.api.patch<AlertResponse>(`/api/v1/geofences/alerts/${alert.id}/processed/`, { processed: !alert.processed });
      await this.load();
      this.render();
    } catch {
      this.toastBus.error("No se pudo actualizar la alerta.");
    }
  }

  private async loadAndRender(): Promise<void> {
    await this.load();
    this.render();
  }

  private fieldValue(name: string, item?: GeofenceItem): string | number | boolean {
    if (!item) {
      if (name === "active") return true;
      if (name === "geofence_type") return "polygon";
      if (name === "company_id") return this.data.companies[0]?.id ?? "";
      if (name === "color") return "#f13811";
      return "";
    }
    if (name === "active") return item.active;
    if (name === "company_id") return item.company_id;
    if (name === "geofence_type") return item.geofence_type || item.type;
    if (name === "color") return this.geofenceColor(item);
    if (name === "coordinates") return this.coordinatesText(item);
    if (name === "lat") return this.circleCenter(item).lat ?? "";
    if (name === "lon") return this.circleCenter(item).lon ?? "";
    if (name === "radius_m") return this.circleRadius(item) ?? "";
    if (name === "description") return item.description || "";
    return (item as unknown as Record<string, string | number | boolean | null>)[name] ?? "";
  }

  private parseCoordinates(value: string): number[][] {
    const raw = value.trim();
    if (!raw) return [];
    if (raw.startsWith("[")) {
      try {
        return this.pointsFromCoordinates(JSON.parse(raw));
      } catch {
        return [];
      }
    }
    return raw.split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => line.split(/[,\s]+/).map((part) => Number(part)).filter((part) => Number.isFinite(part)))
      .filter((parts) => parts.length >= 2)
      .map((parts) => [parts[0], parts[1]])
      .filter(([lat, lon]) => lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180);
  }

  private coordinatesText(item: GeofenceItem): string {
    return this.pointsFromCoordinates(item.geometry?.coordinates).map(([lat, lon]) => `${lat}, ${lon}`).join("\n");
  }

  private pointsFromCoordinates(coordinates: unknown): number[][] {
    let raw = coordinates;
    if (Array.isArray(raw) && raw.length && Array.isArray(raw[0]) && Array.isArray(raw[0][0])) {
      raw = raw[0];
    }
    if (!Array.isArray(raw)) return [];
    return raw.map((point) => {
      if (Array.isArray(point) && point.length >= 2) return [Number(point[0]), Number(point[1])];
      if (point && typeof point === "object") {
        const typed = point as { lat?: unknown; lon?: unknown; lng?: unknown };
        return [Number(typed.lat), Number(typed.lon ?? typed.lng)];
      }
      return [Number.NaN, Number.NaN];
    }).filter(([lat, lon]) => Number.isFinite(lat) && Number.isFinite(lon));
  }

  private circleCenter(item: GeofenceItem): { lat?: number; lon?: number } {
    const center = item.geometry?.center ?? {};
    const lat = Number(center.lat);
    const lon = Number(center.lon ?? center.lng);
    return {
      lat: Number.isFinite(lat) ? lat : undefined,
      lon: Number.isFinite(lon) ? lon : undefined
    };
  }

  private circleRadius(item: GeofenceItem): number | undefined {
    const radius = Number(item.geometry?.radius_m ?? item.geometry?.radius);
    return Number.isFinite(radius) ? radius : undefined;
  }

  private shapeMeta(item: GeofenceItem): string {
    const type = item.geofence_type || item.type;
    if (type === "circle") {
      const radius = this.circleRadius(item);
      return radius ? `${Math.round(radius)} m` : "sin radio";
    }
    const points = this.pointsFromCoordinates(item.geometry?.coordinates).length;
    return `${points} puntos`;
  }

  private geofenceColor(item: GeofenceItem): string {
    return this.normalizeColor(item.color || item.geometry?.color || item.geometry?.style?.color || item.geometry?.style?.fillColor || "#f13811");
  }

  private normalizeColor(value: string): string {
    const raw = String(value || "").trim();
    return /^#[0-9a-f]{3}([0-9a-f]{3})?$/i.test(raw) ? raw.toLowerCase() : "#f13811";
  }

  private companyOptions(): Array<{ value: string; label: string }> {
    return this.data.companies.map((company) => ({ value: company.id, label: company.name }));
  }

  private typeOptions(): Array<{ value: string; label: string }> {
    return [
      { value: "polygon", label: "Polígono" },
      { value: "circle", label: "Círculo" }
    ];
  }

  private typeLabel(value: string): string {
    return value === "circle" ? "círculo" : "polígono";
  }

  private eventLabel(value: string): string {
    if (value === "enter") return "ingreso";
    if (value === "exit") return "salida";
    return value || "evento";
  }

  private setDeleteVisible(visible: boolean): void {
    const button = this.root.querySelector<HTMLElement>("[data-delete-button]");
    if (button) button.hidden = !visible;
  }

  private formatDate(value: string | null): string {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("es-EC", {
      timeZone: "America/Guayaquil",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  }
}
