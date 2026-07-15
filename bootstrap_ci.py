"""
Bootstrap confidence intervals for Brier scores and score DIFFERENCES.

Every weight-tuning decision this session was made by eyeballing a single
point estimate (e.g. "0.1628 -> 0.1590, that's better"). With 320 train /
163 holdout matches, small deltas can easily be noise — the H2H tier/decay
sweep's 0.0003-0.0004 "improvement" was flagged as suspect for exactly this
reason but never actually quantified. This script does that properly:

  - bootstrap_ci(): percentile CI on a single config's Brier score, by
    resampling MATCHES (not errors independently — same match's error stays
    together, but which matches appear in a given resample varies).
  - paired_bootstrap_diff(): CI on the DIFFERENCE between two configs'
    scores, using the SAME resampled match indices for both — this is the
    standard paired-bootstrap approach and has much tighter variance than
    comparing two independent CIs, because it cancels out cross-match
    variance that both configs share.

Applied to the two live decisions from this session:
  1. Gap-combination weights: adopted (W_BASE/W_TAC/W_H2H/W_REL_GD + K_SIG)
  2. H2H tier/decay params: rejected (ALPHA_H2H already removed separately;
     this checks H2H_DECAY_POWER + tier weights)
"""
import importlib.util
import numpy as np

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]
N_BOOT = 5000
RNG = np.random.default_rng(0)


def get_errors(years, dataset):
    _, _, errors = wcp.evaluate_brier("data", years, dataset=dataset, return_errors=True)
    return np.array([e[2] for e in errors])


def bootstrap_ci(errors, n_boot=N_BOOT):
    n = len(errors)
    means = np.empty(n_boot)
    for i in range(n_boot):
        idx = RNG.integers(0, n, n)
        means[i] = errors[idx].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return errors.mean(), lo, hi


def paired_bootstrap_diff(errors_a, errors_b, n_boot=N_BOOT):
    """errors_a/errors_b must be the same length, same match order (a - b)."""
    n = len(errors_a)
    diffs = errors_a - errors_b
    boot_means = np.empty(n_boot)
    for i in range(n_boot):
        idx = RNG.integers(0, n, n)
        boot_means[i] = diffs[idx].mean()
    lo, hi = np.percentile(boot_means, [2.5, 97.5])
    point = diffs.mean()
    significant = (lo > 0) or (hi < 0)
    return point, lo, hi, significant


print("Loading datasets...")
train_ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
holdout_ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)

# =============================================================================
# Part 1: plain CI on current (adopted) defaults
# =============================================================================
print("\n=== Current defaults: Brier score with 95% CI ===")
train_errors = get_errors(TRAIN_YEARS, train_ds)
holdout_errors = get_errors(HOLDOUT_YEARS, holdout_ds)
t_mean, t_lo, t_hi = bootstrap_ci(train_errors)
h_mean, h_lo, h_hi = bootstrap_ci(holdout_errors)
print(f"  train   ({len(train_errors)}): {t_mean:.4f}  [{t_lo:.4f}, {t_hi:.4f}]")
print(f"  holdout ({len(holdout_errors)}): {h_mean:.4f}  [{h_lo:.4f}, {h_hi:.4f}]")

# =============================================================================
# Part 2: was the gap-weight optimization (adopted) actually significant?
# =============================================================================
print("\n=== Gap-combination weights: old defaults vs adopted ===")
OLD_W = (0.55, 0.15, 0.10, 0.20)
OLD_K_SIG = 1.4
NEW_W = (wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD)
NEW_K_SIG = wcp.K_SIG

wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = OLD_W
wcp.K_SIG = OLD_K_SIG
old_train = get_errors(TRAIN_YEARS, train_ds)
old_holdout = get_errors(HOLDOUT_YEARS, holdout_ds)

wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = NEW_W
wcp.K_SIG = NEW_K_SIG
new_train = get_errors(TRAIN_YEARS, train_ds)
new_holdout = get_errors(HOLDOUT_YEARS, holdout_ds)

pt, plo, phi, psig = paired_bootstrap_diff(old_train, new_train)
print(f"  train   diff (old-new): {pt:+.4f}  [{plo:+.4f}, {phi:+.4f}]  significant={psig}")
ph, phlo, phhi, phsig = paired_bootstrap_diff(old_holdout, new_holdout)
print(f"  holdout diff (old-new): {ph:+.4f}  [{phlo:+.4f}, {phhi:+.4f}]  significant={phsig}")

# =============================================================================
# Part 3: was the H2H tier/decay "improvement" (rejected) actually noise?
# =============================================================================
print("\n=== H2H tier/decay params: current defaults vs optimizer's result ===")
CUR_DECAY_POWER = wcp.H2H_DECAY_POWER
CUR_TIER = dict(wcp.H2H_TIER_WEIGHTS)

cur_train = get_errors(TRAIN_YEARS, train_ds)
cur_holdout = get_errors(HOLDOUT_YEARS, holdout_ds)

wcp.H2H_DECAY_POWER = 4.0
wcp.H2H_TIER_WEIGHTS = {"world_cup": 3.0, "other": 1.0, "friendly": 0.2}
opt_train = get_errors(TRAIN_YEARS, train_ds)
opt_holdout = get_errors(HOLDOUT_YEARS, holdout_ds)

pt2, plo2, phi2, psig2 = paired_bootstrap_diff(cur_train, opt_train)
print(f"  train   diff (cur-opt): {pt2:+.4f}  [{plo2:+.4f}, {phi2:+.4f}]  significant={psig2}")
ph2, phlo2, phhi2, phsig2 = paired_bootstrap_diff(cur_holdout, opt_holdout)
print(f"  holdout diff (cur-opt): {ph2:+.4f}  [{phlo2:+.4f}, {phhi2:+.4f}]  significant={phsig2}")

# restore
wcp.H2H_DECAY_POWER = CUR_DECAY_POWER
wcp.H2H_TIER_WEIGHTS = CUR_TIER
