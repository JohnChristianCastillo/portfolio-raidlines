/**
 * Which spells are drawn, grouped by importance. A group header is a
 * select-all / clear-all. Toggling filters data already held, so it never waits
 * on the network.
 */

import type { SpellGroup, TooltipText } from "../api";
import SpellIcon from "./SpellIcon";
import Tooltip from "./Tooltip";

interface Props {
  groups: SpellGroup[];
  enabled: ReadonlySet<number>;
  onToggle: (id: number) => void;
  onGroup: (ids: number[], on: boolean) => void;
  tips: Record<string, TooltipText>;
}

export default function SpellToggles({
  groups,
  enabled,
  onToggle,
  onGroup,
  tips,
}: Props) {
  return (
    <section className="toggles">
      {groups.map((group) => {
        const ids = group.spells.map((s) => s.id);
        const allOn = ids.length > 0 && ids.every((id) => enabled.has(id));

        return (
          <div className="toggle-group" key={group.key}>
            <button
              type="button"
              className="toggle-group-label"
              style={{ color: group.color }}
              onClick={() => onGroup(ids, !allOn)}
              title={allOn ? `Hide all ${group.label}` : `Show all ${group.label}`}
              disabled={ids.length === 0}
            >
              {group.label}
            </button>

            <div className="toggle-row">
              {group.spells.length === 0 && (
                <span className="toggle-empty">none tracked yet</span>
              )}
              {group.spells.map((spell) => {
                const on = enabled.has(spell.id);
                return (
                  <Tooltip
                    key={spell.id}
                    content={tips[String(spell.id)] ?? { name: spell.name }}
                  >
                    <button
                      type="button"
                      aria-pressed={on}
                      title={spell.name}
                      className={on ? "spell-toggle is-on" : "spell-toggle"}
                      style={{ "--accent": group.color } as React.CSSProperties}
                      onClick={() => onToggle(spell.id)}
                    >
                      <SpellIcon
                        icon={spell.icon}
                        short={spell.short}
                        alt={spell.name}
                      />
                    </button>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        );
      })}
    </section>
  );
}
