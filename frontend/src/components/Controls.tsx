/**
 * Which fight are we looking at. Difficulty is buttons rather than a dropdown, and
 * every boss is laid out at once, so switching either is one click. One boss at a
 * time.
 */

import type { Difficulty, Encounter, Spec, Zone } from "../api";

interface Props {
  zones: Zone[];
  zoneId: number | null;
  onZone: (id: number) => void;
  difficulties: Difficulty[];
  difficultyId: number | null;
  onDifficulty: (id: number) => void;
  encounters: Encounter[];
  encounterId: number | null;
  onEncounter: (id: number) => void;
  specs: Spec[];
  specKey: string;
  onSpec: (key: string) => void;
}

export default function Controls({
  zones,
  zoneId,
  onZone,
  difficulties,
  difficultyId,
  onDifficulty,
  encounters,
  encounterId,
  onEncounter,
  specs,
  specKey,
  onSpec,
}: Props) {
  return (
    <section className="controls">
      <div className="control-group">
        <span className="control-label">Raid</span>
        <select
          className="select"
          value={zoneId ?? ""}
          onChange={(e) => onZone(Number(e.target.value))}
        >
          {zones.map((zone) => (
            <option key={zone.id} value={zone.id}>
              {zone.name}
              {zone.frozen ? " (closed)" : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="control-group">
        <span className="control-label">Difficulty</span>
        <div className="difficulty-row">
          {difficulties.map((difficulty) => (
            <button
              key={difficulty.id}
              type="button"
              title={difficulty.name}
              aria-pressed={difficultyId === difficulty.id}
              className={
                difficultyId === difficulty.id
                  ? "difficulty-button is-on"
                  : "difficulty-button"
              }
              onClick={() => onDifficulty(difficulty.id)}
            >
              {difficulty.short}
            </button>
          ))}
        </div>
      </div>

      <div className="control-group">
        <span className="control-label">Spec</span>
        <select
          className="select"
          value={specKey}
          onChange={(e) => onSpec(e.target.value)}
        >
          {specs.map((spec) => (
            <option key={spec.key} value={spec.key}>
              {spec.label}
            </option>
          ))}
        </select>
      </div>

      <div className="control-group control-group--wide">
        <span className="control-label">Boss</span>
        <div className="boss-row">
          {encounters.map((encounter) => (
            <button
              key={encounter.id}
              type="button"
              aria-pressed={encounterId === encounter.id}
              className={
                encounterId === encounter.id ? "boss-button is-on" : "boss-button"
              }
              onClick={() => onEncounter(encounter.id)}
            >
              {encounter.name}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
