const API = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/$/, "");

export type Row = Record<string, unknown>;

export async function request(path: string, options?: RequestInit): Promise<any> {
  try {
    const response = await fetch(`${API}${path}`, options);
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(body?.detail ?? `API respondeu com HTTP ${response.status}`);
    return body;
  } catch (error) {
    if (error instanceof TypeError) throw new Error(`Não foi possível conectar à API em ${API}.`);
    throw error;
  }
}
