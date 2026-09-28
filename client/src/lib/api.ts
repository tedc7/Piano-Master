// API client (arch §4): the device id, attempts through a small local outbox, and client logs.
// The outbox keeps finished attempts through a Wi-Fi drop and sends them when the piano server
// is reachable again (§2.1). iPadOS may clear local storage when space is low; the device then
// registers again as a new device (§5), and practice never waits on the network.

const API = "/api";
const DEVICE_KEY = "pm.device.v1";
const OUTBOX_KEY = "pm.outbox.v1";
const OUTBOX_MAX = 200;
export const CLIENT_VERSION = "0.3.0";

function read<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage full or blocked */ }
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

async function send(path: string, method: string, body: unknown): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 10000);
  try {
    return await fetch(API + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

interface LogEntry { time: string; level: "info" | "warning" | "error"; message: string; context?: unknown }

class ApiClient {
  readonly deviceId: string;
  pending = 0;                         // attempts waiting in the outbox
  online: boolean | null = null;       // null until the first request
  private flushing = false;
  private logs: LogEntry[] = [];
  private logTimer = 0;
  private listeners = new Set<() => void>();

  constructor() {
    let id = read<string | null>(DEVICE_KEY, null);
    if (!id) {
      id = newId();
      write(DEVICE_KEY, id);
    }
    this.deviceId = id;
    this.pending = read<unknown[]>(OUTBOX_KEY, []).length;
  }

  onChange(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private changed(): void {
    for (const fn of this.listeners) fn();
  }

  /** Register (or refresh) this device, then send anything left in the outbox. */
  async start(): Promise<void> {
    try {
      const r = await send(`/devices/${this.deviceId}`, "PUT", { userAgent: navigator.userAgent, clientVersion: CLIENT_VERSION });
      this.online = r.ok;
    } catch {
      this.online = false;
    }
    this.changed();
    window.addEventListener("online", () => void this.flush());
    setInterval(() => void this.flush(), 30000);
    await this.flush();
  }

  /** Queue an attempt and try to send it now. Attempt ids make resends harmless. */
  saveAttempt(attempt: object): void {
    const box = read<object[]>(OUTBOX_KEY, []);
    box.push({ ...attempt, deviceId: this.deviceId, clientVersion: CLIENT_VERSION });
    // keep the newest if the server has been away a long time
    write(OUTBOX_KEY, box.slice(-OUTBOX_MAX));
    this.pending = Math.min(box.length, OUTBOX_MAX);
    this.changed();
    void this.flush();
  }

  async flush(): Promise<void> {
    if (this.flushing) return;
    this.flushing = true;
    try {
      for (;;) {
        const box = read<{ id: string }[]>(OUTBOX_KEY, []);
        if (!box.length) break;
        let r: Response;
        try {
          r = await send("/attempts", "POST", box[0]);
        } catch {
          this.online = false;
          break;
        }
        this.online = true;
        // 2xx: stored; 4xx: the server will never take it (log it and drop it); 5xx: retry later
        if (r.status >= 500) break;
        if (!r.ok) this.log("error", `attempt rejected: HTTP ${r.status}`, { id: box[0].id, body: (await r.text()).slice(0, 500) });
        const rest = read<{ id: string }[]>(OUTBOX_KEY, []).filter((a) => a.id !== box[0].id);
        write(OUTBOX_KEY, rest);
        this.pending = rest.length;
      }
    } finally {
      this.flushing = false;
      this.changed();
    }
  }

  /** Client events and errors for the parent's "Recent problems" list (§11.3); sent in batches. */
  log(level: LogEntry["level"], message: string, context?: unknown): void {
    this.logs.push({ time: new Date().toISOString(), level, message, context });
    if (this.logs.length > 100) this.logs.shift();
    clearTimeout(this.logTimer);
    this.logTimer = window.setTimeout(() => void this.sendLogs(), 2000);
  }

  private async sendLogs(): Promise<void> {
    if (!this.logs.length) return;
    const batch = this.logs.splice(0);
    try {
      const r = await send("/logs", "POST", { deviceId: this.deviceId, entries: batch });
      if (!r.ok && r.status >= 500) this.logs.unshift(...batch);
    } catch {
      this.logs.unshift(...batch);
    }
  }
}

export const api = new ApiClient();
