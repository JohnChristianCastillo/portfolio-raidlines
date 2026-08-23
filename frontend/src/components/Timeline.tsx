/**
 * The board: one row per parse, two columns, name and timeline.
 *
 * Every row shares one horizontal scale, running from the pull to the longest kill
 * on the page. That is the whole point of the thing: ten logs of different lengths
 * only become comparable once they are drawn against the same ruler. A row whose own
 * kill was faster stops early and the remainder is dimmed, so a short row reads as
 * "killed it sooner" rather than "stopped pressing buttons".
 *
 * Markers overlap when cooldowns cluster. That is expected and the spec says so
 * outright; hovering lifts one out of the pile rather than the layout trying to
 * spread them and lying about when things happened.
 */

import type { Player, Spec, Timelines } from "../api";
import { formatTime } from "../mrt";
import SpellIcon from "./SpellIcon";

interface Props {
  data: Timelines;
  spec: Spec | null;
  enabled: ReadonlySet<number>;
  onPlayer: (player: Player) => void;
}

/** Ruler ticks: aim for roughly a dozen, on a round interval. */
function tickInterval(duration: number): number {
  for (const candidate of [15, 30, 60, 120, 300]) {
    if (duration / candidate <= 14) return candidate;
  }
  return 600;
}

export default function Timeline({ data, spec, enabled, onPlayer }: Props) {
  const { maxDuration, players, warnings } = data;

  // Spell colour comes from its catalog group, so a defensive is the same blue on
  // the timeline as on its toggle.
  const colorOf = new Map<number, string>();
  const shortOf = new Map<number, string>();
  for (const group of spec?.groups ?? []) {
    for (const s of group.spells) {
      colorOf.set(s.id, group.color);
      shortOf.set(s.id, s.short);
    }
  }

  if (players.length === 0) {
    return (
      <div className="empty">
        <p>No ranked parses for this boss and difficulty.</p>
        {warnings.map((w) => (
          <p className="warning" key={w}>
            {w}
          </p>
        ))}
      </div>
    );
  }

  const span = maxDuration > 0 ? maxDuration : 1;
  const step = tickInterval(span);
  const ticks: number[] = [];
  for (let t = 0; t <= span; t += step) ticks.push(t);

  const pct = (seconds: number) => `${(seconds / span) * 100}%`;

  return (
    <div className="timeline">
      {warnings.length > 0 && (
        <div className="warnings">
          {warnings.map((w) => (
            <p className="warning" key={w}>
              {w}
            </p>
          ))}
        </div>
      )}

      <div className="timeline-row timeline-row--ruler">
        <div className="cell-name cell-name--ruler">
          {enabled.size === 0 ? "no spells selected" : `${enabled.size} tracked`}
        </div>
        <div className="cell-track">
          <div className="track-inner">
            {ticks.map((t) => (
              <div className="tick" key={t} style={{ left: pct(t) }}>
                <span className="tick-label">{formatTime(t).slice(0, 5)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {players.map((player) => {
        const casts = player.casts.filter((c) => enabled.has(c.spellId));
        return (
          <div className="timeline-row" key={`${player.reportCode}-${player.fightId}`}>
            <button
              type="button"
              className="cell-name"
              onClick={() => onPlayer(player)}
              title={`${player.name}${player.server ? `-${player.server}` : ""} - click for the MRT note`}
            >
              <span className="rank">#{player.rank}</span>
              <span className="player-name">{player.name}</span>
              <span className="amount">
                {(player.amount / 1000).toFixed(1)}k
              </span>
            </button>

            <div className="cell-track">
              <div className="track-inner">
                {ticks.map((t) => (
                  <div className="tick tick--faint" key={t} style={{ left: pct(t) }} />
                ))}

                <div className="fight-bar" style={{ width: pct(player.duration) }} />
                {player.duration < span && (
                  <span className="kill-time" style={{ left: pct(player.duration) }}>
                    {formatTime(player.duration).slice(0, 5)}
                  </span>
                )}

                {casts.map((cast, index) => (
                  <button
                    type="button"
                    // Two casts can share a spell and a timestamp after rounding, so
                    // the index is part of the key.
                    key={`${cast.spellId}-${cast.t}-${index}`}
                    className="cast"
                    style={{
                      left: pct(cast.t),
                      borderColor: colorOf.get(cast.spellId) ?? "#888",
                    }}
                    title={`${cast.name || shortOf.get(cast.spellId) || cast.spellId} at ${formatTime(cast.t)}`}
                    onClick={() => onPlayer(player)}
                  >
                    <SpellIcon
                      icon={cast.icon}
                      short={shortOf.get(cast.spellId) ?? "?"}
                      alt={cast.name}
                    />
                    <span className="cast-time">{formatTime(cast.t).slice(0, 5)}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
