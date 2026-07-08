import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";

type HealthPayload = {
  service: string;
  status: string;
  database: string;
};

export class DashboardPage {
  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient
  ) {}

  async mount(): Promise<void> {
    const healthUrl = this.root.dataset.apiHealthUrl ?? "/api/v1/health/";
    this.root.replaceChildren(
      createElement("div", { className: "rb-loading" }, "Cargando estado...")
    );

    const health = await this.api.get<HealthPayload>(healthUrl);
    this.root.replaceChildren(
      createElement("div", { className: "rb-status-grid" }, [
        this.statusItem("Servicio", health.service),
        this.statusItem("Estado", health.status),
        this.statusItem("Base de datos", health.database)
      ])
    );
  }

  private statusItem(label: string, value: string): HTMLElement {
    return createElement("div", { className: "rb-status-item" }, [
      createElement("span", { className: "rb-status-label" }, label),
      createElement("strong", { className: "rb-status-value" }, value)
    ]);
  }
}
