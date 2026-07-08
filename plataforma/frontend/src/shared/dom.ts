type Child = HTMLElement | string | Array<HTMLElement | string>;

type ElementOptions = {
  className?: string;
  dataset?: Record<string, string>;
  attrs?: Record<string, string>;
  onClick?: (event: MouseEvent) => void;
  onKeyDown?: (event: KeyboardEvent) => void;
  onInput?: (event: Event) => void;
  onChange?: (event: Event) => void;
};

export function createElement<K extends keyof HTMLElementTagNameMap>(
  tagName: K,
  options: ElementOptions = {},
  children: Child = []
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tagName);

  if (options.className) {
    element.className = options.className;
  }
  for (const [key, value] of Object.entries(options.dataset ?? {})) {
    element.dataset[key] = value;
  }
  for (const [key, value] of Object.entries(options.attrs ?? {})) {
    element.setAttribute(key, value);
  }
  if (options.onClick) {
    element.addEventListener("click", (event) => options.onClick?.(event as MouseEvent));
  }
  if (options.onKeyDown) {
    element.addEventListener("keydown", (event) => options.onKeyDown?.(event as KeyboardEvent));
  }
  if (options.onInput) {
    element.addEventListener("input", (event) => options.onInput?.(event));
  }
  if (options.onChange) {
    element.addEventListener("change", (event) => options.onChange?.(event));
  }

  appendChildren(element, children);
  return element;
}

function appendChildren(parent: HTMLElement, children: Child): void {
  const items = Array.isArray(children) ? children : [children];
  for (const child of items) {
    if (Array.isArray(child)) {
      appendChildren(parent, child);
    } else if (typeof child === "string") {
      parent.append(document.createTextNode(child));
    } else {
      parent.append(child);
    }
  }
}
