export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { credentials: "same-origin", ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : "The request could not be completed.");
  }
  return response.json();
}

export const percent = (p: number | null | undefined, digits = 0) => p == null ? "—" : `${(p * 100).toFixed(digits)}%`;
export const kickoff = (date: string) => new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos" }).format(new Date(date));
export const readable = (s: string) => s.replaceAll("_", " ");
