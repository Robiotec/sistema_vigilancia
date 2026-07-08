export class FormBinder<T extends Record<string, unknown>> {
  constructor(private readonly form: HTMLFormElement) {}

  read(): T {
    const data = new FormData(this.form);
    const payload: Record<string, unknown> = {};
    for (const [key, value] of data.entries()) {
      payload[key] = value;
    }
    return payload as T;
  }

  reset(values: Partial<Record<keyof T, string | number | boolean | null>> = {}): void {
    this.form.reset();
    for (const [key, value] of Object.entries(values)) {
      const field = this.form.elements.namedItem(key);
      if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement || field instanceof HTMLTextAreaElement) {
        field.value = value == null ? "" : String(value);
      }
    }
  }
}
