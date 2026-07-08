import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { ToastBus } from "../shared/toast";

type ProfilePayload = {
  user: {
    id: string;
    username: string;
    name: string;
    email: string;
    company_name: string;
    active: boolean;
    roles: string[];
    role_label: string;
    created_at: string;
    updated_at: string;
  };
  stats: {
    companies: number;
    cameras: number;
    vehicles: number;
    rboxes: number;
    drones: number;
  };
  updated_at: string;
};

export class ProfilePage {
  private payload?: ProfilePayload;
  private form?: HTMLFormElement;

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.root.replaceChildren(createElement("div", { className: "rb-loading" }, "Cargando perfil..."));
    await this.load();
    this.render();
  }

  private async load(): Promise<void> {
    this.payload = await this.api.get<ProfilePayload>("/api/v1/auth/profile/");
  }

  private render(): void {
    const payload = this.payload;
    if (!payload) return;
    const user = payload.user;
    this.form = createElement("form", { className: "rb-profile-form rb-device-form" }) as HTMLFormElement;
    this.form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.submit();
    });
    this.form.replaceChildren(
      this.input("name", "Nombre visible", user.name, "text"),
      this.input("email", "Correo", user.email, "email"),
      this.input("current_password", "Contraseña actual", "", "password"),
      this.input("new_password", "Nueva contraseña", "", "password"),
      this.input("confirm_password", "Confirmar contraseña", "", "password"),
      createElement("div", { className: "rb-profile-actions" }, [
        createElement("button", { className: "btn btn-danger", attrs: { type: "submit" } }, "Guardar cambios")
      ])
    );

    this.root.replaceChildren(
      createElement("div", { className: "rb-admin-header" }, [
        createElement("div", {}, [
          createElement("span", { className: "rb-kicker" }, "Perfil operativo"),
          createElement("h1", { className: "h4 mb-1" }, user.name || user.username),
          createElement("p", { className: "rb-muted mb-0" }, `${user.role_label} · ${user.company_name || "Sin organización"}`)
        ])
      ]),
      createElement("section", { className: "rb-profile-hero" }, [
        createElement("div", { className: "rb-profile-avatar" }, this.initials(user.name || user.username)),
        createElement("div", { className: "rb-profile-identity" }, [
          createElement("span", { className: "rb-kicker" }, "Cuenta autenticada"),
          createElement("strong", {}, user.username),
          createElement("span", { className: "rb-muted" }, user.email || "Sin correo registrado")
        ])
      ]),
      createElement("section", { className: "rb-reports-kpis" }, [
        this.stat("Empresas", payload.stats.companies),
        this.stat("Cámaras", payload.stats.cameras),
        this.stat("Vehículos", payload.stats.vehicles),
        this.stat("RBox", payload.stats.rboxes),
        this.stat("Drones", payload.stats.drones)
      ]),
      createElement("section", { className: "rb-profile-grid" }, [
        createElement("article", { className: "rb-panel" }, [
          createElement("div", { className: "rb-panel-heading" }, [
            createElement("h2", { className: "h5 mb-0" }, "Datos de cuenta")
          ]),
          createElement("div", { className: "rb-profile-data" }, [
            this.dataRow("ID", user.id),
            this.dataRow("Usuario", user.username),
            this.dataRow("Rol", user.role_label),
            this.dataRow("Estado", user.active ? "Activo" : "Inactivo"),
            this.dataRow("Creado", this.formatDate(user.created_at)),
            this.dataRow("Actualizado", this.formatDate(user.updated_at))
          ])
        ]),
        createElement("article", { className: "rb-panel" }, [
          createElement("div", { className: "rb-panel-heading" }, [
            createElement("h2", { className: "h5 mb-0" }, "Editar perfil")
          ]),
          this.form
        ]),
        createElement("article", { className: "rb-panel rb-profile-quick-panel" }, [
          createElement("div", { className: "rb-panel-heading" }, [
            createElement("div", {}, [
              createElement("span", { className: "rb-kicker" }, "Accion rapida"),
              createElement("h2", { className: "h5 mb-0" }, "Ventanas disponibles")
            ])
          ]),
          this.quickLinks(user.roles)
        ])
      ])
    );
  }

  private quickLinks(roles: string[]): HTMLElement {
    const permissions = this.pagePermissions(roles);
    const links = [
      ["dashboard", "/", "Dashboard"],
      ["cameras", "/camaras/", "Camaras"],
      ["map", "/mapa/", "Mapa"],
      ["events", "/eventos/", "Eventos"],
      ["vehicles", "/gestion-kilometros/", "Kilometros"],
      ["reports", "/reportes/", "Reportes"],
      ["notifications", "/notificaciones/", "Notificaciones"],
      ["admin_users", "/usuarios/", "Usuarios"]
    ]
      .filter(([permission]) => permissions.has(permission))
      .map(([, href, label]) => createElement("a", { className: "rb-profile-quick-link", attrs: { href } }, label));
    return createElement("div", { className: "rb-profile-quick-links" }, links.length ? links : [
      createElement("a", { className: "rb-profile-quick-link", attrs: { href: "/perfil/" } }, "Perfil")
    ]);
  }

  private pagePermissions(roles: string[]): Set<string> {
    const permissions = new Set<string>(["profile"]);
    const roleMap: Record<string, string[]> = {
      master: ["admin_users", "admin_orgs", "edit", "dashboard", "cameras", "map", "events", "vehicles", "reports", "notifications"],
      admin: ["admin_users", "edit", "dashboard", "cameras", "map", "events", "vehicles", "reports", "notifications"],
      viewer: ["dashboard", "cameras", "map", "events", "vehicles", "reports"],
      operator_cameras: ["cameras"],
      operator_map: ["map", "vehicles"]
    };
    roles.forEach((role) => roleMap[role]?.forEach((permission) => permissions.add(permission)));
    return permissions;
  }

  private input(name: string, label: string, value: string, type: string): HTMLElement {
    const input = createElement("input", {
      className: "form-control",
      attrs: { type, name, autocomplete: type === "password" ? "new-password" : "off" }
    }) as HTMLInputElement;
    input.value = value;
    return createElement("label", { className: "rb-profile-field" }, [
      createElement("span", { className: "form-label" }, label),
      input
    ]);
  }

  private async submit(): Promise<void> {
    if (!this.form) return;
    const data = new FormData(this.form);
    const payload = {
      name: String(data.get("name") || ""),
      email: String(data.get("email") || ""),
      current_password: String(data.get("current_password") || ""),
      new_password: String(data.get("new_password") || ""),
      confirm_password: String(data.get("confirm_password") || "")
    };
    try {
      this.payload = await this.api.put<ProfilePayload>("/api/v1/auth/profile/", payload);
      this.toastBus.success("Perfil actualizado.");
      this.render();
    } catch {
      this.toastBus.error("No se pudo guardar el perfil.");
    }
  }

  private stat(label: string, value: number): HTMLElement {
    return createElement("article", { className: "rb-access-card" }, [
      createElement("span", {}, label),
      createElement("strong", {}, String(value ?? 0))
    ]);
  }

  private dataRow(label: string, value: string): HTMLElement {
    return createElement("div", { className: "rb-profile-data-row" }, [
      createElement("span", {}, label),
      createElement("strong", {}, value || "--")
    ]);
  }

  private initials(value: string): string {
    return value
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "RB";
  }

  private formatDate(value: string): string {
    if (!value) return "--";
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
}
