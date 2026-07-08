import { Modal } from "bootstrap";

export class ModalController {
  private readonly modal: Modal;

  constructor(private readonly element: HTMLElement) {
    this.modal = Modal.getOrCreateInstance(element);
  }

  open(): void {
    this.modal.show();
  }

  close(): void {
    this.modal.hide();
  }

  setTitle(value: string): void {
    const title = this.element.querySelector<HTMLElement>("[data-modal-title]");
    if (title) {
      title.textContent = value;
    }
  }
}
