import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { ToastBus } from "../shared/toast";

type LoginResponse = {
  ok: boolean;
  redirect?: string;
  user: {
    username: string;
    name: string;
    roles: string[];
  };
};

const BRAND_MARK_SRC = "/static/brand/logoSimplificadoC.png";
const BRAND_WORDMARK_SRC = "/static/brand/LoogoBlanco.png";
const SVG_NS = "http://www.w3.org/2000/svg";

export class LoginPage {
  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  mount(): void {
    const usernameInput = createElement("input", {
      attrs: {
        id: "login-username",
        name: "username",
        type: "text",
        placeholder: "robiotec",
        autocomplete: "username",
        required: "true"
      }
    }) as HTMLInputElement;
    const passwordInput = createElement("input", {
      attrs: {
        id: "login-password",
        name: "password",
        type: "password",
        placeholder: "************",
        autocomplete: "current-password",
        required: "true"
      }
    }) as HTMLInputElement;
    const feedback = createElement("p", {
      className: "login-feedback",
      attrs: { role: "status", "aria-live": "polite" }
    });
    const submitButton = createElement("button", { className: "login-submit", attrs: { type: "submit" } }, "Entrar al sistema") as HTMLButtonElement;
    const passwordToggle = createElement("button", {
      className: "login-password-toggle",
      attrs: { type: "button", "aria-label": "Mostrar contraseña", "aria-pressed": "false", "data-state": "hidden" },
      onClick: () => {
        const visible = passwordInput.type !== "text";
        passwordInput.type = visible ? "text" : "password";
        passwordToggle.dataset.state = visible ? "visible" : "hidden";
        passwordToggle.setAttribute("aria-pressed", String(visible));
        passwordToggle.setAttribute("aria-label", visible ? "Ocultar contraseña" : "Mostrar contraseña");
        passwordInput.focus();
      }
    }) as HTMLButtonElement;
    passwordToggle.append(this.passwordIcon("login-password-toggle-icon login-password-toggle-icon-closed", false));
    passwordToggle.append(this.passwordIcon("login-password-toggle-icon login-password-toggle-icon-open", true));

    const form = createElement("form", { className: "login-form", attrs: { novalidate: "true" } }, [
      createElement("label", { className: "login-field", attrs: { for: "login-username" } }, [
        createElement("span", {}, "Usuario"),
        usernameInput
      ]),
      createElement("label", { className: "login-field login-field-password", attrs: { for: "login-password" } }, [
        createElement("span", {}, "Contraseña"),
        createElement("div", { className: "login-password-wrap" }, [passwordInput, passwordToggle])
      ]),
      feedback,
      submitButton
    ]) as HTMLFormElement;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.submit(form, feedback, submitButton);
    });

    this.root.replaceChildren(
      createElement("header", { className: "login-panel-head" }, [
        createElement("div", { className: "login-mobile-brand", attrs: { "aria-hidden": "true" } }, [
          createElement("img", { className: "login-mobile-brand-logo", attrs: { src: BRAND_WORDMARK_SRC, alt: "ROBIOTEC" } })
        ]),
        createElement("div", { className: "login-panel-badge", attrs: { "aria-hidden": "true" } }, [
          createElement("img", { attrs: { src: BRAND_MARK_SRC, alt: "" } })
        ]),
        createElement("h2", {}, "Inicia sesión"),
        createElement("p", {}, "Ingresa con tus credenciales operativas para continuar hacia el control principal."),
        createElement("p", { className: "login-panel-copy-mobile" }, "Accede rápido al monitoreo y sigue con tu operación."),
        createElement("div", { className: "login-mobile-pills", attrs: { "aria-hidden": "true" } }, [
          createElement("span", {}, "Cámaras"),
          createElement("span", {}, "Mapa"),
          createElement("span", {}, "Alertas")
        ])
      ]),
      form,
      createElement("div", { className: "login-divider" }, createElement("span", {}, "Perfiles rápidos")),
      createElement("div", { className: "login-alt-grid" }, [
        createElement("article", { className: "login-alt-card" }, [
          createElement("strong", {}, "Supervisor"),
          createElement("p", {}, "Acceso orientado a visión global, coordinación y seguimiento estratégico.")
        ]),
        createElement("article", { className: "login-alt-card" }, [
          createElement("strong", {}, "Analista"),
          createElement("p", {}, "Entrada para revisar evidencia, trazas de eventos y contexto técnico.")
        ])
      ]),
      createElement("p", { className: "login-footnote" }, "Usa un usuario registrado en la base para ingresar.")
    );
  }

  private passwordIcon(className: string, visible: boolean): SVGSVGElement {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", className);
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("aria-hidden", "true");
    if (visible) {
      this.appendSvgPath(svg, "M2.75 12s3.35-6 9.25-6 9.25 6 9.25 6-3.35 6-9.25 6-9.25-6-9.25-6Z");
      const circle = document.createElementNS(SVG_NS, "circle");
      circle.setAttribute("cx", "12");
      circle.setAttribute("cy", "12");
      circle.setAttribute("r", "3");
      circle.setAttribute("stroke", "currentColor");
      circle.setAttribute("stroke-width", "1.8");
      svg.append(circle);
      return svg;
    }

    this.appendSvgPath(svg, "M3 3 21 21");
    this.appendSvgPath(svg, "M10.58 10.58a2 2 0 0 0 2.84 2.84");
    this.appendSvgPath(svg, "M9.88 5.09A10.94 10.94 0 0 1 12 4.91c5.05 0 8.27 4.15 9 5.09a1.12 1.12 0 0 1 0 1.34 16.76 16.76 0 0 1-3.22 3.19");
    this.appendSvgPath(svg, "M6.61 6.61A16.2 16.2 0 0 0 3 10a1.12 1.12 0 0 0 0 1.34c.75 1 4 5.09 9 5.09a10.5 10.5 0 0 0 4.29-.91");
    return svg;
  }

  private appendSvgPath(svg: SVGSVGElement, d: string): void {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.8");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    svg.append(path);
  }

  private async submit(form: HTMLFormElement, feedback: HTMLElement, submitButton: HTMLButtonElement): Promise<void> {
    const data = new FormData(form);
    const username = String(data.get("username") ?? "").trim();
    const password = String(data.get("password") ?? "");
    if (!username || !password) {
      this.setFeedback(feedback, "Ingresa tu usuario y contraseña para continuar.", "error");
      return;
    }

    const defaultLabel = submitButton.textContent || "Entrar al sistema";
    submitButton.disabled = true;
    submitButton.textContent = "Validando acceso...";
    this.setFeedback(feedback, "Consultando credenciales en la base de datos...", "pending");
    try {
      const payload = await this.api.post<LoginResponse>("/api/v1/auth/login/", { username, password }, { silent: true });
      this.setFeedback(feedback, "Acceso autorizado. Redirigiendo...", "success");
      const nextUrl = this.nextUrl();
      window.location.assign(nextUrl === "/" ? this.safePath(payload.redirect || "/") : nextUrl);
    } catch {
      this.setFeedback(feedback, "Usuario o clave incorrectos.", "error");
      this.toastBus.error("Usuario o clave incorrectos.");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = defaultLabel;
    }
  }

  private setFeedback(element: HTMLElement, message: string, state: "pending" | "success" | "error" = "pending"): void {
    element.textContent = message;
    element.dataset.state = state;
  }

  private nextUrl(): string {
    const value = this.root.dataset.next || "/";
    return this.safePath(value);
  }

  private safePath(value: string): string {
    if (!value.startsWith("/") || value.startsWith("//")) {
      return "/";
    }
    return value;
  }
}
