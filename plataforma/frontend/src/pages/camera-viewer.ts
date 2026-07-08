import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import { RealtimeCameraFrame } from "../shared/realtime-camera-player";
import { ToastBus } from "../shared/toast";

type CameraEvent = {
  id: string;
  event_type_label: string;
  event_category_label: string;
  detected_at: string;
  title: string;
  camera_name: string;
  plate: string | null;
  person_name: string | null;
  person_id: string | null;
  crop_path: string | null;
  image_file_path: string | null;
  video_file_path: string | null;
  primary: string;
  summary: string;
};

type ViewerCamera = {
  id: string;
  name: string;
  company_name: string;
  unique_code: string;
  camera_type: string;
  inference_type: string;
  status: string;
  active: boolean;
  uses_rbox: boolean;
  rbox_name: string;
  vehicle_name: string;
  path: string;
  viewer_url: string;
  whep_url: string;
  normal_path: string;
  normal_viewer_url: string;
  normal_whep_url: string;
  normal_online: boolean;
  inference_path: string;
  inference_viewer_url: string;
  inference_whep_url: string;
  inference_online: boolean;
  online: boolean;
  source: string;
  stream_status: string;
  events: CameraEvent[];
};

type ViewerPayload = {
  items: ViewerCamera[];
  total: number;
  mediamtx: {
    ok: boolean;
    error: string;
    online_paths: number;
  };
};

type EventsPayload = {
  items: CameraEvent[];
  total: number;
};

type InferenceOption = {
  value: string;
  label: string;
};

type CameraVideoMode = "normal" | "inference";

const REFRESH_MS = 30_000;
const SNAPSHOT_REFRESH_MS = 4_000;
const VIDEO_MODE_STORAGE_KEY = "robiotec.camera_video_mode";
const INFERENCE_OPTIONS: InferenceOption[] = [
  { value: "inactiva", label: "SIN INFERENCIA" },
  { value: "placa", label: "DETECCIÓN DE PLACAS" },
  { value: "rostro", label: "DETECCIÓN DE ROSTROS" },
  { value: "zona", label: "CONTROL DE ACCESO" },
  { value: "movimiento", label: "ALERTA COMPORTAMIENTO" }
];

export class CameraViewerPage {
  private payload: ViewerPayload = { items: [], total: 0, mediamtx: { ok: false, error: "", online_paths: 0 } };
  private selectedId = "";
  private listElement?: HTMLElement;
  private viewerElement?: HTMLElement;
  private eventsElement?: HTMLElement;
  private eventDetailElement?: HTMLElement;
  private statusElement?: HTMLElement;
  private timer = 0;
  private snapshotTimer = 0;
  private snapshotImage?: HTMLImageElement;
  private snapshotCameraId = "";
  private liveCameraId = "";
  private liveViewerUrl = "";
  private liveVideoMode: CameraVideoMode = "normal";
  private liveFrame?: HTMLIFrameElement;
  private inferenceSelect?: HTMLSelectElement;
  private inferenceLoadButton?: HTMLButtonElement;
  private selectedEvent?: CameraEvent;
  private eventDetailVisible = false;
  private readonly videoModeByCamera = new Map<string, CameraVideoMode>();

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.restoreVideoModes();
    this.root.classList.add("rb-camera-page");
    this.root.replaceChildren(createElement("div", { className: "rb-loading" }, "Cargando cámaras..."));
    await this.load();
    this.render();
    this.timer = window.setInterval(() => void this.refresh(false), REFRESH_MS);
    window.addEventListener("beforeunload", () => {
      window.clearInterval(this.timer);
      window.clearInterval(this.snapshotTimer);
    });
  }

  private async load(): Promise<void> {
    this.payload = await this.api.get<ViewerPayload>("/api/v1/streaming/camera-viewer/");
    if (!this.payload.items.some((item) => item.id === this.selectedId)) {
      const requestedCamera = new URLSearchParams(window.location.search).get("camera") || "";
      const requested = this.payload.items.find((item) =>
        item.id === requestedCamera
        || item.name === requestedCamera
        || item.path === requestedCamera
      );
      this.selectedId = requested?.id ?? this.payload.items[0]?.id ?? "";
    }
  }

  private render(): void {
    this.listElement = createElement("div", { className: "rb-camera-list" });
    this.viewerElement = createElement("section", { className: "rb-camera-viewer-panel" });
    this.eventsElement = createElement("div", { className: "rb-camera-events" });
    this.eventDetailElement = createElement("div", {
      className: "rb-camera-event-modal",
      attrs: { role: "dialog", "aria-modal": "true", "aria-labelledby": "camera-event-detail-title" }
    });
    this.statusElement = createElement("span", { className: "rb-map-status" });

    this.root.replaceChildren(
      createElement("div", { className: "rb-admin-header" }, [
        createElement("div", {}, [
          createElement("span", { className: "rb-kicker" }, "Centro visual"),
          createElement("h1", { className: "h4 mb-1" }, "Centro de cámaras"),
          createElement("p", { className: "rb-muted mb-0" }, "Video en vivo, estado del stream y eventos recientes.")
        ]),
        createElement("div", { className: "rb-admin-actions" }, [
          this.statusElement,
          createElement("button", {
            className: "btn btn-danger btn-sm",
            attrs: { type: "button" },
            onClick: () => void this.refresh(true)
          }, "Actualizar")
        ])
      ]),
      createElement("section", { className: "rb-camera-shell rb-camera-stage" }, [
        createElement("aside", { className: "rb-panel rb-camera-selector" }, [
          createElement("div", { className: "rb-panel-heading" }, [
            createElement("h2", { className: "h6 mb-0" }, "Cámaras"),
            createElement("span", { className: "rb-count" }, String(this.payload.total))
          ]),
          this.listElement
        ]),
        this.viewerElement,
        createElement("aside", { className: "rb-panel rb-camera-events-panel" }, [
          createElement("div", { className: "rb-panel-heading" }, [
            createElement("h2", { className: "h6 mb-0" }, "Eventos"),
            createElement("span", { className: "rb-count" }, String(this.currentCamera()?.events.length ?? 0))
          ]),
          this.eventsElement
        ])
      ]),
      this.eventDetailElement
    );
    this.renderAll();
  }

  private renderAll(options: { viewer?: boolean } = {}): void {
    this.renderList();
    if (options.viewer !== false) {
      this.renderViewer();
    }
    this.renderEvents();
    this.renderEventDetail();
    this.setStatus();
  }

  private renderList(): void {
    if (!this.listElement) return;
    if (!this.payload.items.length) {
      this.listElement.replaceChildren(createElement("p", { className: "rb-muted mb-0" }, "Sin camaras activas."));
      return;
    }
    this.listElement.replaceChildren(...this.payload.items.map((camera) => createElement("article", {
      className: "rb-camera-pill-shell"
    }, createElement("button", {
      className: `rb-camera-row rb-camera-pill ${camera.id === this.selectedId ? "is-active" : ""}`,
      attrs: { type: "button", "aria-label": `Abrir camara ${camera.name}` },
      onClick: () => {
        this.selectedId = camera.id;
        this.renderAll();
        void this.reloadEvents(camera.id);
      }
    }, [
      createElement("span", { className: "rb-camera-pill-preview" }, camera.online
        ? createElement("img", {
          className: "rb-camera-pill-snapshot",
          attrs: { alt: camera.name, src: this.snapshotUrl(camera.id, this.currentVideoMode(camera)), loading: "lazy" }
        })
        : createElement("span", { className: "rb-camera-pill-preview-empty" }, "Sin video")),
      createElement("span", { className: camera.online ? "rb-camera-dot is-online" : "rb-camera-dot" }),
      createElement("span", { className: "rb-camera-row-copy rb-camera-pill-main" }, [
        createElement("span", { className: "rb-camera-pill-topline" }, [
          createElement("strong", { className: "rb-camera-pill-title" }, camera.name),
          createElement("span", { className: camera.online ? "rb-camera-pill-state is-online" : "rb-camera-pill-state" }, camera.online ? "LIVE" : "OFF")
        ]),
        createElement("small", { className: "rb-camera-pill-association" }, this.cameraAssociation(camera)),
        createElement("span", { className: "rb-camera-pill-status" }, camera.path || "sin-path"),
        createElement("span", { className: "rb-camera-pill-tags" }, [
          createElement("span", { className: "rb-camera-pill-tag" }, this.cameraTypeLabel(camera.camera_type)),
          createElement("span", { className: "rb-camera-pill-tag" }, this.inferenceLabel(camera.inference_type))
        ])
      ])
    ]))));
  }

  private renderViewer(): void {
    if (!this.viewerElement) return;
    const camera = this.currentCamera();
    window.clearInterval(this.snapshotTimer);
    this.snapshotImage = undefined;
    if (!camera) {
      this.clearLiveFrame();
      this.viewerElement.replaceChildren(
        this.renderInferenceToolbar(undefined),
        createElement("div", { className: "rb-camera-empty rb-primary-view is-empty" }, "Selecciona una cámara para abrir el video.")
      );
      return;
    }
    const videoMode = this.currentVideoMode(camera);
    const viewerUrl = this.viewerUrlForMode(camera, videoMode);
    const modeOnline = this.isOnlineForMode(camera, videoMode);
    let viewerBody: HTMLElement;
    if (modeOnline && viewerUrl) {
      viewerBody = this.liveVideoFrame(camera, viewerUrl, videoMode);
    } else if (modeOnline) {
      this.clearLiveFrame();
      this.snapshotImage = createElement("img", {
        className: "rb-camera-frame",
        attrs: { alt: `Video ${camera.name}`, src: this.snapshotUrl(camera.id, videoMode) }
      });
      viewerBody = createElement("div", { className: "rb-primary-view" }, this.snapshotImage);
      this.snapshotCameraId = camera.id;
      this.snapshotTimer = window.setInterval(() => this.refreshSnapshot(), SNAPSHOT_REFRESH_MS);
    } else {
      this.clearLiveFrame();
      viewerBody = createElement("div", { className: "rb-camera-empty rb-primary-view is-empty" }, viewerUrl
        ? `La vista ${this.videoModeLabel(videoMode).toLowerCase()} no tiene video activo.`
        : "Esta cámara no tiene un path de video configurado.");
    }
    this.viewerElement.replaceChildren(
      this.renderInferenceToolbar(camera),
      viewerBody
    );
  }

  private renderInferenceToolbar(camera?: ViewerCamera): HTMLElement {
    this.inferenceSelect = createElement("select", { attrs: { id: "camera-inference-type" } },
      INFERENCE_OPTIONS.map((option) => createElement("option", { attrs: { value: option.value } }, option.label))
    ) as HTMLSelectElement;
    this.inferenceSelect.value = this.normalizedInference(camera?.inference_type ?? "inactiva");
    this.inferenceSelect.disabled = !camera;

    this.inferenceLoadButton = createElement("button", {
      className: "rb-camera-inference-load",
      attrs: { type: "button" },
      onClick: () => void this.saveInferenceSelection()
    }, "Cargar") as HTMLButtonElement;
    this.inferenceLoadButton.disabled = !camera;

    const activeMode = camera ? this.currentVideoMode(camera) : "normal";
    const cameraHeader = camera
      ? createElement("div", { className: "rb-camera-inline-head rb-camera-status-card" }, [
        createElement("div", { className: "rb-camera-title-block" }, [
          createElement("span", { className: "rb-kicker" }, this.isOnlineForMode(camera, activeMode) ? "En linea" : "Sin video"),
          createElement("h2", { className: "h5 mb-0" }, camera.name)
        ])
      ])
      : createElement("div", { className: "rb-camera-inline-head rb-camera-status-card" }, [
        createElement("div", { className: "rb-camera-title-block" }, [
          createElement("span", { className: "rb-kicker" }, "Visor"),
          createElement("h2", { className: "h5 mb-0" }, "Selecciona una cámara")
        ])
      ]);

    return createElement("div", { className: "rb-camera-inference-toolbar rb-camera-topbar" }, [
      createElement("div", { className: "rb-camera-inference-controls" }, [
        createElement("label", { className: "rb-camera-inference-field" }, [
          createElement("span", {}, "Tipo de inferencia:"),
          this.inferenceSelect
        ]),
        this.inferenceLoadButton
      ]),
      cameraHeader
    ]);
  }

  private liveVideoFrame(camera: ViewerCamera, viewerUrl: string, videoMode: CameraVideoMode): HTMLElement {
    if (this.liveFrame && this.liveCameraId === camera.id && this.liveViewerUrl === viewerUrl && this.liveVideoMode === videoMode) {
      return createElement("div", { className: "rb-primary-view rb-camera-live-shell" }, [
        this.renderVideoModeButton(camera, videoMode),
        this.liveFrame
      ]);
    }
    this.clearLiveFrame();
    this.liveCameraId = camera.id;
    this.liveViewerUrl = viewerUrl;
    this.liveVideoMode = videoMode;
    this.liveFrame = RealtimeCameraFrame.create({
      viewerUrl,
      title: `${this.videoModeLabel(videoMode)} ${camera.name}`,
      className: "rb-camera-frame rb-camera-live-frame",
      muted: true
    });
    return createElement("div", { className: "rb-primary-view rb-camera-live-shell" }, [
      this.renderVideoModeButton(camera, videoMode),
      this.liveFrame
    ]);
  }

  private clearLiveFrame(): void {
    if (this.liveFrame) {
      this.liveFrame.srcdoc = "";
      this.liveFrame.remove();
    }
    this.liveFrame = undefined;
    this.liveCameraId = "";
    this.liveViewerUrl = "";
    this.liveVideoMode = "normal";
  }

  private snapshotUrl(cameraId: string, videoMode: CameraVideoMode): string {
    return `/api/v1/streaming/camera-viewer/${cameraId}/snapshot/?mode=${videoMode}&t=${Date.now()}`;
  }

  private refreshSnapshot(): void {
    if (!this.snapshotImage || !this.snapshotCameraId) return;
    const camera = this.payload.items.find((item) => item.id === this.snapshotCameraId);
    this.snapshotImage.src = this.snapshotUrl(this.snapshotCameraId, camera ? this.currentVideoMode(camera) : "normal");
  }

  private renderEvents(): void {
    if (!this.eventsElement) return;
    const camera = this.currentCamera();
    if (!camera || !camera.events.length) {
      this.eventsElement.replaceChildren(createElement("p", { className: "rb-muted mb-0" }, "Sin eventos recientes para esta camara."));
      this.selectedEvent = undefined;
      this.eventDetailVisible = false;
      this.renderEventDetail();
      return;
    }
    if (this.selectedEvent && !camera.events.some((event) => event.id === this.selectedEvent?.id)) {
      this.selectedEvent = undefined;
      this.eventDetailVisible = false;
      this.renderEventDetail();
    }
    this.eventsElement.replaceChildren(...camera.events.map((event) => {
      const imagePath = event.crop_path || event.image_file_path || "";
      return createElement("article", {
        className: `rb-camera-event ${this.eventToneClass(event)}`,
        attrs: { role: "button", tabindex: "0", "aria-label": `Abrir detalle de ${event.primary || event.title || "evento"}` },
        onClick: () => this.openEventDetail(event),
        onKeyDown: (keyboardEvent) => {
          if (keyboardEvent.key !== "Enter" && keyboardEvent.key !== " ") return;
          keyboardEvent.preventDefault();
          this.openEventDetail(event);
        }
      }, [
        imagePath
          ? createElement("img", { className: "rb-camera-event-img", attrs: { src: this.mediaUrl("crop", imagePath), alt: "Evidencia", loading: "lazy" } })
          : createElement("div", { className: "rb-camera-event-img rb-camera-event-img-empty" }, this.shortEvent(event)),
        createElement("div", { className: "rb-camera-event-copy" }, [
          createElement("span", { className: "rb-event-tag rb-camera-event-badge" }, event.event_type_label || event.event_category_label || "Evento"),
          createElement("strong", {}, event.primary || event.title || "Evento detectado"),
          createElement("small", {}, this.formatDate(event.detected_at)),
          createElement("small", {}, event.summary || "")
        ])
      ]);
    }));
  }

  private renderEventDetail(): void {
    if (!this.eventDetailElement) return;
    const event = this.selectedEvent;
    if (!event || !this.eventDetailVisible) {
      this.eventDetailElement.hidden = true;
      this.eventDetailElement.replaceChildren();
      return;
    }

    const imagePath = event.image_file_path || event.crop_path || "";
    const rows = [
      ["Camara", event.camera_name],
      ["Fecha", this.formatDate(event.detected_at)],
      ["Tipo", event.event_type_label || event.event_category_label || "Evento"],
      ["Persona", event.person_name || event.person_id || ""],
      ["Placa", event.plate || ""],
      ["Resumen", event.summary || ""]
    ].filter(([, value]) => String(value || "").trim());

    this.eventDetailElement.hidden = false;
    this.eventDetailElement.replaceChildren(
      createElement("button", {
        className: "rb-camera-event-modal-backdrop",
        attrs: { type: "button", "aria-label": "Cerrar detalle del evento" },
        onClick: () => this.closeEventDetail()
      }),
      createElement("section", { className: "rb-camera-event-dialog" }, [
        createElement("button", {
          className: "rb-camera-event-dialog-close",
          attrs: { type: "button", "aria-label": "Cerrar detalle del evento" },
          onClick: () => this.closeEventDetail()
        }, "x"),
        createElement("span", { className: "rb-kicker" }, "Detalle del evento"),
        createElement("h2", { className: "h5 mb-0", attrs: { id: "camera-event-detail-title" } }, event.primary || event.title || "Evento detectado"),
        event.video_file_path
          ? createElement("video", {
            className: "rb-camera-event-detail-media",
            attrs: { controls: "true", playsinline: "true", preload: "metadata", src: this.mediaUrl("video", event.video_file_path) }
          })
          : imagePath
            ? createElement("img", { className: "rb-camera-event-detail-media", attrs: { src: this.mediaUrl("crop", imagePath), alt: "Evidencia" } })
            : createElement("div", { className: "rb-camera-event-detail-media rb-camera-event-detail-empty" }, "Sin evidencia asociada"),
        createElement("div", { className: "rb-camera-event-detail-grid" }, rows.map(([label, value]) => createElement("div", { className: "rb-camera-event-detail-row" }, [
          createElement("span", {}, String(label)),
          createElement("strong", {}, String(value))
        ])))
      ])
    );
  }

  private openEventDetail(event: CameraEvent): void {
    this.selectedEvent = event;
    this.eventDetailVisible = true;
    this.renderEventDetail();
  }

  private closeEventDetail(): void {
    this.eventDetailVisible = false;
    this.renderEventDetail();
  }

  private async refresh(showToast: boolean): Promise<void> {
    try {
      await this.load();
      const selected = this.currentCamera();
      const selectedMode = selected ? this.currentVideoMode(selected) : "normal";
      const selectedViewerUrl = selected ? this.viewerUrlForMode(selected, selectedMode) : "";
      const selectedOnline = selected ? this.isOnlineForMode(selected, selectedMode) : false;
      const nextViewerKey = selected ? `${selected.id}:${selectedMode}:${selectedOnline}:${selectedViewerUrl}:${selected.stream_status}` : "";
      const currentViewerKey = this.liveCameraId ? `${this.liveCameraId}:${this.liveVideoMode}:true:${this.liveViewerUrl}:${selected?.stream_status ?? ""}` : "";
      this.renderAll({ viewer: showToast || nextViewerKey !== currentViewerKey });
      if (showToast) this.toastBus.success("Cámaras actualizadas.");
    } catch {
      if (showToast) this.toastBus.error("No se pudo actualizar el visor.");
    }
  }

  private async reloadEvents(cameraId: string): Promise<void> {
    try {
      const payload = await this.api.get<EventsPayload>(`/api/v1/streaming/camera-viewer/${cameraId}/events/?limit=8`, { silent: true });
      const camera = this.payload.items.find((item) => item.id === cameraId);
      if (camera) {
        camera.events = payload.items;
        this.renderEvents();
      }
    } catch {
      // El refresco general cubre errores temporales de eventos.
    }
  }

  private renderVideoModeButton(camera: ViewerCamera, currentMode: CameraVideoMode): HTMLElement {
    const nextMode: CameraVideoMode = currentMode === "normal" ? "inference" : "normal";
    const online = this.isOnlineForMode(camera, currentMode);
    const nextLabel = nextMode === "inference" ? "Inferencia" : "Normal";
    const currentLabel = this.videoModeLabel(currentMode);
    return createElement("button", {
      className: `rb-camera-infer-toggle ${currentMode === "inference" ? "is-active" : ""} ${online ? "is-online" : "is-unavailable"}`,
      attrs: {
        type: "button",
        "aria-label": currentMode === "inference"
          ? "Volver a vista normal"
          : "Activar vista de inferencia"
      },
      onClick: () => this.setVideoMode(camera, nextMode)
    }, [
      createElement("span", { className: "rb-camera-infer-toggle-icon", attrs: { "aria-hidden": "true" } }, currentMode === "inference" ? "◎" : "◉"),
      createElement("span", { className: "rb-camera-infer-toggle-label" }, currentLabel),
      createElement("span", { className: "rb-camera-infer-toggle-hint" }, nextLabel)
    ]);
  }

  private async saveInferenceSelection(): Promise<void> {
    const camera = this.currentCamera();
    const nextInference = this.normalizedInference(this.inferenceSelect?.value || "inactiva");
    if (!camera) return;
    this.inferenceLoadButton && (this.inferenceLoadButton.disabled = true);
    try {
      const payload = await this.api.patch<{ inference_type: string }>(
        `/api/v1/streaming/camera-viewer/${camera.id}/inference/`,
        { inference_type: nextInference }
      );
      camera.inference_type = payload.inference_type || nextInference;
      this.toastBus.success("Inferencia actualizada.");
      this.renderViewer();
      this.renderList();
    } catch {
      this.toastBus.error("No se pudo actualizar la inferencia.");
    } finally {
      this.inferenceLoadButton && (this.inferenceLoadButton.disabled = false);
    }
  }

  private currentCamera(): ViewerCamera | undefined {
    return this.payload.items.find((item) => item.id === this.selectedId);
  }

  private currentVideoMode(camera: ViewerCamera): CameraVideoMode {
    const stored = this.videoModeByCamera.get(camera.id);
    if (stored) return stored;
    if (camera.normal_online) return "normal";
    if (camera.inference_online) return "inference";
    return this.isInferencePath(camera.path) ? "inference" : "normal";
  }

  private setVideoMode(camera: ViewerCamera, mode: CameraVideoMode): void {
    this.videoModeByCamera.set(camera.id, mode);
    this.storeVideoModes();
    this.renderViewer();
    this.renderList();
  }

  private viewerUrlForMode(camera: ViewerCamera, mode: CameraVideoMode): string {
    if (mode === "inference") return camera.inference_viewer_url || "";
    return camera.normal_viewer_url || camera.viewer_url || "";
  }

  private isOnlineForMode(camera: ViewerCamera | undefined, mode: CameraVideoMode): boolean {
    if (!camera) return false;
    if (mode === "inference") return Boolean(camera.inference_online);
    if (camera.normal_path || camera.normal_viewer_url) return Boolean(camera.normal_online);
    return Boolean(camera.online);
  }

  private isInferencePath(path: string): boolean {
    return /\/+INFERENCE\/?$/i.test(String(path || "").trim());
  }

  private videoModeLabel(mode: CameraVideoMode): string {
    return mode === "inference" ? "Inferencia" : "Normal";
  }

  private restoreVideoModes(): void {
    try {
      const raw = window.localStorage.getItem(VIDEO_MODE_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      if (!parsed || typeof parsed !== "object") return;
      Object.entries(parsed).forEach(([cameraId, mode]) => {
        if (mode === "normal" || mode === "inference") {
          this.videoModeByCamera.set(cameraId, mode);
        }
      });
    } catch {
      this.videoModeByCamera.clear();
    }
  }

  private storeVideoModes(): void {
    try {
      const payload = Object.fromEntries(this.videoModeByCamera.entries());
      window.localStorage.setItem(VIDEO_MODE_STORAGE_KEY, JSON.stringify(payload));
    } catch {
      // El toggle sigue funcionando aunque el navegador bloquee localStorage.
    }
  }

  private setStatus(): void {
    if (!this.statusElement) return;
    const online = this.payload.items.filter((item) => item.online).length;
    const apiState = this.payload.mediamtx.ok ? `${this.payload.mediamtx.online_paths} paths` : "MediaMTX sin respuesta";
    this.statusElement.textContent = `${online}/${this.payload.total} en linea · ${apiState}`;
  }

  private cameraAssociation(camera: ViewerCamera): string {
    if (camera.uses_rbox) return camera.rbox_name ? `RBox ${camera.rbox_name}` : "RBox";
    if (camera.vehicle_name) return `Unidad ${camera.vehicle_name}`;
    return camera.company_name || "Directa";
  }

  private cameraTypeLabel(value: string): string {
    return {
      fixed: "Fija",
      mobile: "Móvil",
      drone: "Dron",
      vehicle: "Vehículo"
    }[String(value || "").toLowerCase()] ?? (value || "Cámara");
  }

  private normalizedInference(value: string): string {
    const normalized = String(value || "").trim().toLowerCase();
    if (INFERENCE_OPTIONS.some((option) => option.value === normalized)) return normalized;
    return "inactiva";
  }

  private mediaUrl(kind: "crop" | "video", path: string): string {
    return `/api/v1/events/media/${kind}/?path=${encodeURIComponent(path)}`;
  }

  private shortEvent(event: CameraEvent): string {
    return (event.event_type_label || event.event_category_label || "EV").slice(0, 2).toUpperCase();
  }

  private eventToneClass(event: CameraEvent): string {
    const raw = `${event.event_type_label} ${event.event_category_label} ${event.title}`.toLowerCase();
    if (raw.includes("placa") || raw.includes("plate")) return "is-plate";
    if (raw.includes("rostro") || raw.includes("persona") || raw.includes("face")) return "is-person";
    if (raw.includes("zona") || raw.includes("access")) return "is-zone";
    if (raw.includes("mov") || raw.includes("motion")) return "is-motion";
    return "";
  }

  private inferenceLabel(value: string): string {
    return {
      inactiva: "Sin inferencia",
      placa: "Placas",
      rostro: "Rostros",
      zona: "Zona",
      movimiento: "Movimiento"
    }[value] ?? value;
  }

  private formatDate(value: string): string {
    if (!value) return "Sin fecha";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString("es-EC", {
      timeZone: "America/Guayaquil",
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  }
}
