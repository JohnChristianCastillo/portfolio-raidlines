/**
 * Pick a spec by clicking its class emblem, then its specialisation icon.
 *
 * Two rows rather than a dropdown, for the same reason the boss row is buttons:
 * this is the control people change most, and a raider recognises the art faster
 * than they read a list. The class row also keeps the second row short, since no
 * class has more than four specs.
 *
 * Only classes with a catalog appear. The art for all forty specs is already
 * shipped, so a spec shows up the moment its catalog is written.
 */

import type { Spec } from "../api";
import Asset from "./Asset";

interface Props {
  specs: Spec[];
  specKey: string;
  onSpec: (key: string) => void;
}

export default function SpecPicker({ specs, specKey, onSpec }: Props) {
  const selected = specs.find((s) => s.key === specKey) ?? specs[0];
  if (!selected) return null;

  // Class order follows the spec list, so it is stable rather than alphabetical by
  // whatever happens to be configured.
  const classes: { key: string; name: string }[] = [];
  for (const spec of specs) {
    if (!classes.some((c) => c.key === spec.classKey)) {
      classes.push({ key: spec.classKey, name: spec.className });
    }
  }
  const siblings = specs.filter((s) => s.classKey === selected.classKey);

  function pickClass(classKey: string) {
    // Keep the spec if the class did not change, otherwise take its first spec.
    if (classKey === selected.classKey) return;
    const first = specs.find((s) => s.classKey === classKey);
    if (first) onSpec(first.key);
  }

  return (
    <>
      <div className="control-group">
        <span className="control-label">Class</span>
        <div className="icon-row">
          {classes.map((entry) => (
            <button
              key={entry.key}
              type="button"
              title={entry.name}
              aria-pressed={entry.key === selected.classKey}
              className={
                entry.key === selected.classKey
                  ? "icon-button is-on"
                  : "icon-button"
              }
              onClick={() => pickClass(entry.key)}
            >
              <Asset path={`classes/${entry.key}.png`} alt={entry.name} />
            </button>
          ))}
        </div>
      </div>

      <div className="control-group">
        <span className="control-label">Spec</span>
        <div className="icon-row">
          {siblings.map((spec) => (
            <button
              key={spec.key}
              type="button"
              title={spec.label}
              aria-pressed={spec.key === selected.key}
              className={
                spec.key === selected.key ? "icon-button is-on" : "icon-button"
              }
              onClick={() => onSpec(spec.key)}
            >
              <Asset path={`specs/${spec.specId}.jpg`} alt={spec.label} />
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
