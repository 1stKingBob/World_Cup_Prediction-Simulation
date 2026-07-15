#!/usr/bin/env python3.10
"""
Holdout validation for coordinate_descent_tuning.py's result.

Trains the same coordinate-descent sweep on ONE year only, then checks the
resulting weights' Brier score on the OTHER year (never touched during
tuning). If the found weights are real signal, held-out performance should
be close to training performance. If it's overfitting to a small 128-match
sample, held-out performance will be much worse than training performance.
"""

import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

spec = importlib.util.spec_from_file_location("wc_predictor", os.path.join(HERE, "wc_predictor (1).py"))
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_DATASET = None


def evaluate_on(dataset, years):
    brier, _ = wcp.evaluate_brier(DATA_DIR, years, dataset=dataset)
    return brier


def evaluate():
    return evaluate_on(TRAIN_DATASET, TRAIN_YEARS)


def set_simplex(names, values):
    total = sum(values)
    for n, v in zip(names, values):
        setattr(wcp, n, v / total)


def get_simplex(names):
    return [getattr(wcp, n) for n in names]


def sweep_simplex_dim(names, idx, candidates):
    base = get_simplex(names)
    others_idx = [i for i in range(len(names)) if i != idx]
    others_base = [base[i] for i in others_idx]
    others_sum = sum(others_base) or 1.0
    best_value, best_brier, best_group = base[idx], evaluate(), base
    for v in candidates:
        remaining = 1.0 - v
        trial = list(base)
        trial[idx] = v
        for i in others_idx:
            trial[i] = base[i] / others_sum * remaining
        set_simplex(names, trial)
        b = evaluate()
        if b < best_brier:
            best_value, best_brier, best_group = v, b, trial
    set_simplex(names, best_group)
    return best_brier


def sweep_scalar(attr_name, candidates):
    base = getattr(wcp, attr_name)
    best_value, best_brier = base, evaluate()
    for v in candidates:
        setattr(wcp, attr_name, v)
        b = evaluate()
        if b < best_brier:
            best_value, best_brier = v, b
    setattr(wcp, attr_name, best_value)
    return best_brier


def sweep_h2h_tier(candidates_wc, candidates_fr):
    best_brier = evaluate()
    best_wc = wcp.H2H_TIER_WEIGHTS["world_cup"]
    for v in candidates_wc:
        wcp.H2H_TIER_WEIGHTS["world_cup"] = v
        b = evaluate()
        if b < best_brier:
            best_wc, best_brier = v, b
    wcp.H2H_TIER_WEIGHTS["world_cup"] = best_wc
    best_fr = wcp.H2H_TIER_WEIGHTS["friendly"]
    for v in candidates_fr:
        wcp.H2H_TIER_WEIGHTS["friendly"] = v
        b = evaluate()
        if b < best_brier:
            best_fr, best_brier = v, b
    wcp.H2H_TIER_WEIGHTS["friendly"] = best_fr
    return best_brier


def reset_defaults():
    wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = 0.55, 0.15, 0.10, 0.20
    wcp.WEIGHT_STATIC_GD, wcp.WEIGHT_PLAYER_PERF = 0.45, 0.55
    wcp.HIST_WEIGHTS = [1.00, 0.92, 0.83, 0.73, 0.62, 0.49, 0.34, 0.15]
    wcp.CURR_WEIGHTS = [1 - h for h in wcp.HIST_WEIGHTS]
    wcp.K_SIG = 1.4
    wcp.H2H_TIER_WEIGHTS = {"world_cup": 1.3, "other": 1.0, "friendly": 0.7}
    wcp.H2H_MAX_AGE_YEARS = 5
    wcp.H2H_DECAY_POWER = 1.5


def run_coordinate_descent(label):
    frac_grid = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
                 0.50, 0.55, 0.60, 0.65, 0.70]
    gap_names = ["W_BASE", "W_TAC", "W_H2H", "W_REL_GD"]
    layer1_names = ["WEIGHT_STATIC_GD", "WEIGHT_PLAYER_PERF"]

    reset_defaults()
    start = evaluate()

    for cycle in range(2):
        for i in range(4):
            sweep_simplex_dim(gap_names, i, frac_grid)
        sweep_simplex_dim(layer1_names, 0, frac_grid)
        sweep_scalar("K_SIG", [0.6, 0.8, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0])
        sweep_h2h_tier([1.0, 1.2, 1.4, 1.6, 1.8, 2.0], [0.3, 0.5, 0.7, 0.9, 1.0])
        sweep_scalar("H2H_MAX_AGE_YEARS", [2, 3, 4, 5, 6, 7, 8])
        sweep_scalar("H2H_DECAY_POWER", [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0])

    end = evaluate()
    print(f"[{label}] train Brier: {start:.4f} -> {end:.4f}")
    print(f"  W_BASE={wcp.W_BASE:.3f} W_TAC={wcp.W_TAC:.3f} W_H2H={wcp.W_H2H:.3f} W_REL_GD={wcp.W_REL_GD:.3f}")
    print(f"  WEIGHT_STATIC_GD={wcp.WEIGHT_STATIC_GD:.3f} K_SIG={wcp.K_SIG:.3f}")
    print(f"  H2H_TIER_WEIGHTS={wcp.H2H_TIER_WEIGHTS}  H2H_MAX_AGE_YEARS={wcp.H2H_MAX_AGE_YEARS}  H2H_DECAY_POWER={wcp.H2H_DECAY_POWER:.3f}")
    return end


def main():
    global TRAIN_DATASET, TRAIN_YEARS

    print("Loading datasets...")
    full_dataset = wcp.load_backtest_dataset(DATA_DIR, [2018, 2022])
    print("Done.\n")

    for train_year, test_year in [(2018, 2022), (2022, 2018)]:
        print("=" * 70)
        print(f"TRAIN ON {train_year}, TEST ON {test_year}")
        print("=" * 70)

        TRAIN_YEARS = [train_year]
        TRAIN_DATASET = full_dataset
        run_coordinate_descent(f"train={train_year}")

        test_brier = evaluate_on(full_dataset, [test_year])
        print(f"  >>> HELD-OUT Brier on {test_year}: {test_brier:.4f}")

        # baseline: what does the *original default* weights get on the held-out year?
        reset_defaults()
        baseline_test = evaluate_on(full_dataset, [test_year])
        print(f"  >>> baseline (default weights) Brier on {test_year}: {baseline_test:.4f}")
        print()


if __name__ == "__main__":
    main()
