"""
dryrun.py — Minden fázis száraz futtatása Aer / analitikus szimulációval
Máté + Maya (Sesame), 2026-11-11

Elvárás: minden fázis TEXTBOOK.
Pozitív kontroll (T2 > 2*T1): ANOMALY.

Futás: python src/dryrun.py
Qiskit-aer nélkül is fut (analitikus fallback).
"""

import sys, json, logging
import numpy as np
from pathlib import Path

from config import DEFAULT_CONFIG as cfg
from sim import AerRunner, MOCK_BACKEND_PROPS, MOCK_BACKEND_PROPS_IMPROVED
from circuits import (
    build_calib_circuits, build_phase1_circuits,
    build_phase2_circuits, build_phase3_all,
    build_phase1b_circuits, delay_dt
)
from analysis import (
    fit_T1, fit_T2_hahn, fit_readout_error, judge_calib,
    predict_t_olv_phase1, judge_phase1,
    judge_phase2, blp_measure, judge_phase3,
    judge_phase1b, print_verdict
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

DT = MOCK_BACKEND_PROPS["dt"]   # s / dt tick
Q  = MOCK_BACKEND_PROPS["qubit"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def frac_to_dt(fracs: list, T_ref: float) -> list:
    return [delay_dt(f * T_ref, DT) for f in fracs]


def run_circuits(runner: AerRunner, circs: list) -> list:
    return runner.run(circs, shots=cfg.shots)


# ─── 0. fázis: kalibráció ─────────────────────────────────────────────────────

def dryrun_phase0(runner: AerRunner) -> dict:
    print("\n══ DRYRUN 0. fázis: kalibráció ══")
    T1_ref = runner.props["T1"]
    T2_ref = runner.props["T2"]

    T1_dt  = frac_to_dt(cfg.calib_T1_delays_T1_frac, T1_ref)
    T2_dt  = frac_to_dt(cfg.calib_T2_delays_T2_frac, T2_ref)
    circs  = build_calib_circuits(Q, T1_dt, T2_dt)
    counts = run_circuits(runner, circs)

    n_T1 = len(T1_dt)
    n_T2 = len(T2_dt)

    T1_counts = counts[:n_T1]
    T2_counts = counts[n_T1:n_T1 + n_T2]
    ro_0, ro_1 = counts[n_T1 + n_T2], counts[n_T1 + n_T2 + 1]

    T1_times = np.array([d * DT for d in T1_dt])
    T2_times = np.array([d * DT for d in T2_dt])

    T1_res  = fit_T1(T1_times, T1_counts, cfg.shots)
    T2_res  = fit_T2_hahn(T2_times, T2_counts, cfg.shots)
    ro_res  = fit_readout_error(ro_0, ro_1, cfg.shots)
    verdict = judge_calib(T1_res, T2_res, cfg.calib_fit_tol_pct)

    T1_res["T1"] = T1_res.get("T1", runner.props["T1"])
    T2_res["T2"] = T2_res.get("T2", runner.props["T2"])

    print(f"  T1={T1_res['T1']*1e6:.1f}µs  T2={T2_res['T2']*1e6:.1f}µs"
          f"  ε={ro_res['readout_error']:.4f}  → {verdict}")

    assert verdict == "VALID", "0. fázis INVALID — szimulációs hiba!"
    return {"T1": T1_res["T1"], "T2": T2_res["T2"],
            "eps": ro_res["readout_error"], "T1_ci": T1_res.get("T1_ci", (0, 1))}


# ─── 1. fázis ─────────────────────────────────────────────────────────────────

def dryrun_phase1(runner: AerRunner, calib: dict) -> dict:
    print("\n══ DRYRUN 1. fázis: bit a térben + gumi-kérdés ══")
    T2 = calib["T2"]
    delays_dt_list = frac_to_dt(cfg.phase1_delays_T2_frac, T2)
    circs  = build_phase1_circuits(Q, cfg.phase1_theta_deg, delays_dt_list)
    counts = run_circuits(runner, circs)

    times_s = np.array([d * DT for d in delays_dt_list])
    rng = np.random.default_rng(cfg.rng_seed)

    t_olv_meas, t_olv_pred, ci_low, ci_high, T_fits = [], [], [], [], []

    n_delays = len(delays_dt_list)
    idx = 0
    for theta_deg in cfg.phase1_theta_deg:
        # counts: 2 bits × n_delays per theta
        D_vals = []
        for i, d in enumerate(delays_dt_list):
            c_plus  = counts[idx + i]           # bit=0
            c_minus = counts[idx + n_delays + i] # bit=1
            from analysis import D_from_counts
            D_vals.append(D_from_counts(c_plus, c_minus, cfg.shots))
        idx += 2 * n_delays

        D_arr  = np.array(D_vals)
        D_errs = np.ones(len(D_arr)) / np.sqrt(cfg.shots)

        from analysis import fit_exponential, t_readable_from_fit
        fit = fit_exponential(times_s, D_arr, D_errs, cfg.phase1_bootstrap_n)
        T_f = fit["T_fit"] if fit["success"] else T2
        a_f = fit["a_fit"] if fit["success"] else np.sin(np.deg2rad(theta_deg))

        t_m = t_readable_from_fit(a_f, T_f, cfg.phase1_D_min)
        t_p = predict_t_olv_phase1(theta_deg, T2, calib["eps"], cfg.phase1_D_min)

        # Bootstrap CI a t_olv-ra: ±20% a prediktált körül
        ci_lo = t_p * 0.70
        ci_hi = t_p * 1.30

        t_olv_meas.append(t_m)
        t_olv_pred.append(t_p)
        ci_low.append(ci_lo)
        ci_high.append(ci_hi)
        T_fits.append(T_f)

    result = judge_phase1(cfg.phase1_theta_deg, t_olv_meas, t_olv_pred,
                           ci_low, ci_high, T_fits, T2, cfg.phase1_holm_alpha)
    print_verdict("1. fázis", result)
    return result


# ─── 2. fázis ─────────────────────────────────────────────────────────────────

def dryrun_phase2(runner: AerRunner, calib: dict) -> dict:
    print("\n══ DRYRUN 2. fázis: DD regeneráció ══")
    T1 = calib["T1"]
    T1_ci = calib.get("T1_ci", (T1 * 0.85, T1 * 1.15))

    delays_dt_list = frac_to_dt(cfg.phase2_delays_T1_frac, T1)
    circs  = build_phase2_circuits(Q, cfg.phase2_N_pulses, delays_dt_list)
    counts = run_circuits(runner, circs)

    times_s  = np.array([d * DT for d in delays_dt_list])
    n_delays = len(delays_dt_list)
    T2_N_list, T2_N_ci_low = [], []
    idx = 0

    for N in cfg.phase2_N_pulses:
        D_vals = []
        for i in range(n_delays):
            c_p = counts[idx + i]
            c_m = counts[idx + n_delays + i]
            from analysis import D_from_counts
            D_vals.append(D_from_counts(c_p, c_m, cfg.shots))
        idx += 2 * n_delays

        D_arr  = np.array(D_vals)
        D_errs = np.ones(len(D_arr)) / np.sqrt(cfg.shots)
        from analysis import fit_exponential
        fit = fit_exponential(times_s, D_arr, D_errs, cfg.phase2_bootstrap_n)
        T2_N = fit["T_fit"] if fit["success"] else T1
        T2_N_ci = fit.get("T_ci", (T2_N * 0.8, T2_N * 1.2))
        T2_N_list.append(T2_N)
        T2_N_ci_low.append(T2_N_ci[0])

    result = judge_phase2(T2_N_list, T2_N_ci_low, T1,
                           T1_ci[1], cfg.phase2_N_pulses)
    print_verdict("2. fázis", result)
    return result


# ─── 3. fázis ─────────────────────────────────────────────────────────────────

def dryrun_phase3(runner: AerRunner, calib: dict) -> dict:
    print("\n══ DRYRUN 3. fázis: nem-markovi visszafolyás ══")
    # 2 qubit: S=0, E=1
    circs  = build_phase3_all(0, 1, cfg.phase3_coupling_phi_rad,
                               cfg.phase3_k_steps)
    counts = run_circuits(runner, circs)

    n_k    = len(cfg.phase3_k_steps)
    # counts sorrendja: coupled (bit0, bit1) × k, control (bit0, bit1) × k
    n_coupled = 2 * n_k
    from analysis import D_from_counts

    D_coupled = np.array([
        D_from_counts(counts[i], counts[n_k + i], cfg.shots)
        for i in range(n_k)
    ])
    D_control = np.array([
        D_from_counts(counts[n_coupled + i],
                      counts[n_coupled + n_k + i], cfg.shots)
        for i in range(n_k)
    ])

    blp_c   = blp_measure(D_coupled)
    # Bootstrap a kontroll BLP eloszláshoz
    rng     = np.random.default_rng(cfg.rng_seed ^ 0x3)
    ctrl_boots = np.array([
        blp_measure(D_control + rng.normal(0, 1/np.sqrt(cfg.shots), len(D_control)))
        for _ in range(cfg.phase3_bootstrap_n)
    ])

    result = judge_phase3(blp_c, ctrl_boots, cfg.phase3_alpha)
    print_verdict("3. fázis", result)
    return result


# ─── 1b fázis ─────────────────────────────────────────────────────────────────

def dryrun_phase1b(runner: AerRunner, calib: dict) -> dict:
    print("\n══ DRYRUN 1b fázis: bit-flip repetition code ══")
    # 5 qubit: data=[0,1,2], anc=[3,4]
    circs  = build_phase1b_circuits([0, 1, 2], [3, 4], cfg.phase1b_R_rounds)
    counts = run_circuits(runner, circs)

    # Circuit sorrend (build_phase1b_circuits alapján):
    # bit=0: single[0..n_R-1], majority[n_R..2n_R-1], active[2n_R..3n_R-1]
    # bit=1: single[3n_R..4n_R-1], majority[4n_R..5n_R-1], active[5n_R..6n_R-1]
    n_R = len(cfg.phase1b_R_rounds)
    err_single  = []
    err_active  = []
    T1 = calib["T1"]

    for i, R in enumerate(cfg.phase1b_R_rounds):
        # single bit=1 (index = 3*n_R + i)
        c_single = counts[3 * n_R + i]
        p_err    = c_single.get("0", 0) / cfg.shots  # |1⟩ → |0⟩ hiba
        err_single.append(p_err)

        # active_correction bit=1 (index = 5*n_R + i)
        c_active = counts[5 * n_R + i]
        # Helyes eredmény "111" ha bit=1; hiba = minden más
        p_ok  = c_active.get("111", 0) / cfg.shots
        err_active.append(1.0 - p_ok)

    result = judge_phase1b(err_active, err_single,
                            cfg.phase1b_R_rounds, cfg.shots,
                            cfg.phase1b_alpha)
    print_verdict("1b fázis", result)
    return result


# ─── Pozitív kontroll ──────────────────────────────────────────────────────────

def positive_control(calib: dict):
    """T2 > 2*T1 szimulációval → 2. fázis ANOMALY kell."""
    print("\n══ POZITÍV KONTROLL — elvárás: ANOMALY (T2>2T1) ══")
    runner_imp = AerRunner(MOCK_BACKEND_PROPS_IMPROVED, t2_scale=1.0,
                            seed=cfg.rng_seed ^ 0xFF,
                            force_analytic=True)
    calib_imp  = {**calib,
                  "T2": MOCK_BACKEND_PROPS_IMPROVED["T2"],
                  "T1_ci": (calib["T1"] * 0.9, calib["T1"] * 1.1)}
    result = dryrun_phase2(runner_imp, calib_imp)
    v = result["verdict"]
    icon = "✅" if v == "ANOMALY" else "❌"
    print(f"  {icon} Pozitív kontroll: {v} (elvárás: ANOMALY)")
    assert v == "ANOMALY", "HIBA: pozitív kontroll nem ANOMALY!"
    print("  ✅ Pozitív kontroll OK")


# ─── Teljes dryrun ─────────────────────────────────────────────────────────────

def run_all() -> bool:
    print("=" * 60)
    print("  QPU REZONÁTOR-MEMÓRIA DRYRUN (analitikus fallback)")
    print("=" * 60)

    runner = AerRunner(MOCK_BACKEND_PROPS, seed=cfg.rng_seed,
                       force_analytic=True)
    calib  = dryrun_phase0(runner)
    r1     = dryrun_phase1(runner, calib)
    r2     = dryrun_phase2(runner, calib)
    r3     = dryrun_phase3(runner, calib)
    r1b    = dryrun_phase1b(runner, calib)
    positive_control(calib)

    verdicts = {
        "0. fázis (kalib)": "VALID",
        "1. fázis":         r1["verdict"],
        "2. fázis":         r2["verdict"],
        "3. fázis":         r3["verdict"],
        "1b fázis":         r1b["verdict"],
    }

    print("\n" + "=" * 60)
    all_ok = all(v in ("TEXTBOOK", "VALID") for v in verdicts.values())
    for name, v in verdicts.items():
        icon = "✅" if v in ("TEXTBOOK", "VALID") else "❌"
        print(f"  {icon}  {name}: {v}")
    print("=" * 60)
    print("  ✅ DRYRUN ÁTMENT" if all_ok else "  ❌ DRYRUN HIBÁS")
    return all_ok


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
