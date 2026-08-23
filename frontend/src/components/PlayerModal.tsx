/**
 * One parse as a Method Raid Tools note, ready to paste. Covers the spells
 * currently toggled on. The header comment lines are copied too; MRT ignores them.
 */

import { useEffect, useMemo, useState } from "react";
import type { Player } from "../api";
import { buildReminder, reminderHeader } from "../mrt";

interface Props {
  player: Player;
  encounterName: string;
  difficultyName: string;
  enabled: ReadonlySet<number>;
  onClose: () => void;
}

export default function PlayerModal({
  player,
  encounterName,
  difficultyName,
  enabled,
  onClose,
}: Props) {
  const [copied, setCopied] = useState(false);

  const note = useMemo(() => {
    const body = buildReminder(player.casts, enabled);
    const header = reminderHeader(player, encounterName, difficultyName);
    return body ? `${header}\n${body}` : header;
  }, [player, enabled, encounterName, difficultyName]);

  const lineCount = useMemo(
    () => player.casts.filter((c) => enabled.has(c.spellId)).length,
    [player, enabled],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(note);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // Needs a secure context, which http on a LAN address is not. The textarea
      // stays selectable.
      setCopied(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`MRT note for ${player.name}`}
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

        <p className="modal-hint">
          {lineCount === 0
            ? "Nothing toggled on."
            : `${lineCount} reminders. Paste into an MRT note.`}
        </p>

        <textarea className="note" readOnly value={note} spellCheck={false} />

        <footer className="modal-foot">
          <button type="button" className="copy" onClick={copy}>
            {copied ? "Copied" : "Copy note"}
          </button>
          <span className="modal-note">Absolute times only.</span>
        </footer>
      </div>
    </div>
  );
}
