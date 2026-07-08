type ApiClientOptions = {
  baseUrl?: string;
  onError?: (message: string) => void;
};

type RequestOptions = RequestInit & {
  silent?: boolean;
};

export class ApiClient {
  private readonly baseUrl: string;
  private readonly onError?: (message: string) => void;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
    this.onError = options.onError;
  }

  async get<T>(url: string, options: RequestOptions = {}): Promise<T> {
    return this.request<T>(url, { ...options, method: "GET" });
  }

  async post<T>(url: string, body: unknown, options: RequestOptions = {}): Promise<T> {
    return this.request<T>(url, {
      ...options,
      method: "POST",
      body: JSON.stringify(body)
    });
  }

  async put<T>(url: string, body: unknown, options: RequestOptions = {}): Promise<T> {
    return this.request<T>(url, {
      ...options,
      method: "PUT",
      body: JSON.stringify(body)
    });
  }

  async patch<T>(url: string, body: unknown, options: RequestOptions = {}): Promise<T> {
    return this.request<T>(url, {
      ...options,
      method: "PATCH",
      body: JSON.stringify(body)
    });
  }

  async delete<T>(url: string, options: RequestOptions = {}): Promise<T> {
    return this.request<T>(url, { ...options, method: "DELETE" });
  }

  private async request<T>(url: string, options: RequestOptions): Promise<T> {
    const response = await fetch(`${this.baseUrl}${url}`, {
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": this.csrfToken(),
        ...(options.headers ?? {})
      },
      ...options
    });

    if (!response.ok) {
      const message = await this.errorMessage(response);
      if (!options.silent) {
        this.onError?.(message);
      }
      throw new Error(message);
    }

    if (response.status === 204) {
      return undefined as T;
    }
    return response.json() as Promise<T>;
  }

  private csrfToken(): string {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  private async errorMessage(response: Response): Promise<string> {
    try {
      const payload = await response.json();
      return payload.detail ?? payload.error ?? `Error ${response.status}`;
    } catch {
      return `Error ${response.status}`;
    }
  }
}
