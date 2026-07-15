# World Cup Predictor — Complete Formula Reference

---

## Variable Definitions

### Inputs (per team T)

| Variable | Definition |
|---|---|
| `r_raw(T)` | Team T's raw FIFA ranking |
| `conf(T)` | Team T's confederation (AFC, CAF, CONCACAF, CONMEBOL, OFC, UEFA) |
| `C(conf)` | Confederation calibration coefficient (one per confederation) |
| `g(T)` | Number of games team T has played this tournament so far |
| `GD_m` | Team T's goal difference in tournament match m |
| `opp_m` | The opponent team T faced in match m |
| `rating(p, m)` | SofaScore rating for player p in match m |
| `XI(T)` | Expected starting XI for team T in the upcoming match |
| `H(T)` | Team T's historical performance score (last 3 World Cups) |
| `is_host(T)` | 1 if team T is a host nation playing in their own country, 0 otherwise |

### Constants (tuned during backtesting)

| Constant | Description | Starting range |
|---|---|---|
| `C(conf)` | Confederation adjustment per confederation | Estimated from historical data |
| `k_rel` | Log compression sensitivity for Relative GD | 0.3–0.5 |
| `k_sig` | Sigmoid steepness constant | TBD via backtesting |
| `α_home` | Home advantage boost magnitude | 0.08–0.10 |
| `α_stakes` | Stakes/motivation adjustment magnitude | 0.05 |
| `α_h2h` | Head-to-head cap | 0.05 |

---

## Step 0: Confederation Calibration

Adjust all FIFA rankings upstream, before they're used anywhere else:

```
r(T) = r_raw(T) × C(conf(T))
```

All subsequent formulas use `r(T)`, never `r_raw(T)`.

---

## Step 1: Layer 1 — Base Team Score

Computed independently per team. Updates after each match played.

### 1a. Static GD

```
StaticGD(T) = (1 / g) × Σ [GD_m × M(r(opp_m))]
              for m = 1 to g
```

Where `M(r)` is the piecewise linear multiplier function, interpolating between anchor points:

| r (opponent adjusted rank) | M(r) |
|---|---|
| 1 | 2.0 |
| 5 | 1.8 |
| 10 | 1.5 |
| 15 | 1.4 |
| 25 | 1.1 |
| 30 | 1.0 |
| 45 | 0.7 |
| 60 | 0.6 |

For any rank between two anchors, linearly interpolate. Example: `r = 20` falls between anchors 15 (1.4) and 25 (1.1), so `M(20) = 1.4 + (20-15)/(25-15) × (1.1-1.4) = 1.4 + 0.5 × (-0.3) = 1.25`.

### 1b. Player Performance

**Per-player weighted rating:**

```
R(p, g) = Σ [w_m × rating(p, m)]
           for m = 1 to g
```

Where `w_m` follows the recency weight table:

| g (games played) | w₁ (most recent) → wₘ (oldest) |
|---|---|
| 1 | 0.50 + 0.50 × prev_tournament_avg(p) |
| 2 | 0.50, 0.50 |
| 3 | 0.35, 0.35, 0.30 |
| 4 | 0.35, 0.35, 0.15, 0.15 |
| 5 | 0.30, 0.30, 0.14, 0.13, 0.13 |
| 6 | 0.30, 0.30, 0.10, 0.10, 0.10, 0.10 |
| 7 | 0.30, 0.30, 0.08, 0.08, 0.08, 0.08, 0.08 |

**Tactical importance multiplier:**

```
τ(p) = corr(player_ratings_last_10-15_intl_matches, team_results_same_matches)
```

If player has fewer than 5 caps: `τ(p) = 1.0`

**Squad depth decay:**

```
D(T, g) = decay modifier based on (unique_players_used / total_minutes_distributed)
```

Thin rotation → D decreases as tournament progresses. Deep rotation → D stays near 1.0.

**Team player performance score:**

```
PlayerPerf(T) = D(T, g) × (1 / |XI|) × Σ [τ(p) × R(p, g)]
                for p ∈ XI(T)
```

### 1c. Current Tournament Score

```
Current(T) = 0.45 × StaticGD*(T) + 0.55 × PlayerPerf*(T)
```

Where `*` denotes normalized (standardized) versions — see Step 4.

### 1d. Base Score

```
BaseScore(T) = w_hist(g) × H*(T) + w_curr(g) × Current(T)
```

Historical vs. current weights by games played:

| g | w_hist(g) | w_curr(g) |
|---|---|---|
| 0 | 1.00 | 0.00 |
| 1 | 0.92 | 0.08 |
| 2 | 0.83 | 0.17 |
| 3 | 0.73 | 0.27 |
| 4 | 0.62 | 0.38 |
| 5 | 0.49 | 0.51 |
| 6 | 0.34 | 0.66 |
| 7 | 0.15 | 0.85 |

---

## Step 2: Layer 2a — Per-Team Match Adjustments

Computed independently per team, per fixture. Does not depend on the opponent.

```
AdjustedScore(T) = BaseScore(T) + HomeAdv(T) + Stakes(T)
```

**Home advantage:**

```
HomeAdv(T) = α_home × is_host(T)
```

Where `α_home ≈ 0.08–0.10`. Only applies when the host nation is playing in their own country's venues.

**Stakes / motivation:**

```
Stakes(T) = 0               if not the 3rd group match
           = -α_stakes       if team already qualified (rotation/lower intensity)
           = 0               if team still needs to qualify (fully motivated)
```

Where `α_stakes ≈ 0.05`. Only triggers on the final group stage match.

---

## Step 3: Layer 2b — Relational Match Terms

Computed per specific matchup (A vs B). Cannot be assigned to either team alone.

### 3a. Tactical Matchup

```
Tac(A, B) = Matrix[style(A)][style(B)]
```

Where `style(T)` ∈ {Possession, Counter, HighPress, Direct, LowBlock} and Matrix values range from approximately -0.10 to +0.10:

|  | vs Poss | vs Counter | vs Press | vs Direct | vs LowBlock |
|---|---|---|---|---|---|
| **Poss** | 0 | -0.04 | -0.08 | +0.04 | -0.04 |
| **Counter** | +0.04 | 0 | +0.04 | -0.04 | -0.04 |
| **Press** | +0.08 | -0.04 | 0 | -0.08 | +0.04 |
| **Direct** | -0.04 | +0.04 | +0.08 | 0 | +0.08 |
| **LowBlock** | +0.04 | +0.04 | -0.04 | -0.08 | 0 |

Note: Matrix is antisymmetric — `Matrix[X][Y] = -Matrix[Y][X]`. The value is from team A's perspective.

### 3b. Head-to-Head

```
h2h_raw(A, B) = recency-weighted win ratio of A from last 5–8 competitive meetings

H2H(A, B) = clamp( 2 × α_h2h × (h2h_raw(A, B) - 0.5),  -α_h2h,  +α_h2h )
```

Where `α_h2h = 0.05` (the ±5% cap).

Examples:
- A won 4 of 5 → h2h_raw = 0.8 → H2H = 2 × 0.05 × (0.8 - 0.5) = +0.03
- A won 1 of 5 → h2h_raw = 0.2 → H2H = 2 × 0.05 × (0.2 - 0.5) = -0.03
- Even split → h2h_raw = 0.5 → H2H = 0

Edge cases:
- 0–1 past meetings → H2H = 0
- Most recent meeting > 8 years ago → apply time decay toward 0

### 3c. Relative GD Comparison

**Per-team overperformance score:**

```
OverPerf(T) = (1 / g) × Σ [GD_m × (1 + k_rel × ln(r(T) / r(opp_m)))]
              for m = 1 to g
```

Where `k_rel = 0.3–0.5`.

**Contextualized comparison:**

```
RelGDComp(A, B) = (OverPerf(A) - OverPerf(B)) × Context(A, B)
```

Where `Context(A, B)` weights the comparison by how relevant each team's past opponents are to this specific matchup. Teams whose overperformance came against opponents of similar caliber to the current opponent get more credit:

```
Context(A, B) = f(average_opponent_quality_faced_by_A_and_B, r(A), r(B))
```

The exact form of `Context()` is a backtesting target — starting with a simple version:

```
Context(A, B) = 1.0 (no contextualization initially)
```

Then refined during Phase 6 calibration to account for opponent-quality relevance.

---

## Step 4: Normalization

Before combining components, standardize each one so they contribute on comparable scales:

```
x* = (x - μ_x) / σ_x
```

Where `μ_x` and `σ_x` are the mean and standard deviation of that component across all teams in the tournament (for Layer 1 components) or across all matchups (for Layer 2b components).

Components that require normalization:
- `StaticGD(T)` → `StaticGD*(T)` (before combining with PlayerPerf in Current score)
- `PlayerPerf(T)` → `PlayerPerf*(T)` (before combining with StaticGD in Current score)
- `H(T)` → `H*(T)` (before combining with Current in Base score)
- `AdjustedScore(A) - AdjustedScore(B)` → normalized gap
- `Tac(A, B)` → `Tac*(A, B)`
- `H2H(A, B)` → `H2H*(A, B)`
- `RelGDComp(A, B)` → `RelGDComp*(A, B)`

Note: HomeAdv and Stakes are already on a defined scale (flat percentage values), but are included within AdjustedScore before normalization of the gap.

---

## Step 5: Weighted Combination → Gap

```
Gap(A, B) = w₁ × [AdjustedScore*(A) - AdjustedScore*(B)]
          + w₂ × Tac*(A, B)
          + w₃ × H2H*(A, B)
          + w₄ × RelGDComp*(A, B)
```

Where weights reflect approximate category shares:

| Weight | Component | Starting value |
|---|---|---|
| w₁ | Base + match adjustments (Layer 1 + 2a) | ~0.55 |
| w₂ | Tactical matchup | ~0.15 |
| w₃ | Head-to-head | ~0.10 |
| w₄ | Relative GD Comparison | ~0.20 |

Weights sum to 1.0. Exact values tuned during Phase 6 backtesting.

---

## Step 6: Sigmoid → Win Probability

```
P(A wins) = 1 / (1 + e^(-Gap(A,B) / k_sig))

P(B wins) = 1 - P(A wins)
```

Where `k_sig` is the steepness constant (tuned during backtesting).

Properties:
- Gap = 0 → P(A wins) = 0.50 (even match)
- Gap > 0 → P(A wins) > 0.50 (A favored)
- Gap < 0 → P(A wins) < 0.50 (B favored)
- Gap → +∞ → P(A wins) → 1.00 (never reaches it)
- Gap → -∞ → P(A wins) → 0.00 (never reaches it)

---

## Full Pipeline Summary (end to end)

```
For a match between Team A and Team B:

  ┌─────────────────────────────────────────────────────────┐
  │ STEP 0: Confederation Calibration                       │
  │   r(T) = r_raw(T) × C(conf(T))                         │
  └─────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────┐
  │ STEP 1: Layer 1 — Base Team Score (per team)            │
  │                                                         │
  │   StaticGD(T) = avg of [GD × M(opponent_rank)]          │
  │   PlayerPerf(T) = depth_decay × avg of [τ(p) × R(p)]   │
  │   Current(T) = 0.45 × StaticGD* + 0.55 × PlayerPerf*   │
  │   BaseScore(T) = w_hist × H* + w_curr × Current         │
  └─────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────┐
  │ STEP 2: Layer 2a — Per-Team Adjustments                 │
  │                                                         │
  │   AdjustedScore(T) = BaseScore(T) + HomeAdv + Stakes    │
  └─────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────┐
  │ STEP 3: Layer 2b — Relational Terms (per matchup)       │
  │                                                         │
  │   Tac(A,B) = matchup matrix lookup                      │
  │   H2H(A,B) = capped recency-weighted win ratio          │
  │   RelGDComp(A,B) = contextualized overperformance gap   │
  └─────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────┐
  │ STEP 4: Normalize all components                        │
  └─────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────┐
  │ STEP 5: Weighted combination                            │
  │                                                         │
  │   Gap = w₁ × [AdjScore*(A) - AdjScore*(B)]              │
  │       + w₂ × Tac*(A,B)                                  │
  │       + w₃ × H2H*(A,B)                                  │
  │       + w₄ × RelGDComp*(A,B)                             │
  └─────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────┐
  │ STEP 6: Sigmoid conversion                              │
  │                                                         │
  │   P(A wins) = 1 / (1 + e^(-Gap / k_sig))               │
  │   P(B wins) = 1 - P(A wins)                             │
  └─────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────┐
  │ STEP 7: Monte Carlo Simulation                          │
  │                                                         │
  │   Repeat N times (N = 10,000+):                         │
  │     For each fixture in bracket:                        │
  │       Sample winner from P(A wins)                      │
  │       Advance winner to next round                      │
  │     Record tournament winner                            │
  │                                                         │
  │   Tournament winner odds = count / N per team           │
  │   Round advancement odds = count / N per team per round │
  └─────────────────────────────────────────────────────────┘
```

---

## Parameters to Tune (Phase 6 Backtesting)

| Parameter | What it controls | Method |
|---|---|---|
| `C(conf)` per confederation | Ranking calibration across confederations | Historical ranking-vs-performance analysis |
| M(r) anchor values | How much opponent quality amplifies GD | Grid search + Brier score |
| `k_rel` | Log compression in Relative GD | Grid search + Brier score |
| `k_sig` | Sigmoid steepness (probability sensitivity) | Grid search + calibration check |
| `w₁, w₂, w₃, w₄` | Cross-component weights in gap | Grid search + Brier score |
| 0.45 / 0.55 split | Static GD vs Player Perf within current score | Grid search + Brier score |
| w_hist / w_curr curve | Historical vs current balance per round | Grid search + Brier score |
| `α_home` | Home advantage magnitude | Grid search + Brier score |
| `α_stakes` | Stakes adjustment magnitude | Grid search + Brier score |
| `α_h2h` | H2H cap | Grid search + Brier score |
| Matchup matrix values | Tactical interaction strengths | Grid search + Brier score |
| `Context(A,B)` function | Relative GD contextualization | Grid search + Brier score |
| `τ(p)` threshold | Min caps before tactical importance kicks in | Sensitivity analysis |
| `D(T,g)` decay rate | Squad depth fatigue function | Grid search + Brier score |

All tuned together as one combined search problem, not individually.
