export const SVG_NS = "http://www.w3.org/2000/svg";

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function formatTime(seconds) {
  if (!Number.isFinite(seconds)) {
    return "00:00";
  }

  const totalSeconds = Math.max(0, Math.floor(seconds));
  const mins = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const secs = String(totalSeconds % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}

export function createSvgElement(tagName, attributes = {}) {
  const element = document.createElementNS(SVG_NS, tagName);

  Object.entries(attributes).forEach(([key, value]) => {
    element.setAttribute(key, String(value));
  });

  return element;
}
