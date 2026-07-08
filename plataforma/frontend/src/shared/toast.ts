import { Toast } from "bootstrap";
import { createElement } from "./dom";

export class ToastBus {
  constructor(private readonly region: HTMLElement | null) {}

  success(message: string): void {
    this.show(message, "text-bg-success");
  }

  error(message: string): void {
    this.show(message, "text-bg-danger");
  }

  info(message: string): void {
    this.show(message, "text-bg-dark");
  }

  private show(message: string, variant: string): void {
    if (!this.region) {
      return;
    }

    const element = createElement("div", {
      className: `toast align-items-center border-0 ${variant}`,
      attrs: { role: "status", "aria-live": "polite", "aria-atomic": "true" }
    }, [
      createElement("div", { className: "d-flex" }, [
        createElement("div", { className: "toast-body" }, message),
        createElement("button", {
          className: "btn-close btn-close-white me-2 m-auto",
          attrs: { type: "button", "data-bs-dismiss": "toast", "aria-label": "Cerrar" }
        })
      ])
    ]);

    this.region.append(element);
    const toast = Toast.getOrCreateInstance(element, { delay: 3500 });
    element.addEventListener("hidden.bs.toast", () => element.remove(), { once: true });
    toast.show();
  }
}
