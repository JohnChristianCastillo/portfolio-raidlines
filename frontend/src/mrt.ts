/**
 * Building the Method Raid Tools reminder string.
 *
 * MRT reads a plain-text note where each line is a time and one or more spells:
 *
 *     {time:01:35.8} -  {spell:121471}
 *
 * The format is reproduced exactly as the game's own exports write it, two spaces
 * after the dash included, because the note is pasted straight into the addon and
 * there is no reason to risk a parser that is fussier than it looks.
 *
 * This lives in the frontend rather than the backend on purpose: the string depends
 * on which spells are toggled on, which is browser state. Computing it here makes
 * the export update the instant a toggle changes, with no round trip, and keeps one
 * copy of the formatting rule.
 *
 * Only absolute times are emitted. Phase-relative anchors ({time:0:05,pg2}) are a
 * later milestone: they need the boss's phase transitions out of Warcraft Logs and a
 * mapping onto MRT's own phase tokens, and getting that subtly wrong would desync a
 * raid's reminders rather than merely look wrong.
 */

import type { Cast, Player } from "./api";

/** Seconds since pull, as MRT writes it: mm:ss.t, minutes zero-padded. */
export function formatTime(seconds: number): string {
  // Round to tenths first, in integer space. Splitting a float into minutes and a
  // remainder and only then rounding lets 59.97 render as "00:60.0", which is both
  // wrong and the kind of thing nobody notices until it is in a raid's note.
  const tenths = Math.max(0, Math.round(seconds * 10));
  const minutes = Math.floor(tenths / 600);
  const wholeSeconds = Math.floor((tenths % 600) / 10);
  const remainder = tenths % 10;
  return (
    `${String(minutes).padStart(2, "0")}:` +
    `${String(wholeSeconds).padStart(2, "0")}.${remainder}`
  );
}

/**
 * One reminder line per cast, in time order, for the enabled spells only.
 *
 * Casts at the same instant are kept as separate lines rather than merged onto one.
 * MRT accepts both, and separate lines survive hand-editing better: deleting one
 * reminder does not silently take another with it.
 */
export function buildReminder(casts: Cast[], enabled: ReadonlySet<number>): string {
  return casts
    .filter((cast) => enabled.has(cast.spellId))
    .slice()
    .sort((a, b) => a.t - b.t)
    .map((cast) => `{time:${formatTime(cast.t)}} -  {spell:${cast.spellId}}`)
    .join("\n");
}

/** A comment header, so a note pasted into MRT still says where it came from. */
export function reminderHeader(
  player: Player,
  encounterName: string,
  difficultyName: string,
): string {
  const realm = player.server ? `-${player.server}` : "";
  return [
    `-- ${player.name}${realm} (${player.region}) rank #${player.rank}`,
    `-- ${encounterName}, ${difficultyName}, ${formatTime(player.duration)} kill`,
    `-- ${player.reportUrl}`,
  ].join("\n");
}
