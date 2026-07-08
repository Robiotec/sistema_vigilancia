const SIDEBAR_STORAGE_KEY = "robiotec.sidebar.collapsed";

export class AppSidebar {
  constructor(
    private readonly shell: HTMLElement,
    private readonly toggle: HTMLButtonElement | null
  ) {}

  mount(): void {
    if (!this.toggle) return;
    this.applyStoredState();
    this.toggle.addEventListener("click", () => this.toggleState());
  }

  private applyStoredState(): void {
    const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    const collapsed = stored == null ? true : stored === "true";
    this.setCollapsed(collapsed);
  }

  private toggleState(): void {
    this.setCollapsed(!this.shell.classList.contains("is-sidebar-collapsed"));
  }

  private setCollapsed(collapsed: boolean): void {
    this.shell.classList.toggle("is-sidebar-collapsed", collapsed);
    this.toggle?.setAttribute("aria-expanded", String(!collapsed));
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed));
  }
}
