import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-draw";
import "leaflet-draw/dist/leaflet.draw.css";

import { ApiClient } from "../shared/api";
import { createElement } from "../shared/dom";
import {
  FleetCameraLink,
  FleetDeviceModel,
  FleetDevicePayload,
  FleetTelemetryPayload
} from "../shared/fleet-device";
import { ToastBus } from "../shared/toast";

const ECUADOR_CENTER: L.LatLngExpression = [-1.8312, -78.1834];
const ECUADOR_BOUNDS: L.LatLngBoundsExpression = [
  [-5.1, -81.2],
  [1.6, -75.1]
];
const ROUTE_LINE_COLOR = "#8b5cf6";
const ROUTE_POINT_COLOR = "#38bdf8";
const ROUTE_START_COLOR = "#22c55e";
const ROUTE_CURRENT_COLOR = "#a855f7";
const ROUTE_SEGMENT_MAX_GAP_SECONDS = 30 * 60;
const ROUTE_SEGMENT_MAX_DISTANCE_KM = 8;
const ROUTE_SEGMENT_MAX_SPEED_KMH = 180;
const ARCOM_MIN_ZOOM = 9;
const OSINT_CATEGORIES: Array<[string, string]> = [
  ["none", "Nada"],
  ["all", "Todo OSINT"],
  ["eventos_homicido_sicariato", "Homicidios/Sicariatos"],
  ["eventos_operativos_ffoo", "Operativos FFOO"],
  ["eventos_marcadores_criminales", "Marcadores Criminales"],
  ["eventos_mineria_ilegal", "Mineria Ilegal"],
  ["eventos_paso_ilegal", "Pasos Ilegales"],
  ["eventos_paso_oficial", "Pasos Oficiales"],
  ["eventos_unidades_ffaa", "Unidades FFAA"],
  ["rutas_narcotrafico", "Rutas Narcotrafico"],
  ["punto_interes_policias", "UPC / Policia"],
  ["punto_interes_gdos.puntos", "Puntos GDO"],
  ["zonas_poligonos_gdo", "Zonas GDO"]
];

type OsintFeature = {
  type: "Feature";
  properties?: Record<string, unknown>;
  geometry?: { type?: string; coordinates?: unknown };
};

type OsintPayload = {
  features?: OsintFeature[];
};

type Paginated<T> = {
  count: number;
  results: T[];
};

type FleetVehicle = FleetDevicePayload;

type DroneDevice = {
  id: string;
  name: string;
  unique_code: string | null;
  drone_type: string | null;
  active: boolean;
};

type LatestLocation = FleetTelemetryPayload;

type LatestLocationsPayload = {
  count: number;
  generated_at: string;
  results: LatestLocation[];
};

type RoutePoint = {
  id: string;
  lat: number;
  lon: number;
  speed: number | null;
  heading: number | null;
  received_at: string;
  segment_status?: string | null;
  segment_reason?: string | null;
  distance_km?: number | null;
  elapsed_seconds?: number | null;
  implied_speed_kmh?: number | null;
  counted_for_km?: boolean | null;
  segment_geometry?: Array<[number, number]>;
};

type RouteSegmentStatus = "start" | "normal" | "osrm" | "raw" | "gap" | "suspicious";

type RouteSegmentMeta = {
  status: RouteSegmentStatus;
  reason: string | null;
  distanceKm: number;
  elapsedSeconds: number;
  impliedSpeedKmh: number;
};

type VehicleRoutePayload = {
  vehicle: FleetVehicle;
  date: string;
  total_points: number;
  total_km: number;
  segments: RoutePoint[][];
  points: RoutePoint[];
};

type GeofenceGeometry = {
  type?: string;
  coordinate_order?: string;
  coordinates?: unknown;
  center?: { lat?: number; lon?: number; lng?: number };
  radius_m?: number;
  radius?: number;
  color?: string;
  style?: { color?: string; fillColor?: string };
};

type GeofenceItem = {
  id: string;
  company_id?: string;
  company_name?: string;
  name: string;
  type: string;
  geofence_type: string;
  geometry: GeofenceGeometry;
  color: string | null;
  active: boolean;
  description: string;
};

type ZoneGeometry =
  | { type: "polygon"; coordinates: number[][] }
  | { type: "circle"; center: { lat: number; lon: number }; radius_m: number };

type MiningConcession = {
  nombre_concesion?: string;
  codigo_catastral?: string;
  estado_actual?: string;
  empresa?: string;
  fase_recurso_mineral?: string;
  tipo_mineral?: string;
};

type MiningLookupPayload = {
  found: boolean;
  concession: MiningConcession | null;
};

export class FleetMapPage {
  private map?: L.Map;
  private mapResizeObserver?: ResizeObserver;
  private mapResizeTimer = 0;
  private liveRefreshTimer = 0;
  private basemapLayer?: L.Layer;
  private geofenceLayer = L.layerGroup();
  private markerLayer = L.layerGroup();
  private routeLayer = L.layerGroup();
  private arcomLayer = L.layerGroup();
  private osintLayer = L.layerGroup();
  private geofenceShapes = new Map<string, L.Layer>();
  private vehicles: FleetVehicle[] = [];
  private latest: LatestLocation[] = [];
  private geofences: GeofenceItem[] = [];
  private currentRoute?: VehicleRoutePayload;
  private osintSelection = "none";
  private arcomEnabled = false;
  private selectedDeviceId = "";
  private labelToDevice = new Map<string, FleetVehicle>();
  private deviceSearchInput?: HTMLInputElement;
  private deviceSuggestions?: HTMLElement;
  private dateInput?: HTMLInputElement;
  private statusElement?: HTMLElement;
  private focusElement?: HTMLElement;
  private miningElement?: HTMLElement;
  private summaryElement?: HTMLElement;
  private selectedMiningConcession: MiningConcession | null = null;
  private selectedMiningLookupKey = "";
  private arcomCheckbox?: HTMLInputElement;
  private osintSelect?: HTMLSelectElement;
  private zoneTypeSelect?: HTMLSelectElement;
  private zoneDrawButton?: HTMLButtonElement;
  private drawHandler?: { enable: () => void; disable: () => void };
  private drawnLayer?: L.Layer;
  private pendingZoneGeometry?: ZoneGeometry;
  private zoneModalMode: "create" | "edit" = "create";
  private editingGeofence?: GeofenceItem;
  private editingGeofenceLayer?: L.Layer;
  private zonePanel?: HTMLElement;
  private zonePanelTitle?: HTMLElement;
  private zonePanelMeta?: HTMLElement;
  private zonePanelFeedback?: HTMLElement;
  private zoneNameInput?: HTMLInputElement;
  private zoneColorInput?: HTMLInputElement;
  private zoneDeleteButton?: HTMLButtonElement;
  private zonePanelDrag?: { startX: number; startY: number; startLeft: number; startTop: number };
  private readonly handleWindowResize = () => this.refreshMapSize();
  private readonly handleRootClick = (event: MouseEvent) => this.onRootClick(event);
  private readonly handleZonePanelPointerMove = (event: PointerEvent) => this.moveZonePanel(event);
  private readonly handleZonePanelPointerUp = () => this.stopZonePanelDrag();

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly toastBus: ToastBus
  ) {}

  async mount(): Promise<void> {
    this.root.classList.add("rb-fleet-map-page");
    this.renderShell();
    this.root.addEventListener("click", this.handleRootClick);
    this.initializeMap();
    window.addEventListener("resize", this.handleWindowResize);
    window.addEventListener("beforeunload", () => {
      this.mapResizeObserver?.disconnect();
      window.clearTimeout(this.mapResizeTimer);
      window.clearInterval(this.liveRefreshTimer);
      window.removeEventListener("resize", this.handleWindowResize);
      this.root.removeEventListener("click", this.handleRootClick);
    });
    await this.loadLatest();
    this.liveRefreshTimer = window.setInterval(() => void this.refreshLiveMap(), 15000);
  }

  private renderShell(): void {
    this.deviceSearchInput = createElement("input", {
      className: "form-control form-control-sm",
      attrs: { type: "text", placeholder: "Buscar vehículo o dron...", autocomplete: "off", role: "combobox", "aria-expanded": "false" }
    }) as HTMLInputElement;
    this.deviceSearchInput.addEventListener("input", () => this.onDeviceSearchInput());
    this.deviceSearchInput.addEventListener("focus", () => this.onDeviceSearchFocus());
    this.deviceSuggestions = createElement("div", { className: "rb-map-device-suggestions", attrs: { role: "listbox" } });
    this.deviceSuggestions.hidden = true;
    this.dateInput = createElement("input", {
      className: "form-control form-control-sm",
      attrs: { type: "date" }
    }) as HTMLInputElement;
    this.dateInput.value = new Date().toISOString().slice(0, 10);
    this.statusElement = createElement("span", { className: "rb-map-status" }, "Cargando flota...");
    this.focusElement = createElement("div", { className: "rb-map-focus" });
    this.miningElement = createElement("div", { className: "rb-map-mining" });
    this.summaryElement = createElement("div", { className: "rb-route-summary" }, "Selecciona un vehículo para ver su recorrido.");
    const deviceSearch = createElement("div", { className: "rb-map-device-search" }, [
      this.deviceSearchInput,
      this.deviceSuggestions
    ]);

    const reloadButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => void this.loadLatest()
    }, "Actualizar");

    const routeButton = createElement("button", {
      className: "btn btn-danger btn-sm",
      attrs: { type: "button" },
      onClick: () => void this.loadRoute()
    }, "Recorrido");

    const basemapSelect = createElement("select", { className: "form-select form-select-sm" }, [
      createElement("option", { attrs: { value: "gray" } }, "Principal"),
      createElement("option", { attrs: { value: "satellite" } }, "Satelital"),
      createElement("option", { attrs: { value: "dark" } }, "Oscuro"),
      createElement("option", { attrs: { value: "relief" } }, "Relieve")
    ]) as HTMLSelectElement;
    basemapSelect.addEventListener("change", () => this.setBasemap(basemapSelect.value));

    this.arcomCheckbox = createElement("input", { attrs: { type: "checkbox", id: "map-arcom-toggle" } }) as HTMLInputElement;
    this.arcomCheckbox.addEventListener("change", () => {
      this.arcomEnabled = Boolean(this.arcomCheckbox?.checked);
      void this.refreshArcomLayer();
    });
    const arcomLabel = createElement("label", { className: "rb-map-switch", attrs: { for: "map-arcom-toggle" } }, [
      this.arcomCheckbox,
      createElement("span", {}, "Capa ARCOM")
    ]);

    this.osintSelect = createElement("select", { className: "form-select form-select-sm" },
      OSINT_CATEGORIES.map(([value, label]) => createElement("option", { attrs: { value } }, label))
    ) as HTMLSelectElement;
    this.osintSelect.addEventListener("change", () => {
      this.osintSelection = this.osintSelect?.value || "none";
      void this.refreshOsintLayer();
    });

    const recenterButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => this.recenter()
    }, "Recentrar");

    const exportButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => this.exportRoute()
    }, "Exportar rutas");

    const clearButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => this.clearRoute()
    }, "Clear");

    this.zoneTypeSelect = createElement("select", { className: "form-select form-select-sm" }, [
      createElement("option", { attrs: { value: "polygon" } }, "Polígono"),
      createElement("option", { attrs: { value: "circle" } }, "Círculo")
    ]) as HTMLSelectElement;

    this.zoneDrawButton = createElement("button", {
      className: "btn btn-outline-light btn-sm",
      attrs: { type: "button" },
      onClick: () => this.toggleZoneDraw()
    }, "Nueva zona") as HTMLButtonElement;

    const zonePanelElement = this.buildZonePanel();

    this.root.replaceChildren(
      createElement("section", { className: "rb-map-shell" }, [
        createElement("div", { className: "rb-admin-header" }, [
          createElement("div", {}, [
            createElement("span", { className: "rb-kicker" }, "Operaciones"),
            createElement("h1", { className: "h4 mb-1" }, "Mapa y recorridos"),
            createElement("p", { className: "rb-muted mb-0" }, "Ubicación actual y recorrido diario de la flota.")
          ]),
          createElement("div", { className: "rb-map-toolbar" }, [
            deviceSearch,
            this.dateInput,
            routeButton,
            reloadButton
          ])
        ]),
        createElement("div", { className: "rb-map-toolbar rb-map-toolbar-secondary" }, [
          arcomLabel,
          this.osintSelect,
          basemapSelect,
          recenterButton,
          exportButton,
          clearButton,
          this.zoneTypeSelect,
          this.zoneDrawButton
        ]),
        createElement("div", { className: "rb-map-layout" }, [
          createElement("aside", { className: "rb-map-sidebar" }, [
            createElement("div", { className: "rb-panel-heading" }, [
              createElement("h2", { className: "h6 mb-0" }, "Unidad seleccionada"),
              this.statusElement
            ]),
            this.focusElement,
            this.summaryElement,
            this.miningElement
          ]),
          createElement("div", { className: "rb-fleet-map-stage" }, [
            createElement("div", { className: "rb-fleet-map-canvas", attrs: { id: "fleet-map-canvas" } }),
            zonePanelElement
          ])
        ])
      ])
    );
  }

  private buildZonePanel(): HTMLElement {
    this.zoneNameInput = createElement("input", {
      className: "rb-zone-floating-name",
      attrs: { type: "text", maxlength: "160", placeholder: "Nombre de zona" }
    }) as HTMLInputElement;
    this.zoneColorInput = createElement("input", {
      className: "rb-zone-floating-color-input",
      attrs: { type: "color", value: "#f13811" }
    }) as HTMLInputElement;
    this.zoneColorInput.addEventListener("input", () => this.updateZonePreviewColor());
    this.zoneDeleteButton = createElement("button", {
      className: "btn btn-outline-danger btn-sm",
      attrs: { type: "button" },
      onClick: () => void this.deleteGeofence(this.editingGeofence?.id)
    }, "Eliminar") as HTMLButtonElement;
    this.zoneDeleteButton.hidden = true;
    this.zonePanelTitle = createElement("strong", { attrs: { id: "zone-floating-title" } }, "Nueva geocerca");
    this.zonePanelMeta = createElement("span", {}, "0 puntos");
    this.zonePanelFeedback = createElement("div", {
      className: "rb-zone-floating-feedback",
      attrs: { "aria-live": "polite" }
    });
    const closeButton = createElement("button", {
      className: "rb-zone-floating-close",
      attrs: { type: "button", "aria-label": "Cerrar editor de geocerca" },
      onClick: () => this.cancelZoneWorkflow()
    }, "x");
    const header = createElement("div", { className: "rb-zone-floating-head" }, [
      createElement("div", {}, [this.zonePanelTitle, this.zonePanelMeta]),
      closeButton
    ]);
    header.addEventListener("pointerdown", (event) => this.startZonePanelDrag(event));

    this.zonePanel = createElement("div", {
      className: "rb-zone-floating-panel",
      attrs: { role: "dialog", "aria-modal": "false", "aria-labelledby": "zone-floating-title" }
    }, [
      header,
      this.zoneNameInput,
      createElement("label", { className: "rb-zone-floating-color" }, [
        createElement("span", {}, "Color"),
        this.zoneColorInput
      ]),
      createElement("div", { className: "rb-zone-floating-actions" }, [
        this.zoneDeleteButton,
        createElement("button", {
          className: "btn btn-outline-light btn-sm",
          attrs: { type: "button" },
          onClick: () => this.cancelZoneWorkflow()
        }, "Cancelar"),
        createElement("button", {
          className: "btn btn-danger btn-sm",
          attrs: { type: "button" },
          onClick: () => void this.saveZone()
        }, "Guardar")
      ]),
      this.zonePanelFeedback
    ]);
    this.zonePanel.hidden = true;
    return this.zonePanel;
  }

  private initializeMap(): void {
    const mapElement = this.root.querySelector<HTMLElement>("#fleet-map-canvas");
    if (!mapElement) return;

    this.map = L.map(mapElement, {
      center: ECUADOR_CENTER,
      zoom: 7,
      zoomControl: true
    });
    this.basemapLayer = this.buildBasemap("gray").addTo(this.map);
    this.geofenceLayer.addTo(this.map);
    this.markerLayer.addTo(this.map);
    this.routeLayer.addTo(this.map);
    this.arcomLayer.addTo(this.map);
    this.osintLayer.addTo(this.map);
    this.map.on("moveend", () => {
      void this.refreshArcomLayer();
      void this.refreshOsintLayer();
    });
    this.map.on(L.Draw.Event.CREATED, (event: L.LeafletEvent) => {
      this.onZoneCreated((event as L.DrawEvents.Created).layer);
    });
    if (typeof ResizeObserver !== "undefined") {
      this.mapResizeObserver = new ResizeObserver(() => this.refreshMapSize());
      this.mapResizeObserver.observe(mapElement);
    }
    this.refreshMapSize();
    window.setTimeout(() => this.refreshMapSize(), 300);
  }

  private refreshMapSize(): void {
    if (!this.map) return;
    window.requestAnimationFrame(() => this.map?.invalidateSize());
    window.clearTimeout(this.mapResizeTimer);
    this.mapResizeTimer = window.setTimeout(() => this.map?.invalidateSize(), 180);
  }

  private buildBasemap(style: string): L.Layer {
    if (style === "satellite") {
      return L.layerGroup([
        L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
          maxZoom: 19,
          attribution: "&copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
        }),
        L.tileLayer("https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {
          maxZoom: 19,
          opacity: 0.92
        })
      ]);
    }
    if (style === "dark") {
      return L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        subdomains: "abcd",
        maxZoom: 20,
        attribution: "&copy; OpenStreetMap contributors &copy; CARTO"
      });
    }
    if (style === "relief") {
      return L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 18,
        attribution: "Tiles &copy; Esri"
      });
    }
    return L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19,
      attribution: "Tiles &copy; Esri"
    });
  }

  private setBasemap(style: string): void {
    if (!this.map) return;
    if (this.basemapLayer) {
      this.map.removeLayer(this.basemapLayer);
    }
    this.basemapLayer = this.buildBasemap(style).addTo(this.map);
    this.refreshMapSize();
  }

  private recenter(): void {
    if (!this.map) return;
    this.map.fitBounds(ECUADOR_BOUNDS);
  }

  private clearRoute(): void {
    this.clearDeviceSelection({ clearRoute: true, clearSearch: true });
  }

  private toggleZoneDraw(): void {
    if (this.drawHandler || this.editingGeofenceLayer || this.drawnLayer || this.pendingZoneGeometry) {
      this.cancelZoneWorkflow();
      return;
    }
    if (!this.map) return;
    this.zoneModalMode = "create";
    this.editingGeofence = undefined;
    this.zoneDeleteButton && (this.zoneDeleteButton.hidden = true);
    const shapeType = this.zoneTypeSelect?.value === "circle" ? "circle" : "polygon";
    const color = this.zoneColorInput?.value || "#f13811";
    const shapeOptions = { color, fillColor: color, fillOpacity: 0.15 };
    const drawMap = this.map as unknown as L.DrawMap;
    this.drawHandler = shapeType === "circle"
      ? new L.Draw.Circle(drawMap, { shapeOptions })
      : new L.Draw.Polygon(drawMap, { shapeOptions, allowIntersection: false });
    this.drawHandler.enable();
    this.zoneDrawButton?.classList.add("active");
    if (this.zoneDrawButton) this.zoneDrawButton.textContent = "Cancelar dibujo";
    if (this.zoneNameInput) this.zoneNameInput.value = "";
    this.zoneDeleteButton && (this.zoneDeleteButton.hidden = true);
    this.openZonePanel(
      "Nueva geocerca",
      shapeType === "circle"
        ? "Dibuja el círculo en el mapa y suelta para abrir el panel."
        : "Dibuja el polígono en el mapa y cierra la forma para guardar."
    );
  }

  private cancelZoneWorkflow(): void {
    this.drawHandler?.disable();
    this.drawHandler = undefined;
    this.drawnLayer && this.map?.removeLayer(this.drawnLayer);
    this.drawnLayer = undefined;
    this.disableLayerEditing(this.editingGeofenceLayer);
    this.editingGeofenceLayer && this.map?.removeLayer(this.editingGeofenceLayer);
    const hadEditingLayer = Boolean(this.editingGeofenceLayer);
    this.editingGeofenceLayer = undefined;
    this.editingGeofence = undefined;
    this.zoneModalMode = "create";
    this.pendingZoneGeometry = undefined;
    this.zoneDrawButton?.classList.remove("active");
    if (this.zoneDrawButton) this.zoneDrawButton.textContent = "Nueva zona";
    this.zoneDeleteButton && (this.zoneDeleteButton.hidden = true);
    this.closeZonePanel();
    if (hadEditingLayer) this.drawGeofences();
  }

  private onZoneCreated(layer: L.Layer): void {
    this.drawHandler = undefined;
    this.zoneDrawButton?.classList.remove("active");
    if (this.zoneDrawButton) this.zoneDrawButton.textContent = "Nueva zona";
    this.drawnLayer = layer;
    this.map?.addLayer(layer);

    const geometry = this.geometryFromLayer(layer);
    if (!geometry) {
      this.toastBus.info("Dibuja una geocerca válida.");
      this.map?.removeLayer(layer);
      this.drawnLayer = undefined;
      return;
    }
    this.pendingZoneGeometry = geometry;

    this.zoneModalMode = "create";
    this.zoneDeleteButton && (this.zoneDeleteButton.hidden = true);
    if (this.zoneNameInput) this.zoneNameInput.value = "";
    this.openZonePanel("Nueva geocerca", "Ajusta nombre y color. El panel se puede arrastrar.");
  }

  private async saveZone(): Promise<void> {
    const name = this.zoneNameInput?.value.trim();
    const color = this.zoneColorInput?.value || "#f13811";
    if (this.zoneModalMode === "edit") {
      await this.saveEditedZone(name || "", color);
      return;
    }
    if (!name || !this.pendingZoneGeometry) {
      this.toastBus.info("Ingresa un nombre para la zona.");
      return;
    }
    const payload = this.buildGeofencePayload(name, color, this.pendingZoneGeometry);

    try {
      await this.api.post("/api/v1/geofences/geofences/", payload);
      this.toastBus.success("Geocerca creada.");
      this.closeZonePanel();
      if (this.drawnLayer) this.map?.removeLayer(this.drawnLayer);
      this.drawnLayer = undefined;
      this.pendingZoneGeometry = undefined;
      await this.reloadGeofences();
    } catch {
      this.toastBus.error("No se pudo guardar la geocerca.");
    }
  }

  private async saveEditedZone(name: string, color: string): Promise<void> {
    const item = this.editingGeofence;
    const layer = this.editingGeofenceLayer;
    const geometry = layer ? this.geometryFromLayer(layer) : null;
    if (!item || !layer || !geometry) {
      this.toastBus.info("Selecciona una geocerca válida para editar.");
      return;
    }
    if (!name) {
      this.toastBus.info("Ingresa un nombre para la zona.");
      return;
    }
    try {
      await this.api.put(`/api/v1/geofences/geofences/${item.id}/`, this.buildGeofencePayload(name, color, geometry, item));
      this.toastBus.success("Geocerca actualizada.");
      this.closeZonePanel();
      this.disableLayerEditing(layer);
      this.map?.removeLayer(layer);
      this.editingGeofenceLayer = undefined;
      this.editingGeofence = undefined;
      this.zoneModalMode = "create";
      await this.reloadGeofences();
    } catch {
      this.toastBus.error("No se pudo actualizar la geocerca.");
    }
  }

  private buildGeofencePayload(name: string, color: string, geometry: ZoneGeometry, existing?: GeofenceItem): Record<string, unknown> {
    const payload: Record<string, unknown> = {
      name,
      type: geometry.type,
      geofence_type: geometry.type,
      color,
      active: existing?.active ?? true,
      description: existing?.description || ""
    };
    if (existing?.company_id) {
      payload.company_id = existing.company_id;
    }
    if (geometry.type === "circle") {
      payload.lat = geometry.center.lat;
      payload.lon = geometry.center.lon;
      payload.radius_m = geometry.radius_m;
      payload.geometry = {
        type: "Circle",
        center: geometry.center,
        radius_m: geometry.radius_m,
        color,
        style: { color, fillColor: color }
      };
      return payload;
    }
    payload.geometry = {
      type: "Polygon",
      coordinate_order: "latlon",
      coordinates: geometry.coordinates,
      color,
      style: { color, fillColor: color }
    };
    return payload;
  }

  private async reloadGeofences(): Promise<void> {
    const geofences = await this.api.get<GeofenceItem[]>("/api/v1/geofences/geofences/");
    this.geofences = geofences;
    this.drawGeofences();
    this.renderFocusPanel();
  }

  private openZonePanel(title: string, feedback = ""): void {
    if (this.zonePanelTitle) this.zonePanelTitle.textContent = title;
    this.setZonePanelFeedback(feedback);
    this.syncZonePanelMeta();
    if (this.zonePanel) {
      this.zonePanel.hidden = false;
    }
  }

  private closeZonePanel(): void {
    if (this.zonePanel) {
      this.zonePanel.hidden = true;
    }
    this.setZonePanelFeedback("");
    this.stopZonePanelDrag();
  }

  private setZonePanelFeedback(message: string, tone = ""): void {
    if (!this.zonePanelFeedback) return;
    this.zonePanelFeedback.textContent = message;
    this.zonePanelFeedback.dataset.tone = tone;
  }

  private syncZonePanelMeta(): void {
    if (!this.zonePanelMeta) return;
    const geometry = this.editingGeofenceLayer
      ? this.geometryFromLayer(this.editingGeofenceLayer)
      : this.pendingZoneGeometry;
    if (!geometry) {
      this.zonePanelMeta.textContent = "0 puntos";
      return;
    }
    if (geometry.type === "circle") {
      this.zonePanelMeta.textContent = `${Math.round(geometry.radius_m)} m`;
      return;
    }
    const count = geometry.coordinates.length;
    this.zonePanelMeta.textContent = `${count} punto${count === 1 ? "" : "s"}`;
  }

  private startZonePanelDrag(event: PointerEvent): void {
    if (event.button !== 0) return;
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest("button,input,label")) return;
    if (!this.zonePanel?.parentElement) return;
    const panelRect = this.zonePanel.getBoundingClientRect();
    const parentRect = this.zonePanel.parentElement.getBoundingClientRect();
    this.zonePanelDrag = {
      startX: event.clientX,
      startY: event.clientY,
      startLeft: panelRect.left - parentRect.left,
      startTop: panelRect.top - parentRect.top
    };
    this.zonePanel.style.left = `${this.zonePanelDrag.startLeft}px`;
    this.zonePanel.style.top = `${this.zonePanelDrag.startTop}px`;
    this.zonePanel.style.right = "auto";
    this.zonePanel.style.bottom = "auto";
    this.zonePanel.classList.add("is-dragging");
    window.addEventListener("pointermove", this.handleZonePanelPointerMove);
    window.addEventListener("pointerup", this.handleZonePanelPointerUp, { once: true });
    event.preventDefault();
  }

  private moveZonePanel(event: PointerEvent): void {
    if (!this.zonePanelDrag || !this.zonePanel?.parentElement) return;
    const parent = this.zonePanel.parentElement;
    const maxLeft = Math.max(8, parent.clientWidth - this.zonePanel.offsetWidth - 8);
    const maxTop = Math.max(8, parent.clientHeight - this.zonePanel.offsetHeight - 8);
    const nextLeft = Math.min(maxLeft, Math.max(8, this.zonePanelDrag.startLeft + event.clientX - this.zonePanelDrag.startX));
    const nextTop = Math.min(maxTop, Math.max(8, this.zonePanelDrag.startTop + event.clientY - this.zonePanelDrag.startY));
    this.zonePanel.style.left = `${nextLeft}px`;
    this.zonePanel.style.top = `${nextTop}px`;
  }

  private stopZonePanelDrag(): void {
    window.removeEventListener("pointermove", this.handleZonePanelPointerMove);
    window.removeEventListener("pointerup", this.handleZonePanelPointerUp);
    this.zonePanel?.classList.remove("is-dragging");
    this.zonePanelDrag = undefined;
  }

  private exportRoute(): void {
    if (!this.currentRoute || !this.currentRoute.points.length) {
      this.toastBus.info("No hay recorrido cargado para exportar.");
      return;
    }
    const rows = ["lat,lon,velocidad,rumbo,fecha_hora"];
    for (const point of this.currentRoute.points) {
      rows.push([point.lat, point.lon, point.speed ?? "", point.heading ?? "", point.received_at].join(","));
    }
    const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = createElement("a", {
      attrs: {
        href: url,
        download: `recorrido_${this.vehicleLabel(this.currentRoute.vehicle)}_${this.currentRoute.date}.csv`
      }
    }) as HTMLAnchorElement;
    link.click();
    URL.revokeObjectURL(url);
  }

  private async refreshArcomLayer(): Promise<void> {
    this.arcomLayer.clearLayers();
    if (!this.arcomEnabled || !this.map || this.map.getZoom() < ARCOM_MIN_ZOOM) return;
    try {
      const payload = await this.api.get<OsintPayload>(
        `/api/v1/fleet/geointel/arcom/concessions/?bbox=${this.currentBbox()}&limit=120`,
        { silent: true }
      );
      for (const feature of payload.features ?? []) {
        this.drawGeoJsonFeature(feature, this.arcomLayer, {
          color: "#f59e0b",
          weight: 1.6,
          opacity: 0.8,
          fillColor: "#f59e0b",
          fillOpacity: 0.12
        }, (props) => `<strong>${this.escapeHtml(String(props.nombre_concesion || "Concesion"))}</strong><br>` +
          `Codigo: ${this.escapeHtml(String(props.codigo_catastral || "--"))}<br>` +
          `Estado: ${this.escapeHtml(String(props.estado_actual || "--"))}<br>` +
          `Empresa: ${this.escapeHtml(String(props.empresa || "--"))}`);
      }
    } catch {
      // capa opcional: silencioso si apicentral no responde
    }
  }

  private async refreshOsintLayer(): Promise<void> {
    this.osintLayer.clearLayers();
    if (this.osintSelection === "none" || !this.map) return;
    try {
      const payload = await this.api.get<OsintPayload>(
        `/api/v1/fleet/geointel/osint/layers/?bbox=${this.currentBbox()}&limit=2000&layer=${encodeURIComponent(this.osintSelection)}`,
        { silent: true }
      );
      for (const feature of payload.features ?? []) {
        this.drawGeoJsonFeature(feature, this.osintLayer, {
          color: "#ef4444",
          weight: 1.7,
          opacity: 0.78,
          fillColor: "#22c55e",
          fillOpacity: 0.12
        }, (props) => `<strong>${this.escapeHtml(String(props.nombre || props.titulo || "OSINT"))}</strong><br>` +
          `Tipo: ${this.escapeHtml(String(props.tipo || props.category || "--"))}`);
      }
    } catch {
      // capa opcional: silencioso si apicentral no responde
    }
  }

  private drawGeoJsonFeature(
    feature: OsintFeature,
    target: L.LayerGroup,
    style: L.PathOptions,
    popupBuilder: (props: Record<string, unknown>) => string
  ): void {
    const geometry = feature.geometry;
    if (!geometry || !geometry.type) return;
    const props = feature.properties ?? {};
    if (geometry.type === "Point") {
      const coords = geometry.coordinates as [number, number];
      if (!Array.isArray(coords) || coords.length < 2) return;
      const iconUrl = typeof props.url_icono === "string" ? props.url_icono.trim() : "";
      const marker = iconUrl
        ? L.marker([coords[1], coords[0]], { icon: L.icon({ iconUrl, iconSize: [26, 26], iconAnchor: [13, 13] }) })
        : L.circleMarker([coords[1], coords[0]], { radius: 6, color: style.color, fillColor: style.fillColor, fillOpacity: 0.85, weight: 1.5 });
      marker.bindPopup(popupBuilder(props)).addTo(target);
      return;
    }
    L.geoJSON(feature as unknown as GeoJSON.Feature, { style }).bindPopup(popupBuilder(props)).addTo(target);
  }

  private currentBbox(): string {
    if (!this.map) return "-81.2,-5.1,-75.1,1.6";
    const bounds = this.map.getBounds();
    return [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].join(",");
  }

  private escapeHtml(value: string): string {
    return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char] as string));
  }

  private onRootClick(event: MouseEvent): void {
    const target = event.target instanceof Element ? event.target : null;
    if (!target?.closest(".rb-map-device-search")) {
      this.hideDeviceSuggestions();
    }
    const editButton = target?.closest<HTMLElement>("[data-geofence-edit]");
    if (editButton) {
      event.preventDefault();
      event.stopPropagation();
      this.openGeofenceEdit(editButton.dataset.geofenceEdit || editButton.getAttribute("data-geofence-edit") || "");
      return;
    }
    const deleteButton = target?.closest<HTMLElement>("[data-geofence-delete]");
    if (deleteButton) {
      event.preventDefault();
      event.stopPropagation();
      void this.deleteGeofence(deleteButton.dataset.geofenceDelete || deleteButton.getAttribute("data-geofence-delete") || "");
    }
  }

  private async loadLatest(
    { fitMarkers = true, refreshRoute = false, silent = false }: { fitMarkers?: boolean; refreshRoute?: boolean; silent?: boolean } = {}
  ): Promise<void> {
    if (!silent) this.setStatus("Cargando...");
    try {
      const [vehicles, drones, latest, geofences] = await Promise.all([
        this.api.get<Paginated<FleetVehicle>>("/api/v1/devices/vehicles/"),
        this.api.get<Paginated<DroneDevice>>("/api/v1/devices/drones/"),
        this.api.get<LatestLocationsPayload>("/api/v1/fleet/latest/"),
        this.api.get<GeofenceItem[]>("/api/v1/geofences/geofences/")
      ]);
      const droneDevices = drones.results.map((drone) => this.droneToFleetVehicle(drone));
      this.vehicles = [...this.dedupeVehicles(vehicles.results), ...droneDevices];
      this.latest = latest.results;
      this.geofences = geofences;
      this.renderDeviceOptions();
      this.drawGeofences();
      this.refreshMapSize();
      this.drawMarkers(fitMarkers);
      this.refreshMapSize();
      this.renderFocusPanel();
      this.renderMiningPanel();
      void this.lookupSelectedMiningConcession(this.selectedTelemetry());
      this.setStatus(`${latest.count} con GPS`);
      if (this.currentRoute && this.currentRoute.vehicle.id === this.selectedDeviceId) {
        this.drawRoute(this.currentRoute, { fit: false });
      }
      if (refreshRoute && this.shouldRefreshSelectedRoute()) {
        void this.loadRoute({ fit: false, silent: true });
      }
    } catch {
      if (!silent) {
        this.setStatus("Error");
        this.toastBus.error("No se pudo cargar el mapa de flota.");
      }
    }
  }

  private async refreshLiveMap(): Promise<void> {
    await this.loadLatest({ fitMarkers: false, refreshRoute: true, silent: true });
  }

  private droneToFleetVehicle(drone: DroneDevice): FleetVehicle {
    return {
      id: drone.id,
      name: drone.name,
      plate: null,
      unique_code: drone.unique_code,
      driver_name: null,
      vehicle_type: "dron",
      vehicle_subtype: drone.drone_type,
      active: drone.active,
      cameras: []
    };
  }

  private isDrone(vehicle: FleetVehicle): boolean {
    return new FleetDeviceModel(vehicle).isDrone;
  }

  private renderDeviceOptions(): void {
    this.labelToDevice.clear();
    for (const device of this.vehicles) {
      this.labelToDevice.set(this.vehicleLabel(device).toLowerCase(), device);
    }
    this.renderDeviceSuggestions(this.deviceSearchInput?.value || "");
  }

  private onDeviceSearchInput(): void {
    const term = (this.deviceSearchInput?.value || "").trim();
    const match = this.labelToDevice.get(term.toLowerCase());
    if (match) {
      this.selectDevice(match.id, true);
      this.hideDeviceSuggestions();
      return;
    }
    if (this.selectedDeviceId) {
      this.clearDeviceSelection({ clearRoute: true });
    }
    this.renderDeviceSuggestions(term);
  }

  private onDeviceSearchFocus(): void {
    const term = (this.deviceSearchInput?.value || "").trim();
    const exactMatch = this.labelToDevice.get(term.toLowerCase());
    if (!term || (exactMatch && exactMatch.id === this.selectedDeviceId)) {
      this.hideDeviceSuggestions();
      return;
    }
    this.renderDeviceSuggestions(term);
  }

  private renderDeviceSuggestions(filterTerm = ""): void {
    if (!this.deviceSuggestions) return;
    const needle = filterTerm.trim().toLowerCase();
    const devices = (needle
      ? this.vehicles.filter((device) => this.deviceMatchesSearch(device, needle))
      : this.vehicles
    ).slice(0, 40);

    if (!devices.length) {
      this.deviceSuggestions.replaceChildren(
        createElement("div", { className: "rb-map-device-suggestion-empty" }, "Sin resultados")
      );
      this.showDeviceSuggestions();
      return;
    }

    this.deviceSuggestions.replaceChildren(...devices.map((vehicle) => {
      const device = new FleetDeviceModel(vehicle);
      const latest = this.latest.find((item) => item.vehicle.id === vehicle.id);
      const speed = latest?.speed == null ? "--" : `${Number(latest.speed).toFixed(1)} km/h`;
      return createElement("button", {
        className: `rb-map-device-suggestion ${vehicle.id === this.selectedDeviceId ? "is-active" : ""}`,
        attrs: { type: "button", role: "option" },
        onClick: () => {
          this.selectDevice(vehicle.id, true);
          this.hideDeviceSuggestions();
        }
      }, [
        createElement("span", { className: "rb-device-title" }, device.title),
        createElement("span", { className: "rb-device-meta" }, [
          speed,
          latest ? this.freshnessLabel(latest.freshness) : "sin telemetría",
          device.capabilityLabel()
        ].join(" · "))
      ]);
    }));
    this.showDeviceSuggestions();
  }

  private deviceMatchesSearch(device: FleetVehicle, needle: string): boolean {
    const searchable = [
      this.vehicleLabel(device),
      device.name,
      device.plate,
      device.unique_code,
      device.driver_name,
      device.brand,
      device.model,
      this.isDrone(device) ? "dron drone" : "vehiculo vehículo"
    ];
    return searchable.some((value) => String(value || "").toLowerCase().includes(needle));
  }

  private showDeviceSuggestions(): void {
    if (!this.deviceSuggestions) return;
    this.deviceSuggestions.hidden = false;
    this.deviceSearchInput?.setAttribute("aria-expanded", "true");
  }

  private hideDeviceSuggestions(): void {
    if (!this.deviceSuggestions) return;
    this.deviceSuggestions.hidden = true;
    this.deviceSearchInput?.setAttribute("aria-expanded", "false");
  }

  private clearDeviceSelection(
    { clearRoute = false, clearSearch = false }: { clearRoute?: boolean; clearSearch?: boolean } = {}
  ): void {
    this.selectedDeviceId = "";
    this.selectedMiningLookupKey = "";
    this.selectedMiningConcession = null;
    if (clearRoute) {
      this.routeLayer.clearLayers();
      this.currentRoute = undefined;
      this.setRouteSummary("Selecciona un vehículo para ver su recorrido.");
    }
    if (clearSearch && this.deviceSearchInput) {
      this.deviceSearchInput.value = "";
    }
    this.renderFocusPanel();
    this.renderMiningPanel();
    this.renderDeviceSuggestions(this.deviceSearchInput?.value || "");
  }

  private drawMarkers(fit = true): void {
    if (!this.map) return;
    this.markerLayer.clearLayers();
    const bounds = L.latLngBounds([]);

    for (const item of this.latest) {
      if (!this.validCoordinate(item.lat, item.lon)) continue;
      const latLng: L.LatLngExpression = [Number(item.lat), Number(item.lon)];
      bounds.extend(latLng);
      L.marker(latLng, { icon: this.deviceIcon(item) })
        .bindTooltip(`${this.vehicleLabel(item.vehicle)} · ${this.freshnessLabel(item.freshness)}`)
        .on("click", () => {
          if (this.drawHandler) return;
          this.selectDevice(item.vehicle.id, true);
        })
        .addTo(this.markerLayer);
    }

    if (fit && bounds.isValid()) {
      this.map.fitBounds(bounds.pad(0.2), { maxZoom: 15 });
    }
  }

  private deviceIcon(item: LatestLocation): L.DivIcon {
    const color = this.markerColor(item.freshness);
    const glyph = item.kind === "drone" ? this.droneSvg(color) : this.carSvg(color);
    const selected = item.vehicle.id === this.selectedDeviceId;
    return L.divIcon({
      className: `rb-fleet-device-icon ${selected ? "is-selected" : ""}`,
      html: `<span class="rb-device-marker-shell ${selected ? "is-selected" : ""}">${glyph}</span>`,
      iconSize: [30, 30],
      iconAnchor: [15, 15],
      popupAnchor: [0, -15]
    });
  }

  private carSvg(color: string): string {
    return `<svg width="30" height="30" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="11" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="1.5"/>
      <path d="M5.5 14.5l1-3.6a1.6 1.6 0 0 1 1.55-1.15h7.9a1.6 1.6 0 0 1 1.55 1.15l1 3.6" stroke="${color}" stroke-width="1.4" fill="${color}" fill-opacity="0.85"/>
      <rect x="4.6" y="14.2" width="14.8" height="2.6" rx="1" fill="${color}"/>
      <circle cx="7.6" cy="16.8" r="1.4" fill="#0b0f14" stroke="${color}" stroke-width="1"/>
      <circle cx="16.4" cy="16.8" r="1.4" fill="#0b0f14" stroke="${color}" stroke-width="1"/>
    </svg>`;
  }

  private droneSvg(color: string): string {
    return `<svg width="30" height="30" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="11" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="1.5"/>
      <path d="M7 7l3.2 3.2M17 7l-3.2 3.2M7 17l3.2-3.2M17 17l-3.2-3.2" stroke="${color}" stroke-width="1.4"/>
      <circle cx="6.4" cy="6.4" r="2" fill="${color}"/>
      <circle cx="17.6" cy="6.4" r="2" fill="${color}"/>
      <circle cx="6.4" cy="17.6" r="2" fill="${color}"/>
      <circle cx="17.6" cy="17.6" r="2" fill="${color}"/>
      <rect x="9.4" y="9.4" width="5.2" height="5.2" rx="1.2" fill="${color}"/>
    </svg>`;
  }

  private drawGeofences(): void {
    if (!this.map) return;
    this.geofenceLayer.clearLayers();
    this.geofenceShapes.clear();
    for (const geofence of this.geofences) {
      const color = this.geofenceColor(geofence, geofence.active !== false ? "#f13811" : "#94a3b8");
      const shape = this.layerFromGeofence(geofence, this.geofenceStyle(geofence, color));
      if (!shape) continue;
      shape.bindTooltip(geofence.name || "Geocerca");
      shape.bindPopup(this.geofencePopupContent(geofence, color));
      shape.addTo(this.geofenceLayer);
      this.geofenceShapes.set(geofence.id, shape);
    }
  }

  private layerFromGeofence(geofence: GeofenceItem, style: L.PathOptions): L.Layer | null {
    const type = String(geofence.geofence_type || geofence.type || "").toLowerCase();
    if (type === "circle") {
      const circle = this.circleData(geofence);
      return circle ? L.circle([circle.lat, circle.lon], { ...style, radius: circle.radius }) : null;
    }
    const points = this.geofencePoints(geofence);
    if (points.length < 3) return null;
    return L.polygon(points.map(([lat, lon]) => [lat, lon] as L.LatLngExpression), style);
  }

  private geofenceStyle(geofence: GeofenceItem, color: string): L.PathOptions {
    const active = geofence.active !== false;
    return {
      color,
      weight: 2,
      opacity: active ? 0.82 : 0.5,
      fillColor: color,
      fillOpacity: active ? 0.12 : 0.07,
      dashArray: active ? undefined : "6 6"
    };
  }

  private geofencePopupContent(geofence: GeofenceItem, color: string): HTMLElement {
    const swatch = createElement("span");
    swatch.style.background = color;
    const editButton = createElement("button", {
      attrs: { type: "button", "data-geofence-edit": geofence.id },
      onClick: () => {
        this.map?.closePopup();
        this.openGeofenceEdit(geofence.id);
      }
    }, "Editar");
    const deleteButton = createElement("button", {
      className: "is-danger",
      attrs: { type: "button", "data-geofence-delete": geofence.id },
      onClick: () => {
        this.map?.closePopup();
        void this.deleteGeofence(geofence.id);
      }
    }, "Eliminar");
    const meta = [
      `Tipo: ${this.geofenceTypeLabel(geofence)}`,
      this.geofenceShapeSummary(geofence),
      geofence.active === false ? "inactiva" : "activa",
      geofence.company_name ? `Organizacion: ${geofence.company_name}` : ""
    ].filter(Boolean).join(" · ");
    return createElement("div", { className: "rb-geofence-popup" }, [
      createElement("strong", {}, [swatch, geofence.name || "Geocerca"]),
      createElement("small", {}, meta),
      createElement("div", { className: "rb-geofence-popup-actions" }, [editButton, deleteButton])
    ]);
  }

  private openGeofenceEdit(geofenceId: string): void {
    if (!this.map || !geofenceId) return;
    const item = this.geofences.find((geofence) => geofence.id === geofenceId);
    if (!item) return;
    this.cancelZoneWorkflow();
    const color = this.geofenceColor(item, "#f13811");
    const layer = this.layerFromGeofence(item, {
      ...this.geofenceStyle(item, color),
      weight: 3,
      fillOpacity: 0.2
    });
    if (!layer) {
      this.toastBus.info("Esta geocerca no tiene geometría editable.");
      return;
    }
    const original = this.geofenceShapes.get(item.id);
    if (original) this.geofenceLayer.removeLayer(original);
    this.zoneModalMode = "edit";
    this.editingGeofence = item;
    this.editingGeofenceLayer = layer;
    layer.addTo(this.map);
    this.enableLayerEditing(layer);
    this.fitLayer(layer);
    if (this.zoneNameInput) this.zoneNameInput.value = item.name || "";
    if (this.zoneColorInput) this.zoneColorInput.value = color;
    this.zoneDeleteButton && (this.zoneDeleteButton.hidden = false);
    this.openZonePanel(`Editar ${item.name || "geocerca"}`, "Arrastra puntos o ajusta el círculo. Puedes mover este panel.");
  }

  private async deleteGeofence(geofenceId?: string | null): Promise<void> {
    const id = String(geofenceId || "").trim();
    if (!id) return;
    if (!window.confirm("Eliminar esta geocerca")) return;
    try {
      await this.api.delete(`/api/v1/geofences/geofences/${id}/`);
      this.toastBus.success("Geocerca eliminada.");
      this.closeZonePanel();
      if (this.editingGeofenceLayer) {
        this.disableLayerEditing(this.editingGeofenceLayer);
        this.map?.removeLayer(this.editingGeofenceLayer);
      }
      this.editingGeofenceLayer = undefined;
      this.editingGeofence = undefined;
      this.zoneModalMode = "create";
      await this.reloadGeofences();
    } catch {
      this.toastBus.error("No se pudo eliminar la geocerca.");
    }
  }

  private enableLayerEditing(layer: L.Layer): void {
    const editable = layer as L.Layer & { editing?: { enable: () => void } };
    editable.editing?.enable();
    layer.on("edit drag resize move", () => this.syncZonePanelMeta());
  }

  private disableLayerEditing(layer?: L.Layer): void {
    const editable = layer as (L.Layer & { editing?: { disable: () => void } }) | undefined;
    editable?.editing?.disable();
  }

  private fitLayer(layer: L.Layer): void {
    const bounded = layer as L.Layer & { getBounds?: () => L.LatLngBounds };
    const bounds = bounded.getBounds?.();
    if (bounds?.isValid()) {
      this.map?.fitBounds(bounds.pad(0.16), { maxZoom: 17 });
    }
  }

  private geometryFromLayer(layer: L.Layer): ZoneGeometry | null {
    if (layer instanceof L.Circle) {
      const center = layer.getLatLng();
      const radius = layer.getRadius();
      if (!this.validCoordinate(center.lat, center.lng) || !Number.isFinite(radius) || radius <= 0) return null;
      return { type: "circle", center: { lat: center.lat, lon: center.lng }, radius_m: radius };
    }
    if (layer instanceof L.Polygon) {
      const rawLatLngs = layer.getLatLngs();
      const ring = (Array.isArray(rawLatLngs[0]) ? rawLatLngs[0] : rawLatLngs) as L.LatLng[];
      const coordinates = ring
        .map((point) => [Number(point.lat), Number(point.lng)])
        .filter(([lat, lon]) => this.validCoordinate(lat, lon));
      return coordinates.length >= 3 ? { type: "polygon", coordinates } : null;
    }
    return null;
  }

  private updateZonePreviewColor(): void {
    const color = this.zoneColorInput?.value || "#f13811";
    const layer = this.editingGeofenceLayer || this.drawnLayer;
    const path = layer as (L.Layer & { setStyle?: (style: L.PathOptions) => void }) | undefined;
    path?.setStyle?.({ color, fillColor: color });
  }

  private async loadRoute({ fit = true, silent = false }: { fit?: boolean; silent?: boolean } = {}): Promise<void> {
    const deviceId = this.selectedDeviceId;
    const date = this.dateInput?.value;
    if (!deviceId || !date) {
      if (!silent) this.toastBus.info("Selecciona vehículo y fecha.");
      return;
    }
    const device = this.vehicles.find((item) => item.id === deviceId);
    const segment = device ? new FleetDeviceModel(device).routeSegment : "vehicles";

    if (!silent) this.setRouteSummary("Cargando recorrido...");
    try {
      const route = await this.api.get<VehicleRoutePayload>(`/api/v1/fleet/${segment}/${deviceId}/route/?date=${date}`);
      this.currentRoute = route;
      this.drawRoute(route, { fit });
      this.setRouteSummary(this.routeSummary(route));
    } catch {
      if (!silent) this.setRouteSummary("No se pudo cargar el recorrido.");
    }
  }

  private drawRoute(route: VehicleRoutePayload, { fit = true }: { fit?: boolean } = {}): void {
    if (!this.map) return;
    this.routeLayer.clearLayers();
    const bounds = L.latLngBounds([]);
    const routePoints = this.routePointsWithLivePosition(route);

    for (const point of routePoints) {
      bounds.extend([Number(point.lat), Number(point.lon)]);
    }

    for (let index = 1; index < routePoints.length; index += 1) {
      const previous = routePoints[index - 1];
      const point = routePoints[index];
      const meta = this.routeSegmentMeta(previous, point);
      const latLngs = this.routeSegmentLatLngs(previous, point);
      if (latLngs.length < 2) continue;
      const line = L.polyline(latLngs, this.routeSegmentStyle(meta)).addTo(this.routeLayer);
      if (meta.status !== "normal" && meta.status !== "osrm") {
        line.bindTooltip(this.routeSegmentTooltip(meta));
      }
    }

    for (const point of routePoints) {
      L.circleMarker([Number(point.lat), Number(point.lon)], {
        color: ROUTE_POINT_COLOR,
        fillColor: ROUTE_POINT_COLOR,
        fillOpacity: 0.86,
        radius: 3,
        weight: 1
      }).addTo(this.routeLayer);
    }

    this.addRouteEndpointMarkers(routePoints);

    if (fit && bounds.isValid()) {
      this.map.fitBounds(bounds.pad(0.18), { maxZoom: 16 });
    }
    this.refreshMapSize();
  }

  private addRouteEndpointMarkers(points: RoutePoint[]): void {
    const firstPoint = points[0];
    const lastPoint = points.at(-1);
    if (firstPoint) {
      L.circleMarker([Number(firstPoint.lat), Number(firstPoint.lon)], {
        color: "#14532d",
        fillColor: ROUTE_START_COLOR,
        fillOpacity: 1,
        radius: 8,
        weight: 2
      }).bindTooltip(`Inicio del recorrido · ${this.formatDate(firstPoint.received_at)}`).addTo(this.routeLayer);
    }
    if (lastPoint && lastPoint.id !== firstPoint?.id) {
      L.circleMarker([Number(lastPoint.lat), Number(lastPoint.lon)], {
        color: "#faf5ff",
        fillColor: ROUTE_CURRENT_COLOR,
        fillOpacity: 1,
        radius: 9,
        weight: 2.5
      }).bindTooltip(`Va por aqui · ${this.formatDate(lastPoint.received_at)}`).addTo(this.routeLayer);
    }
  }

  private routePointsWithLivePosition(route: VehicleRoutePayload): RoutePoint[] {
    const routePoints = route.points.filter((point) => this.validCoordinate(point.lat, point.lon));
    const livePoint = this.liveRoutePoint(route);
    if (!livePoint) return routePoints;
    const lastPoint = routePoints.at(-1);
    if (!lastPoint) return [livePoint];
    const liveAt = new Date(livePoint.received_at).getTime();
    const lastAt = new Date(lastPoint.received_at).getTime();
    const distanceKm = this.routeDistanceKm(lastPoint, livePoint);
    if (Number.isFinite(liveAt) && Number.isFinite(lastAt) && liveAt <= lastAt && distanceKm < 0.015) {
      return routePoints;
    }
    return [...routePoints, livePoint];
  }

  private liveRoutePoint(route: VehicleRoutePayload): RoutePoint | null {
    if (route.vehicle.id !== this.selectedDeviceId) return null;
    const item = this.selectedTelemetry();
    if (!item || !this.validCoordinate(item.lat, item.lon)) return null;
    const routeDate = this.dateInput?.value || route.date;
    if (!this.sameEcuadorDate(item.received_at, routeDate)) return null;
    return {
      id: `live-${item.vehicle.id}`,
      lat: Number(item.lat),
      lon: Number(item.lon),
      speed: item.speed == null ? null : Number(item.speed),
      heading: item.heading == null ? null : Number(item.heading),
      received_at: item.received_at,
      segment_status: "raw",
      segment_reason: "live_position",
      counted_for_km: false
    };
  }

  private sameEcuadorDate(value: string, expectedDate: string): boolean {
    if (!value || !expectedDate) return false;
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return false;
    return parsed.toLocaleDateString("en-CA", { timeZone: "America/Guayaquil" }) === expectedDate;
  }

  private shouldRefreshSelectedRoute(): boolean {
    if (!this.currentRoute || !this.selectedDeviceId || this.currentRoute.vehicle.id !== this.selectedDeviceId) return false;
    const today = new Date().toLocaleDateString("en-CA", { timeZone: "America/Guayaquil" });
    return (this.dateInput?.value || this.currentRoute.date) === today;
  }

  private routeSummary(route: VehicleRoutePayload): string {
    const validPoints = route.points.filter((point) => this.validCoordinate(point.lat, point.lon));
    const firstPoint = validPoints[0];
    const lastPoint = validPoints.at(-1);
    const range = firstPoint && lastPoint
      ? ` · ${this.formatDate(firstPoint.received_at)} -> ${this.formatDate(lastPoint.received_at)}`
      : "";
    return `${this.vehicleLabel(route.vehicle)} · ${route.total_km.toFixed(2)} km · ${route.total_points} puntos${range}`;
  }

  private routeSegmentMeta(previous: RoutePoint, point: RoutePoint): RouteSegmentMeta {
    const distanceKm = this.numberOr(point.distance_km, this.routeDistanceKm(previous, point));
    const elapsedSeconds = this.numberOr(point.elapsed_seconds, this.routeElapsedSeconds(previous, point));
    const impliedSpeedKmh = this.numberOr(
      point.implied_speed_kmh,
      elapsedSeconds > 0 ? (distanceKm / elapsedSeconds) * 3600 : 0
    );
    const explicitStatus = point.segment_status ? this.normalizeRouteStatus(point.segment_status) : null;
    const computed = this.computedRouteStatus(distanceKm, elapsedSeconds, impliedSpeedKmh);
    return {
      status: explicitStatus && explicitStatus !== "start" ? explicitStatus : computed.status,
      reason: point.segment_reason || computed.reason,
      distanceKm,
      elapsedSeconds,
      impliedSpeedKmh
    };
  }

  private normalizeRouteStatus(value: string | null | undefined): RouteSegmentStatus {
    const status = String(value || "").toLowerCase();
    if (["start", "normal", "osrm", "raw", "gap", "suspicious"].includes(status)) {
      return status as RouteSegmentStatus;
    }
    return "normal";
  }

  private computedRouteStatus(
    distanceKm: number,
    elapsedSeconds: number,
    impliedSpeedKmh: number
  ): { status: RouteSegmentStatus; reason: string | null } {
    if (elapsedSeconds <= 0) return { status: "suspicious", reason: "non_increasing_gps_time" };
    if (elapsedSeconds > ROUTE_SEGMENT_MAX_GAP_SECONDS) return { status: "gap", reason: "large_time_gap" };
    if (distanceKm > ROUTE_SEGMENT_MAX_DISTANCE_KM) return { status: "gap", reason: "large_distance_gap" };
    if (impliedSpeedKmh > ROUTE_SEGMENT_MAX_SPEED_KMH) return { status: "suspicious", reason: "impossible_speed" };
    return { status: "normal", reason: null };
  }

  private routeSegmentStyle(meta: RouteSegmentMeta): L.PolylineOptions {
    if (meta.status === "gap" || meta.status === "suspicious") {
      return {
        color: ROUTE_LINE_COLOR,
        opacity: 0.58,
        weight: 3,
        dashArray: "2 8",
        lineCap: "round"
      };
    }
    if (meta.status === "raw") {
      return {
        color: ROUTE_LINE_COLOR,
        opacity: 0.72,
        weight: 3,
        dashArray: "7 8",
        lineCap: "round"
      };
    }
    return {
      color: ROUTE_LINE_COLOR,
      opacity: 0.92,
      weight: 4,
      lineCap: "round"
    };
  }

  private routeSegmentLatLngs(previous: RoutePoint, point: RoutePoint): L.LatLngExpression[] {
    const geometry = Array.isArray(point.segment_geometry) ? point.segment_geometry : [];
    const latLngs = geometry
      .map((coordinate) => this.routeGeometryPoint(coordinate))
      .filter((coordinate): coordinate is L.LatLngExpression => coordinate !== null);
    if (latLngs.length >= 2) return latLngs;
    return [
      [Number(previous.lat), Number(previous.lon)],
      [Number(point.lat), Number(point.lon)]
    ];
  }

  private routeGeometryPoint(coordinate: unknown): L.LatLngExpression | null {
    if (!Array.isArray(coordinate) || coordinate.length < 2) return null;
    const lat = Number(coordinate[0]);
    const lon = Number(coordinate[1]);
    return this.validCoordinate(lat, lon) ? [lat, lon] : null;
  }

  private routeSegmentTooltip(meta: RouteSegmentMeta): string {
    const statusLabel = meta.status === "raw" ? "Tramo GPS sin ajuste OSRM" : "Salto o tramo dudoso";
    const reason = this.routeReasonLabel(meta.reason);
    const distance = `${meta.distanceKm.toFixed(2)} km`;
    const minutes = meta.elapsedSeconds > 0 ? `${Math.round(meta.elapsedSeconds / 60)} min` : "sin tiempo valido";
    const speed = `${meta.impliedSpeedKmh.toFixed(1)} km/h`;
    return [statusLabel, reason, distance, minutes, speed].filter(Boolean).join(" · ");
  }

  private routeReasonLabel(reason: string | null): string {
    const labels: Record<string, string> = {
      large_time_gap: "mucho tiempo entre GPS",
      large_distance_gap: "distancia alta entre GPS",
      impossible_speed: "velocidad irreal",
      non_increasing_gps_time: "hora GPS no avanza",
      osrm_budget_deferred: "OSRM pendiente",
      osrm_disabled: "OSRM no configurado",
      osrm_no_match: "sin coincidencia OSRM",
      inside_geofence: "dentro de geocerca",
      route_fallback: "ruta OSRM alternativa"
    };
    return reason ? labels[reason] || reason : "";
  }

  private routeDistanceKm(previous: RoutePoint, point: RoutePoint): number {
    return this.distanceMeters(Number(previous.lat), Number(previous.lon), Number(point.lat), Number(point.lon)) / 1000;
  }

  private routeElapsedSeconds(previous: RoutePoint, point: RoutePoint): number {
    const previousAt = new Date(previous.received_at).getTime();
    const pointAt = new Date(point.received_at).getTime();
    if (Number.isNaN(previousAt) || Number.isNaN(pointAt)) return 0;
    return Math.max((pointAt - previousAt) / 1000, 0);
  }

  private numberOr(value: number | null | undefined, fallback: number): number {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  }

  private async selectDevice(deviceId: string, autoLoadRoute: boolean): Promise<void> {
    const previousDeviceId = this.selectedDeviceId;
    this.selectedDeviceId = deviceId;
    if (this.deviceSearchInput) {
      const device = this.vehicles.find((item) => item.id === deviceId);
      if (device) this.deviceSearchInput.value = this.vehicleLabel(device);
    }
    const item = this.latest.find((entry) => entry.vehicle.id === deviceId);
    if (item && this.validCoordinate(item.lat, item.lon)) {
      this.focusSelectedDevice(item);
    }
    this.drawMarkers(false);
    this.hideDeviceSuggestions();
    this.renderFocusPanel();
    this.renderMiningPanel();
    void this.lookupSelectedMiningConcession(item);
    if (autoLoadRoute) {
      await this.loadRoute();
      this.focusSelectedDevice(this.selectedTelemetry());
    } else if (previousDeviceId !== deviceId && this.currentRoute?.vehicle.id !== deviceId) {
      this.routeLayer.clearLayers();
      this.currentRoute = undefined;
      this.setRouteSummary("Selecciona recorrido para cargar la ruta de esta unidad.");
    }
  }

  private focusSelectedDevice(item?: LatestLocation): void {
    if (!item || !this.map || !this.validCoordinate(item.lat, item.lon)) return;
    this.map.setView([Number(item.lat), Number(item.lon)], 18, { animate: true });
  }

  private renderFocusPanel(): void {
    if (!this.focusElement) return;
    const item = this.selectedTelemetry();
    const devicePayload = item?.vehicle ?? this.vehicles.find((entry) => entry.id === this.selectedDeviceId);
    if (!devicePayload) {
      this.focusElement.replaceChildren(
        createElement("div", { className: "rb-map-focus-empty" }, "Selecciona un vehículo o dron para ver su información.")
      );
      return;
    }
    const device = item ? FleetDeviceModel.fromTelemetry(item) : new FleetDeviceModel(devicePayload);
    const geofenceNames = item && this.validCoordinate(item.lat, item.lon)
      ? this.geofencesContainingPoint(Number(item.lat), Number(item.lon)).map((geofence) => geofence.name || "Geocerca")
      : [];
    const speed = item?.speed == null ? "--" : `${Number(item.speed).toFixed(1)} km/h`;
    const heading = item?.heading == null ? "--" : `${Number(item.heading).toFixed(0)} deg`;

    this.focusElement.replaceChildren(
      createElement("div", { className: "rb-map-focus-head" }, [
        this.renderVehicleIdentity(devicePayload, device, item)
      ]),
      createElement("div", { className: "rb-map-focus-stats" }, [
        this.focusStat(device.isDrone ? "Piloto" : "Chofer", device.driverLabel),
        this.focusStat("Velocidad", speed),
        this.focusStat("Rumbo", heading),
        this.focusStat("Reporte", item ? this.formatDate(item.received_at) : "--")
      ]),
      this.renderCameraLinks(device.cameras),
      createElement("div", { className: "rb-map-zone-chip-list" },
        geofenceNames.length
          ? geofenceNames.map((name) => createElement("span", { className: "rb-map-zone-chip" }, name))
          : [createElement("span", { className: "rb-map-zone-chip is-muted" }, "Fuera de geocercas internas")]
      )
    );
  }

  private renderVehicleIdentity(vehicle: FleetVehicle, device: FleetDeviceModel, item?: LatestLocation): HTMLElement {
    const gpsStatus = item && this.validCoordinate(item.lat, item.lon) ? "Activo" : "Desactivado";
    return createElement("div", { className: "rb-map-focus-details" }, [
      this.focusDetail("Tipo", device.typeLabel, "Marca", vehicle.brand || "--"),
      this.focusDetail("Placa", device.title, "Modelo", vehicle.model || "--"),
      this.focusDetail("Año", vehicle.year ? String(vehicle.year) : "--"),
      this.focusDetail("GPS", gpsStatus)
    ]);
  }

  private focusDetail(leftLabel: string, leftValue: string, rightLabel?: string, rightValue?: string): HTMLElement {
    return createElement("div", { className: "rb-map-focus-detail-row" }, [
      createElement("span", {}, [
        createElement("em", {}, `${leftLabel}:`),
        " ",
        createElement("strong", {}, leftValue)
      ]),
      rightLabel ? createElement("span", {}, [
        createElement("em", {}, `${rightLabel}:`),
        " ",
        createElement("strong", {}, rightValue || "--")
      ]) : ""
    ]);
  }

  private renderCameraLinks(cameras: FleetCameraLink[]): HTMLElement {
    if (!cameras.length) {
      return createElement("div", { className: "rb-map-camera-links" }, [
        createElement("span", { className: "rb-map-mini-kicker" }, "Cámaras"),
        createElement("p", { className: "rb-muted mb-0" }, "Sin cámaras asociadas.")
      ]);
    }
    return createElement("div", { className: "rb-map-camera-links" }, [
      createElement("span", { className: "rb-map-mini-kicker" }, "Cámaras asociadas"),
      ...cameras.map((camera) => createElement("a", {
        className: `rb-map-camera-pill ${camera.online ? "is-online" : ""}`,
        attrs: { href: `/camaras/?camera=${encodeURIComponent(camera.id)}` }
      }, [
        createElement("strong", {}, camera.name),
        createElement("small", {}, [camera.online ? "en vivo" : "sin video", camera.path || ""].filter(Boolean).join(" · "))
      ]))
    ]);
  }

  private focusStat(label: string, value: string): HTMLElement {
    return createElement("article", { className: "rb-map-focus-stat" }, [
      createElement("span", {}, label),
      createElement("strong", {}, value)
    ]);
  }

  private async lookupSelectedMiningConcession(item?: LatestLocation): Promise<void> {
    if (!item || !this.validCoordinate(item.lat, item.lon)) {
      this.selectedMiningLookupKey = "";
      this.selectedMiningConcession = null;
      this.renderMiningPanel();
      return;
    }
    const lat = Number(item.lat);
    const lon = Number(item.lon);
    const lookupKey = `${item.vehicle.id}:${lat.toFixed(5)}:${lon.toFixed(5)}`;
    if (lookupKey === this.selectedMiningLookupKey) return;
    this.selectedMiningLookupKey = lookupKey;
    this.renderMiningPanel("Consultando ARCOM...");
    try {
      const payload = await this.api.get<MiningLookupPayload>(
        `/api/v1/fleet/geointel/arcom/concession-lookup/?lat=${lat}&lon=${lon}`,
        { silent: true }
      );
      if (this.selectedMiningLookupKey !== lookupKey) return;
      this.selectedMiningConcession = payload.found ? payload.concession : null;
    } catch {
      if (this.selectedMiningLookupKey !== lookupKey) return;
      this.selectedMiningConcession = null;
    }
    this.renderMiningPanel();
  }

  private renderMiningPanel(status = ""): void {
    if (!this.miningElement) return;
    const item = this.selectedTelemetry();
    if (!item) {
      this.miningElement.replaceChildren(
        createElement("section", { className: "rb-mining-card" }, [
          createElement("span", { className: "rb-map-mini-kicker" }, "Zona minera"),
          createElement("p", { className: "rb-muted mb-0" }, "Selecciona una unidad para consultar ARCOM.")
        ])
      );
      return;
    }
    if (status) {
      this.miningElement.replaceChildren(
        createElement("section", { className: "rb-mining-card" }, [
          createElement("span", { className: "rb-map-mini-kicker" }, "Zona minera"),
          createElement("p", { className: "rb-muted mb-0" }, status)
        ])
      );
      return;
    }
    const concession = this.selectedMiningConcession;
    if (!concession) {
      this.miningElement.replaceChildren(
        createElement("section", { className: "rb-mining-card" }, [
          createElement("span", { className: "rb-map-mini-kicker" }, "Zona minera"),
          createElement("strong", {}, "Sin concesion detectada"),
          createElement("p", { className: "rb-muted mb-0" }, "La posición actual no cruza una concesión ARCOM disponible.")
        ])
      );
      return;
    }
    this.miningElement.replaceChildren(
      createElement("section", { className: "rb-mining-card is-detected" }, [
        createElement("span", { className: "rb-map-mini-kicker" }, "Concesion minera detectada"),
        createElement("strong", {}, concession.nombre_concesion || "--"),
        createElement("div", { className: "rb-mining-grid" }, [
          this.miningItem("Código", concession.codigo_catastral || "--"),
          this.miningItem("Estado", concession.estado_actual || "--"),
          this.miningItem("Titular", concession.empresa || "--"),
          this.miningItem("Mineral", concession.tipo_mineral || "--")
        ])
      ])
    );
  }

  private miningItem(label: string, value: string): HTMLElement {
    return createElement("article", { className: "rb-mining-item" }, [
      createElement("span", {}, label),
      createElement("strong", {}, value)
    ]);
  }

  private selectedTelemetry(): LatestLocation | undefined {
    return this.latest.find((entry) => entry.vehicle.id === this.selectedDeviceId);
  }

  private vehicleLabel(vehicle: FleetVehicle): string {
    return new FleetDeviceModel(vehicle).label;
  }

  private dedupeVehicles(vehicles: FleetVehicle[]): FleetVehicle[] {
    const grouped = new Map<string, FleetVehicle>();
    for (const vehicle of vehicles) {
      const key = this.fleetKey(vehicle);
      if (!grouped.has(key)) {
        grouped.set(key, vehicle);
      }
    }
    return Array.from(grouped.values()).sort((left, right) => this.vehicleLabel(left).localeCompare(this.vehicleLabel(right)));
  }

  private fleetKey(vehicle: FleetVehicle): string {
    const raw = String(vehicle.plate || vehicle.name || vehicle.unique_code || vehicle.id).toUpperCase();
    const plateMatch = raw.match(/([A-Z]{2,4})[ -]?([0-9]{3,5})/);
    if (plateMatch) {
      return `${plateMatch[1]}${plateMatch[2]}`;
    }
    return raw.replace(/[^A-Z0-9]/g, "") || vehicle.id;
  }

  private setStatus(value: string): void {
    if (this.statusElement) {
      this.statusElement.textContent = value;
    }
  }

  private setRouteSummary(value: string): void {
    if (this.summaryElement) {
      this.summaryElement.textContent = value;
    }
  }

  private freshnessLabel(value: LatestLocation["freshness"]): string {
    return value === "online" ? "en línea" : "sin telemetría (+1h)";
  }

  private markerColor(value: LatestLocation["freshness"]): string {
    return value === "online" ? "#22c55e" : "#ef4444";
  }

  private geofenceColor(item: GeofenceItem, fallback: string): string {
    const color = String(item.color || item.geometry?.color || item.geometry?.style?.color || item.geometry?.style?.fillColor || "").trim();
    return /^#[0-9a-f]{3}([0-9a-f]{3})?$/i.test(color) ? color.toLowerCase() : fallback;
  }

  private geofenceTypeLabel(item: GeofenceItem): string {
    return String(item.geofence_type || item.type || "").toLowerCase() === "circle" ? "círculo" : "polígono";
  }

  private geofenceShapeSummary(item: GeofenceItem): string {
    if (String(item.geofence_type || item.type || "").toLowerCase() === "circle") {
      const circle = this.circleData(item);
      return circle ? `${Math.round(circle.radius)} m` : "sin radio";
    }
    return `${this.geofencePoints(item).length} puntos`;
  }

  private geofencesContainingPoint(lat: number, lon: number): GeofenceItem[] {
    return this.geofences.filter((geofence) => {
      if (geofence.active === false) return false;
      const type = String(geofence.geofence_type || geofence.type || "").toLowerCase();
      if (type === "circle") {
        const circle = this.circleData(geofence);
        return Boolean(circle && this.distanceMeters(lat, lon, circle.lat, circle.lon) <= circle.radius);
      }
      const points = this.geofencePoints(geofence);
      return points.length >= 3 && this.pointInPolygon(lat, lon, points);
    });
  }

  private pointInPolygon(lat: number, lon: number, points: number[][]): boolean {
    let inside = false;
    let previous = points[points.length - 1];
    for (const current of points) {
      const currentLon = Number(current[1]);
      const currentLat = Number(current[0]);
      const previousLon = Number(previous[1]);
      const previousLat = Number(previous[0]);
      const intersects = (currentLat > lat) !== (previousLat > lat)
        && lon < ((previousLon - currentLon) * (lat - currentLat)) / ((previousLat - currentLat) || 1e-12) + currentLon;
      if (intersects) inside = !inside;
      previous = current;
    }
    return inside;
  }

  private distanceMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const toRad = (value: number) => value * Math.PI / 180;
    const radiusMeters = 6371008.8;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2
      + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * radiusMeters * Math.asin(Math.sqrt(a));
  }

  private circleData(item: GeofenceItem): { lat: number; lon: number; radius: number } | null {
    const center = item.geometry?.center ?? {};
    const lat = Number(center.lat);
    const lon = Number(center.lon ?? center.lng);
    const radius = Number(item.geometry?.radius_m ?? item.geometry?.radius);
    if (!this.validCoordinate(lat, lon) || !Number.isFinite(radius) || radius <= 0) return null;
    return { lat, lon, radius };
  }

  private geofencePoints(item: GeofenceItem): number[][] {
    let coordinates = item.geometry?.coordinates;
    const coordinateOrder = String(item.geometry?.coordinate_order || "").toLowerCase();
    if (
      String(item.geometry?.type || "").toLowerCase() === "polygon"
      && coordinateOrder !== "latlon"
      && Array.isArray(coordinates)
      && coordinates.length
      && Array.isArray(coordinates[0])
      && Array.isArray(coordinates[0][0])
    ) {
      coordinates = coordinates[0];
    }
    if (!Array.isArray(coordinates)) return [];
    return coordinates.map((point) => {
      if (Array.isArray(point) && point.length >= 2) {
        const first = Number(point[0]);
        const second = Number(point[1]);
        return coordinateOrder && coordinateOrder !== "latlon" ? [second, first] : [first, second];
      }
      if (point && typeof point === "object") {
        const typed = point as { lat?: unknown; lon?: unknown; lng?: unknown };
        return [Number(typed.lat), Number(typed.lon ?? typed.lng)];
      }
      return [Number.NaN, Number.NaN];
    }).filter(([lat, lon]) => this.validCoordinate(lat, lon));
  }

  private validCoordinate(lat: number | null, lon: number | null): boolean {
    return lat != null && lon != null && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
  }

  private formatDate(value: string): string {
    if (!value) return "--";
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
