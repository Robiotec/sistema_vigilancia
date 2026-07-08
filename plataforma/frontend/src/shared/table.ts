import { createElement } from "./dom";

type Column<T> = {
  label: string;
  value: (row: T) => string | HTMLElement;
  className?: string;
};

export class DataTable<T> {
  constructor(
    private readonly table: HTMLTableElement,
    private readonly columns: Array<Column<T>>
  ) {}

  render(rows: T[]): void {
    this.table.replaceChildren(this.header(), this.body(rows));
  }

  private header(): HTMLTableSectionElement {
    const thead = document.createElement("thead");
    const row = document.createElement("tr");
    for (const column of this.columns) {
      row.append(createElement("th", {}, column.label));
    }
    thead.append(row);
    return thead;
  }

  private body(rows: T[]): HTMLTableSectionElement {
    const tbody = document.createElement("tbody");
    for (const item of rows) {
      const row = document.createElement("tr");
      for (const column of this.columns) {
        row.append(createElement("td", { className: column.className }, column.value(item)));
      }
      tbody.append(row);
    }
    return tbody;
  }
}
