import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { ToastBus } from "../shared/toast";
import { FleetMapPage } from "./fleet-map";

type DailyFleetReport = {
  date: string;
  generated_at: string;
  totals: {
    total_km: number;
    active_vehicles: number;
    total_vehicles: number;
    total_points: number;
    geofence_intervals: number;
    geofence_minutes: number;
  };
  vehicles: FleetVehicleRow[];
  geofence_intervals: GeofenceInterval[];
};

type FleetVehicleRow = {
  vehicle_id: string;
  label: string;
  plate: string;
  brand?: string | null;
  model?: string | null;
  year?: number | null;
  driver_name: string;
  vehicle_subtype_name: string;
  total_km: number;
  total_points: number;
  max_speed: number;
  geofence_intervals: GeofenceInterval[];
};

type GeofenceInterval = {
  vehicle_id: string;
  vehicle_label: string;
  geofence_name: string;
  entry_at: string;
  exit_at: string;
  duration_minutes: number;
  status: string;
};

type SettingsPayload = {
  ok: boolean;
  settings: {
    enabled: boolean;
    send_time: string;
    recipients: string[];
    fallback_recipients: string[];
    last_sent_date: string;
  };
};

type SendNowPayload = {
  ok: boolean;
  date: string;
  total: number;
};

type FleetKilometersView = "km" | "routes" | "geofences";
type FleetReportPeriod = "day" | "week" | "month" | "range";

export class FleetKilometersPage {
  private dateInput?: HTMLInputElement;
  private toDateInput?: HTMLInputElement;
  private periodSelect?: HTMLSelectElement;
  private vehicleFilterSelect?: HTMLSelectElement;
  private enabledInput?: HTMLInputElement;
  private timeInput?: HTMLInputElement;
  private recipientsInput?: HTMLTextAreaElement;
  private statusElement?: HTMLElement;
  private kpiElement?: HTMLElement;
  private tableElement?: HTMLElement;
  private geofenceElement?: HTMLElement;
  private currentReport?: DailyFleetReport;
  private viewButtons: HTMLButtonElement[] = [];
  private viewPanels: HTMLElement[] = [];
  private routeMapRoot?: HTMLElement;
  private routeMapMounted = false;
  private settingsModal?: HTMLElement;

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.renderShell();
    await Promise.all([this.loadReport(), this.loadSettings()]);
  }

  private renderShell(): void {
    this.dateInput = createElement("input", {
      className: "form-control form-control-sm",
      attrs: { type: "date", title: "Desde" }
    }) as HTMLInputElement;
    this.dateInput.value = this.yesterday();
    this.toDateInput = createElement("input", {
      className: "form-control form-control-sm",
      attrs: { type: "date", title: "Hasta" }
    }) as HTMLInputElement;
    this.toDateInput.value = this.yesterday();
    this.periodSelect = createElement("select", { className: "form-select form-select-sm" }, [
      createElement("option", { attrs: { value: "day" } }, "Diario"),
      createElement("option", { attrs: { value: "week" } }, "Semanal"),
      createElement("option", { attrs: { value: "month" } }, "Mensual"),
      createElement("option", { attrs: { value: "range" } }, "Rango")
    ]) as HTMLSelectElement;
    this.periodSelect.addEventListener("change", () => this.applyPeriodDates());
    this.vehicleFilterSelect = createElement("select", { className: "form-select form-select-sm" }, [
      createElement("option", { attrs: { value: "all" } }, "Todos"),
      createElement("option", { attrs: { value: "volqueta" } }, "Volqueta"),
      createElement("option", { attrs: { value: "camion" } }, "Camion"),
      createElement("option", { attrs: { value: "camioneta" } }, "Camioneta"),
      createElement("option", { attrs: { value: "retroexcavadora" } }, "Retroexcavadora"),
      createElement("option", { attrs: { value: "otra" } }, "Otra"),
      createElement("option", { attrs: { value: "sin_especificar" } }, "Sin especificar")
    ]) as HTMLSelectElement;
    this.vehicleFilterSelect.addEventListener("change", () => {
      if (this.currentReport) this.renderReport(this.currentReport);
    });

    this.enabledInput = createElement("input", {
      className: "form-check-input",
      attrs: { type: "checkbox", id: "fleet-report-enabled" }
    }) as HTMLInputElement;
    this.timeInput = createElement("input", {
      className: "form-control form-control-sm",
      attrs: { type: "time" }
    }) as HTMLInputElement;
    this.timeInput.value = "07:00";
    this.recipientsInput = createElement("textarea", {
      className: "form-control",
      attrs: { rows: "4", placeholder: "correo@dominio.com" }
    }) as HTMLTextAreaElement;
    this.statusElement = createElement("span", { className: "rb-map-status" }, "Cargando...");
    this.kpiElement = createElement("div", { className: "rb-km-kpis" });
    this.tableElement = createElement("div", { className: "rb-km-table-wrap" });
    this.geofenceElement = createElement("div", { className: "rb-km-geofence-list" });

    const loadButton = createElement("button", {
      className: "btn btn-danger btn-sm",
      attrs: { type: "button" },
      onClick: () => void this.loadReport()
    }, "Cargar");
    const pdfButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => this.openPdf()
    }, "PDF");
    const csvButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => this.exportCsv()
    }, "CSV");
    const todayButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => this.setDateAndLoad(this.today())
    }, "Hoy");
    const yesterdayButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => this.setDateAndLoad(this.yesterday())
    }, "Ayer");
    const saveButton = createElement("button", {
      className: "btn btn-danger btn-sm",
      attrs: { type: "button" },
      onClick: () => void this.saveSettings()
    }, "Guardar envío");
    const sendButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => void this.sendNow()
    }, "Enviar ahora");
    const reportSettingsButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => this.openSettingsModal()
    }, "Envío PDF");
    this.settingsModal = this.buildSettingsModal(saveButton, sendButton);
    const kmPanel = createElement("div", { className: "rb-km-view is-active", attrs: { "data-km-view-panel": "km" } }, [
      createElement("div", { className: "rb-km-layout" }, [
        createElement("section", { className: "rb-panel rb-km-main-panel" }, [
          createElement("div", { className: "rb-panel-heading" }, [
            createElement("h2", { className: "h6 mb-0" }, "Resumen diario"),
            this.statusElement
          ]),
          this.kpiElement,
          this.tableElement
        ])
      ])
    ]);
    this.routeMapRoot = createElement("div", { className: "rb-km-route-map-root" });
    const routesPanel = createElement("div", { className: "rb-km-view", attrs: { "data-km-view-panel": "routes", hidden: "true" } }, [
      this.routeMapRoot
    ]);
    const geofencePanel = createElement("div", { className: "rb-km-view", attrs: { "data-km-view-panel": "geofences", hidden: "true" } }, [
      createElement("section", { className: "rb-panel rb-km-geofence-panel" }, [
        createElement("div", { className: "rb-panel-heading" }, [
          createElement("h2", { className: "h6 mb-0" }, "Informes de geocercas por vehículo")
        ]),
        this.geofenceElement
      ])
    ]);
    const tabs = createElement("div", { className: "rb-km-tabs", attrs: { role: "tablist", "aria-label": "Gestión de flota" } }, [
      this.viewButton("km", "Km de flota", true),
      this.viewButton("routes", "Mapa de recorridos"),
      this.viewButton("geofences", "Informes de geocercas")
    ]);
    this.viewPanels = [kmPanel, routesPanel, geofencePanel];

    this.root.replaceChildren(
      createElement("section", { className: "rb-km-shell" }, [
        createElement("div", { className: "rb-admin-header" }, [
          createElement("div", {}, [
            createElement("span", { className: "rb-kicker" }, "Flota"),
            createElement("h1", { className: "h4 mb-1" }, "Gestión de kilómetros"),
            createElement("p", { className: "rb-muted mb-0" }, "Kilometraje diario, permanencia en geocercas y envio PDF.")
          ]),
          createElement("div", { className: "rb-map-toolbar rb-km-toolbar" }, [
            this.periodSelect,
            this.dateInput,
            this.toDateInput,
            this.vehicleFilterSelect,
            todayButton,
            yesterdayButton,
            loadButton,
            reportSettingsButton,
            pdfButton,
            csvButton
          ])
        ]),
        tabs,
        ...this.viewPanels,
        this.settingsModal
      ])
    );
    this.applyPeriodDates();
  }

  private buildSettingsModal(saveButton: HTMLElement, sendButton: HTMLElement): HTMLElement {
    const enabledInput = this.enabledInput as HTMLInputElement;
    const timeInput = this.timeInput as HTMLInputElement;
    const recipientsInput = this.recipientsInput as HTMLTextAreaElement;
    const closeButton = createElement("button", {
      className: "rb-km-settings-close",
      attrs: { type: "button", "aria-label": "Cerrar" },
      onClick: () => this.closeSettingsModal()
    }, "x");
    return createElement("div", { className: "rb-km-settings-modal", attrs: { hidden: "true" } }, [
      createElement("div", { className: "rb-km-settings-backdrop", onClick: () => this.closeSettingsModal() }),
      createElement("section", { className: "rb-panel rb-km-settings-dialog", attrs: { role: "dialog", "aria-modal": "true" } }, [
        createElement("div", { className: "rb-panel-heading" }, [
          createElement("h2", { className: "h6 mb-0" }, "Envío diario PDF"),
          closeButton
        ]),
        createElement("label", { className: "form-check form-switch rb-km-switch" }, [
          enabledInput,
          createElement("span", { className: "form-check-label" }, "Activar envío diario")
        ]),
        createElement("label", { className: "form-label" }, "Hora"),
        timeInput,
        createElement("label", { className: "form-label mt-3" }, "Correos"),
        recipientsInput,
        createElement("div", { className: "rb-admin-actions mt-3" }, [saveButton, sendButton])
      ])
    ]);
  }

  private openSettingsModal(): void {
    if (this.settingsModal) this.settingsModal.hidden = false;
  }

  private closeSettingsModal(): void {
    if (this.settingsModal) this.settingsModal.hidden = true;
  }

  private viewButton(view: FleetKilometersView, label: string, active = false): HTMLButtonElement {
    const button = createElement("button", {
      className: `rb-km-tab ${active ? "is-active" : ""}`,
      attrs: { type: "button", role: "tab", "aria-selected": String(active), "data-km-view": view },
      onClick: () => this.setView(view)
    }, label) as HTMLButtonElement;
    this.viewButtons.push(button);
    return button;
  }

  private setView(view: FleetKilometersView): void {
    this.viewButtons.forEach((button) => {
      const active = button.dataset.kmView === view;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", String(active));
    });
    this.viewPanels.forEach((panel) => {
      const active = panel.dataset.kmViewPanel === view;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
    if (view === "routes") {
      void this.ensureRouteMap();
    }
  }

  private async ensureRouteMap(): Promise<void> {
    if (!this.routeMapRoot || this.routeMapMounted) return;
    this.routeMapMounted = true;
    await new FleetMapPage(this.routeMapRoot, this.api, this.toastBus).mount();
  }

  private async loadReport(): Promise<void> {
    const dates = this.reportDates();
    this.setStatus("Calculando...");
    try {
      const reports = await Promise.all(
        dates.map((date) => this.api.get<DailyFleetReport>(`/api/v1/reports/fleet-daily/?date=${date}`))
      );
      this.currentReport = this.aggregateReports(reports);
      this.renderReport(this.currentReport);
      this.setStatus(`${this.reportTitle()} · Generado ${this.formatDateTime(this.currentReport.generated_at)}`);
    } catch {
      this.setStatus("Error");
    }
  }

  private aggregateReports(reports: DailyFleetReport[]): DailyFleetReport {
    const source = reports.length ? reports : [];
    const first = source[0];
    const last = source.at(-1);
    const vehicles = new Map<string, FleetVehicleRow>();
    const geofenceIntervals = source.flatMap((report) => report.geofence_intervals || []);
    source.forEach((report) => {
      (report.vehicles || []).forEach((row) => {
        const key = row.vehicle_id || row.plate || row.label;
        const existing = vehicles.get(key);
        if (!existing) {
          vehicles.set(key, { ...row, geofence_intervals: [...(row.geofence_intervals || [])] });
          return;
        }
        existing.total_km += Number(row.total_km || 0);
        existing.total_points += Number(row.total_points || 0);
        existing.max_speed = Math.max(Number(existing.max_speed || 0), Number(row.max_speed || 0));
        existing.geofence_intervals.push(...(row.geofence_intervals || []));
      });
    });
    const vehicleRows = Array.from(vehicles.values()).sort((left, right) => Number(right.total_km || 0) - Number(left.total_km || 0));
    return {
      date: first && last && first.date !== last.date ? `${first.date} / ${last.date}` : first?.date || this.dateInput?.value || this.yesterday(),
      generated_at: new Date().toISOString(),
      totals: {
        total_km: source.reduce((total, report) => total + Number(report.totals.total_km || 0), 0),
        active_vehicles: vehicleRows.filter((row) => Number(row.total_points || 0) > 0).length,
        total_vehicles: Math.max(...source.map((report) => Number(report.totals.total_vehicles || 0)), vehicleRows.length, 0),
        total_points: source.reduce((total, report) => total + Number(report.totals.total_points || 0), 0),
        geofence_intervals: geofenceIntervals.length,
        geofence_minutes: geofenceIntervals.reduce((total, row) => total + Number(row.duration_minutes || 0), 0)
      },
      vehicles: vehicleRows,
      geofence_intervals: geofenceIntervals
    };
  }

  private async loadSettings(): Promise<void> {
    try {
      const payload = await this.api.get<SettingsPayload>("/api/v1/reports/fleet-daily/settings/", { silent: true });
      const settings = payload.settings;
      if (this.enabledInput) this.enabledInput.checked = settings.enabled;
      if (this.timeInput) this.timeInput.value = (settings.send_time || "07:00").slice(0, 5);
      if (this.recipientsInput) {
        const recipients = settings.recipients.length ? settings.recipients : settings.fallback_recipients;
        this.recipientsInput.value = recipients.join("\n");
      }
    } catch {
      this.toastBus.info("La configuración del envío diario requiere permisos de administración.");
    }
  }

  private async saveSettings(): Promise<void> {
    try {
      const payload = await this.api.put<SettingsPayload>("/api/v1/reports/fleet-daily/settings/", {
        enabled: Boolean(this.enabledInput?.checked),
        send_time: this.timeInput?.value || "07:00",
        recipients: this.recipients()
      });
      this.toastBus.success(payload.settings.enabled ? "Envío diario activado." : "Envío diario desactivado.");
    } catch {
      this.toastBus.error("No se pudo guardar la configuración.");
    }
  }

  private async sendNow(): Promise<void> {
    try {
      const payload = await this.api.post<SendNowPayload>("/api/v1/reports/fleet-daily/send-now/", {
        date: this.dateInput?.value || this.yesterday(),
        recipients: this.recipients()
      });
      this.toastBus.success(`PDF enviado a ${payload.total} correo(s).`);
    } catch {
      this.toastBus.error("No se pudo enviar el PDF.");
    }
  }

  private renderReport(report: DailyFleetReport): void {
    this.kpiElement?.replaceChildren(
      this.kpi("Km flota", `${Number(report.totals.total_km || 0).toFixed(2)}`),
      this.kpi("Activos", `${report.totals.active_vehicles} / ${report.totals.total_vehicles}`),
      this.kpi("Puntos GPS", String(report.totals.total_points || 0)),
      this.kpi("Geocercas", String(report.totals.geofence_intervals || 0))
    );
    this.renderVehicles(report.vehicles);
    this.renderGeofences(report.geofence_intervals);
  }

  private renderVehicles(rows: FleetVehicleRow[]): void {
    if (!this.tableElement) return;
    const filteredRows = this.filteredRows(rows);
    const table = createElement("table", { className: "table table-dark table-sm align-middle rb-km-table" });
    table.append(
      createElement("thead", {}, createElement("tr", {}, [
        createElement("th", {}, "Vehículo"),
        createElement("th", {}, "Marca"),
        createElement("th", {}, "Modelo"),
        createElement("th", {}, "Año"),
        createElement("th", {}, "Chofer"),
        createElement("th", {}, "Tipo de automóvil"),
        createElement("th", {}, "Km"),
        createElement("th", {}, "Puntos"),
        createElement("th", {}, "Geocercas")
      ])),
      createElement("tbody", {}, filteredRows.map((row) => createElement("tr", {}, [
        createElement("td", {}, row.label || row.plate || row.vehicle_id),
        createElement("td", {}, row.brand || "--"),
        createElement("td", {}, row.model || "--"),
        createElement("td", {}, row.year ? String(row.year) : "--"),
        createElement("td", {}, row.driver_name || "--"),
        createElement("td", {}, row.vehicle_subtype_name || "--"),
        createElement("td", {}, Number(row.total_km || 0).toFixed(2)),
        createElement("td", {}, String(row.total_points || 0)),
        createElement("td", {}, String(row.geofence_intervals?.length || 0))
      ])))
    );
    this.tableElement.replaceChildren(table);
  }

  private filteredRows(rows: FleetVehicleRow[]): FleetVehicleRow[] {
    const filter = this.vehicleFilterSelect?.value || "all";
    if (filter === "all") return rows;
    return rows.filter((row) => {
      const normalized = this.normalizedSubtype(row.vehicle_subtype_name);
      return filter === "sin_especificar" ? !normalized : normalized === filter;
    });
  }

  private normalizedSubtype(value: string): string {
    return String(value || "")
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, "_");
  }

  private renderGeofences(rows: GeofenceInterval[]): void {
    if (!this.geofenceElement) return;
    if (!rows.length) {
      this.geofenceElement.replaceChildren(createElement("p", { className: "rb-muted mb-0" }, "Sin permanencias registradas."));
      return;
    }
    const grouped = new Map<string, GeofenceInterval[]>();
    rows.forEach((row) => {
      const key = row.vehicle_label || row.vehicle_id || "Vehículo";
      grouped.set(key, [...(grouped.get(key) || []), row]);
    });
    this.geofenceElement.replaceChildren(...Array.from(grouped.entries()).map(([vehicle, intervals]) => {
      const minutes = intervals.reduce((total, row) => total + Number(row.duration_minutes || 0), 0);
      return createElement("article", { className: "rb-km-geofence-card" }, [
        createElement("div", { className: "rb-km-geofence-card-head" }, [
          createElement("strong", {}, vehicle),
          createElement("span", {}, `${intervals.length} evento${intervals.length === 1 ? "" : "s"} · ${this.minutes(minutes)}`)
        ]),
        createElement("div", { className: "rb-km-geofence-card-list" },
          intervals.map((row) => createElement("div", { className: "rb-route-summary" }, [
            createElement("strong", {}, row.geofence_name),
            createElement("span", {}, `${this.formatTime(row.entry_at)} - ${row.status === "permanece" ? "permanece" : this.formatTime(row.exit_at)} · ${this.minutes(row.duration_minutes)}`)
          ]))
        )
      ]);
    }));
  }

  private kpi(label: string, value: string): HTMLElement {
    return createElement("div", { className: "rb-status-item" }, [
      createElement("span", { className: "rb-status-label" }, label),
      createElement("strong", { className: "rb-status-value" }, value)
    ]);
  }

  private recipients(): string[] {
    return String(this.recipientsInput?.value || "")
      .split(/[\n,;]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  private openPdf(): void {
    if ((this.periodSelect?.value || "day") !== "day") {
      this.toastBus.info("El PDF está disponible para informe diario. Para rangos usa CSV.");
      return;
    }
    const date = this.dateInput?.value || this.yesterday();
    window.open(`/api/v1/reports/fleet-daily/pdf/?date=${date}`, "_blank", "noopener");
  }

  private exportCsv(): void {
    if (!this.currentReport) {
      this.toastBus.info("Carga un reporte antes de exportar.");
      return;
    }
    const rows = this.filteredRows(this.currentReport.vehicles);
    const headers = ["Vehiculo", "Placa", "Marca", "Modelo", "Año", "Chofer", "Tipo", "Km", "Puntos", "Velocidad maxima", "Geocercas"];
    const lines = [
      headers.map((cell) => this.csvCell(cell)).join(","),
      ...rows.map((row) => [
        row.label || row.vehicle_id,
        row.plate || "",
        row.brand || "",
        row.model || "",
        row.year ? String(row.year) : "",
        row.driver_name || "",
        row.vehicle_subtype_name || "",
        Number(row.total_km || 0).toFixed(2),
        String(row.total_points || 0),
        Number(row.max_speed || 0).toFixed(2),
        String(row.geofence_intervals?.length || 0)
      ].map((cell) => this.csvCell(cell)).join(","))
    ];
    const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `km_${this.period()}_${this.vehicleFilterSelect?.value || "all"}_${this.currentReport.date.replace(/[^0-9A-Za-z_-]+/g, "_")}.csv`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  private csvCell(value: string | number): string {
    return `"${String(value ?? "").replace(/"/g, '""')}"`;
  }

  private setDateAndLoad(value: string): void {
    if (this.periodSelect) this.periodSelect.value = "day";
    if (this.dateInput) this.dateInput.value = value;
    if (this.toDateInput) this.toDateInput.value = value;
    void this.loadReport();
  }

  private setStatus(value: string): void {
    if (this.statusElement) this.statusElement.textContent = value;
  }

  private yesterday(): string {
    return this.ecDay(-1);
  }

  private today(): string {
    return this.ecDay(0);
  }

  private applyPeriodDates(): void {
    const period = this.period();
    const base = this.dateInput?.value || this.yesterday();
    if (period === "day") {
      if (this.toDateInput) this.toDateInput.value = base;
      return;
    }
    if (period === "week") {
      if (this.toDateInput) this.toDateInput.value = base;
      if (this.dateInput) this.dateInput.value = this.shiftDate(base, -6);
      return;
    }
    if (period === "month") {
      const date = new Date(`${base}T00:00:00`);
      const first = new Date(date.getFullYear(), date.getMonth(), 1);
      const last = new Date(date.getFullYear(), date.getMonth() + 1, 0);
      if (this.dateInput) this.dateInput.value = this.dateValue(first);
      if (this.toDateInput) this.toDateInput.value = this.dateValue(last);
    }
  }

  private reportDates(): string[] {
    const start = this.dateInput?.value || this.yesterday();
    const end = this.period() === "day" ? start : this.toDateInput?.value || start;
    const dates: string[] = [];
    let cursor = new Date(`${start}T00:00:00`);
    let last = new Date(`${end}T00:00:00`);
    if (cursor > last) {
      const previous = cursor;
      cursor = last;
      last = previous;
    }
    while (cursor <= last && dates.length < 93) {
      dates.push(this.dateValue(cursor));
      cursor = new Date(cursor.getTime() + 86400000);
    }
    return dates.length ? dates : [start];
  }

  private reportTitle(): string {
    const labels: Record<FleetReportPeriod, string> = {
      day: "Informe diario",
      week: "Informe semanal",
      month: "Informe mensual",
      range: "Informe por rango"
    };
    return labels[this.period()];
  }

  private period(): FleetReportPeriod {
    const value = this.periodSelect?.value;
    return value === "week" || value === "month" || value === "range" ? value : "day";
  }

  private shiftDate(value: string, offsetDays: number): string {
    const date = new Date(`${value}T00:00:00`);
    date.setDate(date.getDate() + offsetDays);
    return this.dateValue(date);
  }

  private dateValue(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  private ecDay(offsetDays: number): string {
    const date = new Date(Date.now() - 5 * 3600 * 1000 + offsetDays * 86400000);
    return date.toISOString().slice(0, 10);
  }

  private formatDateTime(value: string): string {
    return value ? new Date(value).toLocaleString("es-EC") : "--";
  }

  private formatTime(value: string): string {
    return value ? new Date(value).toLocaleTimeString("es-EC", { hour: "2-digit", minute: "2-digit" }) : "--";
  }

  private minutes(value: number): string {
    const total = Math.max(0, Math.round(Number(value || 0)));
    const hours = Math.floor(total / 60);
    const minutes = total % 60;
    return hours ? `${hours}h ${String(minutes).padStart(2, "0")}m` : `${minutes}m`;
  }
}
