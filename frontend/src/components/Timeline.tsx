/**
 * One row per parse: name, then timeline. Every row shares one scale, running to
 * the longest kill on the page, which is what makes ten logs comparable. A faster
 * kill stops early and the remainder is dimmed.
 */

import type { BossTimeline, Player, SpellGroup, Timelines, TooltipText } from "../api";
import { classColor } from "../classColors";
import { formatTime } from "../mrt";
import SpellIcon from "./SpellIcon";
import Tooltip from "./Tooltip";

interface Props {
  data: Timelines;
  /** The boss and add abilities, or null when none were published. */
  boss: BossTimeline | null;
  groups: SpellGroup[];
  enabled: ReadonlySet<number>;
  onPlayer: (player: Player) => void;
  tips: Record<string, TooltipText>;
}

/** Roughly a dozen ticks, on a round interval. */
function tickInterval(duration: number): number {
  for (const candidate of [15, 30, 60, 120, 300]) {
    if (duration / candidate <= 14) return candidate;
  }
  return 600;
}

export default function Timeline({ data, boss, groups, enabled, onPlayer, tips }: Props) {
  const { maxDuration, players, warnings } = data;

  // Colour by catalog group, matching the toggles.
  const colorOf = new Map<number, string>();
  const shortOf = new Map<number, string>();
  for (const group of groups) {
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

  // The scale has to cover the boss row as well, or a boss that outlasts the
  // fastest kills runs off the end of it.
  const longest = Math.max(maxDuration, boss?.duration ?? 0);
  const span = longest > 0 ? longest : 1;
  const step = tickInterval(span);
  const ticks: number[] = [];
  for (let t = 0; t <= span; t += step) ticks.push(t);

  const pct = (seconds: number) => `${(seconds / span) * 100}%`;

  const bossCasts = (boss?.casts ?? []).filter((c) => enabled.has(c.toggle));

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

      {boss && bossCasts.length > 0 && (
        <div className="timeline-row timeline-row--boss">
          <div className="cell-name cell-name--boss">
            <span className="boss-name">{boss.boss || "Boss"}</span>
            <Tooltip
              content={{
                name: "Representative timings",
                description:
                  `Medianed across ${boss.samples} top kills, so this is what the ` +
                  "fight usually looks like rather than any one pull. Each player " +
                  "row below is a different pull, so the two will not line up " +
                  "exactly, and they drift further apart later in the fight.",
              }}
            >
              <span className="caveat" aria-label="About these timings">
                ?
              </span>
            </Tooltip>
          </div>
          <div className="cell-track">
            <div className="track-inner">
              {ticks.map((t) => (
                <div className="tick tick--faint" key={t} style={{ left: pct(t) }} />
              ))}
              {bossCasts.map((cast, index) => {
                const text = tips[String(cast.toggle)];
                return (
                  <Tooltip
                    key={`${cast.spellId}-${cast.t}-${index}`}
                    content={
                      text
                        ? { ...text, name: `${text.name} at ${formatTime(cast.t)}` }
                        : { name: `${cast.name} at ${formatTime(cast.t)}` }
                    }
                  >
                    <button
                      type="button"
                      className="cast cast--boss"
                      style={{ left: pct(cast.t) }}
                      title={`${cast.name} at ${formatTime(cast.t)}`}
                    >
                      <SpellIcon
                        icon={cast.icon}
                        short={shortOf.get(cast.toggle) ?? "?"}
                        alt={cast.name}
                      />
                      <span className="cast-time">
                        {formatTime(cast.t).slice(0, 5)}
                      </span>
                    </button>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {players.map((player) => {
        const casts = player.casts.filter((c) => enabled.has(c.toggle));
        return (
          <div className="timeline-row" key={`${player.reportCode}-${player.fightId}`}>
            <button
              type="button"
              className="cell-name"
              onClick={() => onPlayer(player)}
              title={`${player.name}${player.server ? `-${player.server}` : ""} - click for the MRT note`}
            >
              <span className="rank">#{player.rank}</span>
              <span
                className="player-name"
                style={{ color: classColor(data.spec.classKey) }}
              >
                {player.name}
              </span>
              <span className="amount">
                {(player.amount / 1000).toFixed(1)}k
              </span>
              <span className="worn">
                {player.trinkets.map((t) => {
                  // Trinket tooltips are keyed by the negative item ID, the same
                  // toggle the board groups them under.
                  const text = tips[String(-t.id)];
                  const level = [t.itemLevel || null, t.track || null]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <Tooltip
                      key={t.id}
                      content={{
                        name: level ? `${t.name} (${level})` : t.name,
                        // Falls back to the level alone, so the card still opens
                        // and says something when there is no item description.
                        description: text?.description || level || undefined,
                      }}
                    >
                      <SpellIcon
                        icon={t.icon}
                        short={t.name.slice(0, 2)}
                        alt={t.name}
                        title={level ? `${t.name} (${level})` : t.name}
                      />
                    </Tooltip>
                  );
                })}
                {player.heroTree && (
                  // Round, so it reads as a different kind of thing from the
                  // square trinkets sitting next to it. Ours to serve, unlike the
                  // spell icons, so it needs no CDN fallback.
                  <span className="hero">
                    <img
                      className="spell-icon"
                      src={`${import.meta.env.BASE_URL}assets/${player.heroTree.asset}`}
                      alt={player.heroTree.name}
                      title={`${player.heroTree.name} hero talents`}
                      loading="lazy"
                    />
                  </span>
                )}
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

                {casts.map((cast, index) => {
                  const label =
                    cast.name || shortOf.get(cast.toggle) || String(cast.spellId);
                  const text = tips[String(cast.toggle)];
                  return (
                    <Tooltip
                      // Rounding can collide, hence the index in the key.
                      key={`${cast.spellId}-${cast.t}-${index}`}
                      content={
                        text
                          ? { ...text, name: `${text.name} at ${formatTime(cast.t)}` }
                          : null
                      }
                    >
                      <button
                        type="button"
                        className="cast"
                        style={{
                          left: pct(cast.t),
                          borderColor: colorOf.get(cast.toggle) ?? "#888",
                        }}
                        title={`${label} at ${formatTime(cast.t)}`}
                        onClick={() => onPlayer(player)}
                      >
                        <SpellIcon
                          icon={cast.icon}
                          short={shortOf.get(cast.toggle) ?? "?"}
                          alt={cast.name}
                        />
                        <span className="cast-time">
                          {formatTime(cast.t).slice(0, 5)}
                        </span>
                      </button>
                    </Tooltip>
                  );
                })}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
