/**
 * The whole app: pick a tier, difficulty and boss, then read ten timelines.
 *
 * State lives here because every piece of it is shared. The one rule the spec is
 * strict about is enforced in one place, below: nothing is drawn until a difficulty
 * AND a boss AND a spec are all chosen, because until then there is no single
 * timeline the page could honestly be showing.
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
        // Newest tier first, so the default is the one being progressed now.
        if (z.length > 0) setZoneId(z[0].id);
      })
      .catch((e: Error) => setBootError(e.message));
  }, []);

  const spec = useMemo(
    () => meta?.specs.find((s) => s.key === specKey) ?? null,
    [meta, specKey],
  );

  // Seed the toggles from the catalog's defaults whenever the spec changes. Doing it
  // here rather than in SpellToggles keeps the toggle component free of state.
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
        // A slow request for a boss the user has already navigated away from must
        // not overwrite the one they are now looking at.
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
        <h1>Raidline</h1>
        <p>Could not reach the backend: {bootError}</p>
        <p className="hint">
          Is it running? <code>uvicorn app.main:app --port 8600</code>
        </p>
      </div>
    );
  }

  if (!meta) return <div className="booting">Loading Raidline...</div>;

  const specLabel = spec?.label ?? specKey;
  const bossName = timelines?.encounter.name ?? "";

  return (
    <div className="app">
      <header className="masthead">
        <h1>
          <span className="brand">Raidline</span>
          {bossName ? (
            <span className="subject">
              {specLabel} <span className="vs">vs.</span> {bossName}
            </span>
          ) : (
            <span className="subject muted">Pick a difficulty and a boss</span>
          )}
        </h1>
        {!meta.live && (
          <p className="fixture-banner">
            Offline demo data. These are generated fixtures, not real rankings. Add
            Warcraft Logs credentials to <code>backend/.env</code> for live parses.
          </p>
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

      {spec && (
        <SpellToggles
          groups={spec.groups}
          enabled={enabled}
          onToggle={toggleSpell}
          onGroup={setGroup}
        />
      )}

      <main className="board">
        {!ready && (
          <p className="placeholder">
            Choose a difficulty and a boss above. Nothing is shown until both are
            set, since there would be no single timeline to show.
          </p>
        )}
        {ready && loading && <p className="placeholder">Reading logs...</p>}
        {ready && error && <p className="error">{error}</p>}
        {ready && !loading && !error && timelines && (
          <Timeline
            data={timelines}
            spec={spec}
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
