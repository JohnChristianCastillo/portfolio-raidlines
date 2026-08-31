/**
 * Pick a tier, difficulty, boss and spec, then read ten timelines. Nothing renders
 * until all four are set.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchBoss,
  fetchDescriptions,
  fetchMeta,
  fetchTimelines,
  fetchZones,
  type TooltipText,
  type Meta,
  type Player,
  type Timelines,
  type Zone,
  type BossTimeline,
} from "./api";
import Controls from "./components/Controls";
import SpellToggles from "./components/SpellToggles";
import Timeline from "./components/Timeline";
import PlayerModal from "./components/PlayerModal";
import { loadPrefs, savePrefs } from "./prefs";
import "./styles/app.css";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [bootError, setBootError] = useState("");

  // Read once, synchronously, so the first render already has last visit's choices
  // and nothing flashes at a default before being corrected.
  const saved = useRef(loadPrefs()).current;

  const [zoneId, setZoneId] = useState<number | null>(saved.zoneId);
  // Mythic by default: it is what the top parses are set on, and the reference
  // people come here for.
  const [difficultyId, setDifficultyId] = useState<number | null>(
    saved.difficultyId ?? 5,
  );
  const [encounterId, setEncounterId] = useState<number | null>(saved.encounterId);
  const [specKey, setSpecKey] = useState<string>(
    saved.specKey ?? "rogue-subtlety",
  );

  // Per spec, and null for a spec never touched, which means "use the defaults".
  // Storing the defaults instead would freeze them: a spec gaining an ability would
  // never switch it on for anyone who had already visited.
  const [toggles, setToggles] = useState<Record<string, number[]>>(saved.toggles);

  const [timelines, setTimelines] = useState<Timelines | null>(null);
  const [bossLine, setBossLine] = useState<BossTimeline | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [openPlayer, setOpenPlayer] = useState<Player | null>(null);
  const [tips, setTips] = useState<Record<string, TooltipText>>({});

  useEffect(() => {
    // Best effort: no tooltips is a smaller loss than no board.
    fetchDescriptions().then(setTips).catch(() => setTips({}));
  }, []);

  useEffect(() => {
    Promise.all([fetchMeta(), fetchZones()])
      .then(([m, z]) => {
        setMeta(m);
        setZones(z);
        // Newest tier first, unless a remembered one is still in the list. A tier
        // that has since gone is silently replaced rather than left dangling.
        setZoneId((current) =>
          z.some((zone) => zone.id === current) ? current : (z[0]?.id ?? null),
        );
      })
      .catch((e: Error) => setBootError(e.message));
  }, []);

  const spec = useMemo(
    () => meta?.specs.find((s) => s.key === specKey) ?? null,
    [meta, specKey],
  );


  const zone = useMemo(
    () => zones.find((z) => z.id === zoneId) ?? null,
    [zones, zoneId],
  );

  // Trinkets are whatever this board's players brought, so the real group list
  // arrives with the board. Until then the catalog's own groups stand in.
  // The boss abilities become a fifth toggle group, appended to the board's own.
  // They come from a different file, so they are joined here rather than upstream.
  const groups = useMemo(() => {
    const base = timelines?.groups ?? spec?.groups ?? [];
    if (!bossLine?.abilities.length) return base;
    return [
      ...base,
      {
        key: "boss",
        label: bossLine.boss || "Boss",
        color: "#e06c5a",
        spells: bossLine.abilities,
      },
    ];
  }, [timelines, spec, bossLine]);

  // Derived, not seeded by an effect.
  //
  // An effect that fills in the defaults has to run after the board arrives and
  // before the first paint that uses it, which makes correctness depend on effect
  // ordering. Deriving it cannot be too early or too late: with no stored choice
  // for this spec, the defaults simply are the value.
  const enabled = useMemo(() => {
    const stored = toggles[specKey];
    if (stored) return new Set(stored);

    const on = new Set<number>();
    // Only from a board that belongs to this spec. Switching spec leaves the old
    // board in state until the new one lands, and the old spec's abilities are not
    // this spec's defaults.
    if (timelines?.spec.key === specKey) {
      for (const group of groups) {
        for (const spell of group.spells) {
          // The whole specialisation group starts on: it is what the board is for.
          // Elsewhere only what the catalog marks, which for the boss group means
          // its own abilities but not its adds'.
          if (group.key === "spec" || spell.onByDefault) on.add(spell.id);
        }
      }
    }
    return on;
  }, [toggles, specKey, timelines, groups]);

  // Bosses differ per tier, so a tier change invalidates the chosen boss. Default to
  // the first one rather than nothing: the picker should open on a board, not on an
  // instruction to pick a board.
  useEffect(() => {
    const encounters = zones.find((z) => z.id === zoneId)?.encounters ?? [];
    // Nothing to validate against until the tier list has loaded. Without this the
    // effect runs once on mount with zones still empty, finds the remembered boss
    // in an empty list, and clears it, so every visit reset to the first boss.
    if (encounters.length === 0) return;

    setEncounterId((current) =>
      encounters.some((e) => e.id === current) ? current : encounters[0].id,
    );
  }, [zoneId, zones]);

  // Persist whenever any of it changes. Cheap, and it means a crash or a closed
  // laptop loses nothing.
  useEffect(() => {
    savePrefs({ zoneId, difficultyId, encounterId, specKey, toggles });
  }, [zoneId, difficultyId, encounterId, specKey, toggles]);

  const ready = difficultyId !== null && encounterId !== null && specKey !== "";

  useEffect(() => {
    if (!ready) {
      setTimelines(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    // The boss row is per encounter and difficulty, so it is fetched alongside the
    // board rather than being repeated inside every spec's copy.
    fetchBoss(encounterId!, difficultyId!).then((b) => !cancelled && setBossLine(b));

    fetchTimelines(encounterId!, difficultyId!, specKey)
      .then((data) => {
        // A slow reply must not overwrite a boss the user has since moved off.
        if (!cancelled) setTimelines(data);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setError(e.message);
          setTimelines(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ready, encounterId, difficultyId, specKey]);

  // Writing a toggle materialises the whole set for this spec, defaults included,
  // so that from then on it is a choice rather than a fallback.
  function apply(change: (set: Set<number>) => void) {
    const next = new Set(enabled);
    change(next);
    setToggles((previous) => ({ ...previous, [specKey]: [...next] }));
  }

  function toggleSpell(id: number) {
    apply((set) => (set.has(id) ? set.delete(id) : set.add(id)));
  }

  function setGroup(ids: number[], on: boolean) {
    apply((set) => {
      for (const id of ids) {
        if (on) set.add(id);
        else set.delete(id);
      }
    });
  }

  if (bootError) {
    return (
      <div className="boot-error">
        <h1>Raidlines</h1>
        <p>Could not reach the backend: {bootError}</p>
      </div>
    );
  }

  if (!meta) return <div className="booting">Loading Raidlines...</div>;

  const specLabel = spec?.label ?? specKey;
  const bossName = timelines?.encounter.name ?? "";

  return (
    <div className="app">
      <header className="masthead">
        <h1>
          <span className="brand">Raidlines</span>
          {bossName ? (
            <span className="subject">
              {specLabel} <span className="vs">vs.</span> {bossName}
            </span>
          ) : (
            <span className="subject muted">Pick a difficulty and a boss</span>
          )}
        </h1>
        {!meta.live && meta.generatedAt && (
          <p className="fixture-banner">
            Snapshot from {new Date(meta.generatedAt).toLocaleDateString()}.
          </p>
        )}
        {!meta.live && !meta.generatedAt && (
          <p className="fixture-banner">Demo data, not live rankings.</p>
        )}
      </header>

      <Controls
        zones={zones}
        zoneId={zoneId}
        onZone={setZoneId}
        difficulties={meta.difficulties}
        difficultyId={difficultyId}
        onDifficulty={setDifficultyId}
        encounters={zone?.encounters ?? []}
        encounterId={encounterId}
        onEncounter={setEncounterId}
        specs={meta.specs}
        specKey={specKey}
        onSpec={setSpecKey}
      />

      {groups.length > 0 && (
        <SpellToggles
          groups={groups}
          enabled={enabled}
          onToggle={toggleSpell}
          onGroup={setGroup}
          tips={tips}
        />
      )}

      <main className="board">
        {!ready && (
          <p className="placeholder">Pick a difficulty and a boss.</p>
        )}
        {ready && loading && <p className="placeholder">Reading logs...</p>}
        {ready && error && <p className="error">{error}</p>}
        {ready && !loading && !error && timelines && (
          <Timeline
            data={timelines}
            boss={bossLine}
            groups={groups}
            enabled={enabled}
            onPlayer={setOpenPlayer}
            tips={tips}
          />
        )}
      </main>

      {openPlayer && timelines && (
        <PlayerModal
          player={openPlayer}
          encounterName={timelines.encounter.name}
          difficultyName={timelines.difficulty.name}
          enabled={enabled}
          onClose={() => setOpenPlayer(null)}
        />
      )}
    </div>
  );
}
