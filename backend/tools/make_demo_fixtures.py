"""Generate the offline demo fixtures Raidlines falls back to without credentials.

Run once (or after changing the catalog):

    python tools/make_demo_fixtures.py

What this writes is SYNTHETIC. It is not scraped, not a real ranking, and the player
names are invented. Its only job is to give the UI a realistic-sized board to be
built and reviewed against before the Warcraft Logs client exists, and to keep the
app demoable on a machine with no API credentials.

The one thing taken from reality is the shape of the timeline: the base cast pattern
below is a real Subtlety Rogue kill's cooldown usage (the example reminder string in
the spec), so pacing, density and clustering look like the real thing rather than
like evenly spaced noise. Each of the ten rows jitters that base differently, the way
ten different players do.

tools/capture.py replaces all of this with real recorded responses once credentials
are configured.
"""

import json
import random
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "app" / "fixtures"

# A stand-in tier. Replaced by a real capture the moment credentials exist; until
# then the boss row has something to draw and is honestly labelled as a demo.
ZONE_ID = 9001
ZONE_NAME = "Demo Raid (offline fixtures)"
BOSSES = [
    (900101, "Training Dummy Prime"),
    (900102, "The Rehearsal"),
    (900103, "Placeholder, Herald of Fixtures"),
    (900104, "Offline Mode"),
    (900105, "The Understudy"),
    (900106, "Dry Run"),
    (900107, "Mock Encounter"),
    (900108, "The Stand-In"),
]

DIFFICULTIES = [
    {"id": 1, "name": "LFR"},
    {"id": 3, "name": "Normal"},
    {"id": 4, "name": "Heroic"},
    {"id": 5, "name": "Mythic"},
]

# Spell ID -> (display name, wowhead icon slug). Mirrors app/spells.py; a fixture
# stands in for a report's masterData, which is where icons come from live.
ABILITIES = {
    121471: ("Shadow Blades", "inv_knife_1h_grimbatolraid_d_03"),
    185313: ("Shadow Dance", "ability_rogue_shadowdance"),
    185311: ("Crimson Vial", "ability_rogue_crimsonvial"),
    212283: ("Symbols of Death", "spell_shadow_rune"),
    280719: ("Secret Technique", "ability_rogue_secrettechnique"),
    381623: ("Thistle Tea", "inv_drink_milk_05"),
    1856: ("Vanish", "ability_vanish"),
    1966: ("Feint", "ability_rogue_feint"),
    5277: ("Evasion", "spell_shadow_shadowward"),
    31224: ("Cloak of Shadows", "spell_shadow_nethercloak"),
}

# The real kill's pattern: (seconds since pull, spell id).
BASE = [
    (2.7, 121471), (2.7, 185313), (10.8, 185313), (25.7, 185311), (28.5, 185313),
    (48.3, 185313), (69.4, 185313), (85.5, 185311), (95.8, 121471), (95.8, 185313),
    (106.5, 185313), (141.6, 185313), (164.8, 185313), (187.7, 121471),
    (187.8, 185313), (197.8, 185313), (210.8, 185313), (233.4, 185313),
    (255.4, 185313), (279.6, 185313), (279.7, 121471), (289.1, 185313),
    (321.1, 185313), (351.4, 185313), (373.6, 185313), (373.6, 121471),
    (382.7, 185313), (393.9, 185313), (417.2, 185313), (439.3, 185311),
    (449.1, 185313), (464.8, 185313), (464.8, 121471), (475.7, 185313),
]

# The remaining catalog spells, so every toggle group has something to show. Cadence
# is roughly each spell's real cooldown, offset so they do not all land together.
EXTRAS = [
    (212283, 30.0, 8.0),   # Symbols of Death
    (280719, 45.0, 22.0),  # Secret Technique
    (1856, 120.0, 60.0),   # Vanish
    (1966, 95.0, 35.0),    # Feint
    (381623, 90.0, 47.0),  # Thistle Tea
    (5277, 180.0, 110.0),  # Evasion
    (31224, 150.0, 74.0),  # Cloak of Shadows
]

PLAYERS = [
    ("Shadowstitch", "Kazzak", "EU", "Fixture Raiding"),
    ("影之舞者", "Golemagg", "EU", "演示公会"),
    ("Nightbleed", "Tarren Mill", "EU", "Placeholder"),
    ("暗夜潜行", "Illidan", "US", "样本战队"),
    ("Quietstep", "Area 52", "US", "Demo Data"),
    ("Umbrafang", "Twisting Nether", "EU", "Fixture Raiding"),
    ("虚空之刃", "Stormrage", "US", "示例小队"),
    ("Duskwhisper", "Ravencrest", "EU", "Offline"),
    ("Grimveil", "Draenor", "EU", "Mock Guild"),
    ("低语之影", "Blackrock", "US", "占位公会"),
]


def zones_fixture() -> dict:
    return {
        "worldData": {
            "expansions": [
                {
                    "id": 900,
                    "name": "Offline Fixtures",
                    "zones": [
                        {
                            "id": ZONE_ID,
                            "name": ZONE_NAME,
                            "frozen": False,
                            "encounters": [{"id": i, "name": n} for i, n in BOSSES],
                            "difficulties": DIFFICULTIES,
                        }
                    ],
                }
            ]
        }
    }


def casts_for(rng: random.Random, skill: float) -> tuple[list[tuple[float, int]], float]:
    """One player's casts: the base pattern, personalised.

    skill runs 0 (rank 1) to 1 (rank 10) and drives both how late the pull runs and
    how loosely cooldowns are held, which is what makes the board readable as a
    ranking rather than ten identical rows.
    """
    stretch = 1.0 + skill * 0.16
    slop = 1.0 + skill * 3.0

    out: list[tuple[float, int]] = []
    for t, spell in BASE:
        jitter = rng.uniform(-slop, slop * 1.8)
        out.append((max(0.0, round(t * stretch + jitter, 1)), spell))

    duration = round(BASE[-1][0] * stretch + rng.uniform(4.0, 18.0), 1)

    for spell, cooldown, offset in EXTRAS:
        t = offset + rng.uniform(0.0, 6.0)
        while t < duration - 5.0:
            out.append((round(t, 1), spell))
            t += cooldown * rng.uniform(1.0, 1.5) + skill * 12.0

    # A couple of dropped casts, because nobody plays a fight perfectly.
    for _ in range(int(skill * 4)):
        if len(out) > 12:
            out.pop(rng.randrange(len(out)))

    out.sort()
    return out, duration


def fight_fixture(code: str, fight_id: int, casts, duration: float, kill: bool) -> dict:
    # Absolute timestamps, exactly as Warcraft Logs reports them: a report epoch in
    # milliseconds, with the pull some way into it.
    report_start = 1_770_000_000_000
    fight_start = report_start + 480_000
    return {
        "reportData": {
            "report": {
                "code": code,
                "startTime": report_start,
                "masterData": {
                    "abilities": [
                        {"gameID": sid, "name": name, "icon": icon}
                        for sid, (name, icon) in ABILITIES.items()
                    ]
                },
                "fights": [
                    {
                        "id": fight_id,
                        "name": "Demo Encounter",
                        "startTime": fight_start,
                        "endTime": fight_start + int(duration * 1000),
                        "kill": kill,
                        "fightPercentage": 0 if kill else 3.4,
                    }
                ],
                "events": {
                    "data": [
                        {
                            "timestamp": fight_start + int(t * 1000),
                            "type": "cast",
                            "sourceID": 7,
                            "abilityGameID": spell,
                        }
                        for t, spell in casts
                    ],
                    "nextPageTimestamp": None,
                },
            }
        }
    }


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for stale in FIXTURES.glob("*.json"):
        stale.unlink()

    (FIXTURES / "zones.json").write_text(
        json.dumps(zones_fixture(), ensure_ascii=False, indent=1), encoding="utf-8"
    )

    written = 1
    for encounter_id, encounter_name in BOSSES:
        for difficulty in (3, 4, 5):
            # Seeded per boss and difficulty so regenerating is reproducible and a
            # diff of the fixtures is readable.
            rng = random.Random(encounter_id * 100 + difficulty)
            rankings = []
            for rank, (name, server, region, guild) in enumerate(PLAYERS):
                skill = rank / (len(PLAYERS) - 1)
                casts, duration = casts_for(rng, skill)
                code = f"demo{encounter_id}{difficulty}{rank:02d}"
                fight_id = 10 + rank

                (FIXTURES / f"fight_{code}_{fight_id}.json").write_text(
                    json.dumps(
                        fight_fixture(code, fight_id, casts, duration, kill=True),
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                written += 1

                rankings.append(
                    {
                        "name": name,
                        "class": "Rogue",
                        "spec": "Subtlety",
                        # Falls off with rank the way a real ranking page does.
                        "amount": round(193_200 * (1 - skill * 0.11), 1),
                        "duration": int(duration * 1000),
                        "startTime": 1_770_000_480_000,
                        "report": {"code": code, "fightID": fight_id},
                        "guild": {"name": guild},
                        "server": {"name": server, "region": region},
                    }
                )

            variables = {
                "encounterId": encounter_id,
                "difficulty": difficulty,
                "className": "Rogue",
                "specName": "Subtlety",
            }
            name = (
                f"rankings_{variables['encounterId']}_{variables['difficulty']}"
                f"_{variables['className']}-{variables['specName']}".lower()
            )
            (FIXTURES / f"{name}.json").write_text(
                json.dumps(
                    {
                        "worldData": {
                            "encounter": {
                                "id": encounter_id,
                                "name": encounter_name,
                                "characterRankings": {
                                    "page": 1,
                                    "hasMorePages": False,
                                    "count": len(rankings),
                                    "rankings": rankings,
                                },
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            written += 1

    print(f"wrote {written} fixture files to {FIXTURES}")


if __name__ == "__main__":
    main()
