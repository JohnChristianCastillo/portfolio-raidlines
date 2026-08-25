/**
 * What the page remembers between visits.
 *
 * Reopening a tab by hand should land you where you left off: same boss, same
 * difficulty, same spec, same toggles. Closing a tab is not a request to reset.
 *
 * Toggles are stored per spec, because they mean different things per spec. Having
 * Shadow Dance on says nothing about what a Fire Mage should show.
 *
 * Everything here is best effort. localStorage throws in private windows and when
 * the quota is full, and a lost preference is not worth a broken page, so every
 * access is guarded and failure just means defaults.
 */

const KEY = "raidlines.prefs.v1";

export interface Prefs {
  zoneId: number | null;
  difficultyId: number | null;
  encounterId: number | null;
  specKey: string | null;
  /** Spec key -> the toggle IDs switched on. Absent means "use the defaults". */
  toggles: Record<string, number[]>;
}

const EMPTY: Prefs = {
  zoneId: null,
  difficultyId: null,
  encounterId: null,
  specKey: null,
  toggles: {},
};

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    return {
      ...EMPTY,
      ...parsed,
      // Guard the shape: a hand-edited or half-written value should not crash the
      // page on load.
      toggles:
        parsed.toggles && typeof parsed.toggles === "object" ? parsed.toggles : {},
    };
  } catch {
    return EMPTY;
  }
}

export function savePrefs(prefs: Prefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    // Private window, or quota. Not worth telling anyone about.
  }
}
