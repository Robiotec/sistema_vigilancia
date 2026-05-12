export function byId(id) {
  return document.getElementById(id);
}

export function fieldValue(id) {
  const element = byId(id);
  return element ? String(element.value || "").trim() : "";
}

export function fieldRawValue(id) {
  const element = byId(id);
  return element ? String(element.value || "") : "";
}

export function closest(target, selector) {
  return target && typeof target.closest === "function" ? target.closest(selector) : null;
}
