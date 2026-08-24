/**
 * Pick a tier, difficulty, boss and spec, then read ten timelines. Nothing renders
 * until all four are set.
 */

import { useEffect, useMemo, useState } from "react";
import {
  fetchMeta,
  fetchTimelines,
  fetchZones,
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
  const [difficultyId, setDifficultyId] = useState<number | null>(null);
  const [encounterId, setEncounterId] = useState<number | null>(null);
  const [specKey, setSpecKey] = useState<string>("rogue-subtlety");

  const [enabled, setEnabled] = useState<Set<number>>(new Set());

  const [timelines, setTimelines] = useState<Timelines | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [openPlayer, setOpenPlayer] = useState<Player | null>(null);

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

  // Seed toggles from the catalog defaults on every spec change.
  useEffect(() => {
    if (!spec) return;
    const defaults = spec.groups
      .flatMap((g) => g.spells)
      .filter((s) => s.onByDefault)
      .map((s) => s.id);
    setEnabled(new Set(defaults));
  }, [spec]);

  const zone = useMemo(
    () => zones.find((z) => z.id === zoneId) ?? null,
    [zones, zoneId],
  );

  // Trinkets are whatever this board's players brought, so the real group list
  // arrives with the board. Until then the catalog's own groups stand in.
  const groups = timelines?.groups ?? spec?.groups ?? [];

  // Bosses differ per tier, so a tier change invalidates the chosen boss.
  useEffect(() => {
    setEncounterId(null);
    setTimelines(null);
  }, [zoneId]);

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
