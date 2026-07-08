import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { ToastBus } from "../shared/toast";

type EventItem = {
  id: string;
  event_type: string;
  event_type_label: string;
  event_category: string;
  event_category_label: string;
  origin: string;
  camera_id: string;
  camera_name: string;
  detected_at: string;
  title: string;
  description: string | null;
  person_id: string | null;
  person_name: string | null;
  plate: string | null;
  status: string;
  severity: string | null;
  track_id: number | string | null;
  video_file_path: string | null;
  image_file_path: string | null;
  crop_path: string | null;
  detail_payload: Record<string, unknown>;
  primary: string;
  summary: string;
};

type HistoryPayload = {
  items: EventItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

type OptionPayload = {
  items: Array<{ value: string; label: string; count: number }>;
  total: number;
};

const CATEGORY_OPTIONS = [
  ["alerta", "Alertas"],
  ["acceso", "Acceso"],
  ["reconocimiento_facial", "Rostros"],
  ["movimiento", "Movimiento"],
  ["vehiculo", "Vehículos"]
];

const EVENT_TYPE_OPTIONS = [
  ["", "Todos los eventos"],
  ["person", "Persona"],
  ["plate", "Placa"],
  ["clip", "Zona"],
  ["clips_movimiento", "Movimiento"],
  ["clips_zona", "Alerta de zona"]
];

const ORIGIN_OPTIONS = [
  ["fixed_camera", "Cámaras fijas"],
  ["vehicle", "Vehículos"],
  ["drone", "Drones"]
];

export class EventsHistoryPage {
  private page = 1;
  private pageSize = 12;
  private items: EventItem[] = [];
  private searchInput?: HTMLInputElement;
  private dateFromInput?: HTMLInputElement;
  private dateToInput?: HTMLInputElement;
  private timeFromInput?: HTMLInputElement;
  private timeToInput?: HTMLInputElement;
  private cameraIdSelect?: HTMLSelectElement;
  private cameraNameSelect?: HTMLSelectElement;
  private eventTypeSelect?: HTMLSelectElement;
  private listElement?: HTMLElement;
  private paginationElement?: HTMLElement;
  private statusElement?: HTMLElement;

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.renderShell();
    await Promise.all([this.loadOptions(), this.loadHistory(false)]);
  }

  private renderShell(): void {
    this.searchInput = createElement("input", {
      className: "form-control",
      attrs: { type: "search", placeholder: "Buscar por cámara, placa, persona o descripción" }
    }) as HTMLInputElement;
    this.dateFromInput = this.input("date");
    this.dateToInput = this.input("date");
    this.timeFromInput = this.input("time");
    this.timeToInput = this.input("time");
    this.cameraIdSelect = createElement("select", { className: "form-select" }) as HTMLSelectElement;
    this.cameraNameSelect = createElement("select", { className: "form-select" }) as HTMLSelectElement;
    this.eventTypeSelect = createElement("select", { className: "form-select" }) as HTMLSelectElement;
    this.eventTypeSelect.replaceChildren(...EVENT_TYPE_OPTIONS.map(([value, label]) => this.option(value, label)));
    this.listElement = createElement("div", { className: "rb-events-list" });
    this.paginationElement = createElement("div", { className: "rb-events-pagination" });
    this.statusElement = createElement("span", { className: "rb-map-status" }, "Cargando historial...");

    const filters = [
      this.field("Buscar", this.searchInput),
      this.field("Desde", this.dateFromInput),
      this.field("Hasta", this.dateToInput),
      this.field("Hora inicio", this.timeFromInput),
      this.field("Hora fin", this.timeToInput),
      this.field("ID de cámara", this.cameraIdSelect),
      this.field("Nombre de cámara", this.cameraNameSelect),
      this.field("Evento", this.eventTypeSelect),
      this.checkboxGroup("Categoría", CATEGORY_OPTIONS, "category"),
      this.checkboxGroup("Origen", ORIGIN_OPTIONS, "origin")
    ];

    this.root.replaceChildren(
      createElement("section", { className: "rb-events-shell" }, [
        createElement("div", { className: "rb-admin-header" }, [
          createElement("div", {}, [
            createElement("span", { className: "rb-kicker" }, "Historial operativo"),
            createElement("h1", { className: "h4 mb-1" }, "Eventos de cámaras e IA"),
            createElement("p", { className: "rb-muted mb-0" }, "Eventos detectados, evidencias y estados de revision.")
          ]),
          createElement("div", { className: "rb-admin-actions" }, [
            this.statusElement,
            createElement("button", {
              className: "btn btn-outline-light btn-sm",
              attrs: { type: "button" },
              onClick: () => void this.clearFilters()
            }, "Limpiar"),
            createElement("button", {
              className: "btn btn-danger btn-sm",
              attrs: { type: "button" },
              onClick: () => void this.loadHistory(false)
            }, "Actualizar")
          ])
        ]),
        createElement("div", { className: "rb-events-layout" }, [
          createElement("aside", { className: "rb-panel rb-events-filters" }, [
            createElement("div", { className: "rb-panel-heading" }, [
              createElement("h2", { className: "h6 mb-0" }, "Filtros")
            ]),
            ...filters
          ]),
          createElement("section", { className: "rb-panel rb-events-main" }, [
            createElement("div", { className: "rb-panel-heading" }, [
              createElement("h2", { className: "h6 mb-0" }, "Eventos recientes")
            ]),
            this.listElement,
            this.paginationElement
          ])
        ])
      ])
    );

    this.bindFilters();
  }

  private async loadOptions(): Promise<void> {
    await Promise.all([
      this.fillOptions(this.cameraIdSelect, "camera_id", "Todas las cámaras"),
      this.fillOptions(this.cameraNameSelect, "camera_name", "Todos los nombres")
    ]);
  }

  private async fillOptions(select: HTMLSelectElement | undefined, field: string, placeholder: string): Promise<void> {
    if (!select) return;
    try {
      const payload = await this.api.get<OptionPayload>(`/api/v1/events/history/filter-options/?field=${field}`, { silent: true });
      select.replaceChildren(this.option("", placeholder), ...payload.items.map((item) => this.option(item.value, `${item.label} (${item.count})`)));
    } catch {
      select.replaceChildren(this.option("", placeholder));
    }
  }

  private async loadHistory(keepPage = true): Promise<void> {
    if (!keepPage) this.page = 1;
    this.setStatus("Cargando...");
    try {
      const payload = await this.api.get<HistoryPayload>(`/api/v1/events/history/?${this.params().toString()}`);
      this.items = payload.items;
      this.renderList();
      this.renderPagination(payload);
      this.setStatus(`${payload.items.length} de ${payload.total} eventos`);
    } catch {
      this.setStatus("Error");
      this.listElement?.replaceChildren(createElement("p", { className: "rb-muted mb-0" }, "No se pudo cargar el historial."));
    }
  }

  private renderList(): void {
    if (!this.listElement) return;
    if (!this.items.length) {
      this.listElement.replaceChildren(createElement("article", { className: "rb-events-empty" }, "No hay eventos para los filtros seleccionados."));
      return;
    }
    this.listElement.replaceChildren(...this.items.map((item) => {
      const imagePath = item.crop_path || item.image_file_path || "";
      return createElement("article", {
        className: "rb-event-card"
      }, [
        imagePath
          ? createElement("img", { className: "rb-event-thumb", attrs: { src: this.mediaUrl("crop", imagePath), alt: "Evidencia", loading: "lazy" } })
          : createElement("div", { className: "rb-event-thumb rb-event-thumb-empty" }, this.shortKind(item)),
        createElement("div", { className: "rb-event-copy" }, [
          createElement("div", { className: "rb-event-meta" }, [
            createElement("span", { className: "rb-event-tag" }, this.kindLabel(item)),
            createElement("span", { className: "rb-muted" }, this.formatDate(item.detected_at))
          ]),
          createElement("strong", { className: "rb-event-title" }, item.primary || item.title || "Evento detectado"),
          createElement("span", { className: "rb-device-meta" }, item.camera_name || item.camera_id || "Sin cámara"),
          createElement("span", { className: "rb-device-meta" }, item.summary || "")
        ]),
        createElement("button", {
          className: "btn btn-outline-danger btn-sm",
          attrs: { type: "button", "aria-label": "Archivar evento" },
          onClick: (event) => {
            event.stopPropagation();
            void this.updateStatus(item, "dismissed");
          }
        }, "Archivar")
      ]);
    }));
  }

  private renderPagination(payload: HistoryPayload): void {
    if (!this.paginationElement) return;
    const totalPages = Math.max(1, Number(payload.total_pages || 1));
    const current = Math.min(Math.max(1, Number(payload.page || 1)), totalPages);
    const buttons: HTMLElement[] = [];
    buttons.push(this.pageButton("‹", Math.max(1, current - 1), current <= 1));
    const start = Math.max(1, Math.min(current - 2, totalPages - 4));
    const end = Math.min(totalPages, start + 4);
    for (let page = start; page <= end; page += 1) {
      buttons.push(this.pageButton(String(page), page, false, page === current));
    }
    buttons.push(this.pageButton("›", Math.min(totalPages, current + 1), current >= totalPages));
    this.paginationElement.replaceChildren(...buttons);
  }

  private pageButton(label: string, page: number, disabled = false, active = false): HTMLButtonElement {
    const attrs: Record<string, string> = { type: "button" };
    if (disabled) attrs.disabled = "true";
    return createElement("button", {
      className: `rb-events-page ${active ? "is-active" : ""}`,
      attrs,
      onClick: () => {
        if (disabled) return;
        this.page = page;
        void this.loadHistory(true);
      }
    }, label) as HTMLButtonElement;
  }

  private async updateStatus(item: EventItem, status: string): Promise<void> {
    await this.api.patch(`/api/v1/events/history/${item.id}/status/`, { status });
    item.status = status;
    this.renderList();
    this.toastBus.success("Estado actualizado.");
  }

  private async clearFilters(): Promise<void> {
    [
      this.searchInput,
      this.dateFromInput,
      this.dateToInput,
      this.timeFromInput,
      this.timeToInput
    ].forEach((control) => {
      if (control) control.value = "";
    });
    [this.cameraIdSelect, this.cameraNameSelect, this.eventTypeSelect].forEach((control) => {
      if (control) control.value = "";
    });
    this.root.querySelectorAll<HTMLInputElement>("[data-events-category], [data-events-origin]")
      .forEach((input) => {
        input.checked = true;
      });
    await this.loadHistory(false);
  }

  private bindFilters(): void {
    const reload = () => {
      window.clearTimeout(Number(this.root.dataset.reloadTimer || 0));
      const timer = window.setTimeout(() => void this.loadHistory(false), 250);
      this.root.dataset.reloadTimer = String(timer);
    };
    [
      this.searchInput,
      this.dateFromInput,
      this.dateToInput,
      this.timeFromInput,
      this.timeToInput,
      this.cameraIdSelect,
      this.cameraNameSelect,
      this.eventTypeSelect
    ].forEach((control) => control?.addEventListener("input", reload));
    this.root.addEventListener("change", (event) => {
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement) reload();
    });
  }

  private params(): URLSearchParams {
    const params = new URLSearchParams({ page: String(this.page), page_size: String(this.pageSize) });
    this.addParam(params, "q", this.searchInput?.value);
    this.addParam(params, "date_from", this.dateFromInput?.value);
    this.addParam(params, "date_to", this.dateToInput?.value);
    this.addParam(params, "time_from", this.timeFromInput?.value);
    this.addParam(params, "time_to", this.timeToInput?.value);
    this.addParam(params, "camera_id", this.cameraIdSelect?.value);
    this.addParam(params, "camera_name", this.cameraNameSelect?.value);
    this.addParam(params, "event_types", this.eventTypeSelect?.value);
    this.addParam(params, "categories", this.checkedValues("category"));
    this.addParam(params, "origins", this.checkedValues("origin"));
    return params;
  }

  private addParam(params: URLSearchParams, key: string, value: string | undefined): void {
    const normalized = String(value || "").trim();
    if (normalized) params.set(key, normalized);
  }

  private checkedValues(group: string): string {
    return Array.from(this.root.querySelectorAll<HTMLInputElement>(`[data-events-${group}]`))
      .filter((input) => input.checked)
      .map((input) => input.dataset[`events${group[0].toUpperCase()}${group.slice(1)}`] || "")
      .filter(Boolean)
      .join(",");
  }

  private field(label: string, control: HTMLElement): HTMLElement {
    return createElement("label", { className: "rb-events-field" }, [
      createElement("span", { className: "form-label" }, label),
      control
    ]);
  }

  private checkboxGroup(label: string, options: string[][], group: "category" | "origin"): HTMLElement {
    return createElement("div", { className: "rb-events-field rb-events-field-wide" }, [
      createElement("span", { className: "form-label" }, label),
      createElement("div", { className: "rb-events-checks" }, options.map(([value, text]) => createElement("label", { className: "form-check" }, [
        createElement("input", {
          className: "form-check-input",
          dataset: group === "category" ? { eventsCategory: value } : { eventsOrigin: value },
          attrs: { type: "checkbox", checked: "true" }
        }),
        createElement("span", { className: "form-check-label" }, text)
      ])))
    ]);
  }

  private input(type: string): HTMLInputElement {
    return createElement("input", { className: "form-control", attrs: { type } }) as HTMLInputElement;
  }

  private option(value: string, label: string): HTMLOptionElement {
    return createElement("option", { attrs: { value } }, label) as HTMLOptionElement;
  }

  private mediaUrl(kind: "crop" | "video", path: string): string {
    return `/api/v1/events/media/${kind}/?path=${encodeURIComponent(path)}`;
  }

  private kindLabel(item: EventItem): string {
    return item.event_type_label || item.event_category_label || item.event_type || "Evento";
  }

  private shortKind(item: EventItem): string {
    return this.kindLabel(item).slice(0, 2).toUpperCase();
  }

  private formatDate(value: string): string {
    if (!value) return "Sin fecha";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString("es-EC", {
      timeZone: "America/Guayaquil",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  }

  private setStatus(value: string): void {
    if (this.statusElement) this.statusElement.textContent = value;
  }
}
