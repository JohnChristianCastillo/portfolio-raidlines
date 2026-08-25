/**
 * Pick a tier, difficulty, boss and spec, then read ten timelines. Nothing renders
 * until all four are set.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchDescriptions,
  fetchMeta,
  fetchTimelines,
  fetchZones,
  type TooltipText,
  type Meta,
  type Player,
  type Timelines,
  type Zone,
} from "./api";
import Controls from "./components/Controls";
import SpellToggles from "./components/SpellToggles";
import Timeline from "./components/Timeline";
import PlayerModal from "./components/PlayerModal";
import "./styles/app.css";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [bootError, setBootError] = useState("");

  const [zoneId, setZoneId] = useState<number | null>(null);
  // Mythic by default: it is what the top parses are set on, and the reference
  // people come here for.
  const [difficultyId, setDifficultyId] = useState<number | null>(5);
  const [encounterId, setEncounterId] = useState<number | null>(null);
  const [specKey, setSpecKey] = useState<string>("rogue-subtlety");

  const [enabled, setEnabled] = useState<Set<number>>(new Set());

  const [timelines, setTimelines] = useState<Timelines | null>(null);
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
        // Newest tier first.
        if (z.length > 0) setZoneId(z[0].id);
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
  const groups = timelines?.groups ?? spec?.groups ?? [];

  // Seed the toggles once per spec, from the loaded board.
  //
  // Driven by the board rather than by `groups`, and it checks the board is for the
  // spec we are now on. Switching spec leaves the previous board in state until the
  // new one arrives, so seeding off `groups` would briefly read the old spec's
  // spells and switch on abilities the new spec does not have.
  //
  // Not from the catalog groups either: in static mode those arrive as empty shells,
  // since trinkets and potions are discovered per board rather than declared.
  //
  // Keyed on the spec so changing boss keeps whatever the user toggled, while
  // changing spec starts fresh.
  const seededFor = useRef<string | null>(null);
  useEffect(() => {
    if (!timelines || timelines.spec.key !== specKey) return;
    if (seededFor.current === specKey) return;

    const on = new Set<number>();
    for (const group of timelines.groups) {
      for (const spell of group.spells) {
        // The whole specialisation group starts on: it is what the board is for.
        // Elsewhere only what the catalog marks.
        if (group.key === "spec" || spell.onByDefault) on.add(spell.id);
      }
    }
    setEnabled(on);
    seededFor.current = specKey;
  }, [timelines, specKey]);

  // Bosses differ per tier, so a tier change invalidates the chosen boss. Default to
  // the first one rather than nothing: the picker should open on a board, not on an
  // instruction to pick a board.
  useEffect(() => {
    const encounters = zones.find((z) => z.id === zoneId)?.encounters ?? [];
    setEncounterId(encounters.length > 0 ? encounters[0].id : null);
    setTimelines(null);
  }, [zoneId, zones]);

  const ready = difficultyId !== null && encounterId !== null && specKey !== "";

  useEffect(() => {
    if (!ready) {
      setTimelines(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
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

  function toggleSpell(id: number) {
    setEnabled((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function setGroup(ids: number[], on: boolean) {
    setEnabled((previous) => {
      const next = new Set(previous);
      for (const id of ids) {
        if (on) next.add(id);
        else next.delete(id);
      }
      return next;
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
