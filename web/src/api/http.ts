export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";
const REQUEST_TIMEOUT_MS = 15000;

let token: string | null =
  typeof window !== "undefined" ? window.localStorage.getItem("tg_anki_token") : null;

export const setToken = (value: string) => {
  token = value;
  if (typeof window !== "undefined") {
    window.localStorage.setItem("tg_anki_token", value);
  }
};

export const getToken = () => token;

const authHeaders = () => (token ? { Authorization: `Bearer ${token}` } : {});

export async function request<T>(
  path: string,
  options: RequestInit & { fallbackError?: string } = {}
): Promise<T> {
  const { fallbackError = "Request failed", ...init } = options;
  const headers = { ...authHeaders(), ...(init.headers || {}) } as Record<string, string>;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const abortListener = () => controller.abort();
  init.signal?.addEventListener("abort", abortListener, { once: true });

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("Request timeout. Check API domain/port routing in Dokploy.");
    }
    throw err;
  } finally {
    window.clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abortListener);
  }

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || fallbackError);
  }
  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  return (await res.text()) as T;
}

export const buildApiUrl = (path: string) => `${API_BASE_URL}${path}`;
