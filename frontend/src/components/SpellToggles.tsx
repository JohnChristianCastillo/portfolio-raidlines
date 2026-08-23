/**
 * The second row: which spells are drawn.
 *
 * Grouped by importance, in the order the catalog declares (defensives, main
 * abilities, potions, trinkets). A group header doubles as a select-all / clear-all,
 * because turning on every defensive at once is the common move and eight clicks for
 * it would be silly.
 *
 * Toggling filters data the browser already holds. Every tracked spell was fetched
 * when the boss was chosen, so this never waits on the network.
 */

import type { SpellGroup } from "../api";
import SpellIcon from "./SpellIcon";

interface Props {
  groups: SpellGroup[];
  enabled: ReadonlySet<number>;
  onToggle: (id: number) => void;
  onGroup: (ids: number[], on: boolean) => void;
}

export default function SpellToggles({ groups, enabled, onToggle, onGroup }: Props) {
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
                // Potions and trinkets ship empty on purpose: they are season
                // specific and curated by hand. Say so rather than showing a gap.
                <span className="toggle-empty">
                  none configured yet, add them in backend/app/spells.py
                </span>
              )}
              {group.spells.map((spell) => {
                const on = enabled.has(spell.id);
                return (
                  <button
                    key={spell.id}
                    type="button"
                    aria-pressed={on}
                    title={spell.name}
                    className={on ? "spell-toggle is-on" : "spell-toggle"}
                    style={{ "--accent": group.color } as React.CSSProperties}
                    onClick={() => onToggle(spell.id)}
                  >
                    <SpellIcon icon={spell.icon} short={spell.short} alt={spell.name} />
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </section>
  );
}
