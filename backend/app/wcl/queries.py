"""The GraphQL documents Raidline sends to Warcraft Logs.

Kept as plain strings in one file so the whole API surface we depend on is visible
at a glance. Three queries cover the app:

  ZONES      what raids and bosses exist, so the boss row is never hardcoded
  RANKINGS   the top parses for one boss + difficulty + spec
  FIGHT      one player's tracked casts within one logged pull

Note on cost: the rate limit is point-based and scales with returned data, so
RANKINGS asks for one page and FIGHT filters server-side by ability ID. Pulling a
whole fight's cast log unfiltered and discarding it here would work and would also
burn the hourly budget in a handful of clicks.
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
        limit: 2000
      ) {
        data
        nextPageTimestamp
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
