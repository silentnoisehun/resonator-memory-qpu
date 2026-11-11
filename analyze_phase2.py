"""
analyze_phase2.py — 2. fázis (DD) offline elemzése a nyers counts-okból.

Nem csatlakozik az IBM-hez, jobot nem indít. Bemenet: data/phase2/raw_counts.json,
job_meta.json. Kimenet: data/phase2/calib_result.json, phase2_result.json.
Az elemzési lépések a submit_phase2.py-ban lévőkkel azonosak
(ugyanazok a függvények, ugyanaz a seed).
"""
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import DEFAULT_CONFIG as cfg
from rawdata import load_raw, need, write_json
from analysis import (fit_T1, fit_T2_hahn, fit_readout_error, judge_calib_detail,
                      judge_phase2, fit_exponential, print_verdict,
                      D_from_counts, counts_to_expectation)

C, meta, DATA_DIR = load_raw("phase2")
snap  = meta["snapshot"]
DT    = snap["dt"]
SHOTS = meta["shots"]


def delay_dt(t_s, dt_s):
    return max(1, int(np.ceil(t_s / dt_s)))


# A delay-rácsot a beküldő script a PILLANATKÉP T1/T2-jéből számolta; itt csak
# az áramkörök azonosítására kell.
T1_dt = [delay_dt(f * snap["T1"], DT) for f in cfg.calib_T1_delays_T1_frac]
T2_dt = [delay_dt(f * snap["T2"], DT) for f in cfg.calib_T2_delays_T2_frac]
p2_dt = [delay_dt(f * snap["T1"], DT) for f in cfg.phase2_delays_T1_frac]

# ── Kalibráció a job saját karjaiból ─────────────────────────────────────────
T1_res = fit_T1(np.array(T1_dt) * DT, [need(C, f"T1_d{d}") for d in T1_dt], SHOTS)
T2_res = fit_T2_hahn(np.array(T2_dt) * DT, [need(C, f"T2_hahn_d{d}") for d in T2_dt], SHOTS)
ro_res = fit_readout_error(need(C, "readout_0"), need(C, "readout_1"), SHOTS)
calib_verdict, reasons = judge_calib_detail(T1_res, T2_res, cfg.calib_fit_tol_pct)

calib_out = {
    "verdict": calib_verdict, "invalid_reasons": reasons,
    "source": "job saját kalibrációs karjai a raw_counts.json-ból",
    "job_id": meta["job_id"],
    "T1_us": T1_res["T1"] * 1e6, "T2_us": T2_res["T2"] * 1e6,
    "eps": ro_res["readout_error"],
    "T1_ci_us": [v * 1e6 for v in T1_res["T1_ci"]],
    "T2_ci_us": [v * 1e6 for v in T2_res["T2_ci"]],
    "ci_level": "99% (bootstrap percentilis 0.5–99.5)",
    "T1_chi2_red": T1_res.get("chi2_red"), "T2_chi2_red": T2_res.get("chi2_red"),
}
write_json(DATA_DIR / "calib_result.json", calib_out)
print(f"Kalib: T1={calib_out['T1_us']:.1f}µs CI=[{calib_out['T1_ci_us'][0]:.1f}, "
      f"{calib_out['T1_ci_us'][1]:.1f}]  T2_Hahn={calib_out['T2_us']:.1f}µs  "
      f"ε={calib_out['eps']:.4f}  → {calib_verdict}")

if calib_verdict != "VALID":
    result = {"verdict": "INVALID", "reason": "0. fázis (kalibráció) INVALID",
              "calib_invalid_reasons": reasons}
    write_json(DATA_DIR / "phase2_result.json", result)
    print_verdict("2. fázis", result)
    sys.exit(0)

# ── DD-karok ─────────────────────────────────────────────────────────────────
times_s = np.array(p2_dt) * DT
T2_N, T2_N_ci, chi2, D_tab, min_signed = [], [], [], [], []
failed = False
for N in cfg.phase2_N_pulses:
    cp = [need(C, f"p2_N{N}_b0_d{d}") for d in p2_dt]
    cm = [need(C, f"p2_N{N}_b1_d{d}") for d in p2_dt]
    D  = np.array([D_from_counts(a, b, SHOTS) for a, b in zip(cp, cm)])
    # Előjeles kontraszt — csak diagnosztika: ha negatívba megy, a lecsengés
    # nem tiszta exponenciális (koherens forgás), a |D|-re illesztett T2_N
    # ilyenkor nem értelmezhető koherenciaidőként.
    Ds = np.array([(counts_to_expectation(a, SHOTS) - counts_to_expectation(b, SHOTS)) / 2
                   for a, b in zip(cp, cm)])
    fit = fit_exponential(times_s, D, np.ones(len(D)) / np.sqrt(SHOTS),
                          bootstrap_n=cfg.phase2_bootstrap_n, rng_seed=cfg.rng_seed)
    if not fit["success"]:
        print(f"  N={N}: az illesztés nem konvergált"); failed = True; continue
    T2_N.append(fit["T_fit"]); T2_N_ci.append(list(fit["T_ci"]))
    chi2.append(fit["chi2_red"]); D_tab.append(D.tolist()); min_signed.append(float(Ds.min()))
    print(f"  N={N:3d}: T2_N={fit['T_fit']*1e6:.1f}µs  CI=[{fit['T_ci'][0]*1e6:.1f}, "
          f"{fit['T_ci'][1]*1e6:.1f}]  χ²_red={fit['chi2_red']:.2f}  min előjeles D={Ds.min():+.3f}")

if failed:
    result = {"verdict": "INVALID", "reason": "DD-illesztés nem konvergált"}
else:
    result = judge_phase2(T2_N, [ci[0] for ci in T2_N_ci],
                          T1_res["T1"], T1_res["T1_ci"][1], cfg.phase2_N_pulses)
    result.update({
        "job_id": meta["job_id"],
        "T2_N_ci": T2_N_ci, "T2_N_chi2_red": chi2,
        "anomaly_threshold_s": 2 * T1_res["T1_ci"][1],
        "D_abs": D_tab, "min_signed_D": min_signed,
        "fit_quality_note": [
            (f"N={N}: χ²_red={c:.1f}, az előjeles D negatívba megy ({m:+.3f}) — "
             "nem exponenciális lecsengés, a T2_N itt nem értelmezhető koherenciaidőként")
            for N, c, m in zip(cfg.phase2_N_pulses, chi2, min_signed) if c > 5.0 or m < -0.1],
    })
    result = {k: ([bool(x) if isinstance(x, (bool, np.bool_)) else x for x in v]
                  if isinstance(v, list) else v) for k, v in result.items()}
print_verdict("2. fázis", result)
write_json(DATA_DIR / "phase2_result.json", result)
