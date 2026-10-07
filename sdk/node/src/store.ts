/**
 * Local state for the plug-in: dedupe, opt-outs, delayed queue, daily counters, bundle cache.
 * Everything stays on the client's machine. Same schema as the Python plug-in (sqlite file is
 * interchangeable). SqliteStore uses better-sqlite3; PostgresStore lazily imports the optional peer `pg`.
 */
import { randomUUID } from "node:crypto";
import { chmodSync, existsSync } from "node:fs";

/** Fixed-width UTC timestamp (microsecond digits, like the Python plug-in) so text comparison orders correctly. */
export function iso(moment: Date): string {
  return moment.toISOString().replace("Z", "000Z");
}

export interface SendRow {
  id?: string;
  phone: string;
  event: string;
  template_id: string | null;
  status: string;
  reason?: string | null;
  send_at?: string | null;
  sent_at?: string | null;
  created_at: string;
  name?: string | null;
  extra?: Record<string, string> | null;
  claimed_at?: string | null;
}

export interface StoredSend extends Omit<SendRow, "extra" | "id"> {
  id: string;
  extra: Record<string, string>;
}

export interface CounterRow {
  day: string;
  event: string;
  template_id: string;
  sent: number;
  failed: number;
}

export interface Store {
  getMeta(key: string): Promise<string | null>;
  setMeta(key: string, value: string): Promise<void>;
  deleteMeta(key: string): Promise<void>;
  isOptedOut(phone: string): Promise<boolean>;
  addOptOut(phone: string): Promise<void>;
  hasRecentSend(phone: string, event: string, since: Date): Promise<boolean>;
  insertSend(row: SendRow): Promise<string>;
  claimSend(sendId: string, now: Date): Promise<boolean>;
  finishSend(sendId: string, status: string, reason: string | null, sentAt: Date | null): Promise<void>;
  dueSends(now: Date, limit: number): Promise<StoredSend[]>;
  failStuck(before: Date): Promise<number>;
  bumpCounter(day: string, event: string, templateId: string, sent: number, failed: number): Promise<void>;
  counters(days: readonly string[]): Promise<CounterRow[]>;
  close(): Promise<void>;
}

const SCHEMA: readonly string[] = [
  `CREATE TABLE IF NOT EXISTS sends (
    id TEXT PRIMARY KEY, phone TEXT NOT NULL, event TEXT NOT NULL, template_id TEXT,
    status TEXT NOT NULL, reason TEXT, send_at TEXT, sent_at TEXT, created_at TEXT NOT NULL,
    name TEXT, extra TEXT, claimed_at TEXT)`,
  "CREATE INDEX IF NOT EXISTS sends_dedupe ON sends (phone, event, created_at)",
  "CREATE INDEX IF NOT EXISTS sends_due ON sends (status, send_at)",
  "CREATE TABLE IF NOT EXISTS opt_outs (phone TEXT PRIMARY KEY)",
  `CREATE TABLE IF NOT EXISTS counters (
    day TEXT NOT NULL, event TEXT NOT NULL, template_id TEXT NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, event, template_id))`,
  "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
];

const SEND_COLUMNS = [
  "id", "phone", "event", "template_id", "status", "reason", "send_at", "sent_at", "created_at",
  "name", "extra", "claimed_at",
] as const;
const MAX_REASON_CHARS = 300;

interface RunResult {
  rows: Record<string, unknown>[];
  count: number;
}

/** Shared SQL for both backends; subclasses supply `run` (SQL uses ? placeholders). */
abstract class SqlStore implements Store {
  protected abstract run(sql: string, params: readonly unknown[]): Promise<RunResult>;
  abstract close(): Promise<void>;

  protected async initSchema(): Promise<void> {
    for (const statement of SCHEMA) await this.run(statement, []);
  }

  async getMeta(key: string): Promise<string | null> {
    const { rows } = await this.run("SELECT value FROM meta WHERE key = ?", [key]);
    return rows.length ? String(rows[0]!.value) : null;
  }

  async setMeta(key: string, value: string): Promise<void> {
    await this.run(
      "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
      [key, value],
    );
  }

  async deleteMeta(key: string): Promise<void> {
    await this.run("DELETE FROM meta WHERE key = ?", [key]);
  }

  async isOptedOut(phone: string): Promise<boolean> {
    const { rows } = await this.run("SELECT phone FROM opt_outs WHERE phone = ?", [phone]);
    return rows.length > 0;
  }

  async addOptOut(phone: string): Promise<void> {
    await this.run("INSERT INTO opt_outs (phone) VALUES (?) ON CONFLICT (phone) DO NOTHING", [phone]);
  }

  async hasRecentSend(phone: string, event: string, since: Date): Promise<boolean> {
    const { rows } = await this.run(
      "SELECT id FROM sends WHERE phone = ? AND event = ? AND status IN ('queued', 'sending', 'sent') " +
        "AND created_at >= ? LIMIT 1",
      [phone, event, iso(since)],
    );
    return rows.length > 0;
  }

  async insertSend(row: SendRow): Promise<string> {
    const id = row.id ?? randomUUID();
    const full: Record<string, unknown> = Object.fromEntries(SEND_COLUMNS.map((c) => [c, null]));
    Object.assign(full, row, { id, extra: row.extra && Object.keys(row.extra).length ? JSON.stringify(row.extra) : null });
    const marks = SEND_COLUMNS.map(() => "?").join(", ");
    await this.run(
      `INSERT INTO sends (${SEND_COLUMNS.join(", ")}) VALUES (${marks})`,
      SEND_COLUMNS.map((c) => full[c] ?? null),
    );
    return id;
  }

  /** queued -> sending, atomically; false when someone else already claimed it. */
  async claimSend(sendId: string, now: Date): Promise<boolean> {
    const { count } = await this.run(
      "UPDATE sends SET status = 'sending', claimed_at = ? WHERE id = ? AND status = 'queued'",
      [iso(now), sendId],
    );
    return count === 1;
  }

  async finishSend(sendId: string, status: string, reason: string | null, sentAt: Date | null): Promise<void> {
    await this.run("UPDATE sends SET status = ?, reason = ?, sent_at = ? WHERE id = ?", [
      status,
      reason ? reason.slice(0, MAX_REASON_CHARS) : null,
      sentAt ? iso(sentAt) : null,
      sendId,
    ]);
  }

  async dueSends(now: Date, limit: number): Promise<StoredSend[]> {
    const { rows } = await this.run(
      "SELECT * FROM sends WHERE status = 'queued' AND send_at <= ? ORDER BY send_at LIMIT ?",
      [iso(now), limit],
    );
    return rows.map((r) => ({
      ...(r as unknown as StoredSend),
      extra: typeof r.extra === "string" && r.extra ? (JSON.parse(r.extra) as Record<string, string>) : {},
    }));
  }

  /** 'sending' rows left by a crash are failed, never re-sent: Meta may already have delivered them. */
  async failStuck(before: Date): Promise<number> {
    const { count } = await this.run(
      "UPDATE sends SET status = 'failed', reason = 'interrupted' WHERE status = 'sending' AND claimed_at < ?",
      [iso(before)],
    );
    return count;
  }

  async bumpCounter(day: string, event: string, templateId: string, sent: number, failed: number): Promise<void> {
    await this.run(
      "INSERT INTO counters (day, event, template_id, sent, failed) VALUES (?, ?, ?, ?, ?) " +
        "ON CONFLICT (day, event, template_id) DO UPDATE SET sent = counters.sent + excluded.sent, " +
        "failed = counters.failed + excluded.failed",
      [day, event, templateId, sent, failed],
    );
  }

  async counters(days: readonly string[]): Promise<CounterRow[]> {
    if (!days.length) return [];
    const marks = days.map(() => "?").join(", ");
    const { rows } = await this.run(
      `SELECT day, event, template_id, sent, failed FROM counters WHERE day IN (${marks}) ORDER BY day, event, template_id`,
      days,
    );
    return rows.map((r) => ({
      day: String(r.day), event: String(r.event), template_id: String(r.template_id),
      sent: Number(r.sent), failed: Number(r.failed),
    }));
  }
}

interface SqliteStatement {
  reader: boolean;
  all(...params: unknown[]): Record<string, unknown>[];
  run(...params: unknown[]): { changes: number };
}
interface SqliteDb {
  prepare(sql: string): SqliteStatement;
  pragma(source: string): unknown;
  close(): void;
}

export class SqliteStore extends SqlStore {
  private constructor(private readonly db: SqliteDb) {
    super();
  }

  static async open(path = "aira_private_send.db"): Promise<SqliteStore> {
    const mod = (await import("better-sqlite3")) as unknown as { default: new (p: string) => SqliteDb };
    const isNewFile = path !== ":memory:" && path !== "" && !existsSync(path);
    const db = new mod.default(path);
    // the db holds customer phone numbers; set before the WAL files copy its mode
    if (isNewFile && process.platform !== "win32") chmodSync(path, 0o600);
    db.pragma("busy_timeout = 30000");
    if (path !== ":memory:") db.pragma("journal_mode = WAL");
    const store = new SqliteStore(db);
    await store.initSchema();
    return store;
  }

  protected async run(sql: string, params: readonly unknown[]): Promise<RunResult> {
    const stmt = this.db.prepare(sql);
    if (stmt.reader) return { rows: stmt.all(...params), count: 0 };
    return { rows: [], count: stmt.run(...params).changes };
  }

  async close(): Promise<void> {
    this.db.close();
  }
}

interface PgPool {
  query(sql: string, params: unknown[]): Promise<{ rows: Record<string, unknown>[]; rowCount: number | null }>;
  end(): Promise<void>;
}

function toPgPlaceholders(sql: string): string {
  let n = 0;
  return sql.replace(/\?/g, () => `$${++n}`);
}

export class PostgresStore extends SqlStore {
  private constructor(private readonly pool: PgPool) {
    super();
  }

  static async open(connectionString: string): Promise<PostgresStore> {
    let mod: { default?: { Pool: new (o: object) => PgPool }; Pool?: new (o: object) => PgPool };
    try {
      mod = (await import("pg")) as unknown as typeof mod;
    } catch {
      throw new Error("PostgresStore needs the optional peer dependency: npm install pg");
    }
    const Pool = mod.Pool ?? mod.default?.Pool;
    if (!Pool) throw new Error("could not load pg.Pool");
    const store = new PostgresStore(new Pool({ connectionString }));
    await store.initSchema();
    return store;
  }

  protected async run(sql: string, params: readonly unknown[]): Promise<RunResult> {
    const res = await this.pool.query(toPgPlaceholders(sql), [...params]);
    return { rows: res.rows, count: res.rowCount ?? 0 };
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}

const SQLITE_URL_PREFIX = "sqlite:///";

/** 'sqlite:./file.db', 'sqlite:///file.db', 'sqlite:///:memory:', 'postgresql://...', or a Store. */
export async function openStore(spec: string | Store): Promise<Store> {
  if (typeof spec !== "string") return spec;
  if (spec.startsWith(SQLITE_URL_PREFIX)) return SqliteStore.open(spec.slice(SQLITE_URL_PREFIX.length) || undefined);
  if (spec.startsWith("sqlite:")) return SqliteStore.open(spec.slice("sqlite:".length) || undefined);
  if (spec.startsWith("postgres://") || spec.startsWith("postgresql://")) return PostgresStore.open(spec);
  throw new Error("store must be a sqlite: or postgresql:// URL, or a Store object");
}
