export type FleetDeviceKind = "vehicle" | "drone";

export type FleetCameraLink = {
  id: string;
  name: string;
  camera_type?: string;
  inference_type?: string;
  path?: string;
  online?: boolean;
  viewer_url?: string;
  whep_url?: string;
};

export type FleetDevicePayload = {
  id: string;
  company_id?: string;
  name: string;
  plate: string | null;
  unique_code: string | null;
  driver_name: string | null;
  vehicle_type?: string | null;
  vehicle_subtype: string | null;
  brand?: string | null;
  model?: string | null;
  year?: number | null;
  active: boolean;
  cameras?: FleetCameraLink[];
};

export type FleetTelemetryPayload = {
  kind: FleetDeviceKind;
  vehicle: FleetDevicePayload;
  lat: number | null;
  lon: number | null;
  speed: number | null;
  heading: number | null;
  received_at: string;
  freshness: "online" | "stale";
};

export class FleetDeviceModel {
  constructor(
    readonly payload: FleetDevicePayload,
    readonly kind: FleetDeviceKind = payload.vehicle_type === "dron" ? "drone" : "vehicle"
  ) {}

  static fromTelemetry(item: FleetTelemetryPayload): FleetDeviceModel {
    return new FleetDeviceModel(item.vehicle, item.kind);
  }

  get id(): string {
    return this.payload.id;
  }

  get isDrone(): boolean {
    return this.kind === "drone";
  }

  get label(): string {
    if (this.isDrone) {
      return this.payload.name || this.payload.unique_code || this.payload.id;
    }
    return this.payload.plate || this.payload.unique_code || this.payload.name || this.payload.id;
  }

  get title(): string {
    return this.isDrone ? `Dron ${this.label}` : this.label;
  }

  get typeLabel(): string {
    if (this.isDrone) return "Dron";
    return this.payload.vehicle_subtype || this.payload.vehicle_type || "Vehículo";
  }

  get routeSegment(): "vehicles" | "drones" {
    return this.isDrone ? "drones" : "vehicles";
  }

  get cameras(): FleetCameraLink[] {
    return this.payload.cameras ?? [];
  }

  get hasTelemetryOnly(): boolean {
    return this.cameras.length === 0;
  }

  get driverLabel(): string {
    return this.payload.driver_name || (this.isDrone ? "Piloto no asignado" : "Chofer no asignado");
  }

  capabilityLabel(): string {
    const capabilities = ["telemetría"];
    if (this.cameras.length) capabilities.push(`${this.cameras.length} camara${this.cameras.length === 1 ? "" : "s"}`);
    return capabilities.join(" + ");
  }
}
