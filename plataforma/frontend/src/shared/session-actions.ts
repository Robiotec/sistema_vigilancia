import { ApiClient } from "./api";
import { createElement } from "./dom";
import { ToastBus } from "./toast";

type SessionResponse = {
  authenticated: boolean;
  user?: {
    username: string;
    name: string;
    roles: string[];
  };
};

export class SessionActions {
  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    try {
      const session = await this.api.get<SessionResponse>("/api/v1/auth/session/", { silent: true });
      if (session.authenticated && session.user) {
        this.renderAuthenticated(session.user.name || session.user.username);
        return;
      }
    } catch {
      this.renderAnonymous();
      return;
    }
    this.renderAnonymous();
  }

  private renderAuthenticated(name: string): void {
    if (this.root.dataset.variant === "sidebar") {
      this.root.replaceChildren(
        createElement("div", { className: "sidebar-footer-user", attrs: { "aria-label": "Usuario autenticado" } }, [
          createElement("span", { className: "sidebar-footer-user-label" }, "Usuario activo"),
          createElement("strong", { className: "sidebar-footer-user-name" }, name)
        ]),
        createElement("button", {
          className: "sidebar-link sidebar-link-logout",
          attrs: { type: "button", "aria-label": "Cerrar sesión" },
          onClick: () => this.logout()
        }, [
          createElement("span", { className: "sidebar-icon", attrs: { "aria-hidden": "true" } }, "S"),
          createElement("span", { className: "sidebar-link-copy" }, [
            createElement("strong", {}, "Cerrar sesión"),
            createElement("span", {}, "Salir del panel")
          ]),
          createElement("span", { className: "sidebar-link-tooltip", attrs: { "aria-hidden": "true" } }, "Cerrar sesión")
        ])
      );
      return;
    }

    this.root.replaceChildren(
      createElement("span", { className: "rb-session-name" }, name),
      createElement("button", {
        className: "btn btn-outline-light btn-sm",
        attrs: { type: "button" },
        onClick: () => this.logout()
      }, "Salir")
    );
  }

  private renderAnonymous(): void {
    if (this.root.dataset.variant === "sidebar") {
      this.root.replaceChildren(
        createElement("a", { className: "sidebar-link sidebar-link-logout", attrs: { href: "/login/", "aria-label": "Ingresar" } }, [
          createElement("span", { className: "sidebar-icon", attrs: { "aria-hidden": "true" } }, "I"),
          createElement("span", { className: "sidebar-link-copy" }, [
            createElement("strong", {}, "Ingresar"),
            createElement("span", {}, "Abrir sesión")
          ]),
          createElement("span", { className: "sidebar-link-tooltip", attrs: { "aria-hidden": "true" } }, "Ingresar")
        ])
      );
      return;
    }

    this.root.replaceChildren(
      createElement("a", { className: "btn btn-outline-light btn-sm", attrs: { href: "/login/" } }, "Ingresar")
    );
  }

  private async logout(): Promise<void> {
    try {
      await this.api.post("/api/v1/auth/logout/", {});
      window.location.assign("/login/");
    } catch {
      this.toastBus.error("No se pudo cerrar la sesión.");
    }
  }
}
