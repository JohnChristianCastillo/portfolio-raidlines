/**
 * A spell icon from wowhead's CDN, falling back to the spell's short badge when the
 * slug is stale or the CDN is unreachable.
 */

import { useEffect, useState } from "react";

const CDN = "https://wow.zamimg.com/images/wow/icons/medium";

/**
 * Slugs arrive both bare (from the catalog) and with a .jpg (from a report's
 * masterData). Appending blindly gives a .jpg.jpg URL that 404s.
 */
function iconUrl(icon: string): string {
  const slug = icon.replace(/\.(jpg|jpeg|png|gif|webp)$/i, "");
  return `${CDN}/${slug}.jpg`;
}

interface Props {
  icon: string;
  short: string;
  alt: string;
  /** Native tooltip. Without it a bare icon says nothing on hover. */
  title?: string;
}

export default function SpellIcon({ icon, short, alt, title }: Props) {
  const [failed, setFailed] = useState(false);

  // A changed slug deserves a fresh attempt.
  useEffect(() => setFailed(false), [icon]);

  if (!icon || failed) {
    return (
      <span
        className="spell-icon spell-icon--text"
        aria-label={alt}
        title={title ?? alt}
      >
        {short}
      </span>
    );
  }

  return (
    <img
      className="spell-icon"
      src={iconUrl(icon)}
      alt={alt}
      title={title ?? alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
