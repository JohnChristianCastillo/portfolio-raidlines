/**
 * The shape of the backend's data API, and the calls that reach it.
 *
 * These types mirror what backend/app/routers/api.py returns. They are hand-written
 * rather than generated because there are four endpoints and one of them does all
 * the work; a generator would be more moving parts than it saves.
 */

export interface Spell {
  id: number;
  name: string;
  short: string;
  icon: string;
  onByDefault: boolean;
}

export interface SpellGroup {
  key: string;
  label: string;
  color: string;
  spells: Spell[];
}

export interface Spec {
  key: string;
  label: string;
  groups: SpellGroup[];
}

export interface Difficulty {
  id: number;
  name: string;
  short: string;
}

export interface Meta {
  /** false means the backend is replaying recorded fixtures, not live rankings. */
  live: boolean;
  topN: number;
  difficulties: Difficulty[];
  specs: Spec[];
}

export interface Encounter {
  id: number;
  name: string;
}

export interface Zone {
  id: number;
  name: string;
  expansion: string;
  frozen: boolean;
  encounters: Encounter[];
}

export interface Cast {
  spellId: number;
  /** Seconds since the pull. */
  t: number;
  name: string;
  icon: string;
}

export interface Player {
  rank: number;
  name: string;
  server: string;
  region: string;
  guild: string;
  amount: number;
  duration: number;
  kill: boolean;
  reportCode: string;
  fightId: number;
  reportUrl: string;
  casts: Cast[];
}

export interface Timelines {
  encounter: Encounter;
  difficulty: Difficulty;
  spec: { key: string; label: string };
  maxDuration: number;
  players: Player[];
  /** Non-fatal problems worth telling the user about, e.g. an unreadable log. */
  warnings: string[];
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    // FastAPI puts the useful message in `detail`; fall back to the status line.
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) message = body.detail;
    } catch {
      // Body was not JSON. The status line is all we have.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export const fetchMeta = () => get<Meta>("/api/meta");

export const fetchZones = () => get<Zone[]>("/api/zones");

export const fetchTimelines = (
  encounter: number,
  difficulty: number,
  spec: string,
) =>
  get<Timelines>(
    `/api/timelines?encounter=${encounter}&difficulty=${difficulty}&spec=${encodeURIComponent(spec)}`,
  );
