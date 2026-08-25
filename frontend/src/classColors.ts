/**
 * The game's own class colours, keyed by squashed class name.
 *
 * These are Blizzard's values, not approximations. Raiders read a class off its
 * colour faster than off its name, and getting the shade slightly wrong is the kind
 * of thing that looks broken to someone who has stared at these for years.
 *
 * Priest is white and Rogue is a pale yellow, which both sit oddly on a dark page
 * next to the others but are correct, and correct wins here.
 */

export const CLASS_COLORS: Record<string, string> = {
  deathknight: "#C41E3A",
  demonhunter: "#A330C9",
  druid: "#FF7C0A",
  evoker: "#33937F",
  hunter: "#AAD372",
  mage: "#3FC7EB",
  monk: "#00FF98",
  paladin: "#F48CBA",
  priest: "#FFFFFF",
  rogue: "#FFF468",
  shaman: "#0070DD",
  warlock: "#8788EE",
  warrior: "#C69B6D",
};

/** Falls back to the page's normal text colour for a class we do not know. */
export function classColor(classKey: string | undefined): string {
  return (classKey && CLASS_COLORS[classKey]) || "var(--text)";
}
