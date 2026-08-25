/**
 * A hover card in the game's own tooltip style: name, then what it does.
 *
 * Positioned fixed against the trigger's bounding box rather than nested inside it,
 * because the triggers are cast markers packed into a scrolling row with overflow
 * clipping. A nested card would be cut off by the first ancestor that clips.
 *
 * Flips to the left or above when it would otherwise run off the viewport, which
 * matters here: the rightmost markers on a long fight sit at the screen edge.
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

const GAP = 10;
const WIDTH = 320;

export default function Tooltip({ content, children }: Props) {
  const trigger = useRef<HTMLSpanElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useLayoutEffect(() => {
    if (!open || !trigger.current) return;
    const anchor = trigger.current.getBoundingClientRect();
    const height = card.current?.offsetHeight ?? 120;

    let left = anchor.left;
    if (left + WIDTH + GAP > window.innerWidth) {
      left = Math.max(GAP, anchor.right - WIDTH);
    }
    // Below by default, above when there is no room, and never off the top.
    let top = anchor.bottom + GAP;
    if (top + height + GAP > window.innerHeight) {
      top = Math.max(GAP, anchor.top - height - GAP);
    }
    setPos({ top, left });
  }, [open]);

  if (!content?.description) return <>{children}</>;

  return (
    <span
      ref={trigger}
      className="tip-anchor"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open && (
        <div
          ref={card}
          className="tip"
          role="tooltip"
          style={{ top: pos.top, left: pos.left, width: WIDTH }}
        >
          <div className="tip-name">{content.name}</div>
          <div className="tip-body">{content.description}</div>
        </div>
      )}
    </span>
  );
}
