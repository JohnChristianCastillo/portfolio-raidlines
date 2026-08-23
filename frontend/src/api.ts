/** The backend's data API: response types and the calls that reach it. */

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
  /** false = replaying recorded fixtures rather than live rankings. */
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
  expansionId: number;
  frozen: boolean;
  encounters: Encounter[];
}

export interface Cast {
  /** The real spell, which is what the MRT export writes. */
  spellId: number;
  /**
   * What the toggle row switches on. Same as spellId except for trinkets, where
   * several abilities belong to one item and share its toggle.
   */
  toggle: number;
  /** Seconds since the pull. */
  t: number;
  name: string;
  icon: string;
}

export interface Trinket {
  id: number;
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
  /** Report-scoped player ID, needed to ask for talents. Null if they cast nothing. */
  actorId: number | null;
  /** The two trinkets they had equipped. */
  trinkets: Trinket[];
  /** Hero talent tree. Null when it has not been named in spells.py. */
  heroTree: { name: string; icon: string; short: string } | null;
  reportUrl: string;
  casts: Cast[];
}

export interface Timelines {
  encounter: Encounter;
  difficulty: Difficulty;
  spec: { key: string; label: string };
  maxDuration: number;
  players: Player[];
  /** Catalog groups with the trinket group filled in from this board's players. */
  groups: SpellGroup[];
  /** Non-fatal problems, e.g. an unreadable log. */
  warnings: string[];
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    // FastAPI puts the useful message in `detail`.
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) message = body.detail;
    } catch {
      // Not JSON; the status line is all we have.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export const fetchMeta = () => get<Meta>("/api/meta");

export const fetchZones = () => get<Zone[]>("/api/zones");

/** The talent loadout string, fetched only when a player's note is opened. */
export const fetchTalents = (code: string, fight: number, actor: number) =>
  get<{ importCode: string }>(
    `/api/talents?code=${encodeURIComponent(code)}&fight=${fight}&actor=${actor}`,
  );

export const fetchTimelines = (
  encounter: number,
  difficulty: number,
  spec: string,
) =>
  get<Timelines>(
    `/api/timelines?encounter=${encounter}&difficulty=${difficulty}&spec=${encodeURIComponent(spec)}`,
  );
