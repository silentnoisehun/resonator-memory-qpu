"""
analyze_phase1.py — 1. fázis QPU eredmény elemzése
"""
import sys, json
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import DEFAULT_CONFIG as cfg
from circuits import delay_dt
from analysis import (
    fit_T1, fit_T2_hahn, fit_readout_error, judge_calib,
    predict_t_olv_phase1, fit_exponential, t_readable_from_fit,
    judge_phase1, print_verdict, counts_to_expectation, D_from_counts
)

DATA_DIR = Path("data/phase1")
raw      = json.loads((DATA_DIR / "raw_counts.json").read_text())
snap     = json.loads((DATA_DIR / "snapshot.json").read_text())
calib_r  = json.loads((DATA_DIR / "calib_result.json").read_text())

DT    = snap["dt"]
SHOTS = cfg.shots
names = raw["circuits"]
counts_all = raw["counts"]

# Index map
idx = {n: i for i, n in enumerate(names)}

# ── Kalib ───────────────────────────────────────────────────────────────────

T1_calib = calib_r["T1_us"] * 1e-6
T2_calib = calib_r["T2_us"] * 1e-6
eps      = calib_r["eps"]
T1_ci    = calib_r["T1_ci_us"]
T2_ci    = calib_r["T2_ci_us"]

print(f"Kalib: T1={T1_calib*1e6:.1f}µs  T2={T2_calib*1e6:.1f}µs  ε={eps:.4f}  → {calib_r['verdict']}")

# ── 1. fázis analízis ────────────────────────────────────────────────────────

p1_dt_list  = [delay_dt(f * T2_calib, DT) for f in cfg.phase1_delays_T2_frac]
times_s     = np.array([d * DT for d in p1_dt_list])
n_delays    = len(p1_dt_list)

rng = np.random.default_rng(cfg.rng_seed)

t_olv_meas, t_olv_pred, ci_low, ci_high, T_fits = [], [], [], [], []

for theta_deg in cfg.phase1_theta_deg:
    D_vals = []
    for i, d in enumerate(p1_dt_list):
        # signal +θ és -θ
        name_p = f"p1_th{int(theta_deg)}_b0_d{d}"
        name_m = f"p1_th{int(theta_deg)}_b1_d{d}"
        if name_p not in idx or name_m not in idx:
            print(f"  WARN: hiányzó áramkör {name_p} vagy {name_m}")
            D_vals.append(0.0)
            continue
        cp = counts_all[idx[name_p]]
        cm = counts_all[idx[name_m]]
        D_vals.append(D_from_counts(cp, cm, SHOTS))

    D_arr  = np.array(D_vals)
    D_errs = np.ones(len(D_arr)) / np.sqrt(SHOTS)

    fit = fit_exponential(times_s, D_arr, D_errs,
                          bootstrap_n=cfg.phase1_bootstrap_n,
                          rng_seed=cfg.rng_seed)
    T_fit = fit["T_fit"] if fit["success"] else T2_calib
    a_fit = fit["a_fit"] if fit["success"] else 1.0
    T_ci  = fit["T_ci"]

    t_olv_m = t_readable_from_fit(a_fit, T_fit, cfg.phase1_D_min)
    t_olv_p = predict_t_olv_phase1(theta_deg, T2_calib, eps, cfg.phase1_D_min)

    # 99% CI a t_olv-ra bootstrap-ból: T_ci alapján
    t_lo = t_readable_from_fit(a_fit, T_ci[0], cfg.phase1_D_min) if T_ci[0] > 0 else 0
    t_hi = t_readable_from_fit(a_fit, T_ci[1], cfg.phase1_D_min) if T_ci[1] > 0 else t_olv_p * 2

    t_olv_meas.append(t_olv_m)
    t_olv_pred.append(t_olv_p)
    ci_low.append(t_lo)
    ci_high.append(t_hi)
    T_fits.append(T_fit)

    print(f"  θ={theta_deg:4.0f}°  D_vals={[f'{v:.3f}' for v in D_vals]}")
    print(f"         T_fit={T_fit*1e6:.1f}µs  t_olv_meas={t_olv_m*1e6:.1f}µs  "
          f"t_olv_pred={t_olv_p*1e6:.1f}µs  CI=[{t_lo*1e6:.1f}, {t_hi*1e6:.1f}]µs")

result = judge_phase1(
    cfg.phase1_theta_deg, t_olv_meas, t_olv_pred,
    ci_low, ci_high, T_fits, T2_calib, cfg.phase1_holm_alpha
)
print_verdict("1. fázis", result)

# Mentés
(DATA_DIR / "phase1_result.json").write_text(
    json.dumps({k: (v if not isinstance(v, np.ndarray) else v.tolist())
                for k, v in result.items()}, indent=2)
)
print(f"\nEredmény mentve: {DATA_DIR}/phase1_result.json")
