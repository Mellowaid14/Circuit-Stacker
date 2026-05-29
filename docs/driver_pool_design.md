# Global Driver Pool Design

## Goal

Move Circuit Stackers from per-season generated AI fields to one persistent racing world.

All human and AI drivers live in a shared driver pool. Championships draw from that pool based on series style, tier, rating, and eligibility. Drivers age through seasons, retire, and are replaced by new rookies.

This should be implemented in small phases so the app stays playable after each step.

## Core Concepts

### Driver Pool

The driver pool is stored in SQLite.

Each career save should have its own driver pool. Driver pools should not be shared across all saves by default.

Recommended file:

```text
<save_name>_world.db
```

Recommended location:

```text
saves/<save_name>_world.db
```

This makes every save its own racing universe. Starting a new career creates a new driver pool for that save. Loading a save loads that save's own pool.

SQLite is preferred over JSON because this system will eventually need filtering, sorting, career history, retirements, and season/race records. SQLite is built into Python and still keeps everything in one local file.

When creating a new save, the app should create that save's world database and pre-simulate AI seasons before adding the human players. This makes the world feel established, with upper-tier championships already populated.

Pre-simulation goal:

```text
simulate AI-only seasons until all top-tier championships are full
```

Top tier means Tier 5.

Initial world generation should create enough AI drivers to fill all planned championship instances, plus a 10-20% rookie buffer.

After the world is established, human players are added as newly generated rookies entering the lower ladder.

Each save should start its world year from the current real year when the save is created.

### Driver Identity

Every driver gets a stable ID. Names are no longer the primary identity because names may collide or change later.

Human players are stored in the same pool as AI drivers, but with `is_human: true`.

Humans are immune to forced retirement.

### Driver Ratings

Each driver has one global MMR. This keeps ladder movement clear: tiers represent overall career progress, and MMR decides where drivers sit in the global racing world.

Each driver also has a primary discipline:

- `Sports Car`
- `Oval`
- `Open Wheel`

When a driver enters a non-primary discipline, their effective selection MMR is reduced by the cross-discipline penalty. The stored MMR does not split by discipline.

Example:

```json
{
  "id": "uuid",
  "name": "Alex Sumner",
  "is_human": true,
  "status": "active",
  "primary_style": "Sports Car",
  "mmr": 1250,
  "seasons_completed": 0,
  "career_starts": 0,
  "wins": 0,
  "championships": 0,
  "retirement_eligible": false
}
```

## Initial Database Schema

SQLite table:

```sql
CREATE TABLE drivers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_human INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    primary_style TEXT NOT NULL,
    mmr INTEGER NOT NULL DEFAULT 1000,
    sports_car_rating INTEGER NOT NULL DEFAULT 1000,
    oval_rating INTEGER NOT NULL DEFAULT 1000,
    open_wheel_rating INTEGER NOT NULL DEFAULT 1000,
    seasons_completed INTEGER NOT NULL DEFAULT 0,
    retirement_after_seasons INTEGER,
    career_starts INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    championships INTEGER NOT NULL DEFAULT 0,
    last_series_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Optional metadata table:

```sql
CREATE TABLE world_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Championship win history:

```sql
CREATE TABLE driver_championship_wins (
    id TEXT PRIMARY KEY,
    driver_id TEXT NOT NULL,
    championship_id TEXT NOT NULL,
    championship_name TEXT NOT NULL,
    season_year INTEGER NOT NULL,
    style TEXT NOT NULL,
    tier INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(driver_id) REFERENCES drivers(id)
);
```

Race win history:

```sql
CREATE TABLE driver_race_wins (
    id TEXT PRIMARY KEY,
    driver_id TEXT NOT NULL,
    championship_id TEXT NOT NULL,
    championship_name TEXT NOT NULL,
    race_num INTEGER NOT NULL,
    track TEXT NOT NULL,
    layout TEXT NOT NULL,
    season_year INTEGER NOT NULL,
    style TEXT NOT NULL,
    tier INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(driver_id) REFERENCES drivers(id)
);
```

Set:

```text
schema_version = 1
```

The database replaces the earlier JSON idea:

```text
Do not use driver_pool.json for the working driver pool.
```

The app may still support JSON export/import later for backups or sharing, but SQLite should be the live storage.

## Driver Record Shape

In Python, drivers can still be represented as dictionaries when loaded from SQLite:

```json
{
  "id": "uuid",
  "name": "Driver Name",
  "is_human": false,
  "status": "active",
  "primary_style": "Sports Car",
  "ratings": {
    "Sports Car": 1000,
    "Oval": 1000,
    "Open Wheel": 1000
  },
  "seasons_completed": 0,
  "career_starts": 0,
  "wins": 0,
  "championships": 0
}
```

Status values:

- `active`
- `retired`

## Championship Field Selection

When starting a championship, the app should build the field from the global driver pool.

Recommended first version:

1. Determine championship style: `Sports Car`, `Oval`, or `Open Wheel`.
2. Determine championship tier.
3. Select all active AI drivers.
4. Rank AI by global MMR, applying the non-primary style penalty when needed.
5. Pull from the rating band appropriate for that tier.
6. Add human players.
7. If there are not enough AI drivers, generate new rookies.

AI drivers should prefer championships in their primary style.

Phase 2 implementation note:

- The player's selected championship now pulls AI from the save-specific SQLite driver pool.
- If the pool does not have enough active AI, rookies are generated at the baseline MMR.
- A non-primary style uses a 150-point effective MMR penalty.
- AI availability across the full simulated world is intentionally deferred to a later phase.

If an AI driver would otherwise drop down a tier, they can switch to another championship within the same tier first. This helps avoid unnecessary demotion when a same-tier opportunity is available in another style.

If an AI driver switches discipline to avoid tier demotion, the non-primary style MMR penalty still applies when evaluating that same-tier option.

### Tier Pull Logic

Simple first implementation:

- Tier 5 pulls from the highest-rated drivers.
- Tier 4 pulls from the next group.
- Tier 3 pulls from the middle group.
- Tier 2 pulls from the lower group.
- Tier 1 pulls from the lowest-rated and rookie group.

This can be refined later into exact rating bands.

Implemented first tier-aware selection pass:

- The player's championship now pulls AI from a tier slice of the ranked driver pool.
- Tier 1 uses the lower-rated/rookie side of the pool.
- Tier 5 uses the highest-rated side of the pool.
- If the target tier slice is too small, nearby drivers are used as fallback so the field still fills.

## Player Championship Selection

As players climb the ladder, the championship selection screen should show all available player championships grouped by tier.

Display order:

```text
highest available tier first
then lower tiers below
```

Example:

```text
Tier 4 Championships
Tier 3 Championships
Tier 2 Championships
Tier 1 Championships
```

This lets players see their best available options first while still allowing lower-tier choices if they want them.

Promotion/demotion and next-year placement should use MMR as the main driver, but season finishing position should still matter. Strong season results should help a driver move up faster, while poor results should make demotion more likely.

## World Simulation Championship Counts

All AI drivers start in Tier 1 and have to work their way up.

To support larger rookie/lower-tier fields, lower tiers should run multiple AI groups:

- Tier 1 runs 6 instances of each available championship.
- Tier 2 runs 3 instances of each available championship.
- Tier 3 and above run 1 instance of each available championship.

This means the lower levels can hold more drivers, while higher tiers become more selective.

AI drivers can only be assigned to one championship per year.

Human players also lock into one championship per year and cannot change championship mid-season.

Each championship instance should still use the existing random field-size logic up to that championship's `Max_Opp` value.

## Human Players

Humans are added to the driver pool when creating a new career.

Human fields:

- `is_human: true`
- `status: active`
- ratings start from the baseline MMR
- primary style can be selected during career creation in a future step

Player AI difficulty and MMR should stay separate.

- AI difficulty controls exported iRacing season difficulty.
- MMR controls ladder placement and career progression.

This allows any real player skill level to play through the full ladder while the app learns their actual racing level over time.

Initial human MMR baseline:

```text
1000 MMR
```

Primary style rule:

- A human player's primary style is assigned from the first championship they select.
- Example: if the first selected championship is Oval, their primary style becomes `Oval`.

## MMR / Rating Updates

Ratings should update after every race.

Each completed race should update the rating for the discipline being raced.

Suggested first race update:

- Class winner gets the largest increase.
- Top 25% gains rating.
- Middle 50% gets small movement or stays near even.
- Bottom 25% loses rating.
- Driver skill should weight simulated results, but never make outcomes guaranteed.
- Use an Elo/chess-style approach where each driver is rated against every other driver in the race.

For co-op/human results, use the manually entered or imported finish positions just like AI results.

### Elo-Style Race Rating Concept

Each race can be treated as many head-to-head comparisons.

For every pair of drivers in the same class:

- the driver who finished ahead is counted as beating the driver behind
- expected result is calculated from the two drivers' pre-race ratings
- rating movement is the sum of those pair results

This makes beating strong drivers worth more than beating weak drivers.

Keep the first implementation simple and tune the K-factor later.

Initial rating settings:

```text
K-factor = 18.5
Max rating change per race = +/- 35
```

The per-race cap prevents one chaotic race from causing unrealistic rating swings.

Implemented first version:

- Race ratings update after simulated results, manual results, and imported iRacing JSON results.
- Drivers are compared only against drivers in the same class.
- The Driver Pool screen shows the driver's current championship.

Exhibition/non-career races should not affect MMR.

K-factor and rating cap should stay global in the first implementation.

Do not vary K-factor or cap by tier, race length, field size, or discipline until real season testing shows a need.

## Retirement

### Normal Retirement

After `12-20` completed seasons, AI drivers become retirement eligible.

Use a random retirement season target per AI driver:

```json
"retirement_after_seasons": 16
```

Generated AI drivers should receive:

```text
retirement_after_seasons = random integer from 12 to 20
```

When `seasons_completed >= retirement_after_seasons`, the driver can retire at season end.

Human players should have `retirement_after_seasons` set to `null` and should not be automatically retired.

Drivers who retire normally due to retirement age/season count should be kept in the database with:

```text
status = retired
```

This preserves career history for long-term world records.

Implemented first season-end progression pass:

- The completed player championship records class championship winners.
- All participants gain one completed season.
- AI drivers at or above their random retirement target are marked retired and kept in the database.
- Tier 1 bottom-three AI per class are deleted as forced retirements.
- Retired/deleted AI are replaced with new rookies.
- The save's world year advances by one after season completion.

Implemented first AI world simulation pass:

- At player season end, AI-only championship instances are simulated before the world year advances.
- Tier 1 runs 6 AI groups per championship, Tier 2 runs 3, and Tier 3-5 run 1.
- AI fields use random championship field sizes up to the championship max, capped at 40.
- Multiclass AI fields are split into class groups and scored/rated by class.
- AI race results use global MMR weighting, but outcomes remain variable.
- The player championship is skipped so those drivers are only finalized once.
- New rookies are generated as needed to keep AI fields full.

Implemented AI world simulation chunking:

- Each active player season now stores `world_sim_progress` in the save file.
- After each player race, the app shows a "Simming to next event..." screen and runs one saved chunk of AI championship instances.
- The chunk size is based on the number of AI championship instances divided across the player's race count.
- If a save reaches season end before all AI chunks are complete, the sim screen continues running chunks until the world season is caught up.
- Season completion only advances the world year after AI chunks and the player championship are finalized.

## Multiple Human Drivers

The app should support multiple human drivers in one save, but the first implementation should keep their career movement simple.

### Base Version: Shared Party Progression

This is the recommended first implementation.

All human players in the save move together as one career party.

Rules:

- Each human keeps their own global MMR.
- Race-by-race MMR changes still apply to each human individually.
- For promotion/demotion and championship availability, use the shared party result/tier flow first; Group MMR can become an additional display or balancing value later.
- All humans select and run the same championship each season.
- If multiple humans are in the same save, they are always in the same race sessions.
- Season progression waits for the shared championship season to finish.

This keeps co-op easy to understand and avoids needing multiple active schedules at once.

Recommended Group MMR:

```text
group_mmr = average(active human driver MMR)
```

Optional later improvement:

```text
group_mmr = weighted average, slightly favoring the best human result
```

Start with a simple average.

If one human driver starts pulling far ahead while another is struggling, consider a weighted formula later so the party does not climb too high too quickly.

Possible future weighted approach:

```text
group_mmr = average human MMR - balance penalty based on spread between highest and lowest human MMR
```

This would keep the group from being pulled too far upward by one standout driver.

UI should still show each human driver's individual MMR so players can see their own position on the global ladder.

Also show a combined label:

```text
Group MMR
```

`Group MMR` is a co-op overview value. The first implementation still uses the shared party result/tier flow for progression, and Group MMR can become a balancing input later.

Hide `Group MMR` for single-player saves. In single-player, the player's individual MMR is enough and avoids extra UI clutter.

### Advanced Version: Rivals Mode

Rivals Mode should be a later expansion, not part of the first driver-pool implementation.

In Rivals Mode, each human driver has their own path through the ladder.

This would require:

- each human can choose their own championship
- each human has their own schedule
- menu screen needs a way to switch active human driver
- gameplay/results screens need to show the selected human driver's current championship
- world season cannot advance until all human drivers finish their seasons
- if humans choose the same championship, they must share the same races and results
- if humans choose different championships, their seasons progress independently until year-end

Rivals Mode is more realistic, but much more complex. It should be designed after the base shared-party version is stable.

### Forced Retirement

At the end of each season, in the lowest tiers:

- bottom 3 AI drivers from each lower-tier championship instance are forced to retire
- human players are immune
- retired drivers are replaced with newly generated rookies

This keeps the lower ladder fresh.

Example:

```text
5 available Tier 1 championships
6 instances of each championship
bottom 3 forced retirements per instance

5 x 6 x 3 = 90 forced retirements
```

Forced retirement is based on bad performance in that specific championship instance, not a single global bottom-3 list.

Drivers who are forced to retire due to bad performance do not need to be kept in the database. They can be deleted and replaced by newly generated rookies.

Only normal age/season retirements should remain as retired records.

## New Rookies

Rookies should be generated when:

- the pool does not have enough active AI drivers
- forced retirements create openings
- normal retirements reduce pool size

Rookie generation should be based on shortage, not evenly split across every style. If Oval needs more drivers, generate more Oval rookies. If Sports Car needs more, generate more Sports Car rookies.

Rookies should usually enter with:

- baseline MMR
- low `seasons_completed`
- primary style assigned randomly or based on shortage

Rookies should not be intentionally weaker just because they are rookies. They should start at the configured baseline rating, then rise or fall based on results.

Recommended first baseline:

```text
1000 MMR
```

## Driver Pool Screen

Add a screen to view the full driver pool.

The Driver Pool screen should be accessible from the gameplay screen because each save has its own AI world and roster.

Suggested columns:

- Name
- Human/AI
- Status
- Primary Style
- Sports Car Rating
- Oval Rating
- Open Wheel Rating
- Seasons
- Wins
- Championships

Driver detail view should show:

- total race wins
- total championship wins
- list of championship wins with championship name, tier, style, and season year
- optional list of race wins by track/layout

Helpful filters:

- Active only
- Retired
- Human
- Style

Active drivers should be shown by default. Retired drivers should be hidden by default, with a filter to view them.

## Migration Plan

No existing-save migration is required for the first implementation.

The driver pool/world database is created when a new save is created.

First implementation behavior:

1. New save is created.
2. Per-save world database is created.
3. AI-only world is pre-simulated until top-tier championships are full.
4. Human players are added as new rookies.
5. The player chooses their first championship.

Do not rewrite old saves aggressively.

## Implementation Phases

### Phase 1: Passive Driver Pool

Add:

- `driver_pool.py`
- per-save world database creation
- schema migration helpers
- add humans to pool when creating a save
- add AI to pool when a championship starts
- Driver Pool screen for viewing
- gameplay screen entry point to the Driver Pool screen

Do not change championship field selection yet.

This phase is mostly safe and gives visibility.

### Phase 2: Field Selection From Pool

Change championship start so AI drivers come from the pool instead of being generated fresh every time.

Fallback:

- if the pool does not have enough AI, generate rookies

### Phase 3: Ratings

Add race-by-race rating changes for humans and AI.

Use an Elo/chess-style formula where each driver is compared against every other driver in the race.

### Phase 4: Retirement

Add:

- normal retirement after 12-20 seasons
- forced retirement for bottom 3 AI in lowest tiers
- rookie replacement

### Phase 5: Cross-Discipline Penalties

Add primary-style behavior.

Example:

```text
effective_rating = style_rating
if style != primary_style:
    effective_rating -= 150
```

Initial non-primary style penalty:

```text
150 MMR
```

Keep players allowed to choose any available championship.

## Open Questions

Resolved decisions:

- One AI driver can only appear in one championship per year.
- All non-player championships should be simulated each year.
- Non-player championship simulation should be weighted by driver stats/MMR, but not be definitive.
- Human primary style is assigned from the first championship selected.
- Rating changes happen after every race.
- Tier 1 should run 6 AI instances of each available championship.
- Tier 2 should run 3 AI instances of each available championship.
- Tier 3+ should run 1 AI instance of each available championship.
- Human players cannot change championship mid-year.
- Non-primary style penalty starts at 150 MMR.
- Race-by-race MMR should use an Elo/chess-like system where each driver is rated against every other driver in the race.
- AI championship field sizes should keep using the existing random field-size logic with each championship's max size.
- Human exhibition/non-career races should be allowed later, but not in the first implementation.
- K-factor starts at 18.5.
- MMR changes are capped at +/-35 per race.
- Exhibition races do not affect MMR.
- K-factor and rating cap stay global for the first implementation.
- Multiple-human saves use shared party progression first.
- Rivals Mode is a future expansion.
- Initial world generation fills all planned championship instances plus a 10-20% rookie buffer.
- Tier 5 is the top tier.
- Promotion/demotion uses MMR as the main driver, with season finishing position still considered.
- AI drivers prefer primary style, but can move sideways within the same tier to avoid dropping down.
- Rookies are generated based on shortage.
- Save world year starts from the current real year.
- Driver Pool screen shows active drivers by default and hides retired drivers unless filtered.

Current UI decision:

- Show `Group MMR` in Career Overview for multiplayer saves.
- Hide `Group MMR` for single-player saves.

## Recommended Next Step

Implement Phase 1 only:

- create the SQLite driver pool database for each save
- add human players to it
- add existing generated AI into it when championships start
- add a Driver Pool screen

This gives us the new system without changing the current gameplay behavior yet.
