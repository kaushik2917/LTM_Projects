// NEXT_PUBLIC values are embedded by Next.js at build time.
export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8001").replace(/\/$/, "");

export async function getDefense<T>(path: string, signal: AbortSignal): Promise<T> {
  const url = `${API_BASE}/api/defense/${path}`;
  let response: Response;
  try {
    response = await fetch(url, { signal, cache: "no-store" });
  } catch (error) {
    throw new Error(`${url}: ${error instanceof Error ? error.message : String(error)}`);
  }
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); }
  catch { throw new Error(`${url}: HTTP ${response.status}: ${text || "Empty API response"}`); }
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}: ${typeof data.detail === "string" ? data.detail : JSON.stringify(data)}`);
  return data as T;
}
