#!/usr/bin/env python3.10
"""
Backtest & Weight Search
========================
Uses real WC 2018 + 2022 data to score the model's calibration (Brier
score) and search for weights that improve on the hand-picked defaults.

Tunes the model's main "combination" weights:
  - W_BASE / W_TAC / W_H2H / W_REL_GD   (must sum to 1.0)
  - WEIGHT_STATIC_GD / WEIGHT_PLAYER_PERF (must sum to 1.0)
  - K_SIG                                (sigmoid steepness)

Every match in 2018 and 2022 (group + knockout, ~128 matches total) is
predicted "as-of" — using only data available strictly before that match —
via wc_predictor's evaluate_brier(). Draws are scored as a 0.5 outcome
since the model only predicts a win probability.

Usage: python3.10 backtest_weights.py [n_iterations]
"""

import importlib.util
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
YEARS = [2018, 2022]

spec = importlib.util.spec_from_file_location("wc_predictor", os.path.join(HERE, "wc_predictor (1).py"))
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

DEFAULT_WEIGHTS = {
    "W_BASE": wcp.W_BASE, "W_TAC": wcp.W_TAC, "W_H2H": wcp.W_H2H, "W_REL_GD": wcp.W_REL_GD,
    "WEIGHT_STATIC_GD": wcp.WEIGHT_STATIC_GD, "WEIGHT_PLAYER_PERF": wcp.WEIGHT_PLAYER_PERF,
    "K_SIG": wcp.K_SIG,
}


def dirichlet_sample(n, rng, concentration=2.0):
    """n positive values summing to 1.0."""
    xs = [rng.gammavariate(concentration, 1.0) for _ in range(n)]
    total = sum(xs)
    return [x / total for x in xs]


def random_candidate(rng):
    w_base, w_tac, w_h2h, w_rel = dirichlet_sample(4, rng)
    static_gd, player_perf = dirichlet_sample(2, rng)
    k_sig = rng.uniform(0.3, 2.0)
    return {
        "W_BASE": w_base, "W_TAC": w_tac, "W_H2H": w_h2h, "W_REL_GD": w_rel,
        "WEIGHT_STATIC_GD": static_gd, "WEIGHT_PLAYER_PERF": player_perf,
        "K_SIG": k_sig,
    }


def apply_weights(weights):
    for name, value in weights.items():
        setattr(wcp, name, value)


def evaluate(weights):
    apply_weights(weights)
    brier, n = wcp.evaluate_brier(DATA_DIR, YEARS)
    return brier, n


def fmt(weights):
    return (f"W_BASE={weights['W_BASE']:.3f} W_TAC={weights['W_TAC']:.3f} "
            f"W_H2H={weights['W_H2H']:.3f} W_REL_GD={weights['W_REL_GD']:.3f}  |  "
            f"STATIC_GD={weights['WEIGHT_STATIC_GD']:.3f} PLAYER_PERF={weights['WEIGHT_PLAYER_PERF']:.3f}  |  "
            f"K_SIG={weights['K_SIG']:.3f}")


def main():
    n_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    rng = random.Random(42)

    print(f"Backtesting on real WC {YEARS} ({len(YEARS)} tournaments)")
    print("=" * 70)

    baseline_brier, n_matches = evaluate(DEFAULT_WEIGHTS)
    print(f"\nDefault weights:  Brier = {baseline_brier:.4f}   ({n_matches} matches)")
    print(f"  {fmt(DEFAULT_WEIGHTS)}")
    print(f"\n(Reference: always predicting 50/50 scores exactly 0.25 Brier.)")

    print(f"\nSearching {n_iter} random weight combinations...")
    best_weights = DEFAULT_WEIGHTS
    best_brier = baseline_brier

    for i in range(n_iter):
        candidate = random_candidate(rng)
        brier, _ = evaluate(candidate)
        if brier < best_brier:
            best_brier = brier
            best_weights = candidate
            print(f"  [{i+1}/{n_iter}] new best: Brier = {brier:.4f}   {fmt(candidate)}")

    apply_weights(DEFAULT_WEIGHTS)  # restore defaults, don't leave module mutated

    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    print(f"Default:  Brier = {baseline_brier:.4f}")
    print(f"Best:     Brier = {best_brier:.4f}   ({(baseline_brier - best_brier) / baseline_brier * 100:+.1f}% vs default)")
    print(f"\nBest weights:\n  {fmt(best_weights)}")

    if best_weights is not DEFAULT_WEIGHTS:
        import json
        with open("/tmp/best_weights.json", "w") as f:
            json.dump(best_weights, f, indent=2)
        print("\nWrote /tmp/best_weights.json")


if __name__ == "__main__":
    main()
