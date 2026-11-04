// Thin fetch wrapper. All calls go to same-origin /api/* (proxied to the backend by next.config.ts).
export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

const TOKEN_KEY = "udyam.token";

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(t: string | null) {
    try {
      if (t) localStorage.setItem(TOKEN_KEY, t);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* private mode: stay signed-in for this tab only */
    }
  },
};

function messageOf(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string };
    if (d.message) return d.message;
  }
  return fallback;
}

export async function api<T = unknown>(path: string, opts: { method?: string; body?: unknown; form?: FormData; auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method: opts.method ?? (body ? "POST" : "GET"), headers, body, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }
  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail ?? data;
    throw new ApiError(res.status, messageOf(detail, `Request failed (${res.status})`), detail);
  }
  return data as T;
}

export const journeyStore = {
  get(): string | null {
    try {
      return localStorage.getItem("udyam.journey");
    } catch {
      return null;
    }
  },
  set(id: string | null) {
    try {
      if (id) localStorage.setItem("udyam.journey", id);
      else localStorage.removeItem("udyam.journey");
    } catch {
      /* ignore */
    }
  },
};
