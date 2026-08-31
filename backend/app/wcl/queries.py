"""The GraphQL documents Raidlines sends to Warcraft Logs.

Kept as plain strings in one file so the whole API surface we depend on is visible
at a glance:

  ZONES      what raids and bosses exist, so the boss row is never hardcoded
  RANKINGS   the top parses for one boss + difficulty + spec, with gear
  FIGHT      one player's casts within one logged pull
  TALENTS    that player's talent loadout, as an in-game import string
  ENEMY      what the boss and its adds cast during one pull

FIGHT deliberately does not filter by ability. Measured against the live API, a
filtered and an unfiltered cast query cost the same 2 points, so narrowing it buys
nothing and costs plenty: trinkets could not be detected from what players actually
use, and every catalog edit would invalidate the cache.
"""

# characterRankings and events return an untyped JSON scalar, hence no subselection.

ZONES = """
query Zones {
  worldData {
    expansions {
      id
      name
      zones {
        id
        name
        frozen
        encounters { id name }
        difficulties { id name }
      }
    }
  }
}
"""

RANKINGS = """
query Rankings(
  $encounterId: Int!
  $difficulty: Int!
  $className: String!
  $specName: String!
  $metric: CharacterRankingMetricType!
  $page: Int
) {
  worldData {
    encounter(id: $encounterId) {
      id
      name
      characterRankings(
        difficulty: $difficulty
        className: $className
        specName: $specName
        metric: $metric
        page: $page
        # Adds gear and talents to each ranking. Gear slots 12 and 13 are the
        # trinkets, which is where the trinket list comes from.
        includeCombatantInfo: true
      )
    }
  }
}
"""

# masterData gives the icon Warcraft Logs itself uses for each ability, which beats
# the hand-maintained fallback in spells.py because it tracks the live game build.
FIGHT = """
query Fight(
  $code: String!
  $fightId: Int!
  $filter: String!
) {
  reportData {
    report(code: $code) {
      code
      startTime
      masterData {
        abilities { gameID name icon }
      }
      fights(fightIDs: [$fightId]) {
        id
        name
        startTime
        endTime
        kill
        fightPercentage
      }
      events(
        fightIDs: [$fightId]
        dataType: Casts
        filterExpression: $filter
        limit: 3000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

# The loadout string the game's talent UI accepts, e.g. "CUQAAAAAAAAAAAAAAAgx2M...".
# actorID is the report-scoped player ID, which cast events carry as sourceID.
TALENTS = """
query Talents($code: String!, $fightId: Int!, $actorId: Int!) {
  reportData {
    report(code: $code) {
      fights(fightIDs: [$fightId]) {
        id
        talentImportCode(actorID: $actorId)
      }
    }
  }
}
"""

RATE_LIMIT = """
query RateLimit {
  rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }
}
"""


# Everything hostile that cast during the fight, plus the actor list needed to tell
# the boss from its adds. One query per pull; the result is shared by every spec,
# since a boss does the same thing whoever is looking at it.
ENEMY_CASTS = """
query EnemyCasts($code: String!, $fightId: Int!) {
  reportData {
    report(code: $code) {
      masterData {
        actors { id name type subType }
        abilities { gameID name icon }
      }
      fights(fightIDs: [$fightId]) { id name startTime endTime }
      events(
        fightIDs: [$fightId]
        dataType: Casts
        hostilityType: Enemies
        limit: 3000
      ) { data }
    }
  }
}
"""
