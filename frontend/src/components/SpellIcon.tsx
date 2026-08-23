/**
 * A spell icon, with a graceful way to not have one.
 *
 * Icons come from the game's own art, served by wowhead's CDN by slug. Two things
 * can go wrong: the slug can be stale (the catalog is hand-maintained, and a live
 * log's masterData is more current), or the CDN can simply be unreachable, which is
 * the normal case on a machine with no internet or behind a strict content policy.
 *
 * Either way the fallback is the spell's short badge, so a timeline stays readable
 * with no images at all rather than turning into a row of broken-image glyphs.
 */

import { useEffect, useState } from "react";

const CDN = "https://wow.zamimg.com/images/wow/icons/medium";

/**
 * Icon slugs arrive in two forms and only one of them has an extension: the catalog
 * in spells.py stores "ability_rogue_shadowdance", while a report's masterData gives
 * "ability_rogue_shadowdance.jpg". Appending .jpg blindly produced a .jpg.jpg URL
 * that 404s, so every live icon quietly degraded to a text badge while fixtures
 * looked fine. Normalise to the bare slug and add the extension once.
 */
function iconUrl(icon: string): string {
  const slug = icon.replace(/\.(jpg|jpeg|png|gif|webp)$/i, "");
  return `${CDN}/${slug}.jpg`;
}

interface Props {
  icon: string;
  short: string;
  alt: string;
}

export default function SpellIcon({ icon, short, alt }: Props) {
  const [failed, setFailed] = useState(false);

  // A changed slug deserves a fresh attempt; without this a single failure would
  // stick to the component for as long as it is mounted.
  useEffect(() => setFailed(false), [icon]);

  if (!icon || failed) {
    return (
      <span className="spell-icon spell-icon--text" aria-label={alt}>
        {short}
      </span>
    );
  }

  return (
    <img
      className="spell-icon"
      src={iconUrl(icon)}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
