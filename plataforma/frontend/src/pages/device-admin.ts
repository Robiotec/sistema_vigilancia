import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { ModalController } from "../shared/modal";
import { ToastBus } from "../shared/toast";

type Paginated<T> = {
  count: number;
  results: T[];
};

type Company = {
  id: string;
  name: string;
};

type Vehicle = {
  id: string;
  company_id: string;
  plate: string | null;
  name: string;
  vehicle_type: string;
  vehicle_subtype: string | null;
  unique_code: string | null;
  brand: string | null;
  model: string | null;
  year: number | null;
  driver_name: string | null;
  description: string | null;
  active: boolean;
  can_publish: boolean;
};

type RBox = {
  id: string;
  company_id: string;
  name: string;
  serial: string;
  local_ip: string | null;
  public_ip: string | null;
  server_ip: string | null;
  server_port: number | null;
  location: string | null;
  status: string;
  active: boolean;
};

type Camera = {
  id: string;
  company_id: string;
  rbox_id: string | null;
  vehicle_id: string | null;
  drone_id: string | null;
  name: string;
  brand: string;
  model: string | null;
  unique_code: string | null;
  camera_type: string;
  inference_type: string;
  protocol: string;
  ip: string | null;
  port: number | null;
  username: string | null;
  channel: number | null;
  stream: number | null;
  quality: string | null;
  vehicle_position: string | null;
  public_ip_enabled: boolean;
  uses_rbox: boolean;
  notification_telegram: boolean;
  notification_email: boolean;
  status: string;
  active: boolean;
  can_publish: boolean;
};

type Drone = {
  id: string;
  company_id: string;
  name: string;
  provider: string;
  unique_code: string | null;
  drone_type: string;
  model: string | null;
  manufacturer: string | null;
  serial_number: string | null;
  status: string;
  active: boolean;
  can_publish: boolean;
};

type DeviceMode = "camera" | "rbox" | "vehicle" | "drone";
type DevicePanelKind = "camera" | "rbox" | "vehicle" | "drone";

type DeviceState = {
  companies: Company[];
  vehicles: Vehicle[];
  rboxes: RBox[];
  cameras: Camera[];
  drones: Drone[];
};

type FieldSpec = {
  name: string;
  label: string;
  type?: "text" | "number" | "password" | "checkbox" | "select" | "textarea";
  options?: Array<{ value: string; label: string }>;
  required?: boolean;
  placeholder?: string;
};

export class DeviceAdminPage {
  private state: DeviceState = {
    companies: [],
    vehicles: [],
    rboxes: [],
    cameras: [],
    drones: []
  };
  private modal?: ModalController;
  private form?: HTMLFormElement;
  private modalMode: DeviceMode = "camera";
  private editingId = "";

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.root.replaceChildren(createElement("div", { className: "rb-loading" }, "Cargando dispositivos..."));
    await this.load();
    this.render();
  }

  private async load(): Promise<void> {
    const [companies, vehicles, rboxes, cameras, drones] = await Promise.all([
      this.api.get<Paginated<Company>>("/api/v1/organizations/companies/"),
      this.api.get<Paginated<Vehicle>>("/api/v1/devices/vehicles/"),
      this.api.get<Paginated<RBox>>("/api/v1/devices/rboxes/"),
      this.api.get<Paginated<Camera>>("/api/v1/devices/cameras/"),
      this.api.get<Paginated<Drone>>("/api/v1/devices/drones/")
    ]);
    this.state = {
      companies: companies.results,
      vehicles: vehicles.results,
      rboxes: rboxes.results,
      cameras: cameras.results,
      drones: drones.results
    };
  }

  private render(): void {
    const modalElement = this.modalElement();
    this.root.replaceChildren(
      createElement("div", { className: "rb-admin-header" }, [
        createElement("div", {}, [
          createElement("span", { className: "rb-kicker" }, "Administración"),
          createElement("h1", { className: "h4 mb-1" }, "Dispositivos"),
          createElement("p", { className: "rb-muted mb-0" }, "Selecciona un elemento para editarlo.")
        ]),
      createElement("div", { className: "rb-admin-actions" }, [
          createElement("button", {
            className: "btn btn-outline-light",
            attrs: { type: "button" },
            onClick: () => this.openCreate("vehicle")
          }, "Nuevo vehículo"),
          createElement("button", {
            className: "btn btn-outline-light",
            attrs: { type: "button" },
            onClick: () => this.openCreate("drone")
          }, "Nuevo dron"),
          createElement("button", {
            className: "btn btn-outline-light",
            attrs: { type: "button" },
            onClick: () => this.openCreate("rbox")
          }, "Nueva RBox"),
          createElement("button", {
            className: "btn btn-danger",
            attrs: { type: "button" },
            onClick: () => this.openCreate("camera")
          }, "Nueva cámara")
        ])
      ]),
      this.summaryBand(),
      createElement("div", { className: "rb-device-grid" }, [
        this.devicePanel("Cámaras", this.state.cameras.length, "camera", this.cameraList()),
        this.devicePanel("RBox", this.state.rboxes.length, "rbox", this.rboxList()),
        this.devicePanel("Vehículos", this.state.vehicles.length, "vehicle", this.vehicleList()),
        this.devicePanel("Drones", this.state.drones.length, "drone", this.droneList())
      ]),
      modalElement
    );
    this.modal = new ModalController(modalElement);
  }

  private summaryBand(): HTMLElement {
    const total = this.state.cameras.length + this.state.rboxes.length + this.state.vehicles.length + this.state.drones.length;
    const activeVideo = this.state.cameras.filter((camera) => camera.active && camera.can_publish).length
      + this.state.drones.filter((drone) => drone.active && drone.can_publish).length;
    const telemetryLinked = this.state.vehicles.filter((vehicle) => vehicle.active && Boolean(vehicle.unique_code)).length
      + this.state.drones.filter((drone) => drone.active && Boolean(drone.unique_code)).length;
    const inferenceEnabled = this.state.cameras.filter((camera) => this.normalizedInference(camera.inference_type) !== "inactiva").length;
    return createElement("section", { className: "rb-access-summary rb-device-summary" }, [
      this.summaryCard("Total", String(total)),
      this.summaryCard("Video activo", String(activeVideo)),
      this.summaryCard("Telemetria OK", String(telemetryLinked)),
      this.summaryCard("Reconocimiento", String(inferenceEnabled)),
      this.summaryCard("RBox activas", String(this.state.rboxes.filter((rbox) => rbox.active).length))
    ]);
  }

  private summaryCard(label: string, value: string): HTMLElement {
    return createElement("article", { className: "rb-access-card" }, [
      createElement("span", {}, label),
      createElement("strong", {}, value)
    ]);
  }

  private devicePanel(title: string, count: number, kind: DevicePanelKind, content: HTMLElement): HTMLElement {
    return createElement("section", { className: "rb-panel rb-device-panel" }, [
      createElement("div", { className: "rb-panel-heading" }, [
        createElement("h2", { className: "h5 mb-0" }, title),
        createElement("span", { className: "rb-count", dataset: { deviceCount: "true" } }, String(count))
      ]),
      this.devicePanelFilters(kind),
      content,
      createElement("p", {
        className: "rb-muted rb-device-filter-empty mb-0",
        attrs: { "data-device-filter-empty": "true", hidden: "true" }
      }, "Sin resultados para esos filtros.")
    ]);
  }

  private devicePanelFilters(kind: DevicePanelKind): HTMLElement {
    const search = createElement("input", {
      className: "form-control form-control-sm rb-device-filter-search",
      attrs: { type: "search", placeholder: this.deviceSearchPlaceholder(kind), "aria-label": "Filtrar dispositivos" },
      onInput: (event) => this.applyDevicePanelFilters(event)
    }) as HTMLInputElement;
    const status = createElement("select", {
      className: "form-select form-select-sm rb-device-filter-status",
      attrs: { "aria-label": "Filtrar por estado" },
      onChange: (event) => this.applyDevicePanelFilters(event)
    }, [
      createElement("option", { attrs: { value: "all" } }, "Todos"),
      createElement("option", { attrs: { value: "active" } }, "Activos"),
      createElement("option", { attrs: { value: "inactive" } }, "Inactivos")
    ]) as HTMLSelectElement;
    const kindFilter = createElement("select", {
      className: "form-select form-select-sm rb-device-filter-kind",
      attrs: { "aria-label": "Filtrar por tipo" },
      onChange: (event) => this.applyDevicePanelFilters(event)
    }, [
      createElement("option", { attrs: { value: "all" } }, this.deviceKindFilterLabel(kind)),
      ...this.deviceKindOptions(kind).map((option) => createElement("option", { attrs: { value: option.value } }, option.label))
    ]) as HTMLSelectElement;
    return createElement("div", { className: "rb-device-panel-filters" }, [search, status, kindFilter]);
  }

  private applyDevicePanelFilters(event: Event): void {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const panel = target.closest<HTMLElement>(".rb-device-panel");
    if (!panel) return;
    const query = panel.querySelector<HTMLInputElement>(".rb-device-filter-search")?.value.trim().toLowerCase() ?? "";
    const status = panel.querySelector<HTMLSelectElement>(".rb-device-filter-status")?.value ?? "all";
    const kind = panel.querySelector<HTMLSelectElement>(".rb-device-filter-kind")?.value ?? "all";
    let visibleCount = 0;
    panel.querySelectorAll<HTMLElement>(".rb-device-row").forEach((row) => {
      const matchesQuery = !query || (row.dataset.deviceSearch ?? "").includes(query);
      const matchesStatus = status === "all" || row.dataset.deviceStatus === status;
      const matchesKind = kind === "all" || row.dataset.deviceKind === kind;
      const visible = matchesQuery && matchesStatus && matchesKind;
      row.hidden = !visible;
      if (visible) visibleCount += 1;
    });
    const count = panel.querySelector<HTMLElement>("[data-device-count]");
    if (count) count.textContent = String(visibleCount);
    const empty = panel.querySelector<HTMLElement>("[data-device-filter-empty]");
    if (empty) empty.hidden = visibleCount > 0;
  }

  private deviceSearchPlaceholder(kind: DevicePanelKind): string {
    if (kind === "camera") return "Filtrar cámara, código, RBox...";
    if (kind === "rbox") return "Filtrar RBox, serial, IP...";
    if (kind === "vehicle") return "Filtrar placa, chofer, marca...";
    return "Filtrar dron, serial, modelo...";
  }

  private deviceKindFilterLabel(kind: DevicePanelKind): string {
    if (kind === "camera") return "Todos los tipos";
    if (kind === "rbox") return "Todos los estados";
    if (kind === "vehicle") return "Todos los vehículos";
    return "Todos los drones";
  }

  private deviceKindOptions(kind: DevicePanelKind): Array<{ value: string; label: string }> {
    if (kind === "camera") return this.cameraTypeOptions();
    if (kind === "rbox") return this.statusOptions();
    if (kind === "vehicle") return this.vehicleSubtypeOptions();
    return this.droneTypeOptions();
  }

  private searchBlob(values: Array<string | number | null | undefined>): string {
    return values
      .filter((value) => value !== null && value !== undefined)
      .map((value) => String(value).toLowerCase())
      .join(" ");
  }

  private cameraList(): HTMLElement {
    if (!this.state.cameras.length) {
      return createElement("p", { className: "rb-muted mb-0" }, "Sin camaras registradas.");
    }

    return createElement("div", { className: "rb-device-list" }, this.state.cameras.map((camera) => {
      const rbox = this.state.rboxes.find((item) => item.id === camera.rbox_id);
      const meta = [
        camera.unique_code,
        camera.camera_type,
        rbox ? `RBox: ${rbox.name}` : "",
        camera.active ? "activa" : "inactiva"
      ].filter(Boolean).join(" · ");

      return createElement("button", {
        className: "rb-device-row",
        dataset: {
          deviceSearch: this.searchBlob([
            camera.name,
            camera.unique_code,
            camera.camera_type,
            rbox?.name,
            camera.inference_type,
            camera.status
          ]),
          deviceStatus: camera.active ? "active" : "inactive",
          deviceKind: camera.camera_type || "custom"
        },
        attrs: { type: "button" },
        onClick: () => this.openEdit("camera", camera.id)
      }, [
        createElement("span", { className: "rb-device-title" }, camera.name),
        createElement("span", { className: "rb-device-meta" }, meta),
        this.deviceTags([
          [camera.active && camera.can_publish, "Video activo", "ok"],
          [this.normalizedInference(camera.inference_type) !== "inactiva", this.inferenceLabel(camera.inference_type), "accent"],
          [camera.uses_rbox || Boolean(camera.rbox_id), "RBox", "info"],
          [camera.notification_email || camera.notification_telegram, "Alertas", "info"],
          [!camera.active, "Inactiva", "off"]
        ])
      ]);
    }));
  }

  private rboxList(): HTMLElement {
    if (!this.state.rboxes.length) {
      return createElement("p", { className: "rb-muted mb-0" }, "Sin RBox registradas.");
    }

    return createElement("div", { className: "rb-device-list" }, this.state.rboxes.map((rbox) => {
      const meta = [
        rbox.serial,
        rbox.local_ip,
        rbox.status,
        rbox.active ? "activa" : "inactiva"
      ].filter(Boolean).join(" · ");

      return createElement("button", {
        className: "rb-device-row",
        dataset: {
          deviceSearch: this.searchBlob([rbox.name, rbox.serial, rbox.local_ip, rbox.public_ip, rbox.server_ip, rbox.status]),
          deviceStatus: rbox.active ? "active" : "inactive",
          deviceKind: rbox.status || "activo"
        },
        attrs: { type: "button" },
        onClick: () => this.openEdit("rbox", rbox.id)
      }, [
        createElement("span", { className: "rb-device-title" }, rbox.name),
        createElement("span", { className: "rb-device-meta" }, meta),
        this.deviceTags([
          [rbox.active, "Activa", "ok"],
          [this.isOperationalStatus(rbox.status), "Operativa", "info"],
          [!rbox.active, "Inactiva", "off"]
        ])
      ]);
    }));
  }

  private vehicleList(): HTMLElement {
    if (!this.state.vehicles.length) {
      return createElement("p", { className: "rb-muted mb-0" }, "Sin vehiculos registrados.");
    }

    return createElement("div", { className: "rb-device-list" }, this.state.vehicles.map((vehicle) => {
      const meta = [
        vehicle.plate || vehicle.unique_code,
        this.vehicleSubtypeLabel(vehicle.vehicle_subtype),
        vehicle.brand,
        vehicle.year ? String(vehicle.year) : "",
        vehicle.driver_name ? `Chofer: ${vehicle.driver_name}` : "",
        vehicle.active ? "activo" : "inactivo"
      ].filter(Boolean).join(" · ");

      return createElement("button", {
        className: "rb-device-row",
        dataset: {
          deviceSearch: this.searchBlob([
            vehicle.name,
            vehicle.plate,
            vehicle.unique_code,
            vehicle.vehicle_subtype,
            vehicle.brand,
            vehicle.model,
            vehicle.year,
            vehicle.driver_name
          ]),
          deviceStatus: vehicle.active ? "active" : "inactive",
          deviceKind: vehicle.vehicle_subtype || "otra"
        },
        attrs: { type: "button" },
        onClick: () => this.openEdit("vehicle", vehicle.id)
      }, [
        createElement("span", { className: "rb-device-title" }, vehicle.name),
        createElement("span", { className: "rb-device-meta" }, meta),
        this.deviceTags([
          [vehicle.active && Boolean(vehicle.unique_code), "Telemetria OK", "ok"],
          [vehicle.can_publish, "Publica", "info"],
          [vehicle.active, "Activo", "ok"],
          [!vehicle.active, "Inactivo", "off"]
        ])
      ]);
    }));
  }

  private droneList(): HTMLElement {
    if (!this.state.drones.length) {
      return createElement("p", { className: "rb-muted mb-0" }, "Sin drones registrados.");
    }

    return createElement("div", { className: "rb-device-list" }, this.state.drones.map((drone) => {
      const meta = [
        drone.unique_code,
        this.droneTypeLabel(drone.drone_type),
        drone.model,
        drone.status,
        drone.active ? "activo" : "inactivo"
      ].filter(Boolean).join(" · ");

      return createElement("button", {
        className: "rb-device-row",
        dataset: {
          deviceSearch: this.searchBlob([
            drone.name,
            drone.unique_code,
            drone.provider,
            drone.drone_type,
            drone.model,
            drone.manufacturer,
            drone.serial_number,
            drone.status
          ]),
          deviceStatus: drone.active ? "active" : "inactive",
          deviceKind: drone.drone_type || drone.provider || "custom"
        },
        attrs: { type: "button" },
        onClick: () => this.openEdit("drone", drone.id)
      }, [
        createElement("span", { className: "rb-device-title" }, drone.name),
        createElement("span", { className: "rb-device-meta" }, meta),
        this.deviceTags([
          [drone.active && drone.can_publish, "Video activo", "ok"],
          [drone.active && Boolean(drone.unique_code), "Telemetria OK", "ok"],
          [this.isOperationalStatus(drone.status), "Operativo", "info"],
          [!drone.active, "Inactivo", "off"]
        ])
      ]);
    }));
  }

  private deviceTags(items: Array<[boolean, string, "ok" | "info" | "accent" | "off"]>): HTMLElement {
    const tags = items
      .filter(([visible]) => visible)
      .map(([, label, tone]) => createElement("span", { className: `rb-device-status-tag is-${tone}` }, label));
    return createElement("span", { className: "rb-device-tags" }, tags);
  }

  private modalElement(): HTMLElement {
    const form = createElement("form", { className: "modal-body rb-device-form" }) as HTMLFormElement;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.submit();
    });
    this.form = form;

    return createElement("div", {
      className: "modal fade",
      attrs: { tabindex: "-1", "aria-hidden": "true" }
    }, [
      createElement("div", { className: "modal-dialog modal-dialog-centered modal-lg" }, [
        createElement("div", { className: "modal-content rb-modal-content" }, [
          createElement("div", { className: "modal-header" }, [
            createElement("h2", { className: "modal-title h5", attrs: { "data-modal-title": "true" } }, "Editar"),
            createElement("button", { className: "btn-close btn-close-white", attrs: { type: "button", "data-bs-dismiss": "modal", "aria-label": "Cerrar" } })
          ]),
          form,
          createElement("div", { className: "modal-footer" }, [
            createElement("button", {
              className: "btn btn-outline-danger me-auto",
              attrs: { type: "button", "data-delete-button": "true" },
              onClick: () => this.remove()
            }, "Eliminar"),
            createElement("button", { className: "btn btn-outline-light", attrs: { type: "button", "data-bs-dismiss": "modal" } }, "Cancelar"),
            createElement("button", {
              className: "btn btn-danger",
              attrs: { type: "submit", form: "" },
              onClick: () => this.form?.requestSubmit()
            }, "Guardar")
          ])
        ])
      ])
    ]);
  }

  private openCreate(mode: DeviceMode): void {
    this.modalMode = mode;
    this.editingId = "";
    this.fillForm(mode);
    this.modal?.setTitle(this.modalTitle(mode, false));
    this.setDeleteVisible(false);
    this.modal?.open();
  }

  private openEdit(mode: DeviceMode, id: string): void {
    this.modalMode = mode;
    this.editingId = id;
    const item = mode === "camera"
      ? this.state.cameras.find((camera) => camera.id === id)
      : mode === "rbox"
        ? this.state.rboxes.find((rbox) => rbox.id === id)
        : mode === "vehicle"
          ? this.state.vehicles.find((vehicle) => vehicle.id === id)
          : this.state.drones.find((drone) => drone.id === id);
    this.fillForm(mode, item);
    this.modal?.setTitle(this.modalTitle(mode, true));
    this.setDeleteVisible(true);
    this.modal?.open();
  }

  private fillForm(mode: DeviceMode, item?: Camera | RBox | Vehicle | Drone): void {
    if (!this.form) return;
    this.form.replaceChildren();
    this.form.append(createElement("div", { className: "row g-3" }, this.fieldsFor(mode).map((field) => this.fieldControl(field, item))));
  }

  private fieldsFor(mode: DeviceMode): FieldSpec[] {
    const companyOptions = this.state.companies.map((company) => ({ value: company.id, label: company.name }));
    if (mode === "rbox") {
      return [
        { name: "company_id", label: "Empresa", type: "select", options: companyOptions, required: true },
        { name: "name", label: "Nombre", required: true },
        { name: "serial", label: "Serial" },
        { name: "local_ip", label: "IP local" },
        { name: "public_ip", label: "IP pública" },
        { name: "server_ip", label: "Servidor destino" },
        { name: "server_port", label: "Puerto destino", type: "number" },
        { name: "location", label: "Ubicación", type: "textarea" },
        { name: "status", label: "Estado", type: "select", options: this.statusOptions() },
        { name: "active", label: "Activo", type: "checkbox" }
      ];
    }

    if (mode === "vehicle") {
      return [
        { name: "company_id", label: "Empresa", type: "select", options: companyOptions, required: true },
        { name: "name", label: "Nombre o alias", required: true },
        { name: "plate", label: "Placa", placeholder: "ABC9140" },
        { name: "unique_code", label: "Código GPS/API" },
        { name: "vehicle_type", label: "Tipo", type: "select", options: this.vehicleTypeOptions(), required: true },
        { name: "vehicle_subtype", label: "Tipo de automóvil", type: "select", options: this.vehicleSubtypeOptions() },
        { name: "driver_name", label: "Chofer" },
        { name: "brand", label: "Marca" },
        { name: "model", label: "Modelo" },
        { name: "year", label: "Año", type: "number" },
        { name: "description", label: "Observaciones", type: "textarea" },
        { name: "active", label: "Activo", type: "checkbox" },
        { name: "can_publish", label: "Puede publicar", type: "checkbox" }
      ];
    }

    if (mode === "drone") {
      return [
        { name: "company_id", label: "Empresa", type: "select", options: companyOptions, required: true },
        { name: "name", label: "Nombre", required: true },
        { name: "unique_code", label: "Código único" },
        { name: "provider", label: "Proveedor", type: "select", options: this.droneProviderOptions(), required: true },
        { name: "drone_type", label: "Tipo de dron", type: "select", options: this.droneTypeOptions(), required: true },
        { name: "model", label: "Modelo" },
        { name: "manufacturer", label: "Fabricante" },
        { name: "serial_number", label: "Serial" },
        { name: "status", label: "Estado", type: "select", options: this.statusOptions() },
        { name: "active", label: "Activo", type: "checkbox" },
        { name: "can_publish", label: "Puede publicar video", type: "checkbox" }
      ];
    }

    return [
      { name: "company_id", label: "Empresa", type: "select", options: companyOptions, required: true },
      { name: "name", label: "Nombre", required: true },
      { name: "unique_code", label: "Código único" },
      { name: "brand", label: "Marca", type: "select", options: this.brandOptions(), required: true },
      { name: "model", label: "Modelo" },
      { name: "camera_type", label: "Tipo", type: "select", options: this.cameraTypeOptions() },
      { name: "ip", label: "IP/host RTSP" },
      { name: "port", label: "Puerto RTSP", type: "number", placeholder: "554" },
      { name: "username", label: "Usuario RTSP" },
      { name: "password", label: "Clave RTSP", type: "password", placeholder: "En blanco conserva la actual" },
      { name: "channel", label: "Canal", type: "number", placeholder: "1" },
      { name: "quality", label: "Calidad", type: "select", options: this.qualityOptions() },
      { name: "rbox_id", label: "RBox", type: "select", options: this.rboxOptions() },
      { name: "vehicle_id", label: "Vehículo", type: "select", options: this.vehicleOptions() },
      { name: "drone_id", label: "Dron", type: "select", options: this.droneOptions() },
      { name: "inference_type", label: "Inferencia", type: "select", options: this.inferenceOptions() },
      { name: "status", label: "Estado", type: "select", options: this.statusOptions() },
      { name: "uses_rbox", label: "Usa RBox", type: "checkbox" },
      { name: "active", label: "Activo", type: "checkbox" },
      { name: "notification_telegram", label: "Alerta Telegram", type: "checkbox" },
      { name: "notification_email", label: "Alerta correo", type: "checkbox" }
    ];
  }

  private fieldControl(field: FieldSpec, item?: Camera | RBox | Vehicle | Drone): HTMLElement {
    const value = this.fieldValue(field.name, item);
    const wrapper = createElement("div", { className: field.type === "checkbox" ? "col-12 col-md-6 rb-check-wrap" : "col-12 col-md-6" });
    if (field.type === "checkbox") {
      const input = createElement("input", { className: "form-check-input", attrs: { type: "checkbox", name: field.name, id: `field-${field.name}` } }) as HTMLInputElement;
      input.checked = value !== false;
      wrapper.append(createElement("div", { className: "form-check form-switch" }, [
        input,
        createElement("label", { className: "form-check-label", attrs: { for: `field-${field.name}` } }, field.label)
      ]));
      return wrapper;
    }

    wrapper.append(createElement("label", { className: "form-label", attrs: { for: `field-${field.name}` } }, field.label));
    if (field.type === "select") {
      const select = createElement("select", { className: "form-select", attrs: { name: field.name, id: `field-${field.name}` } }) as HTMLSelectElement;
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
      const textarea = createElement("textarea", {
        className: "form-control",
        attrs: { name: field.name, id: `field-${field.name}`, rows: "3" }
      }) as HTMLTextAreaElement;
      textarea.value = String(value ?? "");
      wrapper.append(textarea);
      return wrapper;
    }

    const input = createElement("input", {
      className: "form-control",
      attrs: {
        type: field.type ?? "text",
        name: field.name,
        id: `field-${field.name}`,
        placeholder: field.placeholder ?? ""
      }
    }) as HTMLInputElement;
    input.value = String(value ?? "");
    if (field.name === "plate") {
      input.addEventListener("blur", () => {
        const rawValue = input.value.trim();
        if (!rawValue) return;
        try {
          input.value = this.normalizeVehiclePlate(rawValue);
          input.setCustomValidity("");
        } catch (error) {
          input.setCustomValidity(error instanceof Error ? error.message : "Placa inválida");
          input.reportValidity();
        }
      });
    }
    wrapper.append(input);
    return wrapper;
  }

  private fieldValue(name: string, item?: Camera | RBox | Vehicle | Drone): string | number | boolean | null {
    if (!item) {
      if (name === "active" || name === "can_publish" || name === "uses_rbox" || name === "notification_telegram" || name === "notification_email") return true;
      if (name === "brand" && this.modalMode === "camera") return "dahua";
      if (name === "camera_type") return "fixed";
      if (name === "inference_type") return "inactiva";
      if (name === "status") return "activo";
      if (name === "quality") return "substream";
      if (name === "vehicle_type") return "auto";
      if (name === "provider" || name === "drone_type") return "robiotec";
      if (name === "port") return 554;
      if (name === "channel") return 1;
      return "";
    }
    return (item as unknown as Record<string, string | number | boolean | null>)[name] ?? "";
  }

  private async submit(): Promise<void> {
    if (!this.form) return;
    let payload: Record<string, string | number | boolean | null>;
    try {
      payload = this.readPayload();
    } catch (error) {
      this.toastBus.error(error instanceof Error ? error.message : "Revisa los datos ingresados.");
      return;
    }
    const baseUrl = this.endpointFor(this.modalMode);
    const url = this.editingId ? `${baseUrl}${this.editingId}/` : baseUrl;

    try {
      if (this.editingId) {
        await this.api.patch(url, payload);
      } else {
        await this.api.post(url, payload);
      }
      this.toastBus.success("Cambios guardados.");
      this.closeModalBeforeRender();
      await this.load();
      this.render();
    } catch (error) {
      this.toastBus.error(error instanceof Error ? error.message : "No se pudo guardar. Revisa sesión, permisos y datos.");
    }
  }

  private async remove(): Promise<void> {
    if (!this.editingId) return;
    const baseUrl = this.endpointFor(this.modalMode);
    try {
      await this.api.delete(`${baseUrl}${this.editingId}/`);
      this.toastBus.success("Elemento eliminado.");
      this.closeModalBeforeRender();
      await this.load();
      this.render();
    } catch {
      this.toastBus.error("No se pudo eliminar el elemento.");
    }
  }

  private readPayload(): Record<string, string | number | boolean | null> {
    if (!this.form) return {};
    const payload: Record<string, string | number | boolean | null> = {};
    for (const field of this.fieldsFor(this.modalMode)) {
      const control = this.form.elements.namedItem(field.name);
      if (control instanceof HTMLInputElement && control.type === "checkbox") {
        payload[this.apiName(field.name)] = control.checked;
        continue;
      }
      if (control instanceof HTMLInputElement || control instanceof HTMLSelectElement || control instanceof HTMLTextAreaElement) {
        const rawValue = control.value.trim();
        if (field.type === "number") {
          payload[this.apiName(field.name)] = rawValue ? Number(rawValue) : null;
        } else if (rawValue || field.required) {
          payload[this.apiName(field.name)] = rawValue;
        } else {
          payload[this.apiName(field.name)] = null;
        }
      }
    }
    if (this.modalMode === "camera") {
      payload.protocol = "rtsp";
      payload.stream = payload.quality === "substream" ? 1 : 0;
    }
    if (this.modalMode === "vehicle" && typeof payload.plate === "string" && payload.plate) {
      payload.plate = this.normalizeVehiclePlate(payload.plate);
    }
    return payload;
  }

  private closeModalBeforeRender(): void {
    this.modal?.close();
    document.querySelectorAll(".modal-backdrop").forEach((element) => element.remove());
    document.body.classList.remove("modal-open");
    document.body.style.removeProperty("overflow");
    document.body.style.removeProperty("padding-right");
  }

  private normalizeVehiclePlate(value: string): string {
    const cleaned = value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!cleaned) return "";
    const match = cleaned.match(/^([A-Z]{3})(\d{1,4})$/);
    if (!match) {
      throw new Error("La placa debe tener 3 letras y hasta 4 números. Ejemplo: ABC9140.");
    }
    return `${match[1]}${match[2].padStart(4, "0")}`;
  }

  private endpointFor(mode: DeviceMode): string {
    if (mode === "camera") return "/api/v1/devices/cameras/";
    if (mode === "rbox") return "/api/v1/devices/rboxes/";
    if (mode === "vehicle") return "/api/v1/devices/vehicles/";
    return "/api/v1/devices/drones/";
  }

  private apiName(name: string): string {
    const fieldMap: Record<string, string> = {
      company_id: "company",
      rbox_id: "rbox",
      vehicle_id: "vehicle",
      drone_id: "drone"
    };
    return fieldMap[name] ?? name;
  }

  private modalTitle(mode: DeviceMode, editing: boolean): string {
    const action = editing ? "Editar" : "Nuevo";
    if (mode === "camera") return editing ? "Editar cámara" : "Nueva cámara";
    if (mode === "rbox") return editing ? "Editar RBox" : "Nueva RBox";
    if (mode === "vehicle") return `${action} vehículo`;
    return `${action} dron`;
  }

  private setDeleteVisible(visible: boolean): void {
    const button = this.root.querySelector<HTMLElement>("[data-delete-button]");
    if (button) {
      button.hidden = !visible;
    }
  }

  private brandOptions(): Array<{ value: string; label: string }> {
    return [
      { value: "dahua", label: "Dahua" },
      { value: "hikvision", label: "Hikvision" },
      { value: "custom", label: "Custom" }
    ];
  }

  private cameraTypeOptions(): Array<{ value: string; label: string }> {
    return [
      { value: "fixed", label: "Fija" },
      { value: "vehicle", label: "Vehicular" },
      { value: "drone", label: "Dron" },
      { value: "custom", label: "Personalizada" }
    ];
  }

  private vehicleTypeOptions(): Array<{ value: string; label: string }> {
    return [
      { value: "auto", label: "Vehículo terrestre" }
    ];
  }

  private vehicleSubtypeOptions(): Array<{ value: string; label: string }> {
    return [
      { value: "camioneta", label: "Camioneta" },
      { value: "camion", label: "Camion" },
      { value: "volqueta", label: "Volqueta" },
      { value: "retroexcavadora", label: "Retroexcavadora" },
      { value: "otra", label: "Otra" }
    ];
  }

  private vehicleSubtypeLabel(value: string | null): string {
    const labels = new Map(this.vehicleSubtypeOptions().map((item) => [item.value, item.label]));
    return labels.get(value ?? "") ?? "";
  }

  private droneProviderOptions(): Array<{ value: string; label: string }> {
    return [
      { value: "robiotec", label: "Robiotec" },
      { value: "dji", label: "DJI" }
    ];
  }

  private droneTypeOptions(): Array<{ value: string; label: string }> {
    return [
      { value: "robiotec", label: "Robiotec" },
      { value: "dji", label: "DJI" },
      { value: "custom", label: "Personalizado" }
    ];
  }

  private droneTypeLabel(value: string | null): string {
    const labels = new Map(this.droneTypeOptions().map((item) => [item.value, item.label]));
    return labels.get(value ?? "") ?? value ?? "";
  }

  private qualityOptions(): Array<{ value: string; label: string }> {
    return [
      { value: "substream", label: "Substream" },
      { value: "mainstream", label: "Mainstream" }
    ];
  }

  private inferenceOptions(): Array<{ value: string; label: string }> {
    return [
      { value: "inactiva", label: "Inactiva" },
      { value: "placa", label: "Placas" },
      { value: "rostro", label: "Rostros" },
      { value: "zona", label: "Zona" },
      { value: "movimiento", label: "Movimiento" }
    ];
  }

  private normalizedInference(value: string | null): string {
    const normalized = String(value || "").trim().toLowerCase();
    return this.inferenceOptions().some((option) => option.value === normalized) ? normalized : "inactiva";
  }

  private inferenceLabel(value: string | null): string {
    const normalized = this.normalizedInference(value);
    return this.inferenceOptions().find((option) => option.value === normalized)?.label ?? "Inactiva";
  }

  private isOperationalStatus(value: string | null): boolean {
    return ["activo", "online", "ready", "operativo"].includes(String(value || "").trim().toLowerCase());
  }

  private statusOptions(): Array<{ value: string; label: string }> {
    return [
      { value: "activo", label: "Activo" },
      { value: "inactivo", label: "Inactivo" },
      { value: "mantenimiento", label: "Mantenimiento" },
      { value: "error", label: "Error" }
    ];
  }

  private rboxOptions(): Array<{ value: string; label: string }> {
    return this.state.rboxes.map((rbox) => ({ value: rbox.id, label: `${rbox.name} (${rbox.serial})` }));
  }

  private vehicleOptions(): Array<{ value: string; label: string }> {
    return this.state.vehicles.map((vehicle) => ({
      value: vehicle.id,
      label: `${vehicle.plate || vehicle.name} · ${vehicle.name}`
    }));
  }

  private droneOptions(): Array<{ value: string; label: string }> {
    return this.state.drones.map((drone) => ({
      value: drone.id,
      label: `${drone.unique_code || drone.name} · ${drone.name}`
    }));
  }
}
