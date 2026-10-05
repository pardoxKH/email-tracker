export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Quadrant = "do" | "schedule" | "delegate" | "eliminate";

export interface Task {
  id: number;
  email_id: string;
  email_subject: string;
  email_sender: string;
  title: string;
  details: string;
  due_date: string | null;
  quadrant: Quadrant;
  reasoning: string;
  done: boolean;
  created_at: string;
}

export interface SyncResult {
  emails_scanned: number;
  emails_skipped: number;
  tasks_created: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  authStatus: () => request<{ connected: boolean }>("/auth/status"),
  loginUrl: `${API_URL}/auth/login`,
  logout: () => request<{ connected: boolean }>("/auth/logout", { method: "POST" }),
  sync: () => request<SyncResult>("/sync", { method: "POST" }),
  tasks: () => request<Task[]>("/tasks"),
  updateTask: (id: number, patch: Partial<Pick<Task, "quadrant" | "done">>) =>
    request<Task>(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteTask: (id: number) => request<void>(`/tasks/${id}`, { method: "DELETE" }),
};
