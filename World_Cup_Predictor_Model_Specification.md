# World Cup Predictor Model — Full Specification

---

## Architecture Overview

The model uses a **two-layer architecture** that separates a team's standalone quality from match-specific context, then converts the comparison into a win probability.

- **Layer 1 (Base Team Score):** Measures how good a team is right now, independent of who they're about to play. Updates after each match.
- **Layer 2a (Per-Team Match Adjustments):** Context factors calculated independently for each team per fixture.
- **Layer 2b (Relational Match Terms):** Factors that only exist as a comparison between two specific teams. Cannot be assigned to either team alone.
- **Output Layer:** Converts the score gap into a win probability via a sigmoid function, then feeds into a Monte Carlo simulation engine.

---

## Layer 1: Base Team Score

This layer produces one number per team. It only changes after a match is played, not depending on who's next.

### 1.1 Historical Performance (Last 3 World Cups)

A team's track record across their last 3 World Cup appearances. Any longer and the squad has completely turned over, making the data irrelevant to the current team's identity.

This is the long-run prior — it anchors the score before the current tournament provides any new evidence.

### 1.2 Current Tournament Performance

Made up of two sub-components, weighted as follows within the current-tournament bucket:

| Sub-component | Weight | Purpose |
|---|---|---|
| Static GD | 45% | How well are they doing, adjusted for opposition quality |
| Player Performance | 55% | Most granular, freshest signal — individual form updates every match |

Note: Relative GD was moved to Layer 2b as a relational term — see section 2b.3.

#### 1.2.1 Static GD

Goal difference weighted by the **opponent's FIFA ranking**. A 2-0 win against the #3 team counts for more than a 2-0 win against the #45 team.

The ranking acts as a **quality multiplier** on the raw goal difference. The multiplier uses **piecewise linear interpolation** between anchor points — straight lines between each pair of anchors, producing an overall curved shape because the anchors aren't evenly spaced. Steep at the top (where per-rank quality differences are largest), flatter toward the bottom.

Anchor points:

| Opponent ranking | Multiplier |
|---|---|
| #1 | 2.0x |
| #5 | 1.8x |
| #10 | 1.5x |
| #15 | 1.4x |
| #25 | 1.1x |
| #30 | 1.0x (baseline — "average" WC opponent) |
| #45 | 0.7x |
| #60 | 0.6x |

For any opponent ranking between two anchors, the multiplier is a straight-line interpolation between them. For example, an opponent ranked #20 falls between the #15 (1.4x) and #25 (1.1x) anchors, giving approximately 1.25x.

Simple to implement, no edge-case blowups, and easy to tune during backtesting by adjusting individual anchor values without changing the underlying math.

#### 1.2.2 Player Performance

A team's player performance score is the sum (or average) of each starting XI player's individual match ratings, sourced from SofaScore.

**Per-player weighting across the tournament (recency-weighted mean):**

| Games played | Weights (most recent → oldest) | Split |
|---|---|---|
| 1 game | 50% current + 50% previous tournament | — |
| 2 games | 50% / 50% | Equal |
| 3 games | 35% / 35% / 30% | 70/30 |
| 4 games | 35% / 35% / 15% / 15% | 70/30 |
| 5 games | 30% / 30% / 14% / 13% / 13% | 60/40 |
| 6 games | 30% / 30% / 10% / 10% / 10% / 10% | 60/40 |
| 7 games | 30% / 30% / 8% / 8% / 8% / 8% / 8% | 60/40 |

**Rule:** No single match in the "older" bucket can exceed the weight of a single match in the "recent" bucket. For 3 or fewer matches, this is enforced explicitly via the table above.

**Previous tournament fallback:** When a player has only played 1 game this tournament, 50% of their score comes from their previous tournament performance. This disappears entirely from game 2 onward (no fade-out), since Layer 1's historical weight already carries long-run information at the team level.

**Tactical Importance Multiplier (auto-derived):**

Some players are central to their team's tactical system (e.g. Haaland for Norway's direct play). Rather than manually assigning importance, this is **derived automatically from data**:

1. For each player, look at their last 10–15 international matches.
2. Calculate the **correlation between that player's individual match rating and the team's result** (win/loss or goal difference).
3. Players with high correlation (their form tightly tracks team results) get a higher multiplier. Players with low correlation (team wins regardless of their individual performance) stay near default.

This means:
- When a key player is in form → team score gets a justified boost.
- When a key player is off form → team score drops more than for a generic player.
- When a key player is suspended/injured → replacing them with a lower-multiplier backup amplifies the impact, which matches reality.

Edge case: players with fewer than ~5 international caps default to 1.0x multiplier (no special weighting) until enough data accumulates.

### 1.3 Confederation Calibration

FIFA rankings are not equally meaningful across confederations — a top CONCACAF team's ranking doesn't equal a similarly-ranked UEFA team's actual strength.

This adjustment sits **upstream of everything else**. Before rankings are used in Static GD, Relative GD Comparison (Layer 2b), or anywhere else, they are adjusted by a per-confederation coefficient. Without this correction, every downstream calculation inherits the distortion.

Implementation: a one-time multiplier per confederation (AFC, CAF, CONCACAF, CONMEBOL, OFC, UEFA), estimated from historical ranking-vs-actual-performance discrepancies.

### 1.4 Squad Depth / Rotation Decay

A property of the squad as a whole, not of a single match. Teams with thin benches (fewer unique contributors, more minutes concentrated on the same players) suffer fatigue and injury attrition as the tournament progresses.

Modeled as a **decay modifier on the player performance sum** — the later the tournament goes, the more a thin-rotation team's player performance sum is reduced. Deep squads decay less. Derivable from minutes-played and unique-contributor data, which becomes available as matches are played.

### 1.5 Historical vs. Current Weighting Curve

The dynamic balance between Historical Performance (#1.1) and Current Tournament Performance (#1.2, which now contains Static GD and Player Performance only). Current weight grows as more matches are played, but historical weight never drops below a **15% floor** — even in the final, a team's long-run identity retains some relevance.

**Design principle:** Small drops early (one group-stage game barely tells you anything new), accelerating drops later (by knockouts, each additional game carries more and higher-quality evidence). Drops are monotonically increasing.

| Games played | Historical | Current | Drop from previous |
|---|---|---|---|
| 0 (pre-tournament) | 100% | 0% | — |
| 1 | 92% | 8% | -8 |
| 2 | 83% | 17% | -9 |
| 3 (end of groups) | 73% | 27% | -10 |
| 4 (R16) | 62% | 38% | -11 |
| 5 (QF) | 49% | 51% | -13 |
| 6 (SF) | 34% | 66% | -15 |
| 7 (Final) | 15% | 85% | -19 |

---

## Layer 2a: Per-Team Match Adjustments

Calculated independently for each team per fixture. These are not relational — they don't depend on who the opponent is.

### 2a.1 Home / Host Advantage

A **flat boost applied only to the host nation(s)**. Binary: is this team a host, yes or no. For the 2026 World Cup, applies to the United States, Mexico, and Canada — specifically whichever host is playing in their own country's venues.

No regional proximity scaling, no cultural adjacency. One parameter, clean implementation. Approximate magnitude: +8–10% boost.

### 2a.2 Stakes / Motivation

Only triggers on the **3rd (final) group stage match**. Binary flag, not a complex rules engine. Never applies in knockout rounds (every knockout game is inherently must-win).

| Situation | Adjustment |
|---|---|
| Both teams still need to qualify | No adjustment (both fully motivated) |
| One team already qualified | Small penalty to the qualified team (likely rotation, lower intensity) |
| Both already qualified | Small penalty to both |
| One team already eliminated | Judgment call — could go either way |

Approximate magnitude: ±5%.

### 2a.3 Suspensions (Folded into Player Performance)

Not modeled as a separate component. Instead, when computing the player performance sum for an upcoming match, use the **actual expected starting XI**, which naturally excludes suspended players.

The impact flows through player performance automatically — removing a high-rated player (especially one with a high tactical importance multiplier) lowers the team's player performance sum for that match. No separate weight to tune, no new component.

Card accumulation tracking (which players have 2 yellows and will miss the next game if booked) is sourced from SofaScore's incidents endpoint.

---

## Layer 2b: Relational Match Terms

These only exist as a comparison between two specific teams. They cannot be assigned to either team independently.

### 2b.1 Tactical Matchup (±10%)

**Approach: Hybrid (archetypes now, stat-derived later)**

Pre-tournament: assign each team a primary playstyle archetype from a set of 5:

| Archetype | Description |
|---|---|
| Possession-based | Control the ball, patient buildup |
| Counter-attacking | Defend deep, hit on the break |
| High press | Aggressive pressing, win ball high, fast transitions |
| Physical / direct | Bypass midfield, long balls, set-piece reliance, aerial dominance |
| Defensive / low block | Compact shape, absorb pressure, minimal risk |

As the tournament progresses and real match stats accumulate, shift toward **stat-derived style profiles** across continuous dimensions (possession %, pressing intensity, directness, defensive line height). This mirrors the overall model philosophy: prior knowledge early, observed data later.

**Matchup Matrix (archetype-based):**

Values range from approximately -10% to +10%:

|  | vs Possession | vs Counter | vs High Press | vs Direct | vs Low Block |
|---|---|---|---|---|---|
| **Possession** | 0 | -slight | -moderate | +slight | -slight |
| **Counter** | +slight | 0 | +slight | -slight | -slight |
| **High Press** | +moderate | -slight | 0 | -moderate | +slight |
| **Direct** | -slight | +slight | +moderate | 0 | +moderate |
| **Low Block** | +slight | +slight | -slight | -moderate | 0 |

Where "slight" ≈ ±3–4% and "moderate" ≈ ±7–10%.

**Relationship with Tactical Importance Multiplier:** These are separate components doing different things. The multiplier (in Layer 1) says "Haaland's form matters more to Norway's score." The matchup matrix (in Layer 2b) says "direct football has an advantage against possession football." They interact indirectly — if Haaland is injured, Norway's base score drops (multiplier working), which weakens the value of any tactical matchup advantage (since they can't execute the style). No explicit coupling needed; flagged for Phase 6 backtesting to check for over-crediting.

### 2b.2 Head-to-Head History (±5% cap)

A small nudge to account for psychological dominance patterns that raw quality scores don't capture.

**Which matches count:**
- Last 5–8 meetings between the two teams.
- Competitive matches (World Cup, continental tournaments, qualifiers) weighted more than friendlies. Either exclude friendlies entirely or give them half weight.
- Recency-weighted: recent meetings count more than older ones.

**Scoring:**
- Win/loss record from filtered matches → ratio (e.g. A won 4 of 5 = 0.8 for A, 0.2 for B).
- Map that ratio to the ±5% cap. A 50/50 split → 0% adjustment. An 80/20 record → the full ±5%.

**Edge cases:**
- 0–1 past meetings → default to **zero adjustment** (not enough data).
- Most recent meeting is 8+ years old → apply decay; entire H2H component shrinks toward zero regardless of the record.

**Cap rationale:** H2H is built on tiny sample sizes (5–8 matches is statistically weak). The cap ensures even a completely one-sided record can only nudge the prediction slightly, never override the rest of the model.

**Data source:** SofaScore H2H endpoint, FBref, or any match results database. Only needs who won, not complex stats.

### 2b.3 Relative GD Comparison (±8–10%)

Moved from Layer 1 to Layer 2b because it is inherently relational — it asks "how is each team performing compared to expectation, and how relevant is that overperformance pattern to *this specific matchup*."

**Why it fits better here than in Layer 1:** In Layer 1, relative GD was a general "are you overperforming" metric averaged across all tournament matches, treated as a standalone team property. But a team's overperformance against weak group opponents means less when they now face a top-5 team. Making it relational lets the model contextualize each team's overperformance pattern against the specific caliber of the upcoming opponent.

**How it works per fixture (A vs B):**

1. For each team, take their tournament GD record (raw goal differences from each match played so far).
2. For each past match, compute the overperformance using the log-compressed ratio:

```
weight = 1 + k × ln(own_rank / opponent_rank)
```

Where k = 0.3–0.5. This gives each team a cumulative "overperformance score" — how much better or worse they've done than expected across their tournament matches so far.

Example with k = 0.4 for team ranked #10:

| Opponent | Ratio | Weight | GD | Relative GD contribution |
|---|---|---|---|---|
| vs #12 (weaker) | 0.83 | 0.93 | +1 | +0.93 |
| vs #8 (stronger) | 1.25 | 1.09 | +1 | +1.09 |
| vs #50 (much weaker) | 0.2 | 0.36 | +2 | +0.72 |

3. Compare both teams' overperformance scores, then **contextualize by the ranking gap between A and B specifically** — a team whose overperformance came against #40–60 opponents gets less credit when facing a #5 team than a team whose overperformance came against top-15 opponents.

**Separation from Static GD:** Static GD (Layer 1) handles absolute quality of results — "beating a top team matters more." Relative GD Comparison (Layer 2b) handles form signal — "is this team running hot or cold relative to expectations, and how relevant is that form to this specific opponent." No overlap: Static GD answers "how good are your results," Relative GD Comparison answers "how much should we trust that those results predict what happens next, against *this* opponent."

---

## Score Combination + Output

### Step 1: Compute Independent Scores

```
AdjustedScore(A) = BaseScore(A) + HomeAdv(A) + Stakes(A)
AdjustedScore(B) = BaseScore(B) + HomeAdv(B) + Stakes(B)
```

Each team's score is fully independent of the other.

### Step 2: Compute Gap + Add Relational Terms

```
Gap = AdjustedScore(A) - AdjustedScore(B)
     + TacticalMatchup(A_style, B_style)
     + H2H(A, B)
     + RelativeGDComparison(A, B)
```

Relational terms enter only at the comparison stage.

### Step 3: Normalization

**Why:** The components feeding into the gap are on wildly different scales (GD-based scores, player rating sums, percentage-based adjustments). Without normalization, the component with the biggest natural scale silently dominates, regardless of intended weighting.

**Method:** Standardize each component (subtract mean, divide by standard deviation) before applying weights and summing. This also ensures one sigmoid steepness constant stays well-calibrated throughout the tournament.

**When:** Normalize each raw component before combining into the gap. Only meaningful once real distributions of values exist from actual matches (not from placeholder data).

### Step 4: Sigmoid Conversion

The gap is not a probability — it's a number on an arbitrary scale. A sigmoid (S-curve) converts it into a valid 0–100% win probability:

- Gap = 0 → exactly 50%
- Large positive gap → approaches but never reaches 100%
- Large negative gap → approaches but never reaches 0%
- Diminishing returns: going from a small mismatch to a medium one matters a lot; going from huge to huger barely moves the needle

The **steepness constant (k)** controls how sensitive win probability is to score differences:
- Too steep → even small gaps produce near-certain predictions
- Too flat → even big mismatches barely move off 50/50

Starting value is a placeholder; tuned during backtesting.

### Step 5: Simulation Engine

Since every match resolves as a binary win probability (draws, extra time, and penalties are skipped), the simulation is a straightforward binary tree:

- For each fixture, sample a winner according to the probability (not always picking the favorite).
- Run the bracket forward, round by round, to a champion.
- **Monte Carlo:** repeat thousands of times to get tournament-winner odds and round-by-round advancement probabilities.
- Each simulation snapshot at a given round is a stored prediction state, enabling the "see what predictions looked like at each stage" feature.

**Group stage note:** Since draws are skipped even in groups, every group match is forced into a win/loss. This means simulated group tables won't perfectly resemble real point allocations (where draws award 1 point each). Acknowledged as a simplification.

---

## Overall Weight Distribution

### Across categories (approximate contribution to total gap):

| Category | Share |
|---|---|
| Base Team Score difference (Layer 1) | ~50–55% |
| Per-team match context (Layer 2a) | ~15–20% |
| Relational terms (Layer 2b) | ~25–35% |

Layer 2b's share increased from ~10–15% to ~25–35% because Relative GD Comparison moved there from Layer 1. Layer 1's share decreased correspondingly since it no longer contains the overperformance signal.

### Layer 2 component weights:

| Component | Magnitude | Notes |
|---|---|---|
| Home / host advantage | +8–10% | Only for host nation(s) |
| Stakes / motivation | ±5% | Only 3rd group match |
| Tactical matchup | ±10% | Least data-backed; don't let it dominate |
| Head-to-head | ±5% (capped) | Small sample sizes; nudge only |
| Relative GD Comparison | ±8–10% | Contextualized overperformance signal |

---

## Data Sources

| Data needed | Source | Access method |
|---|---|---|
| Per-player per-match ratings | SofaScore | tunjayoff/sofascore_scraper (Python, public HTTP APIs) |
| Player rating breakdowns | SofaScore | `event/{id}/player/{id}/rating-breakdown` endpoint |
| Match lineups + incidents (cards, subs) | SofaScore | `matches/get-lineups`, `matches/get-incidents` |
| H2H match history | SofaScore | H2H endpoint, or FBref |
| Match results, scores, schedule | World Cup 2026 API / FBref | Open-source REST API or FBref scraping |
| FIFA rankings | FIFA / static source | Infrequently updated; can be manually entered |
| Historical World Cup results (last 3 WCs) | FBref / Wikipedia | Static, one-time collection |

**Hybrid approach rationale:** SofaScore scraper handles player ratings (the one thing nothing else provides as a single per-match score). Match results and schedule data come from more stable/reliable sources. FIFA rankings are static enough to enter manually.

---

## Build Phases

### Phase 1: Skeleton
Get a match resolving into a probability, even with all inputs at zero.
- Wire up gap calculation (AdjustedScore(A) - AdjustedScore(B) + relational terms)
- Implement sigmoid conversion with an arbitrary steepness constant
- Build single-match simulation (two dummy teams → probability → sampled winner)

### Phase 2: Components from readily available data
Only needs FIFA rankings + past World Cup results.
- Confederation calibration (per-confederation coefficient)
- Historical performance (last 3 WCs per team)
- Static GD formula (test against past tournaments)
- Relative GD Comparison formula (Layer 2b — test against past tournaments)
- Historical vs. current weighting curve
- Head-to-head (from historical match results)

### Phase 3: Components needing richer/live data
Needs live tournament data feeds or judgment calls.
- Player performance sum (requires SofaScore scraper setup)
- Tactical importance multiplier (requires enough international match data per player)
- Injury/suspension tracking (via SofaScore incidents)
- Squad depth/rotation decay (derivable from minutes-played data)
- Home/host advantage (needs venue list + host designation)
- Stakes/motivation (small rules engine for group standings logic)

### Phase 4: Hardest, most judgment-heavy
- Tactical matchup archetypes (manual assignment initially, shift to stat-derived as data accumulates)
- Tactical matchup matrix (hand-built from football logic, validated in backtesting)

### Phase 5: Tie it together
- Normalization (only meaningful once real distributions exist from Phase 2/3)
- Cross-component weights (premature until components produce real, differently-scaled numbers)
- Full bracket Monte Carlo simulation (extend from single-match to full tournament)

### Phase 6: Backtesting & Calibration (deferred)
- Run the full model retroactively on 2014, 2018, 2022 World Cups
- Scoring rule: Brier score (measures gap between predicted probability and actual outcome)
- Calibration check: do "70% predictions" actually win ~70% of the time?
- Treat all weights as one combined search problem (grid/random search across combinations)
- Train on 2014 + 2018, test on 2022 (held-out validation)
- Sanity-check fitted weights against football domain knowledge
- Re-run after each future World Cup to account for how football evolves
- Items to tune: historical/current curve shape (#1.5), cross-component weights, sigmoid steepness (k), log compression constant (k in Relative GD Comparison), matchup matrix values, tactical importance correlation threshold, Relative GD contextualization weighting

---

## Active Component Count: 17

| # | Component | Layer | Type |
|---|---|---|---|
| 1 | Historical performance (last 3 WCs) | 1 | Static pre-tournament |
| 2 | Static GD (ranking-weighted) | 1 | Updates per match |
| 3 | Player performance sum (SofaScore ratings) | 1 | Updates per match |
| 4 | Tactical importance multiplier (auto-derived correlation) | 1 | Modifier on #3 |
| 5 | Squad depth / rotation decay | 1 | Modifier on #3, grows over tournament |
| 6 | Confederation calibration | 1 | Upstream adjustment on FIFA rankings |
| 7 | Historical vs. current weighting curve | 1 | Dynamic balance between #1 and #2/#3 |
| 8 | Home / host advantage | 2a | Per-team, per-match |
| 9 | Stakes / motivation | 2a | Per-team, 3rd group match only |
| 10 | Suspensions | — | Folded into #3 via expected XI |
| 11 | Tactical matchup (archetype matrix) | 2b | Relational, per-fixture |
| 12 | Head-to-head history | 2b | Relational, per-fixture |
| 13 | Relative GD Comparison (log-compressed, contextualized) | 2b | Relational, per-fixture |
| 14 | Normalization / standardization | Output | Pre-processing before combination |
| 15 | Cross-component weights | Output | How much each component contributes |
| 16 | Sigmoid conversion + steepness constant | Output | Gap → win probability |
| 17 | Monte Carlo simulation engine | Output | Probability → tournament predictions |
