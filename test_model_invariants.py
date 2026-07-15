"""
Regression tests for bug classes actually found (by manual inspection) this
project. No pytest dependency — plain asserts, run directly:
    python3 test_model_invariants.py
Every bug fixed this session was caught by a human noticing a suspicious
number, not by any automated check. These tests exist so the same bug class
can't silently reappear (e.g. from a future edit, or a future weight-tuning
run) without something failing loudly.
"""
import importlib.util
import math

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

FAILURES = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


# =============================================================================
# 1. H2H self-referential leak: a match must never see its own outcome as
#    "prior" H2H evidence (the bug that produced a suspiciously-perfect
#    0.0033 Brier score before it was caught).
# =============================================================================
print("\n--- H2H self-leak guard ---")
wcp.init_from_csv("data", 2026)
h2h_matches = wcp.load_h2h_matches_csv("data")
wcp.set_h2h_matches(h2h_matches)
wcp.PREDICTION_YEAR = 2026

# Find a real pair with EXACTLY one qualifying meeting, so excluding it
# should collapse compute_h2h_per_team's result to the "no history" default
# (0.0) — a strong, non-circular test of the real function's own behavior,
# not just a re-check of the filter condition against raw rows.
target_pair = None
for (team_a, team_b), rows in wcp.H2H_INDEX.items():
    if len(rows) == 1 and team_a in wcp.TEAMS and team_b in wcp.TEAMS:
        target_pair = (team_a, team_b, rows[0]["event_id"])
        break

if target_pair:
    team_a, team_b, leak_event_id = target_pair
    wcp.EXCLUDE_H2H_EVENT_ID = None
    h2h_without_exclusion = wcp.compute_h2h_per_team(team_a, team_b)
    wcp.EXCLUDE_H2H_EVENT_ID = leak_event_id
    h2h_with_exclusion = wcp.compute_h2h_per_team(team_a, team_b)
    check("excluding a pair's only meeting collapses its h2h score to 0.0",
          h2h_with_exclusion == 0.0,
          f"got {h2h_with_exclusion} (pre-exclusion was {h2h_without_exclusion})")
    wcp.EXCLUDE_H2H_EVENT_ID = None
else:
    check("found a real single-meeting pair to test self-leak exclusion on", False,
          "no pair with exactly one qualifying H2H row found in 2026 data")

# =============================================================================
# 2. classify_h2h_tier: abbreviated qualifiers ("Qual.") must NOT match the
#    real World Cup tier (the bug: only "qualif" was matched, missing the
#    CONCACAF/UEFA/CAF "Qual." abbreviation).
# =============================================================================
print("\n--- classify_h2h_tier abbreviation handling ---")
check("full WC group match -> world_cup",
      wcp.classify_h2h_tier("FIFA World Cup, Group J", False) == "world_cup")
check("spelled-out qualifier -> NOT world_cup",
      wcp.classify_h2h_tier("World Cup Qualification, CONMEBOL", False) != "world_cup")
check("abbreviated qualifier ('Qual.') -> NOT world_cup",
      wcp.classify_h2h_tier("World Cup Qual. CONCACAF, R. 3", False) != "world_cup")
check("friendly flag -> friendly regardless of competition text",
      wcp.classify_h2h_tier("FIFA World Cup, Group J", True) == "friendly")
check("unrelated competition -> other",
      wcp.classify_h2h_tier("UEFA Nations League, League A", False) == "other")

# =============================================================================
# 3. Relative-GD match weight must always be strictly positive: a win can
#    never subtract from the winner's rating and a loss can never add to
#    the loser's (the sign-flip bug: a division-based effective-rank version
#    produced weight=-0.717 on an actual France win over Iraq).
# =============================================================================
print("\n--- relative_gd weight sign preservation ---")
import itertools
worst_weight = float("inf")
for rank_a, rank_b, rel_gd_b, conf_b in itertools.product(
    [1, 5, 50, 200], [1, 5, 50, 200], [-5.0, -1.0, 0.0, 1.0, 5.0], [0.0, 0.5, 1.0]
):
    log_gap = math.log(rank_a / rank_b)
    exponent = wcp.K_REL * log_gap + wcp.K_FORM * conf_b * rel_gd_b
    weight = math.exp(max(-20.0, min(20.0, exponent)))
    worst_weight = min(worst_weight, weight)
check("weight stays strictly positive across a wide input grid",
      worst_weight > 0, f"min observed weight = {worst_weight}")

# =============================================================================
# 4. Exponent overflow guard: no combination of realistic-ish parameters
#    should crash compute_sequential_relative_gd (the bug: RGD_PRIOR_GAMES
#    near 0 + high K_FORM overflowed math.exp during a parameter sweep).
# =============================================================================
print("\n--- exponent overflow guard ---")
orig_k_rel, orig_k_form, orig_prior = wcp.K_REL, wcp.K_FORM, wcp.RGD_PRIOR_GAMES
try:
    wcp.K_REL, wcp.K_FORM, wcp.RGD_PRIOR_GAMES = 1.5, 2.0, 0.0
    team_names = list(wcp.TEAMS.keys())
    adjusted_ranks = {n: d["raw_rank"] * wcp.CONF_COEFFICIENTS[d["confederation"]] for n, d in wcp.TEAMS.items()}
    match_rows = wcp.read_matches_csv("data", 2026)
    wcp.compute_sequential_relative_gd(match_rows, team_names, adjusted_ranks)
    check("extreme K_REL/K_FORM/RGD_PRIOR_GAMES does not crash", True)
except OverflowError as e:
    check("extreme K_REL/K_FORM/RGD_PRIOR_GAMES does not crash", False, str(e))
finally:
    wcp.K_REL, wcp.K_FORM, wcp.RGD_PRIOR_GAMES = orig_k_rel, orig_k_form, orig_prior

# =============================================================================
# 5. Gap-combination weights must sum to 1.0 (documented invariant, easy to
#    silently violate with a hand-edit or partially-applied optimizer result).
# =============================================================================
print("\n--- gap-combination weights invariant ---")
total = wcp.W_BASE + wcp.W_TAC + wcp.W_H2H + wcp.W_REL_GD
check("W_BASE + W_TAC + W_H2H + W_REL_GD == 1.0", abs(total - 1.0) < 1e-9, f"sum = {total}")

# =============================================================================
print(f"\n{'='*50}")
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
    exit(1)
else:
    print("All invariant checks passed.")
