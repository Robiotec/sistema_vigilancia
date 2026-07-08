import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { ModalController } from "../shared/modal";
import { ToastBus } from "../shared/toast";

type RoleItem = {
  id: string;
  name: string;
  label: string;
  description: string;
  active: boolean;
  users: number;
};

type CompanyItem = {
  id: string;
  name: string;
  ruc: string;
  address: string;
  active: boolean;
};

type UserItem = {
  id: string;
  username: string;
  name: string;
  email: string;
  active: boolean;
  company_id: string;
  company_name: string;
  role_names: string[];
  role_label: string;
};

type AccessPayload = {
  users: UserItem[];
  companies: CompanyItem[];
  roles: RoleItem[];
  summary: {
    users: number;
    companies: number;
    roles: number;
    scope: string;
    updated_at: string;
  };
};

type ModalMode = "user" | "company";

type FieldSpec = {
  name: string;
  label: string;
  type?: "text" | "email" | "password" | "select" | "textarea" | "checkbox";
  required?: boolean;
  placeholder?: string;
  options?: Array<{ value: string; label: string }>;
};

export class UserAccessPage {
  private data: AccessPayload = {
    users: [],
    companies: [],
    roles: [],
    summary: { users: 0, companies: 0, roles: 0, scope: "", updated_at: "" }
  };
  private modal?: ModalController;
  private form?: HTMLFormElement;
  private mode: ModalMode = "user";
  private editingId = "";
  private searchInput?: HTMLInputElement;
  private companyFilter?: HTMLSelectElement;

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.root.replaceChildren(createElement("div", { className: "rb-loading" }, "Cargando accesos..."));
    await this.load();
    this.render();
  }

  private async load(): Promise<void> {
    this.data = await this.api.get<AccessPayload>("/api/v1/accounts/access/");
  }

  private render(): void {
    const modalElement = this.modalElement();
    this.searchInput = createElement("input", {
      className: "form-control form-control-sm",
      attrs: { type: "search", placeholder: "Buscar usuario, correo u organizacion" },
      onInput: () => this.renderDirectories()
    }) as HTMLInputElement;
    this.companyFilter = createElement("select", {
      className: "form-select form-select-sm",
      onChange: () => this.renderDirectories()
    }, [
      createElement("option", { attrs: { value: "" } }, "Todas las organizaciones"),
      ...this.data.companies.map((company) => createElement("option", { attrs: { value: company.id } }, company.name))
    ]) as HTMLSelectElement;
    this.root.replaceChildren(
      createElement("div", { className: "rb-admin-header" }, [
        createElement("div", {}, [
          createElement("span", { className: "rb-kicker" }, "Administración"),
          createElement("h1", { className: "h4 mb-1" }, "Gestión de accesos"),
          createElement("p", { className: "rb-muted mb-0" }, "Usuarios, organizaciones y roles operativos.")
        ]),
        createElement("div", { className: "rb-admin-actions" }, [
          createElement("button", {
            className: "btn btn-outline-light",
            attrs: { type: "button" },
            onClick: () => this.openCreate("company")
          }, "Nueva organización"),
          createElement("button", {
            className: "btn btn-danger",
            attrs: { type: "button" },
            onClick: () => this.openCreate("user")
          }, "Nuevo usuario")
        ])
      ]),
      this.summaryBand(),
      createElement("section", { className: "rb-panel rb-access-toolbar" }, [
        createElement("label", { className: "rb-reports-field" }, [
          createElement("span", { className: "form-label" }, "Buscar"),
          this.searchInput
        ]),
        createElement("label", { className: "rb-reports-field" }, [
          createElement("span", { className: "form-label" }, "Organizacion"),
          this.companyFilter
        ])
      ]),
      createElement("div", { className: "rb-device-grid rb-access-grid" }, [
        this.panel("Usuarios", String(this.filteredUsers().length), this.userList()),
        this.panel("Organizaciones", String(this.filteredCompanies().length), this.companyList()),
        this.panel("Roles", String(this.data.roles.length), this.roleList())
      ]),
      modalElement
    );
    this.modal = new ModalController(modalElement);
  }

  private renderDirectories(): void {
    const grid = this.root.querySelector<HTMLElement>(".rb-access-grid");
    if (!grid) return;
    grid.replaceChildren(
      this.panel("Usuarios", String(this.filteredUsers().length), this.userList()),
      this.panel("Organizaciones", String(this.filteredCompanies().length), this.companyList()),
      this.panel("Roles", String(this.data.roles.length), this.roleList())
    );
  }

  private summaryBand(): HTMLElement {
    return createElement("section", { className: "rb-access-summary" }, [
      this.summaryCard("Usuarios", String(this.data.summary.users || this.data.users.length)),
      this.summaryCard("Organizaciones", String(this.data.summary.companies || this.data.companies.length)),
      this.summaryCard("Alcance", this.data.summary.scope === "global" ? "Global" : "Organización"),
      this.summaryCard("Actualizado", this.formatDate(this.data.summary.updated_at))
    ]);
  }

  private summaryCard(label: string, value: string): HTMLElement {
    return createElement("article", { className: "rb-access-card" }, [
      createElement("span", {}, label),
      createElement("strong", {}, value)
    ]);
  }

  private panel(title: string, count: string, content: HTMLElement): HTMLElement {
    return createElement("section", { className: "rb-panel rb-device-panel" }, [
      createElement("div", { className: "rb-panel-heading" }, [
        createElement("h2", { className: "h5 mb-0" }, title),
        createElement("span", { className: "rb-count" }, count)
      ]),
      content
    ]);
  }

  private userList(): HTMLElement {
    const users = this.filteredUsers();
    if (!users.length) {
      return createElement("p", { className: "rb-muted mb-0" }, "Sin usuarios registrados.");
    }
    return createElement("div", { className: "rb-device-list" }, users.map((user) => {
      const meta = [
        user.email,
        user.company_name || "Sin organización",
        user.active ? "activo" : "inactivo"
      ].filter(Boolean).join(" · ");
      return createElement("button", {
        className: "rb-device-row",
        attrs: { type: "button" },
        onClick: () => this.openEdit("user", user.id)
      }, [
        createElement("span", { className: "rb-device-title" }, user.name || user.username),
        createElement("span", { className: "rb-device-meta" }, meta),
        createElement("span", { className: "rb-device-tags" }, [
          createElement("span", { className: "rb-device-status-tag is-accent" }, user.role_label || "Sin rol"),
          createElement("span", { className: user.active ? "rb-device-status-tag is-ok" : "rb-device-status-tag is-off" }, user.active ? "Activo" : "Inactivo")
        ])
      ]);
    }));
  }

  private companyList(): HTMLElement {
    const companies = this.filteredCompanies();
    if (!companies.length) {
      return createElement("p", { className: "rb-muted mb-0" }, "Sin organizaciones registradas.");
    }
    return createElement("div", { className: "rb-device-list" }, companies.map((company) => {
      const meta = [
        company.ruc,
        company.address,
        company.active ? "activa" : "inactiva"
      ].filter(Boolean).join(" · ");
      return createElement("button", {
        className: "rb-device-row",
        attrs: { type: "button" },
        onClick: () => this.openEdit("company", company.id)
      }, [
        createElement("span", { className: "rb-device-title" }, company.name),
        createElement("span", { className: "rb-device-meta" }, meta || "Sin descripción"),
        createElement("span", { className: "rb-device-tags" }, [
          createElement("span", { className: company.active ? "rb-device-status-tag is-ok" : "rb-device-status-tag is-off" }, company.active ? "Activa" : "Inactiva"),
          createElement("span", { className: "rb-device-status-tag is-info" }, `${this.data.users.filter((user) => user.company_id === company.id).length} usuarios`)
        ])
      ]);
    }));
  }

  private filteredUsers(): UserItem[] {
    const needle = this.searchInput?.value.trim().toLowerCase() || "";
    const companyId = this.companyFilter?.value || "";
    return this.data.users.filter((user) => {
      if (companyId && user.company_id !== companyId) return false;
      if (!needle) return true;
      return [
        user.username,
        user.name,
        user.email,
        user.company_name,
        user.role_label,
        ...user.role_names
      ].some((value) => String(value || "").toLowerCase().includes(needle));
    });
  }

  private filteredCompanies(): CompanyItem[] {
    const needle = this.searchInput?.value.trim().toLowerCase() || "";
    const companyId = this.companyFilter?.value || "";
    return this.data.companies.filter((company) => {
      if (companyId && company.id !== companyId) return false;
      if (!needle) return true;
      return [company.name, company.ruc, company.address]
        .some((value) => String(value || "").toLowerCase().includes(needle));
    });
  }

  private roleList(): HTMLElement {
    if (!this.data.roles.length) {
      return createElement("p", { className: "rb-muted mb-0" }, "Sin roles disponibles.");
    }
    return createElement("div", { className: "rb-access-role-list" }, this.data.roles.map((role) => createElement("article", { className: "rb-access-role" }, [
      createElement("span", { className: "rb-event-tag" }, role.name),
      createElement("strong", {}, role.label),
      createElement("small", { className: "rb-muted" }, `${role.users} usuarios asignados`)
    ])));
  }

  private modalElement(): HTMLElement {
    const form = createElement("form", { className: "modal-body rb-device-form" }) as HTMLFormElement;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.submit();
    });
    this.form = form;

    return createElement("div", { className: "modal fade", attrs: { tabindex: "-1", "aria-hidden": "true" } }, [
      createElement("div", { className: "modal-dialog modal-dialog-centered modal-lg" }, [
        createElement("div", { className: "modal-content rb-modal-content" }, [
          createElement("div", { className: "modal-header" }, [
            createElement("h2", { className: "modal-title h5", attrs: { "data-modal-title": "true" } }, "Editar"),
            createElement("button", { className: "btn-close btn-close-white", attrs: { type: "button", "data-bs-dismiss": "modal", "aria-label": "Cerrar" } })
          ]),
          form,
          createElement("div", { className: "modal-footer" }, [
            createElement("button", {
              className: "btn btn-outline-danger me-auto",
              attrs: { type: "button", "data-delete-button": "true" },
              onClick: () => this.remove()
            }, "Eliminar"),
            createElement("button", { className: "btn btn-outline-light", attrs: { type: "button", "data-bs-dismiss": "modal" } }, "Cancelar"),
            createElement("button", {
              className: "btn btn-danger",
              attrs: { type: "button" },
              onClick: () => this.form?.requestSubmit()
            }, "Guardar")
          ])
        ])
      ])
    ]);
  }

  private openCreate(mode: ModalMode): void {
    this.mode = mode;
    this.editingId = "";
    this.fillForm(mode);
    this.modal?.setTitle(mode === "user" ? "Nuevo usuario" : "Nueva organización");
    this.setDeleteVisible(false);
    this.modal?.open();
  }

  private openEdit(mode: ModalMode, id: string): void {
    this.mode = mode;
    this.editingId = id;
    const item = mode === "user"
      ? this.data.users.find((user) => user.id === id)
      : this.data.companies.find((company) => company.id === id);
    this.fillForm(mode, item);
    this.modal?.setTitle(mode === "user" ? "Editar usuario" : "Editar organización");
    this.setDeleteVisible(true);
    this.modal?.open();
  }

  private fillForm(mode: ModalMode, item?: UserItem | CompanyItem): void {
    if (!this.form) return;
    this.form.replaceChildren(createElement("div", { className: "row g-3" }, this.fields(mode).map((field) => this.field(field, item))));
  }

  private fields(mode: ModalMode): FieldSpec[] {
    if (mode === "company") {
      return [
        { name: "name", label: "Organización", required: true },
        { name: "ruc", label: "RUC" },
        { name: "address", label: "Descripción o dirección", type: "textarea" },
        { name: "active", label: "Activa", type: "checkbox" }
      ];
    }
    return [
      { name: "username", label: "Usuario", required: true },
      { name: "email", label: "Correo", type: "email" },
      { name: "name", label: "Nombre" },
      { name: "password", label: "Contraseña", type: "password", placeholder: this.editingId ? "En blanco conserva la actual" : "Mínimo 6 caracteres" },
      { name: "role_names", label: "Rol", type: "select", required: true, options: this.roleOptions() },
      { name: "company_id", label: "Organización", type: "select", options: this.companyOptions() },
      { name: "active", label: "Cuenta activa", type: "checkbox" }
    ];
  }

  private field(field: FieldSpec, item?: UserItem | CompanyItem): HTMLElement {
    const value = this.value(field.name, item);
    const wrapper = createElement("div", { className: field.type === "checkbox" ? "col-12 col-md-6 rb-check-wrap" : "col-12 col-md-6" });
    if (field.type === "checkbox") {
      const input = createElement("input", { className: "form-check-input", attrs: { type: "checkbox", name: field.name, id: `access-${field.name}` } }) as HTMLInputElement;
      input.checked = value !== false;
      wrapper.append(createElement("div", { className: "form-check form-switch" }, [
        input,
        createElement("label", { className: "form-check-label", attrs: { for: `access-${field.name}` } }, field.label)
      ]));
      return wrapper;
    }
    wrapper.append(createElement("label", { className: "form-label", attrs: { for: `access-${field.name}` } }, field.label));
    if (field.type === "select") {
      const select = createElement("select", { className: "form-select", attrs: { name: field.name, id: `access-${field.name}` } }) as HTMLSelectElement;
      if (!field.required) select.append(createElement("option", { attrs: { value: "" } }, "Sin asignar"));
      for (const option of field.options ?? []) {
        const optionElement = createElement("option", { attrs: { value: option.value } }, option.label) as HTMLOptionElement;
        optionElement.selected = option.value === String(value ?? "");
        select.append(optionElement);
      }
      wrapper.append(select);
      return wrapper;
    }
    if (field.type === "textarea") {
      const textarea = createElement("textarea", { className: "form-control", attrs: { name: field.name, id: `access-${field.name}`, rows: "3" } }) as HTMLTextAreaElement;
      textarea.value = String(value ?? "");
      wrapper.append(textarea);
      return wrapper;
    }
    const input = createElement("input", {
      className: "form-control",
      attrs: {
        type: field.type ?? "text",
        name: field.name,
        id: `access-${field.name}`,
        placeholder: field.placeholder ?? ""
      }
    }) as HTMLInputElement;
    input.value = String(value ?? "");
    wrapper.append(input);
    return wrapper;
  }

  private async submit(): Promise<void> {
    const payload = this.readPayload();
    try {
      if (this.mode === "user") {
        if (this.editingId) await this.api.put(`/api/v1/accounts/users/${this.editingId}/`, payload);
        else await this.api.post("/api/v1/accounts/users/", payload);
      } else if (this.editingId) {
        await this.api.put(`/api/v1/accounts/companies/${this.editingId}/`, payload);
      } else {
        await this.api.post("/api/v1/accounts/companies/", payload);
      }
      this.toastBus.success("Cambios guardados.");
      await this.load();
      this.render();
    } catch {
      this.toastBus.error("No se pudo guardar. Revisa permisos y datos.");
    }
  }

  private async remove(): Promise<void> {
    if (!this.editingId) return;
    try {
      const endpoint = this.mode === "user" ? "users" : "companies";
      await this.api.delete(`/api/v1/accounts/${endpoint}/${this.editingId}/`);
      this.toastBus.success("Elemento eliminado.");
      await this.load();
      this.render();
    } catch {
      this.toastBus.error("No se pudo eliminar el elemento.");
    }
  }

  private readPayload(): Record<string, string | boolean | string[]> {
    if (!this.form) return {};
    const payload: Record<string, string | boolean | string[]> = {};
    for (const field of this.fields(this.mode)) {
      const control = this.form.elements.namedItem(field.name);
      if (control instanceof HTMLInputElement && control.type === "checkbox") {
        payload[field.name] = control.checked;
      } else if (control instanceof HTMLInputElement || control instanceof HTMLSelectElement || control instanceof HTMLTextAreaElement) {
        const value = control.value.trim();
        if (field.name === "role_names") {
          payload[field.name] = value ? [value] : [];
        } else if (value || field.required || field.name !== "password") {
          payload[field.name] = value;
        }
      }
    }
    return payload;
  }

  private value(name: string, item?: UserItem | CompanyItem): string | boolean {
    if (!item) {
      if (name === "active") return true;
      if (name === "role_names") return this.data.roles[0]?.name ?? "viewer";
      return "";
    }
    if (name === "role_names" && "role_names" in item) return item.role_names[0] ?? "";
    return (item as unknown as Record<string, string | boolean>)[name] ?? "";
  }

  private roleOptions(): Array<{ value: string; label: string }> {
    return this.data.roles.map((role) => ({ value: role.name, label: role.label }));
  }

  private companyOptions(): Array<{ value: string; label: string }> {
    return this.data.companies.map((company) => ({ value: company.id, label: company.name }));
  }

  private setDeleteVisible(visible: boolean): void {
    const button = this.root.querySelector<HTMLElement>("[data-delete-button]");
    if (button) button.hidden = !visible;
  }

  private formatDate(value: string): string {
    if (!value) return "--";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "--";
    return parsed.toLocaleTimeString("es-EC", { hour: "2-digit", minute: "2-digit" });
  }
}
