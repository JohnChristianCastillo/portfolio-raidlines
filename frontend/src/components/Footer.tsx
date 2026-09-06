/**
 * Attribution, and the line that keeps this project clearly inside Blizzard's
 * fan-content lane.
 *
 * None of the art here is ours. Ability icons are served from Wowhead's CDN, the
 * class, specialisation and hero tree icons in public/assets came off Warcraft Wiki,
 * and all of them are Blizzard's work. Blizzard permits that for non-commercial fan
 * projects and no licence makes it free, so the least this owes them is a credit and
 * a plain statement that nobody here speaks for them.
 *
 * The data has owners too. Every ranking and every cast time comes from Warcraft
 * Logs, and every tooltip from Blizzard's own Game Data API.
 */

export default function Footer() {
  return (
    <footer className="site-footer">
      <p>
        Rankings and combat logs from{" "}
        <a href="https://www.warcraftlogs.com" target="_blank" rel="noopener noreferrer">
          Warcraft Logs
        </a>
        . Ability names and tooltips from the Blizzard Game Data API. Ability icons
        served by{" "}
        <a href="https://www.wowhead.com" target="_blank" rel="noopener noreferrer">
          Wowhead
        </a>
        .
      </p>
      <p className="disclaimer">
        Raidlines is an unofficial fan project, not affiliated with or endorsed by
        Blizzard Entertainment. World of Warcraft and related marks, artwork and
        assets are trademarks or registered trademarks of Blizzard Entertainment, Inc.
        in the U.S. and other countries.
      </p>
    </footer>
  );
}
