/**
 * The Method Raid Tools reminder string: one line per cast, as
 * `{time:01:35.8} -  {spell:121471}`. Spacing matches the game's own exports.
 *
 * Lives here rather than in the backend because the string depends on which spells
 * are toggled on, so it updates with no round trip.
 *
 * Absolute times only. Phase-relative anchors ({time:0:05,pg2}) are a later step.
 */

import type { Cast, Player } from "./api";

/** Seconds since pull, as MRT writes it: mm:ss.t, minutes zero-padded. */
export function formatTime(seconds: number): string {
  // Round to tenths in integer space. Rounding after the split renders 59.97 as
  // "00:60.0".
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
 * One line per cast, in time order, enabled spells only. Simultaneous casts stay on
 * separate lines so hand-editing one does not take another with it.
 */
export function buildReminder(casts: Cast[], enabled: ReadonlySet<number>): string {
  return casts
    // Selected by toggle, written as the real spell: MRT needs the spell ID, not
    // the trinket item the toggle is keyed on.
    .filter((cast) => enabled.has(cast.toggle))
    .slice()
    .sort((a, b) => a.t - b.t)
    .map((cast) => `{time:${formatTime(cast.t)}} -  {spell:${cast.spellId}}`)
    .join("\n");
}

/** Header comment, so the note says which log it came from. */
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
