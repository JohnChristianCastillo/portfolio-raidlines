/**
 * A hover card in the game's own tooltip style: name, then what it does.
 *
 * Positioned above the cursor, not against the trigger. Two reasons, one of them a
 * bug worth remembering: the anchor is display:contents so that wrapping an
 * absolutely positioned cast marker does not add a box and shift the timeline. An
 * element with display:contents generates no box at all, so getBoundingClientRect
 * on it returns zeros, and anchoring to the trigger put every card in the top left
 * corner of the window.
 *
 * Above the cursor rather than below it because the pointer is already on the icon,
 * so a card below would cover the row underneath, and one at the trigger's corner
 * means looking away from what you are pointing at. It flips below only when there
 * is no room above, and is clamped to the viewport horizontally.
 *
 * pointer-events: none, so the card can never sit between the cursor and the thing
 * it describes, whatever the geometry.
 *
 * Renders nothing when there is no text. Potions have no description available, so
 * their markers keep the plain browser tooltip rather than opening an empty card.
 */

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

export interface TooltipContent {
  name: string;
  description?: string;
}

interface Props {
  content: TooltipContent | null;
  children: ReactNode;
}

const GAP = 14;
const EDGE = 8;
const WIDTH = 320;

export default function Tooltip({ content, children }: Props) {
  const card = useRef<HTMLDivElement>(null);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const [placed, setPlaced] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    if (!cursor || !card.current) {
      setPlaced(null);
      return;
    }
    const height = card.current.offsetHeight;

    // Above the cursor by default; below only if it would run off the top.
    let top = cursor.y - height - GAP;
    if (top < EDGE) top = cursor.y + GAP;

    // Centred on the cursor, then pulled back inside the viewport.
    let left = cursor.x - WIDTH / 2;
    left = Math.max(EDGE, Math.min(left, window.innerWidth - WIDTH - EDGE));

    setPlaced({ top, left });
  }, [cursor]);

  if (!content?.description) return <>{children}</>;

  return (
    <span
      className="tip-anchor"
      onMouseEnter={(e) => setCursor({ x: e.clientX, y: e.clientY })}
      onMouseLeave={() => setCursor(null)}
    >
      {children}
      {cursor && (
        <div
          ref={card}
          className="tip"
          role="tooltip"
          style={{
            top: placed?.top ?? -9999,
            left: placed?.left ?? -9999,
            width: WIDTH,
            // Hidden for the one frame between mounting and measuring, so the card
            // never flashes at its provisional position.
            visibility: placed ? "visible" : "hidden",
          }}
        >
          <div className="tip-name">{content.name}</div>
          <div className="tip-body">{content.description}</div>
        </div>
      )}
    </span>
  );
}
