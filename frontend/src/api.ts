/**
 * Where the board data comes from, in either of the two modes the app runs in.
 *
 * Live: a FastAPI backend on /api, which queries Warcraft Logs on demand. This is
 * the development mode, and the one that can answer a question nobody precomputed.
 *
 * Static: precomputed JSON under assets/data, written by backend/tools/snapshot.py.
 * This is what the published site runs on. No API key exists in the browser, no
 * request leaves the page, and it scales to any number of visitors because it is
 * just files on a CDN.
 *
 * The mode is decided at load time by whether a snapshot manifest is present, not
 * by a build flag. That way one build serves both, and running the dev server
 * against a local snapshot needs no rebuild.
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
  role: string;
  /** Squashed class name, which is also the class emblem's filename. */
  classKey: string;
  className: string;
  /** Blizzard specialization ID, which is also the spec icon's filename. */
  specId: number;
  groups: SpellGroup[];
}

export interface Difficulty {
  id: number;
  name: string;
  short: string;
}

export interface Meta {
  /** false = the board data is precomputed rather than queried live. */
  live: boolean;
  topN: number;
  difficulties: Difficulty[];
  specs: Spec[];
  /** When the snapshot was taken. Absent in live mode. */
  generatedAt?: string;
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
  /** Hero talent tree, read off the log's ability icons. Null when undetectable. */
  heroTree: { name: string; short: string; asset: string } | null;
  /** Talent loadout string. Baked in by the snapshot; fetched on demand when live. */
  talents?: string;
  reportUrl: string;
  casts: Cast[];
}

export interface Timelines {
  encounter: Encounter;
  difficulty: Difficulty;
  spec: { key: string; label: string; role?: string; classKey?: string };
  maxDuration: number;
  players: Player[];
  /** Catalog groups with the trinket group filled in from this board's players. */
  groups: SpellGroup[];
  /** Non-fatal problems, e.g. an unreadable log. */
  warnings: string[];
}

const BASE = import.meta.env.BASE_URL;
const DATA = `${BASE}data`;

async function json<T>(url: string): Promise<T> {
  const response = await fetch(url);
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

/** The snapshot manifest, when one was shipped with the build. */
interface Manifest {
  generatedAt: string;
  zone: Zone;
  difficulties: Difficulty[];
  specs: (Omit<Spec, "groups"> & { groups: Omit<SpellGroup, "spells">[] })[];
  topN: number;
}

let manifest: Manifest | null | undefined;

async function loadManifest(): Promise<Manifest | null> {
  if (manifest !== undefined) return manifest;
  try {
    manifest = await json<Manifest>(`${DATA}/manifest.json`);
  } catch {
    // No snapshot in this build, so the live API is the only source.
    manifest = null;
  }
  return manifest;
}

export async function fetchMeta(): Promise<Meta> {
  const snapshot = await loadManifest();
  if (!snapshot) return json<Meta>("/api/meta");

  return {
    live: false,
    topN: snapshot.topN,
    difficulties: snapshot.difficulties,
    generatedAt: snapshot.generatedAt,
    // Spell lists are per board rather than per spec, since trinkets and potions
    // are discovered from each board's players. The groups here are the empty
    // shells the toggle row renders before a boss is chosen.
    specs: snapshot.specs.map((spec) => ({
      ...spec,
      groups: spec.groups.map((group) => ({ ...group, spells: [] })),
    })),
  };
}

export async function fetchZones(): Promise<Zone[]> {
  const snapshot = await loadManifest();
  // A snapshot covers exactly one tier, which is the tier it was taken of.
  return snapshot ? [snapshot.zone] : json<Zone[]>("/api/zones");
}

export async function fetchTimelines(
  encounter: number,
  difficulty: number,
  spec: string,
): Promise<Timelines> {
  const snapshot = await loadManifest();
  if (snapshot) return json<Timelines>(`${DATA}/${spec}/${encounter}-${difficulty}.json`);
  return json<Timelines>(
    `/api/timelines?encounter=${encounter}&difficulty=${difficulty}&spec=${encodeURIComponent(spec)}`,
  );
}

/**
 * The talent loadout string.
 *
 * In static mode the snapshot baked it into the player, so this never touches the
 * network. Live, it is one query, made only for the parse actually opened.
 */
/**
 * Tooltip text for every spell and trinket the boards reference.
 *
 * One file for the whole site rather than a copy inside each board: the same
 * abilities appear on every board of a spec, so inlining the descriptions would have
 * cost more than the boards. Absent in live mode, where tooltips simply show less.
 */
export async function fetchDescriptions(): Promise<Record<string, TooltipText>> {
  const snapshot = await loadManifest();
  if (!snapshot) return {};
  try {
    return await json<Record<string, TooltipText>>(`${DATA}/spells.json`);
  } catch {
    return {};
  }
}

export interface TooltipText {
  name: string;
  description: string;
}

export async function fetchTalents(
  player: Player,
): Promise<{ importCode: string }> {
  if (player.talents !== undefined) return { importCode: player.talents };
  if (player.actorId === null) return { importCode: "" };
  return json<{ importCode: string }>(
    `/api/talents?code=${encodeURIComponent(player.reportCode)}` +
      `&fight=${player.fightId}&actor=${player.actorId}`,
  );
}
