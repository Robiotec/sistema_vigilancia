import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { ToastBus } from "../shared/toast";

type Status = "ok" | "warning" | "error";

type SystemdItem = {
  name: string;
  label: string;
  category: string;
  critical: boolean;
  status: Status;
  active_state: string;
  sub_state: string;
  load_state: string;
  unit_file_state: string;
  result: string;
  description: string;
  error: string;
};

type EndpointItem = {
  name: string;
  label: string;
  category: string;
  critical: boolean;
  url: string;
  status: Status;
  http_status: number;
  latency_ms: number;
  error: string;
};

type MediaMTXPath = {
  name: string;
  ready: boolean;
  source: string;
};

type OperationsPayload = {
  generated_at: string;
  summary: {
    status: Status;
    systemd_total: number;
    systemd_ok: number;
    systemd_warning: number;
    systemd_error: number;
    endpoints_total: number;
    endpoints_ok: number;
    mediamtx_ready_paths: number;
    mediamtx_total_paths: number;
  };
  systemd: SystemdItem[];
  endpoints: EndpointItem[];
  mediamtx: {
    ok: boolean;
    status: Status;
    ready_paths: number;
    total_paths: number;
    error: string;
    items: MediaMTXPath[];
  };
};

export class OperationsPage {
  private payload?: OperationsPayload;
  private statusElement?: HTMLElement;

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.root.replaceChildren(createElement("div", { className: "rb-loading" }, "Cargando servicios..."));
    await this.load();
    this.render();
  }

  private async load(): Promise<void> {
    this.payload = await this.api.get<OperationsPayload>("/api/v1/operations/overview/");
  }

  private render(): void {
    const payload = this.payload;
    if (!payload) return;
    this.statusElement = createElement("span", { className: `rb-operation-status is-${payload.summary.status}` }, this.statusLabel(payload.summary.status));
    this.root.replaceChildren(
      createElement("section", { className: "rb-operation-shell" }, [
        createElement("div", { className: "rb-admin-header" }, [
          createElement("div", {}, [
            createElement("span", { className: "rb-kicker" }, "Operaciones internas"),
            createElement("h1", { className: "h4 mb-1" }, "Servicios externos"),
            createElement("p", { className: "rb-muted mb-0" }, "Estado de procesos systemd, endpoints locales y MediaMTX.")
          ]),
          createElement("div", { className: "rb-admin-actions" }, [
            this.statusElement,
            createElement("button", {
              className: "btn btn-outline-light btn-sm",
              attrs: { type: "button" },
              onClick: () => void this.reload()
            }, "Actualizar")
          ])
        ]),
        this.summaryBand(payload),
        createElement("div", { className: "rb-operation-layout" }, [
          this.panel("Procesos systemd", String(payload.systemd.length), this.systemdList(payload.systemd)),
          createElement("div", { className: "rb-operation-side" }, [
            this.panel("Endpoints", `${payload.summary.endpoints_ok}/${payload.summary.endpoints_total}`, this.endpointList(payload.endpoints)),
            this.panel("MediaMTX", `${payload.mediamtx.ready_paths}/${payload.mediamtx.total_paths}`, this.mediamtxList(payload.mediamtx.items, payload.mediamtx.error))
          ])
        ])
      ])
    );
  }

  private summaryBand(payload: OperationsPayload): HTMLElement {
    return createElement("section", { className: "rb-access-summary" }, [
      this.summaryCard("Estado", this.statusLabel(payload.summary.status)),
      this.summaryCard("Systemd OK", `${payload.summary.systemd_ok}/${payload.summary.systemd_total}`),
      this.summaryCard("Advertencias", String(payload.summary.systemd_warning)),
      this.summaryCard("MediaMTX paths", `${payload.summary.mediamtx_ready_paths}/${payload.summary.mediamtx_total_paths}`)
    ]);
  }

  private summaryCard(label: string, value: string): HTMLElement {
    return createElement("article", { className: "rb-access-card" }, [
      createElement("span", {}, label),
      createElement("strong", {}, value)
    ]);
  }

  private panel(title: string, count: string, content: HTMLElement): HTMLElement {
    return createElement("section", { className: "rb-panel rb-operation-panel" }, [
      createElement("div", { className: "rb-panel-heading" }, [
        createElement("h2", { className: "h5 mb-0" }, title),
        createElement("span", { className: "rb-count" }, count)
      ]),
      content
    ]);
  }

  private systemdList(items: SystemdItem[]): HTMLElement {
    return createElement("div", { className: "rb-operation-list" }, items.map((item) => {
      const meta = [
        item.category,
        `${item.active_state}/${item.sub_state}`,
        item.unit_file_state,
        item.critical ? "crítico" : "secundario"
      ].filter(Boolean).join(" · ");
      return this.row(item.status, item.label, item.name, meta, item.error || item.result || item.description);
    }));
  }

  private endpointList(items: EndpointItem[]): HTMLElement {
    return createElement("div", { className: "rb-operation-list" }, items.map((item) => {
      const meta = [
        item.category,
        item.http_status ? `HTTP ${item.http_status}` : "sin respuesta",
        `${item.latency_ms.toFixed(1)} ms`,
        item.critical ? "crítico" : "secundario"
      ].join(" · ");
      return this.row(item.status, item.label, item.url, meta, item.error);
    }));
  }

  private mediamtxList(items: MediaMTXPath[], error: string): HTMLElement {
    if (error) {
      return createElement("p", { className: "rb-muted mb-0" }, error);
    }
    if (!items.length) {
      return createElement("p", { className: "rb-muted mb-0" }, "Sin paths publicados.");
    }
    return createElement("div", { className: "rb-operation-list rb-operation-path-list" }, items.slice(0, 24).map((item) => {
      const status: Status = item.ready ? "ok" : "warning";
      return this.row(status, item.name, item.source || "sin fuente", item.ready ? "listo" : "sin publicar", "");
    }));
  }

  private row(status: Status, title: string, subtitle: string, meta: string, detail: string): HTMLElement {
    return createElement("article", { className: "rb-operation-row" }, [
      createElement("span", { className: `rb-operation-dot is-${status}` }),
      createElement("div", {}, [
        createElement("strong", {}, title),
        createElement("span", { className: "rb-device-meta" }, subtitle),
        createElement("small", { className: "rb-muted" }, meta),
        detail ? createElement("small", { className: "rb-operation-detail" }, detail) : ""
      ])
    ]);
  }

  private async reload(): Promise<void> {
    try {
      this.statusElement?.classList.remove("is-ok", "is-warning", "is-error");
      if (this.statusElement) this.statusElement.textContent = "Actualizando...";
      await this.load();
      this.render();
    } catch {
      this.toastBus.error("No se pudo actualizar el estado de servicios.");
    }
  }

  private statusLabel(status: Status): string {
    if (status === "ok") return "Operativo";
    if (status === "warning") return "Advertencia";
    return "Revisar";
  }
}
