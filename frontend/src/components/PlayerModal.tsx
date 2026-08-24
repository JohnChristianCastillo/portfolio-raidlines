/**
 * One parse, twice over: the Method Raid Tools note for the spells currently
 * toggled on, and the talent loadout string the game's own import box accepts.
 *
 * Two separate copies rather than one blob, because they are pasted into different
 * places: the note into MRT, the loadout into the talent UI.
 */

import { useEffect, useMemo, useState } from "react";
import { fetchTalents, type Player } from "../api";
import { buildReminder, reminderHeader } from "../mrt";

interface Props {
  player: Player;
  encounterName: string;
  difficultyName: string;
  enabled: ReadonlySet<number>;
  onClose: () => void;
}

type Copied = "" | "note" | "talents";

export default function PlayerModal({
  player,
  encounterName,
  difficultyName,
  enabled,
  onClose,
}: Props) {
  const [copied, setCopied] = useState<Copied>("");
  const [talents, setTalents] = useState("");
  const [talentError, setTalentError] = useState("");
  const [loadingTalents, setLoadingTalents] = useState(false);

  const note = useMemo(() => {
    const body = buildReminder(player.casts, enabled);
    const header = reminderHeader(player, encounterName, difficultyName);
    return body ? `${header}\n${body}` : header;
  }, [player, enabled, encounterName, difficultyName]);

  const lineCount = useMemo(
    () => player.casts.filter((c) => enabled.has(c.toggle)).length,
    [player, enabled],
  );

  // Fetched on open rather than on click, so the button is ready by the time
  // anyone reaches for it. One query, and only for the parse actually opened.
  useEffect(() => {
    let cancelled = false;
    setLoadingTalents(true);
    setTalents("");
    setTalentError("");
    fetchTalents(player)
      .then((r) => {
        if (cancelled) return;
        if (r.importCode) setTalents(r.importCode);
        else setTalentError("this log carries no talent loadout");
      })
      .catch((e: Error) => !cancelled && setTalentError(e.message))
      .finally(() => !cancelled && setLoadingTalents(false));
    return () => {
      cancelled = true;
    };
  }, [player]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function copy(what: Copied, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      window.setTimeout(() => setCopied(""), 1800);
    } catch {
      // Needs a secure context, which http on a LAN address is not. Both boxes
      // stay selectable.
      setCopied("");
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${player.name}: reminder note and talents`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-head">
          <div>
            <h2>
              {player.name}
              {player.server && <span className="realm">-{player.server}</span>}
            </h2>
            <p className="modal-sub">
              rank #{player.rank} on {encounterName} {difficultyName} -{" "}
              {(player.amount / 1000).toFixed(1)}k dps -{" "}
              <a href={player.reportUrl} target="_blank" rel="noreferrer">
                open the log
              </a>
            </p>
          </div>
          <button type="button" className="modal-close" onClick={onClose}>
            Close
          </button>
        </header>

        <section className="modal-section">
          <div className="section-head">
            <h3>Reminders</h3>
            <button
              type="button"
              className="copy"
              onClick={() => copy("note", note)}
              disabled={lineCount === 0}
            >
              {copied === "note" ? "Copied" : "Copy note"}
            </button>
          </div>
          <p className="modal-hint">
            {lineCount === 0
              ? "Nothing toggled on."
              : `${lineCount} reminders. Paste into an MRT note.`}
          </p>
          <textarea className="note" readOnly value={note} spellCheck={false} />
        </section>

        <section className="modal-section">
          <div className="section-head">
            <h3>Talents</h3>
            <button
              type="button"
              className="copy"
              onClick={() => copy("talents", talents)}
              disabled={!talents}
            >
              {copied === "talents" ? "Copied" : "Copy talents"}
            </button>
          </div>
          <p className="modal-hint">
            {loadingTalents
              ? "Loading..."
              : talentError || "Paste into the game's talent import box."}
          </p>
          {talents && (
            <textarea
              className="note note--talents"
              readOnly
              value={talents}
              spellCheck={false}
            />
          )}
        </section>
      </div>
    </div>
  );
}
