"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Quadrant, type Task } from "@/lib/api";

const QUADRANTS: { id: Quadrant; title: string; hint: string }[] = [
  { id: "do", title: "Do first", hint: "Urgent and important" },
  { id: "schedule", title: "Schedule", hint: "Important, not urgent" },
  { id: "delegate", title: "Delegate", hint: "Urgent, not important" },
  { id: "eliminate", title: "Eliminate", hint: "Neither urgent nor important" },
];

export default function Home() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [status, list] = await Promise.all([api.authStatus(), api.tasks()]);
      setConnected(status.connected);
      setTasks(list);
      setError(null);
    } catch (e) {
      setError(`Can't reach the backend: ${(e as Error).message}`);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function sync() {
    setSyncing(true);
    setMessage(null);
    try {
      const r = await api.sync();
      setMessage(
        `Read ${r.emails_scanned} new email${r.emails_scanned === 1 ? "" : "s"}, ` +
          `found ${r.tasks_created} action point${r.tasks_created === 1 ? "" : "s"}.`,
      );
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  async function update(task: Task, patch: Partial<Pick<Task, "quadrant" | "done">>) {
    try {
      const updated = await api.updateTask(task.id, patch);
      setTasks((prev) =>
        updated.done ? prev.filter((t) => t.id !== task.id) : prev.map((t) => (t.id === task.id ? updated : t)),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function onDrop(e: React.DragEvent, quadrant: Quadrant) {
    e.preventDefault();
    const id = Number(e.dataTransfer.getData("text/plain"));
    const task = tasks.find((t) => t.id === id);
    if (task && task.quadrant !== quadrant) await update(task, { quadrant });
  }

  return (
    <main>
      <header>
        <h1>Email Tracker</h1>
        <div className="actions">
          {connected === false && (
            <a className="button" href={api.loginUrl}>
              Connect Gmail
            </a>
          )}
          {connected && (
            <button onClick={sync} disabled={syncing}>
              {syncing ? "Reading inbox…" : "Sync inbox"}
            </button>
          )}
        </div>
      </header>

      {message && <p className="notice">{message}</p>}
      {error && <p className="notice error">{error}</p>}

      <section className="matrix">
        {QUADRANTS.map((q) => {
          const items = tasks.filter((t) => t.quadrant === q.id);
          return (
            <div
              key={q.id}
              className={`quadrant q-${q.id}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => onDrop(e, q.id)}
            >
              <h2>
                {q.title} <span className="count">{items.length}</span>
              </h2>
              <p className="hint">{q.hint}</p>
              <ul>
                {items.map((t) => (
                  <li
                    key={t.id}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData("text/plain", String(t.id))}
                    title={t.reasoning}
                  >
                    <label>
                      <input type="checkbox" onChange={() => update(t, { done: true })} />
                      <span className="title">{t.title}</span>
                    </label>
                    {t.details && <p className="details">{t.details}</p>}
                    <p className="meta">
                      {t.due_date && <span className="due">Due {t.due_date}</span>}
                      <span>
                        {t.email_subject} · {t.email_sender}
                      </span>
                    </p>
                  </li>
                ))}
                {items.length === 0 && <li className="empty">Nothing here</li>}
              </ul>
            </div>
          );
        })}
      </section>
    </main>
  );
}
