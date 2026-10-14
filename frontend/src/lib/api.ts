const TOKEN_KEY = "locklens_token";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function apiUrl(path: string) {
  return path.startsWith("/") ? `${API_BASE_URL}${path}` : `${API_BASE_URL}/${path}`;
}

export function getToken(): string | null { return localStorage.getItem(TOKEN_KEY); }
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(options.headers as any) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(apiUrl(path), { ...options, headers });
  if (res.status === 401) { setToken(null); if (location.pathname !== "/login") location.href = "/login"; throw new ApiError(401, "unauthorized"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { const body = await res.json(); detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body); } catch {}
    throw new ApiError(res.status, detail);
  }
  // A successful DELETE (and a few infrastructure endpoints) may deliberately
  // return no body. Avoid turning that into a misleading JSON parsing error.
  if (res.status === 204 || res.headers.get("content-length") === "0") return undefined as T;
  return res.json();
}

export function downloadUrl(path: string) { return apiUrl(path); }

export async function downloadFile(path: string, filename: string) {
  const token = getToken();
  const res = await fetch(apiUrl(path), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new ApiError(res.status, "export failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  // Let the browser start the download before releasing the object URL.
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
