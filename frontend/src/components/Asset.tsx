/**
 * An image we ship ourselves, under public/assets.
 *
 * Separate from SpellIcon because the two fail differently. Spell icons come from a
 * CDN by slug and fall back to a text badge when a slug is stale; these are files in
 * the build, so a miss means the asset fetcher has not run and the honest thing is
 * an empty box rather than a guess.
 */

import { useEffect, useState } from "react";

interface Props {
  path: string;
  alt: string;
  className?: string;
}

export default function Asset({ path, alt, className }: Props) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [path]);

  if (failed) return <span className={className ?? "asset asset--missing"} />;

  return (
    <img
      className={className ?? "asset"}
      src={`${import.meta.env.BASE_URL}assets/${path}`}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
