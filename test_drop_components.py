"""
Re-test whether W_TAC or W_H2H can be dropped (weight redistributed to the
other three via re-optimization) in the CURRENT model state — this matters
because the model has changed substantially since tactical was last tested
(intl_form and fifa_rank_signal were added since then, both folded into the
"historical"/W_BASE side), so that earlier conclusion may be stale.

Same discipline as every other test this session: softmax reparametrization
over the 3 remaining components (always positive, sums to 1) + K_SIG, train-
only fit, CV, holdout check, 4 random restarts, paired bootstrap on holdout.
"""
import importlib.util
import numpy as np
from scipy.optimize import minimize

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]

CURRENT_W = (wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD)
CURRENT_K_SIG = wcp.K_SIG

print(f"CURRENT: W_BASE={CURRENT_W[0]:.3f} W_TAC={CURRENT_W[1]:.3f} W_H2H={CURRENT_W[2]:.3f} "
      f"W_REL_GD={CURRENT_W[3]:.3f} K_SIG={CURRENT_K_SIG:.3f}")
print(f"  USE_INTL_FORM={wcp.USE_INTL_FORM}  USE_FIFA_RANK_SIGNAL={wcp.USE_FIFA_RANK_SIGNAL}")

train_ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
holdout_ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
fold_ds = {y: wcp.load_backtest_dataset("data", [y]) for y in TRAIN_YEARS}

ref_train, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=train_ds)
ref_holdout, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds)
print(f"  train={ref_train:.4f}  holdout={ref_holdout:.4f}")


def softmax3(u):
    e = np.exp(u - np.max(u))
    return e / e.sum()


def run_drop_test(drop_name, keep_slots):
    """keep_slots: e.g. ('W_BASE','W_H2H','W_REL_GD') if dropping W_TAC."""
    print(f"\n{'='*60}\nDROP {drop_name}\n{'='*60}")

    def apply_params(x):
        w = softmax3(np.array(x[:3]))
        vals = dict(zip(keep_slots, [float(v) for v in w]))
        vals[drop_name] = 0.0
        wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = vals["W_BASE"], vals["W_TAC"], vals["W_H2H"], vals["W_REL_GD"]
        wcp.K_SIG = float(np.clip(x[3], 0.3, 4.0))

    def train_brier(x):
        apply_params(x)
        s, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=train_ds)
        return s

    def cv_briers(x):
        apply_params(x)
        return [wcp.evaluate_brier("data", [y], dataset=fold_ds[y])[0] for y in TRAIN_YEARS]

    def holdout_brier(x):
        apply_params(x)
        s, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds)
        return s

    x0 = np.array([0.0, 0.0, 0.0, CURRENT_K_SIG])
    np.random.seed(13)
    starts = [x0] + [np.array([*np.random.uniform(-2, 2, 3), np.random.uniform(0.5, 2.5)]) for _ in range(3)]
    best = None
    for i, sx0 in enumerate(starts):
        r = minimize(train_brier, sx0, method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-8, "maxiter": 1500})
        apply_params(r.x)
        w = (wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD)
        ho = holdout_brier(r.x)
        print(f"  start {i}: W_BASE={w[0]:.3f} W_TAC={w[1]:.3f} W_H2H={w[2]:.3f} W_REL_GD={w[3]:.3f} "
              f"K_SIG={wcp.K_SIG:.3f}  train={r.fun:.4f}  holdout={ho:.4f}")
        if best is None or r.fun < best.fun:
            best = r

    apply_params(best.x)
    opt_train = train_brier(best.x)
    opt_cv = cv_briers(best.x)
    opt_holdout = holdout_brier(best.x)
    print(f"\n  BEST: train={opt_train:.4f}  cv_mean={np.mean(opt_cv):.4f}  cv_std={np.std(opt_cv):.4f}  holdout={opt_holdout:.4f}")
    print(f"  vs current: train delta={opt_train-ref_train:+.4f}  holdout delta={opt_holdout-ref_holdout:+.4f}")

    # paired bootstrap vs current on holdout
    wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = CURRENT_W
    wcp.K_SIG = CURRENT_K_SIG
    _, _, ref_err_list = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds, return_errors=True)
    ref_err = {(y, eid): e for (y, eid, e) in ref_err_list}
    apply_params(best.x)
    _, _, drop_err_list = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds, return_errors=True)
    drop_err = {(y, eid): e for (y, eid, e) in drop_err_list}
    common = sorted(set(ref_err) & set(drop_err))
    a = np.array([ref_err[k] for k in common])
    b = np.array([drop_err[k] for k in common])
    diffs = a - b
    rng = np.random.default_rng(0)
    n = len(common)
    boot = np.array([diffs[rng.integers(0, n, n)].mean() for _ in range(5000)])
    lo, hi = np.percentile(boot, [2.5, 97.5])
    print(f"  bootstrap (current - dropped): {diffs.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  significant={(lo>0) or (hi<0)}")

    # restore
    wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = CURRENT_W
    wcp.K_SIG = CURRENT_K_SIG


run_drop_test("W_TAC", ("W_BASE", "W_H2H", "W_REL_GD"))
run_drop_test("W_H2H", ("W_BASE", "W_TAC", "W_REL_GD"))
