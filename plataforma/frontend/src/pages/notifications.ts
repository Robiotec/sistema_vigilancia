import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { ToastBus } from "../shared/toast";

type NotificationSettings = {
  email: {
    sender_email: string;
    sender_password: string;
    has_sender_password: boolean;
    smtp_host: string;
    smtp_port: number;
    subject: string;
    message: string;
    recipients: string[];
  };
  telegram: {
    bot_token: string;
    has_bot_token: boolean;
    chat_ids: string[];
    message: string;
    image_path: string;
  };
};

type SettingsPayload = {
  ok: boolean;
  settings: NotificationSettings;
};

type EmailPayload = {
  ok: boolean;
  recipients: string[];
  total: number;
};

type TelegramPayload = {
  ok: boolean;
  chat_ids: string[];
  total: number;
};

type TestPayload = {
  ok: boolean;
  total: number;
  sent?: string[];
};

export class NotificationsPage {
  private settings?: NotificationSettings;
  private emailForm?: HTMLFormElement;
  private telegramForm?: HTMLFormElement;
  private recipientsList?: HTMLElement;
  private chatList?: HTMLElement;
  private statusElement?: HTMLElement;
  private emailCountElement?: HTMLElement;
  private chatCountElement?: HTMLElement;

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.root.replaceChildren(createElement("div", { className: "rb-loading" }, "Cargando notificaciones..."));
    await this.load();
    this.render();
  }

  private async load(): Promise<void> {
    const payload = await this.api.get<SettingsPayload>("/api/v1/alerts/notification-settings/");
    this.settings = payload.settings;
  }

  private render(): void {
    this.statusElement = createElement("span", { className: "rb-map-status" }, "Configuración cargada");
    this.recipientsList = createElement("div", { className: "rb-notification-list" });
    this.chatList = createElement("div", { className: "rb-notification-list" });
    this.emailForm = this.emailSettingsForm();
    this.telegramForm = this.telegramSettingsForm();

    this.root.replaceChildren(
      createElement("section", { className: "rb-notification-shell" }, [
        createElement("div", { className: "rb-admin-header" }, [
          createElement("div", {}, [
            createElement("span", { className: "rb-kicker" }, "Centro de notificación"),
            createElement("h1", { className: "h4 mb-1" }, "Canales de envío"),
            createElement("p", { className: "rb-muted mb-0" }, "Correo, Telegram y destinatarios usados por las alertas.")
          ]),
          this.statusElement
        ]),
        this.summaryBand(),
        createElement("div", { className: "rb-notification-grid" }, [
          this.panel("Correo", "SMTP y destinatarios", [
            this.emailForm,
            this.listHeader("Correos registrados", this.settings?.email.recipients.length ?? 0, "email"),
            this.recipientsList,
            createElement("div", { className: "rb-admin-actions mt-3" }, [
              createElement("button", {
                className: "btn btn-outline-light btn-sm",
                attrs: { type: "button" },
                onClick: () => void this.testEmail()
              }, "Enviar prueba"),
              createElement("button", {
                className: "btn btn-danger btn-sm",
                attrs: { type: "button" },
                onClick: () => void this.saveSettings()
              }, "Guardar correo")
            ])
          ]),
          this.panel("Telegram", "Bot y chats destino", [
            this.telegramForm,
            this.listHeader("IDs registrados", this.settings?.telegram.chat_ids.length ?? 0, "chat"),
            this.chatList,
            createElement("div", { className: "rb-admin-actions mt-3" }, [
              createElement("button", {
                className: "btn btn-outline-light btn-sm",
                attrs: { type: "button" },
                onClick: () => void this.testTelegram()
              }, "Enviar prueba"),
              createElement("button", {
                className: "btn btn-danger btn-sm",
                attrs: { type: "button" },
                onClick: () => void this.saveSettings()
              }, "Guardar Telegram")
            ])
          ])
        ])
      ])
    );
    this.renderRecipients();
    this.renderChatIds();
  }

  private summaryBand(): HTMLElement {
    const email = this.settings?.email;
    const telegram = this.settings?.telegram;
    return createElement("section", { className: "rb-access-summary rb-notification-summary" }, [
      this.summaryCard("Correos", String(email?.recipients.length ?? 0)),
      this.summaryCard("Chat IDs", String(telegram?.chat_ids.length ?? 0)),
      this.summaryCard("SMTP", email?.sender_email && (email.has_sender_password || email.sender_password) ? "Configurado" : "Pendiente"),
      this.summaryCard("Telegram", telegram?.has_bot_token || telegram?.bot_token ? "Configurado" : "Pendiente")
    ]);
  }

  private summaryCard(label: string, value: string): HTMLElement {
    return createElement("article", { className: "rb-access-card" }, [
      createElement("span", {}, label),
      createElement("strong", {}, value)
    ]);
  }

  private panel(title: string, subtitle: string, content: HTMLElement[]): HTMLElement {
    return createElement("section", { className: "rb-panel rb-notification-card" }, [
      createElement("div", { className: "rb-panel-heading" }, [
        createElement("div", {}, [
          createElement("span", { className: "rb-kicker" }, subtitle),
          createElement("h2", { className: "h5 mb-0" }, title)
        ])
      ]),
      ...content
    ]);
  }

  private emailSettingsForm(): HTMLFormElement {
    const settings = this.settings?.email;
    const passwordPlaceholder = settings?.has_sender_password ? "Clave guardada; deja vacío para conservarla" : "Clave SMTP";
    const form = createElement("form", { className: "rb-notification-form" }, [
      this.field("sender_email", "Correo emisor", settings?.sender_email ?? "", "email"),
      this.field("sender_password", "Clave SMTP", "", "password", passwordPlaceholder),
      this.field("smtp_host", "Servidor SMTP", settings?.smtp_host ?? "smtp.office365.com"),
      this.field("smtp_port", "Puerto", String(settings?.smtp_port ?? 587), "number"),
      this.field("subject", "Asunto", settings?.subject ?? ""),
      this.textarea("message", "Mensaje", settings?.message ?? ""),
      this.inlineAdd("notification-email-input", "Correo destinatario", "correo@empresa.com", () => void this.addEmail())
    ]) as HTMLFormElement;
    form.addEventListener("submit", (event) => event.preventDefault());
    return form;
  }

  private telegramSettingsForm(): HTMLFormElement {
    const settings = this.settings?.telegram;
    const tokenPlaceholder = settings?.has_bot_token ? "Token guardado; deja vacío para conservarlo" : "Token del bot";
    const form = createElement("form", { className: "rb-notification-form" }, [
      this.field("bot_token", "Token del bot", "", "password", tokenPlaceholder),
      this.textarea("message", "Mensaje", settings?.message ?? ""),
      this.field("image_path", "Imagen por defecto", settings?.image_path ?? ""),
      this.inlineAdd("notification-chat-input", "Chat ID destino", "ID de chat", () => void this.addChatId())
    ]) as HTMLFormElement;
    form.addEventListener("submit", (event) => event.preventDefault());
    return form;
  }

  private field(name: string, label: string, value: string, type = "text", placeholder = ""): HTMLElement {
    const input = createElement("input", {
      className: "form-control",
      attrs: { name, type, value, placeholder }
    });
    return createElement("label", { className: "rb-notification-field" }, [
      createElement("span", { className: "form-label" }, label),
      input
    ]);
  }

  private textarea(name: string, label: string, value: string): HTMLElement {
    const input = createElement("textarea", {
      className: "form-control",
      attrs: { name, rows: "4" }
    }) as HTMLTextAreaElement;
    input.value = value;
    return createElement("label", { className: "rb-notification-field rb-notification-field-wide" }, [
      createElement("span", { className: "form-label" }, label),
      input
    ]);
  }

  private inlineAdd(inputId: string, label: string, placeholder: string, onClick: () => void): HTMLElement {
    return createElement("div", { className: "rb-notification-field rb-notification-field-wide" }, [
      createElement("span", { className: "form-label" }, label),
      createElement("div", { className: "rb-notification-entry" }, [
        createElement("input", {
          className: "form-control",
          attrs: { id: inputId, placeholder },
          onKeyDown: (event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            onClick();
          }
        }),
        createElement("button", {
          className: "btn btn-danger",
          attrs: { type: "button" },
          onClick
        }, "Agregar")
      ])
    ]);
  }

  private listHeader(label: string, count: number, kind: "email" | "chat"): HTMLElement {
    const countElement = createElement("span", { className: "rb-count" }, String(count));
    if (kind === "email") this.emailCountElement = countElement;
    if (kind === "chat") this.chatCountElement = countElement;
    return createElement("div", { className: "rb-notification-list-head" }, [
      createElement("strong", {}, label),
      countElement
    ]);
  }

  private renderRecipients(): void {
    const recipients = this.settings?.email.recipients ?? [];
    if (!this.recipientsList) return;
    if (this.emailCountElement) this.emailCountElement.textContent = String(recipients.length);
    if (!recipients.length) {
      this.recipientsList.replaceChildren(createElement("p", { className: "rb-muted mb-0" }, "Sin correos configurados."));
      return;
    }
    this.recipientsList.replaceChildren(...recipients.map((email, index) => this.listRow(index + 1, email, () => void this.removeEmail(email))));
  }

  private renderChatIds(): void {
    const chatIds = this.settings?.telegram.chat_ids ?? [];
    if (!this.chatList) return;
    if (this.chatCountElement) this.chatCountElement.textContent = String(chatIds.length);
    if (!chatIds.length) {
      this.chatList.replaceChildren(createElement("p", { className: "rb-muted mb-0" }, "Sin IDs configurados."));
      return;
    }
    this.chatList.replaceChildren(...chatIds.map((chatId, index) => this.listRow(index + 1, chatId, () => void this.removeChatId(chatId))));
  }

  private listRow(index: number, value: string, onRemove: () => void): HTMLElement {
    return createElement("div", { className: "rb-notification-row" }, [
      createElement("span", { className: "rb-notification-index" }, String(index)),
      createElement("strong", {}, value),
      createElement("button", {
        className: "btn btn-outline-danger btn-sm",
        attrs: { type: "button" },
        onClick: onRemove
      }, "Quitar")
    ]);
  }

  private async addEmail(): Promise<void> {
    const input = document.getElementById("notification-email-input") as HTMLInputElement | null;
    const email = input?.value.trim() ?? "";
    if (!email) return;
    const payload = await this.api.post<EmailPayload>("/api/v1/alerts/notification-email-recipients/", { email });
    if (this.settings) this.settings.email.recipients = payload.recipients;
    if (input) input.value = "";
    this.render();
    this.toastBus.success("Correo agregado.");
  }

  private async removeEmail(email: string): Promise<void> {
    const payload = await this.api.delete<EmailPayload>("/api/v1/alerts/notification-email-recipients/", {
      body: JSON.stringify({ email })
    });
    if (this.settings) this.settings.email.recipients = payload.recipients;
    this.render();
    this.toastBus.success("Correo eliminado.");
  }

  private async addChatId(): Promise<void> {
    const input = document.getElementById("notification-chat-input") as HTMLInputElement | null;
    const chatId = input?.value.trim() ?? "";
    if (!chatId) return;
    const payload = await this.api.post<TelegramPayload>("/api/v1/alerts/notification-telegram-chat-ids/", { chat_id: chatId });
    if (this.settings) this.settings.telegram.chat_ids = payload.chat_ids;
    if (input) input.value = "";
    this.render();
    this.toastBus.success("Chat ID agregado.");
  }

  private async removeChatId(chatId: string): Promise<void> {
    const payload = await this.api.delete<TelegramPayload>("/api/v1/alerts/notification-telegram-chat-ids/", {
      body: JSON.stringify({ chat_id: chatId })
    });
    if (this.settings) this.settings.telegram.chat_ids = payload.chat_ids;
    this.render();
    this.toastBus.success("Chat ID eliminado.");
  }

  private async saveSettings(): Promise<void> {
    const emailData = this.formData(this.emailForm);
    const telegramData = this.formData(this.telegramForm);
    const payload = await this.api.put<SettingsPayload>("/api/v1/alerts/notification-settings/", {
      email: {
        sender_email: emailData.sender_email,
        sender_password: emailData.sender_password,
        smtp_host: emailData.smtp_host,
        smtp_port: Number(emailData.smtp_port || 587),
        subject: emailData.subject,
        message: emailData.message,
        recipients: this.settings?.email.recipients ?? []
      },
      telegram: {
        bot_token: telegramData.bot_token,
        message: telegramData.message,
        image_path: telegramData.image_path,
        chat_ids: this.settings?.telegram.chat_ids ?? []
      }
    });
    this.settings = payload.settings;
    this.render();
    this.setStatus("Guardado");
    this.toastBus.success("Configuración guardada.");
  }

  private async testEmail(): Promise<void> {
    const payload = await this.api.post<TestPayload>("/api/v1/alerts/notification-settings/test-email/", {});
    this.toastBus.success(`Correo enviado a ${payload.total} destinatario(s).`);
  }

  private async testTelegram(): Promise<void> {
    const payload = await this.api.post<TestPayload>("/api/v1/alerts/notification-settings/test-telegram/", {});
    this.toastBus.success(`Telegram enviado a ${payload.total} chat(s).`);
  }

  private formData(form?: HTMLFormElement): Record<string, string> {
    const data: Record<string, string> = {};
    if (!form) return data;
    new FormData(form).forEach((value, key) => {
      data[key] = String(value);
    });
    return data;
  }

  private setStatus(value: string): void {
    if (this.statusElement) this.statusElement.textContent = value;
  }
}
