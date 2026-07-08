import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { ToastBus } from "../shared/toast";

type CameraOption = {
  camera_id: string;
  camera_name: string;
};

type ListPayload<T> = {
  items: T[];
  total?: number;
};

type Overview = {
  person_events: number;
  people_detected: number;
  plate_events: number;
  plates_detected: number;
  active_cameras: number;
  first_seen: string;
  last_seen: string;
};

type DailyRow = {
  person_id: string;
  person_name: string;
  work_date: string;
  first_seen: string;
  last_seen: string;
  hours: number;
  sessions: number;
  reentries: number;
  detections: number;
  cameras: string;
};

type SessionRow = {
  person_id: string;
  person_name: string;
  work_date: string;
  session_no: number;
  entry_at: string;
  exit_at: string;
  minutes_inside_session: number;
  minutes_since_previous_exit: number | null;
  detections: number;
  cameras: string;
};

type MonthlyRow = {
  person_id: string;
  person_name: string;
  days_present: number;
  total_hours: number;
  avg_hours_day: number;
  sessions: number;
  reentries: number;
  detections: number;
};

type PlateRow = {
  plate: string;
  camera_name: string;
  detections: number;
  days_detected: number;
  first_seen: string;
  last_seen: string;
};

type ReportTab = "daily" | "individual" | "monthly" | "plates";

export class DetectionReportsPage {
  private activeTab: ReportTab = "daily";
  private cameraSelect?: HTMLSelectElement;
  private gapInput?: HTMLInputElement;
  private fromInput?: HTMLInputElement;
  private toInput?: HTMLInputElement;
  private personInput?: HTMLInputElement;
  private monthInput?: HTMLInputElement;
  private daySelect?: HTMLSelectElement;
  private kpiElement?: HTMLElement;
  private tabElement?: HTMLElement;
  private bodyElement?: HTMLElement;
  private filterFields: Partial<Record<"camera" | "from" | "to" | "gap" | "person" | "month", HTMLElement>> = {};

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.renderShell();
    this.setDefaultDates();
    await this.loadCameras();
    await this.refresh();
  }

  private renderShell(): void {
    this.cameraSelect = createElement("select", { className: "form-select form-select-sm" }) as HTMLSelectElement;
    this.gapInput = createElement("input", {
      className: "form-control form-control-sm",
      attrs: { type: "number", min: "1", max: "720", step: "1", value: "15" }
    }) as HTMLInputElement;
    this.fromInput = createElement("input", { className: "form-control form-control-sm", attrs: { type: "date" } }) as HTMLInputElement;
    this.toInput = createElement("input", { className: "form-control form-control-sm", attrs: { type: "date" } }) as HTMLInputElement;
    this.personInput = createElement("input", {
      className: "form-control form-control-sm",
      attrs: { type: "text", placeholder: "Cédula", inputmode: "numeric" },
      onKeyDown: (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        this.activeTab = "individual";
        this.renderTabs();
        void this.refresh();
      }
    }) as HTMLInputElement;
    this.monthInput = createElement("input", { className: "form-control form-control-sm", attrs: { type: "month" } }) as HTMLInputElement;
    this.daySelect = createElement("select", { className: "form-select form-select-sm" }) as HTMLSelectElement;
    this.kpiElement = createElement("section", { className: "rb-reports-kpis" });
    this.tabElement = createElement("div", { className: "rb-reports-tabs" });
    this.bodyElement = createElement("section", { className: "rb-panel rb-reports-panel" });

    this.root.replaceChildren(
      createElement("div", { className: "rb-admin-header" }, [
        createElement("div", {}, [
          createElement("span", { className: "rb-kicker" }, "RRHH y estadísticas"),
          createElement("h1", { className: "h4 mb-1" }, "Reportes"),
          createElement("p", { className: "rb-muted mb-0" }, "Asistencia por reconocimiento facial y estadísticas de placas.")
        ]),
        createElement("div", { className: "rb-admin-actions" }, [
          createElement("button", { className: "btn btn-danger btn-sm", attrs: { type: "button" }, onClick: () => void this.refresh() }, "Actualizar"),
          createElement("button", { className: "btn btn-outline-light btn-sm", attrs: { type: "button" }, onClick: () => this.exportActive() }, "Exportar CSV")
        ])
      ]),
      this.kpiElement,
      createElement("section", { className: "rb-panel rb-reports-controls" }, [
        this.filterField("camera", "Cámara", this.cameraSelect),
        this.filterField("from", "Desde", this.fromInput),
        this.filterField("to", "Hasta", this.toInput),
        this.filterField("gap", "Brecha", this.gapInput),
        this.filterField("person", "Cédula", this.personInput),
        this.filterField("month", "Mes", this.monthInput)
      ]),
      this.tabElement,
      this.bodyElement
    );
    this.bind();
    this.renderTabs();
  }

  private bind(): void {
    [this.cameraSelect, this.gapInput, this.fromInput, this.toInput, this.personInput, this.monthInput, this.daySelect].forEach((control) => {
      control?.addEventListener("change", () => void this.refresh());
    });
  }

  private renderTabs(): void {
    const tabs: Array<[ReportTab, string]> = [
      ["daily", "Personal diario"],
      ["individual", "Individual"],
      ["monthly", "Mensual"],
      ["plates", "Placas"]
    ];
    this.tabElement?.replaceChildren(...tabs.map(([tab, label]) => createElement("button", {
      className: `rb-reports-tab ${this.activeTab === tab ? "is-active" : ""}`,
      attrs: { type: "button" },
      onClick: () => {
        this.activeTab = tab;
        this.renderTabs();
        void this.refresh();
      }
    }, label)));
    this.updateFilterVisibility();
  }

  private updateFilterVisibility(): void {
    const visibility: Record<ReportTab, Array<keyof typeof this.filterFields>> = {
      daily: ["camera", "from", "to", "gap"],
      individual: ["camera", "from", "to", "gap", "person"],
      monthly: ["camera", "gap", "month"],
      plates: ["camera", "from", "to"]
    };
    const visible = new Set(visibility[this.activeTab]);
    Object.entries(this.filterFields).forEach(([key, element]) => {
      if (element) element.hidden = !visible.has(key as keyof typeof this.filterFields);
    });
  }

  private async loadCameras(): Promise<void> {
    if (!this.cameraSelect) return;
    try {
      const payload = await this.api.get<ListPayload<CameraOption>>("/api/v1/reports/detection/cameras/", { silent: true });
      this.cameraSelect.replaceChildren(
        createElement("option", { attrs: { value: "" } }, "Todas"),
        ...payload.items.map((item) => createElement("option", { attrs: { value: item.camera_id } }, item.camera_name))
      );
    } catch {
      this.cameraSelect.replaceChildren(createElement("option", { attrs: { value: "" } }, "Todas"));
    }
  }

  private async refresh(): Promise<void> {
    try {
      await this.loadOverview();
      if (this.activeTab === "daily") await this.loadDaily();
      if (this.activeTab === "individual") await this.loadIndividual();
      if (this.activeTab === "monthly") await this.loadMonthly();
      if (this.activeTab === "plates") await this.loadPlates();
    } catch {
      this.toastBus.error("No se pudo cargar el reporte.");
    }
  }

  private async loadOverview(): Promise<void> {
    const overview = await this.api.get<Overview>(`/api/v1/reports/detection/overview/?${this.rangeParams()}`, { silent: true });
    this.kpiElement?.replaceChildren(
      this.kpi("Personas", overview.people_detected),
      this.kpi("Eventos rostro", overview.person_events),
      this.kpi("Placas", overview.plates_detected),
      this.kpi("Cámaras activas", overview.active_cameras)
    );
  }

  private async loadDaily(): Promise<void> {
    const payload = await this.api.get<ListPayload<DailyRow>>(`/api/v1/reports/detection/personnel/daily/?${this.rangeParams(true)}`);
    const rows = payload.items.map((row) => [
      row.person_id,
      row.person_name || "--",
      row.work_date,
      this.formatDate(row.first_seen),
      this.formatDate(row.last_seen),
      this.number(row.hours),
      row.reentries,
      row.detections,
      row.cameras
    ]);
    this.renderTable(
      "Personal diario",
      ["Cédula", "Nombre", "Fecha", "Entrada", "Salida", "Horas", "Reingresos", "Detecciones", "Cámaras"],
      rows,
      (index) => {
        const item = payload.items[index];
        if (!item || !this.personInput) return;
        this.personInput.value = item.person_id;
        this.activeTab = "individual";
        this.renderTabs();
        void this.refresh();
      }
    );
  }

  private async loadIndividual(): Promise<void> {
    const personId = this.personInput?.value.trim();
    if (!personId) {
      this.renderMessage("Ingresa una cédula para consultar el detalle individual.");
      return;
    }
    const [summary, sessions] = await Promise.all([
      this.api.get<ListPayload<DailyRow>>(`/api/v1/reports/detection/personnel/individual/?${this.rangeParams(true)}&person_id=${encodeURIComponent(personId)}`),
      this.api.get<ListPayload<SessionRow>>(`/api/v1/reports/detection/personnel/sessions/?${this.rangeParams(true)}&person_id=${encodeURIComponent(personId)}&work_date=${encodeURIComponent(this.daySelect?.value ?? "")}`)
    ]);
    this.syncDayOptions(summary.items);
    this.renderDualTables(
      "Resumen individual",
      ["Fecha", "Entrada", "Salida", "Horas", "Sesiones", "Reingresos", "Cámaras"],
      summary.items.map((row) => [row.work_date, this.formatDate(row.first_seen), this.formatDate(row.last_seen), this.number(row.hours), row.sessions, row.reentries, row.cameras]),
      "Sesiones",
      ["Fecha", "Sesión", "Entrada", "Salida", "Min. sesión", "Min. fuera", "Detecciones"],
      sessions.items.map((row) => [row.work_date, row.session_no, this.formatDate(row.entry_at), this.formatDate(row.exit_at), this.number(row.minutes_inside_session), row.minutes_since_previous_exit ?? "--", row.detections])
    );
  }

  private async loadMonthly(): Promise<void> {
    const [year, month] = String(this.monthInput?.value || "").split("-").map((value) => Number(value));
    if (!year || !month) {
      this.renderMessage("Selecciona un mes para cargar el reporte mensual.");
      return;
    }
    const params = new URLSearchParams({
      year: String(year),
      month: String(month),
      gap_minutes: String(this.gapInput?.value || "15"),
      camera_id: this.cameraSelect?.value || ""
    });
    const payload = await this.api.get<ListPayload<MonthlyRow>>(`/api/v1/reports/detection/personnel/monthly/?${params.toString()}`);
    this.renderTable(
      "Personal mensual",
      ["Cédula", "Nombre", "Días", "Horas", "Promedio", "Sesiones", "Reingresos", "Detecciones"],
      payload.items.map((row) => [row.person_id, row.person_name || "--", row.days_present, this.number(row.total_hours), this.number(row.avg_hours_day), row.sessions, row.reentries, row.detections])
    );
  }

  private async loadPlates(): Promise<void> {
    const payload = await this.api.get<ListPayload<PlateRow>>(`/api/v1/reports/detection/plates/?${this.rangeParams()}`);
    this.renderTable(
      "Placas",
      ["Placa", "Cámara", "Detecciones", "Días", "Primera", "Última"],
      payload.items.map((row) => [row.plate, row.camera_name, row.detections, row.days_detected, this.formatDate(row.first_seen), this.formatDate(row.last_seen)])
    );
  }

  private renderTable(title: string, headers: string[], rows: Array<Array<string | number>>, onRowClick?: (index: number) => void): void {
    this.bodyElement?.replaceChildren(
      createElement("div", { className: "rb-panel-heading" }, [
        createElement("h2", { className: "h5 mb-0" }, title),
        createElement("span", { className: "rb-count" }, String(rows.length))
      ]),
      rows.length ? this.table(headers, rows, onRowClick) : createElement("p", { className: "rb-muted mb-0" }, "Sin datos para los filtros seleccionados.")
    );
  }

  private renderDualTables(titleA: string, headersA: string[], rowsA: Array<Array<string | number>>, titleB: string, headersB: string[], rowsB: Array<Array<string | number>>): void {
    this.bodyElement?.replaceChildren(
      createElement("div", { className: "rb-reports-individual-toolbar" }, [this.field("Dia", this.daySelect as HTMLSelectElement)]),
      createElement("div", { className: "rb-reports-two" }, [
        createElement("section", {}, [
          createElement("h2", { className: "h6" }, titleA),
          rowsA.length ? this.table(headersA, rowsA, (index) => {
            if (!this.daySelect) return;
            this.daySelect.value = String(rowsA[index]?.[0] || "");
            void this.refresh();
          }) : createElement("p", { className: "rb-muted mb-0" }, "Sin resumen.")
        ]),
        createElement("section", {}, [createElement("h2", { className: "h6" }, titleB), rowsB.length ? this.table(headersB, rowsB) : createElement("p", { className: "rb-muted mb-0" }, "Sin sesiones.")])
      ])
    );
  }

  private table(headers: string[], rows: Array<Array<string | number>>, onRowClick?: (index: number) => void): HTMLElement {
    return createElement("div", { className: "rb-reports-table-wrap" }, [
      createElement("table", { className: "rb-reports-table" }, [
        createElement("thead", {}, createElement("tr", {}, headers.map((header) => createElement("th", {}, header)))),
        createElement("tbody", {}, rows.map((row, index) => createElement("tr", {
          className: onRowClick ? "rb-reports-row-action" : "",
          attrs: onRowClick ? { role: "button", tabindex: "0" } : {},
          onClick: () => onRowClick?.(index),
          onKeyDown: (event) => {
            if (!onRowClick || (event.key !== "Enter" && event.key !== " ")) return;
            event.preventDefault();
            onRowClick(index);
          }
        }, row.map((cell) => createElement("td", {}, String(cell ?? ""))))))
      ])
    ]);
  }

  private renderMessage(message: string): void {
    this.bodyElement?.replaceChildren(createElement("p", { className: "rb-muted mb-0" }, message));
  }

  private syncDayOptions(rows: DailyRow[]): void {
    if (!this.daySelect) return;
    const current = this.daySelect.value;
    this.daySelect.replaceChildren(createElement("option", { attrs: { value: "" } }, "Todos"));
    for (const row of rows) {
      const option = createElement("option", { attrs: { value: row.work_date } }, row.work_date) as HTMLOptionElement;
      option.selected = row.work_date === current;
      this.daySelect.append(option);
    }
  }

  private exportActive(): void {
    let url = "";
    if (this.activeTab === "daily") url = `/api/v1/reports/detection/personnel/daily/?${this.rangeParams(true)}&format=csv`;
    if (this.activeTab === "monthly") {
      const [year, month] = String(this.monthInput?.value || "").split("-");
      url = `/api/v1/reports/detection/personnel/monthly/?year=${year}&month=${month}&gap_minutes=${this.gapInput?.value || "15"}&camera_id=${encodeURIComponent(this.cameraSelect?.value || "")}&format=csv`;
    }
    if (this.activeTab === "individual") {
      const personId = this.personInput?.value.trim();
      url = `/api/v1/reports/detection/personnel/sessions/?${this.rangeParams(true)}&person_id=${encodeURIComponent(personId || "")}&work_date=${encodeURIComponent(this.daySelect?.value ?? "")}&format=csv`;
    }
    if (this.activeTab === "plates") url = `/api/v1/reports/detection/plates/?${this.rangeParams()}&format=csv`;
    if (url) window.open(url, "_blank", "noopener");
  }

  private rangeParams(includeGap = false): URLSearchParams {
    const params = new URLSearchParams({
      from_date: this.fromInput?.value || "",
      to_date: this.toInput?.value || "",
      camera_id: this.cameraSelect?.value || ""
    });
    if (includeGap) params.set("gap_minutes", this.gapInput?.value || "15");
    return params;
  }

  private setDefaultDates(): void {
    const today = new Date();
    const from = new Date(today);
    from.setDate(today.getDate() - 7);
    if (this.fromInput) this.fromInput.value = this.isoDay(from);
    if (this.toInput) this.toInput.value = this.isoDay(today);
    if (this.monthInput) this.monthInput.value = this.isoDay(today).slice(0, 7);
  }

  private field(label: string, control: HTMLElement): HTMLElement {
    return createElement("label", { className: "rb-reports-field" }, [
      createElement("span", { className: "form-label" }, label),
      control
    ]);
  }

  private filterField(name: keyof DetectionReportsPage["filterFields"], label: string, control: HTMLElement): HTMLElement {
    const field = this.field(label, control);
    this.filterFields[name] = field;
    return field;
  }

  private kpi(label: string, value: number): HTMLElement {
    return createElement("article", { className: "rb-access-card" }, [
      createElement("span", {}, label),
      createElement("strong", {}, String(value ?? 0))
    ]);
  }

  private isoDay(value: Date): string {
    return value.toISOString().slice(0, 10);
  }

  private formatDate(value: string): string {
    if (!value) return "--";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString("es-EC", {
      timeZone: "America/Guayaquil",
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  }

  private number(value: number | null): string {
    return Number(value || 0).toFixed(2);
  }
}
