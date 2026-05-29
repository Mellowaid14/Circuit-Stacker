# Teams Working Doc

## Purpose

This document is the working design for adding teams into Circuit Stacker.

The goal is to keep the system clear and expandable so we can support:

- team-based player offers
- multiple teams in the same championship making offers
- team prestige and ladder progression
- teams expanding into multiple championships over time
- lower-tier new team creation
- weak teams declining, selling, or folding

This document should guide implementation order so we do not overbuild too early.

## High-Level Vision

Teams should become a second career ladder running alongside drivers.

Drivers try to:

- get promoted
- win championships
- move into better cars and better series

Teams should try to:

- hire the best drivers they can
- win in their current series
- improve prestige and reputation
- move into more prestigious championships
- eventually build multiple championship programs

Long term, the world should feel like:

- great drivers rise through the ladder
- strong teams rise through the ladder
- major teams can build empires across multiple series
- weak teams can stagnate, shrink, sell, or disappear

## Guiding Principles

- Build teams in phases.
- Keep V1 focused on player offers and team hiring.
- Do not force empire logic into the first implementation.
- Use static CSV data only for base identity and setup.
- Put living team state in save/world state or DB.
- Avoid one-team-takes-everything behavior.
- Favor believable progression over maximum complexity.

## Phase Plan

### Phase 1 - Seasonal Team Seat Assignment

Goal:

- teams are assigned into championships season by season
- teams fill seats with drivers
- player receives team offers

What Phase 1 should include:

- `Teams.csv`
- championship `Total_Seats`
- teams assigned by style / tier fit instead of fixed championship ownership
- one-seat and two-seat team entries
- team prestige
- driver-to-team assignment
- player offseason team offers
- team shown in standings / exports / driver profile

What Phase 1 should not include yet:

- buying and selling programs
- finances simulation
- multi-program empires
- constructors points
- teammate chemistry
- persistent championship ownership

### Phase 2 - Team Ratings and Identity

Goal:

- make teams feel different from one another

Add:

- prestige
- reputation
- ambition
- stability
- simple financial strength

Effects:

- stronger teams offer better seats
- ambitious teams chase stronger drivers
- unstable teams make odd choices
- weak teams can begin declining

### Phase 3 - Team Programs

Goal:

- one team can run multiple programs in different championships

Important concept:

- a `Team` is the parent organization
- a `Team Program` is one active entry in one championship

Example:

- Apex Motorsport
- Apex Motorsport MX-5 Program
- Apex Motorsport GT4 Program
- Apex Motorsport IMSA GT3 Program

This is the phase that should support the "team empire" idea.

### Phase 4 - Expansion, Sales, and Entry Movement

Goal:

- teams can expand upward
- weak teams can sell or lose programs
- new teams can enter lower tiers

Possible outcomes:

- dominate a lower tier and launch a higher-tier program
- overspend and retreat
- sell a seat/program
- get bought out
- start a second discipline program

## Core Data Model

### Static Data

Static data should live in CSVs.

Main static file:

- `Teams.csv`

Possible future static files:

- `Team Names.csv` for generated new teams
- `Team Sponsors.csv`
- `Team Nationalities.csv`

### Dynamic World Data

Dynamic data should live in save/world data, not CSV.

This should eventually include:

- current active team roster
- current drivers under each team
- prestige changes
- reputation changes
- financial strength
- active programs
- entry history
- titles
- expansions and sales

## Recommended CSV Schema for Phase 1

### Teams.csv

Recommended columns:

- `Team_ID`
- `Team`
- `Game`
- `Base_Style`
- `Min_Tier`
- `Max_Tier`
- `Prestige`
- `Two_Car_Bias`

Recommended rules:

- `Team_ID` must be unique.
- `Game` allows the same team concepts to exist safely in both iRacing and AMS2.
- `Base_Style` controls which discipline pool the team belongs to.
- `Min_Tier` and `Max_Tier` define the ladder range where the team can appear.
- `Prestige` should use a consistent scale, likely `1-100`.
- `Two_Car_Bias` controls how likely the team is to receive a second seat in a championship.

### Suggested Optional Columns Later

- `Base_Discipline`
- `Country`
- `Ambition`
- `Stability`
- `Funding`
- `Expected_Finish`
- `Can_Expand`
- `Expansion_Bias`

## Team vs Team Program

This should be the long-term model:

- `Team` = organization
- `Team Program` = one championship entry run by that organization

### Why this matters

Without programs:

- one team can only really exist in one place
- empire expansion gets messy

With programs:

- one team can exist in many championships
- each program can have its own seats and drivers
- expansion is easier to model

### Example

Parent Team:

- `Apex Motorsport`

Programs:

- `Apex Motorsport MX-5 Cup`
- `Apex Motorsport GT4 Challenge`
- `Apex Motorsport IMSA GT3`

## Phase 1 Seat Model

Phase 1 should not treat teams as permanent owners of championship entries yet.

Instead:

- championships define `Total_Seats`
- the season builder creates team entries for that season
- eligible teams are selected from `Teams.csv`
- teams receive `1` or `2` seats based on fit and bias
- drivers are assigned into those seats

This gives us:

- team identity in the championship
- multiple teams in the same series
- player offers from teams
- seasonal movement without full ownership simulation

### Why this is the recommended Phase 1 model

- much less CSV setup
- avoids manually assigning every team to every championship
- keeps the system flexible
- supports later team movement naturally
- lets us add team programs later without rebuilding everything

## Championship Seat Data

For Phase 1, championships should move away from thinking in raw driver count only.

Recommended championship field concept:

- `Total_Seats`

This value is the total number of entries to fill in the series.

Example:

- MX-5 Cup: 12 seats
- GT4 Challenge: 20 seats
- F1: 22 seats

In multiclass championships, seat totals can still be handled by class as needed later.

## Phase 1 Team Assignment Rules

For each championship season:

1. Read the championship style and tier.
2. Build an eligible team pool from `Teams.csv` using:
   - matching `Game`
   - matching `Base_Style`
   - championship tier within `Min_Tier` and `Max_Tier`
3. Fill the championship seat total by assigning teams:
   - each team gets at least 1 seat when selected
   - some teams may receive a second seat
   - second seat chance is influenced by `Two_Car_Bias`
   - prestige can also lightly influence selection
4. Once all seats are allocated, assign drivers to those team seats.

### Important note

Phase 1 teams are not yet permanent owners of those seats.

They are seasonal entries.

That means:

- a team may appear in MX-5 Cup this year
- and not appear there next year
- or appear with 1 seat one year and 2 the next

This is acceptable for Phase 1 because the goal is:

- team flavor
- player offers
- early team identity

not full program ownership yet.

## Driver Hiring Logic

All teams want to hire the best drivers they can, but their offer quality should depend on the team.

### Basic Offer Score

A team should rank drivers using a weighted score such as:

- MMR
- recent results
- tier fit
- championship fit
- discipline fit
- age / potential
- small randomness

### Team Preferences

Possible team biases:

- prefer current drivers if performing well
- prefer same discipline drivers
- prefer young talent
- prefer proven veterans

### Player Offers

The player should receive offers when:

- their MMR is high enough
- their recent results are good enough
- a seat is open
- the team sees them as a fit

Possible outcome:

- multiple offers from the same championship
- offers from different championships
- stronger teams offering later in the ladder

## Team Prestige

Prestige should represent how desirable and respected a team is.

Prestige can influence:

- driver interest
- offer strength
- future expansion access
- reputation in world news

Prestige should increase from:

- wins
- podiums
- titles
- long-term success

Prestige should decrease from:

- repeated poor results
- instability
- failed expansion

## Team Reputation

Reputation should represent short-term momentum.

Reputation can:

- rise faster than prestige
- fall faster than prestige
- help explain sudden good or bad years

Examples:

- a mid team on a hot streak
- a giant team having a disaster year

## Team Money / Financial Strength

Long term, money should be separate from prestige.

Money should control:

- whether a team can expand
- whether a team can keep top drivers
- whether a team can survive poor seasons

Prestige should control:

- whether a team is attractive
- whether a top championship would accept the team

Recommended long-term rule:

- money lets a team try
- prestige lets the team be accepted

## Expansion Rules

Teams should not be able to buy everything immediately.

Expansion should require:

- enough money
- enough prestige
- enough stability
- enough recent success

Possible requirements:

- one title in the current tier
- multiple strong seasons
- no recent financial distress

### Expansion Frequency

Expansion should be slow.

Suggested controls:

- only one new program every few seasons
- expansion cooldown
- increased overhead for each extra program

## Selling / Losing Programs

Programs should leave the world for believable reasons.

Reasons a team sells or loses a program:

- poor finances
- repeated failure
- owner retirement
- strategic retreat
- a bigger buyer appears

This is how new teams can still enter the ladder instead of old giants owning everything forever.

## New Team Entry

Lower tiers should continue receiving new teams over time.

Possible triggers:

- a weak team folds
- a program is sold
- the game needs more seats
- a generated startup team is created

New teams should usually enter:

- lower tiers first
- lower prestige
- lower funding

This keeps the base of the ladder healthy.

## Anti-Monopoly Rules

Important long-term goal:

- big teams should grow
- but they should not own everything

Possible anti-monopoly controls:

- hard cap on active programs
- diminishing returns with each extra program
- management strain
- expansion cooldown
- championship acceptance rules
- high cost to maintain multiple programs

## Championship Prestige

To support team ambition, championships likely need a prestige value.

Recommended addition to `Championships.csv` later:

- `Prestige`

This would help teams decide:

- which series they want to reach
- whether moving up is worth the cost

It would also help compare championships inside the same tier.

## Multiclass Handling

Multiclass championships should be supported through:

- `Championship_ID`
- `Car_Class`
- `Car_ID`

Examples:

- IMSA shared field with different class entries
- Production Car Challenge class-specific teams

Key rule:

- teams should attach to the correct class entry, not just the championship umbrella

For Phase 1:

- multiclass support can stay simple
- teams can be assigned inside the correct class seat pool
- full cross-class team empire logic should wait until later phases

## Game Support

### iRacing

Likely early support:

- team offers
- team shown in exports
- driver-team assignment in roster logic

### AMS2

Likely early support:

- team shown in app
- team attached to season/championship state
- roster exports may later include team flavor if useful

## World News Opportunities

Teams can create better news later, such as:

- Team signs rising star
- Shock move to a bigger team
- Veteran re-signs with title contender
- Team launches new program
- Major team sells lower-tier program
- Team clinches constructors title

## Open Questions

- Should teams have teammates from Phase 1, or only player-facing offers first?
- Should player choose championship first, then team?
- Or should team offers be the main way the player enters a championship?
- Should teams be able to cross disciplines, or mostly stay in one discipline?
- How often should weak teams fold or sell?
- Should generated new teams use templates by style / tier / country?
- Should prestige and money both start in CSV, or prestige only at first?

## Recommended Implementation Order

### V1

- create `Teams.csv`
- add `Team_ID`
- add championship `Total_Seats`
- assign seasonal team seats by style / tier fit
- assign AI drivers to teams
- show team in standings / driver detail / exports
- generate player team offers at season end

### V2

- add team prestige / reputation logic
- make better teams pursue stronger drivers
- add re-signing logic

### V3

- add team programs
- allow multi-championship expansion
- allow small generated team entry

### V4

- add buying / selling programs
- add full ladder-climbing team simulation
- add team empires and long-term decline

## Current Recommendation

Do not build the full empire system first.

Start with:

- `Teams.csv`
- championship `Total_Seats`
- seasonal team seat assignment
- player team offers
- team prestige

Then grow from there.

That will give the app real team identity quickly without locking us into a messy system too early.
