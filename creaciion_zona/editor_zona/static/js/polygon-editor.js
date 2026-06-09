import { clamp, createSvgElement } from "./utils.js";

export class PolygonEditor {
  constructor({
    video,
    overlay,
    stage,
    output,
    pointCount,
    videoSize,
    stateBadge,
    copyFeedback,
    videoName,
  }) {
    this.video = video;
    this.overlay = overlay;
    this.stage = stage;
    this.output = output;
    this.pointCount = pointCount;
    this.videoSize = videoSize;
    this.stateBadge = stateBadge;
    this.copyFeedback = copyFeedback;
    this.videoName = videoName;
    this.state = {
      points: [],
      closed: false,
      hoverPoint: null,
    };
  }

  initialize() {
    this.refreshUi();
    this.renderOverlay();
  }

  syncVideoMetadata() {
    if (!this.video.videoWidth || !this.video.videoHeight) {
      return;
    }

    this.stage.style.aspectRatio = `${this.video.videoWidth} / ${this.video.videoHeight}`;
    this.videoSize.textContent = `Resolucion: ${this.video.videoWidth} x ${this.video.videoHeight}`;
    this.renderOverlay();
    this.refreshUi();
  }

  addPointFromEvent(event) {
    if (!this.video.videoWidth || !this.video.videoHeight || this.state.closed) {
      return;
    }

    this.state.points.push(this.eventToPoint(event));
    this.state.hoverPoint = null;
    this.setFeedback("Punto agregado al poligono.");
    this.commit();
  }

  updateHoverFromEvent(event) {
    if (!this.state.points.length || this.state.closed) {
      this.clearHover();
      return;
    }

    this.state.hoverPoint = this.eventToPoint(event);
    this.renderOverlay();
  }

  clearHover() {
    if (this.state.hoverPoint === null) {
      return;
    }

    this.state.hoverPoint = null;
    this.renderOverlay();
  }

  closePolygon() {
    if (this.state.points.length < 3) {
      this.setFeedback("Necesitas al menos 3 puntos para cerrar el poligono.");
      return;
    }

    this.state.closed = true;
    this.state.hoverPoint = null;
    this.setFeedback("Poligono cerrado correctamente.");
    this.commit();
  }

  undoLastPoint() {
    if (!this.state.points.length) {
      return;
    }

    if (this.state.closed) {
      this.state.closed = false;
    }

    this.state.points.pop();
    this.setFeedback("Ultimo punto eliminado.");
    this.commit();
  }

  clearPolygon() {
    this.state.points = [];
    this.state.closed = false;
    this.state.hoverPoint = null;
    this.setFeedback("Poligono limpiado.");
    this.commit();
  }

  async copyJson() {
    try {
      await navigator.clipboard.writeText(this.output.value);
      this.setFeedback("JSON copiado al portapapeles.");
    } catch (error) {
      this.output.select();
      this.output.setSelectionRange(0, this.output.value.length);
      this.setFeedback("No se pudo usar el portapapeles automatico. El JSON quedo seleccionado.");
    }
  }

  refreshUi() {
    this.output.value = JSON.stringify(this.buildPayload(), null, 2);
    this.pointCount.textContent = `Puntos: ${this.state.points.length}`;
    this.updateBadge();
  }

  renderOverlay() {
    this.syncOverlayViewport();
    this.overlay.replaceChildren();

    if (!this.state.points.length) {
      return;
    }

    const displayedPoints = this.state.points.map((point) => this.displayPoint(point));
    this.overlay.appendChild(this.createShape(displayedPoints));

    if (!this.state.closed && this.state.hoverPoint !== null) {
      this.overlay.appendChild(this.createHoverGuide(displayedPoints[displayedPoints.length - 1], this.displayPoint(this.state.hoverPoint)));
    }

    displayedPoints.forEach((point, index) => {
      this.overlay.appendChild(this.createPointCircle(point));
      this.overlay.appendChild(this.createPointLabel(point, index));
    });
  }

  commit() {
    this.refreshUi();
    this.renderOverlay();
  }

  buildPayload() {
    return {
      video: {
        file: this.videoName,
        width: this.video.videoWidth || null,
        height: this.video.videoHeight || null,
      },
      polygon_closed: this.state.closed,
      points: this.state.points.map((point, index) => ({
        index: index + 1,
        normalized_x: point.normalized_x,
        normalized_y: point.normalized_y,
        pixel_x: point.pixel_x,
        pixel_y: point.pixel_y,
      })),
    };
  }

  updateBadge() {
    if (this.state.closed) {
      this.stateBadge.textContent = "Poligono cerrado";
      return;
    }

    if (this.state.points.length === 0) {
      this.stateBadge.textContent = "Esperando puntos";
      return;
    }

    this.stateBadge.textContent = "Polilinea en construccion";
  }

  setFeedback(message) {
    this.copyFeedback.textContent = message;
  }

  syncOverlayViewport() {
    const width = Math.max(this.overlay.clientWidth, 1);
    const height = Math.max(this.overlay.clientHeight, 1);
    this.overlay.setAttribute("viewBox", `0 0 ${width} ${height}`);
  }

  eventToPoint(event) {
    const rect = this.overlay.getBoundingClientRect();
    const x = clamp(event.clientX - rect.left, 0, rect.width);
    const y = clamp(event.clientY - rect.top, 0, rect.height);
    const normalizedX = rect.width ? Number((x / rect.width).toFixed(6)) : 0;
    const normalizedY = rect.height ? Number((y / rect.height).toFixed(6)) : 0;

    return {
      normalized_x: normalizedX,
      normalized_y: normalizedY,
      pixel_x: this.video.videoWidth ? Number((normalizedX * this.video.videoWidth).toFixed(2)) : null,
      pixel_y: this.video.videoHeight ? Number((normalizedY * this.video.videoHeight).toFixed(2)) : null,
    };
  }

  displayPoint(point) {
    return {
      x: point.normalized_x * this.overlay.clientWidth,
      y: point.normalized_y * this.overlay.clientHeight,
    };
  }

  createShape(displayedPoints) {
    const pointString = displayedPoints
      .map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`)
      .join(" ");

    const shape = createSvgElement(this.state.closed ? "polygon" : "polyline", {
      points: pointString,
      fill: this.state.closed ? "rgba(255, 159, 67, 0.26)" : "none",
      stroke: "#ff9f43",
      "stroke-width": 4,
      "stroke-linejoin": "round",
      "stroke-linecap": "round",
      "vector-effect": "non-scaling-stroke",
    });

    shape.style.filter = "drop-shadow(0 0 8px rgba(0, 0, 0, 0.85))";
    return shape;
  }

  createHoverGuide(lastPoint, hoverPoint) {
    const guide = createSvgElement("line", {
      x1: lastPoint.x,
      y1: lastPoint.y,
      x2: hoverPoint.x,
      y2: hoverPoint.y,
      stroke: "rgba(46, 196, 182, 0.95)",
      "stroke-width": 3,
      "stroke-dasharray": "8 8",
      "vector-effect": "non-scaling-stroke",
    });

    guide.style.filter = "drop-shadow(0 0 6px rgba(0, 0, 0, 0.85))";
    return guide;
  }

  createPointCircle(point) {
    const circle = createSvgElement("circle", {
      cx: point.x,
      cy: point.y,
      r: 7,
      fill: "#2ec4b6",
      stroke: "#ecf6ff",
      "stroke-width": 3,
    });

    circle.style.filter = "drop-shadow(0 0 6px rgba(0, 0, 0, 0.85))";
    return circle;
  }

  createPointLabel(point, index) {
    const label = createSvgElement("text", {
      x: point.x + 10,
      y: point.y - 10,
      fill: "#ecf6ff",
      "font-size": 14,
      "font-family": "Segoe UI, sans-serif",
      "paint-order": "stroke",
      stroke: "rgba(0, 0, 0, 0.8)",
      "stroke-width": 4,
      "stroke-linejoin": "round",
    });

    label.textContent = String(index + 1);
    return label;
  }
}
