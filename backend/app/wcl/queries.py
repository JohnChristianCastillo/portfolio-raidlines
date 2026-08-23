"""The GraphQL documents Raidline sends to Warcraft Logs.

Kept as plain strings in one file so the whole API surface we depend on is visible
at a glance:

  ZONES      what raids and bosses exist, so the boss row is never hardcoded
  RANKINGS   the top parses for one boss + difficulty + spec, with gear
  FIGHT      one player's casts within one logged pull
  TALENTS    that player's talent loadout, as an in-game import string

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
        metric: dps
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
