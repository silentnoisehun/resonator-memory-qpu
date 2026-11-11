"""
analyze_phase1.py — 1. fázis QPU eredmény elemzése (AMENDED ANALYSIS)

Offline elemzés: csak a data/phase1/ alatti, már kimért adatokat olvassa.
Nem csatlakozik az IBM-hez, tokent nem igényel, jobot nem indít.

Bemenet (nem módosul):
    data/phase1/raw_counts.json   — nyers counts (ez az igazság)
    data/phase1/snapshot.json     — futtatás előtti backend-pillanatkép
                                    (csak a dt-hez és a delay-rács
                                    rekonstruálásához kell)
Kimenet (felülíródik):
    data/phase1/calib_result.json
    data/phase1/phase1_result.json

Javítások az eredeti elemzéshez képest (az eredeti, érvénytelen
ítéletfájlok a git-történetben megmaradnak: ea0fa8d, 7288337):
  a) A kalibrációt a job saját T1 / Hahn / readout karjaiból újraillesztjük
     (nem a korábbi calib_result.json-ból olvassuk). Értelmetlen fit →
     a kalib automatikusan INVALID, és az 1. fázis ítélete is INVALID.
  b) A tankönyvi jóslat a job saját Hahn-karjából mért T2-vel és a saját
     readout-karokból mért ε-nal számol, nem a pillanatkép T2-jével.
  c) in_band: a jóslatnak a mért t_olv 99%-os bootstrap CI-jébe kell esnie.
"""
import sys, json
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import DEFAULT_CONFIG as cfg
from analysis import (
    fit_T1, fit_T2_hahn, fit_readout_error, judge_calib_detail,
    predict_t_olv_phase1, fit_exponential, t_readable_from_fit,
    judge_phase1, print_verdict, D_from_counts
)

DATA_DIR = Path(__file__).parent / "data" / "phase1"
raw      = json.loads((DATA_DIR / "raw_counts.json").read_text())
snap     = json.loads((DATA_DIR / "snapshot.json").read_text())
meta     = json.loads((DATA_DIR / "job_meta.json").read_text())

if raw["job_id"] != meta["job_id"]:
    sys.exit(f"HIBA: raw_counts job_id ({raw['job_id']}) != job_meta job_id ({meta['job_id']})")

DT    = snap["dt"]
SHOTS = meta["shots"]
names = raw["circuits"]
counts_all = raw["counts"]


def delay_dt(t_s: float, dt_s: float) -> int:
    # Azonos a circuits.delay_dt-vel; ide másolva, hogy az offline elemzéshez
    # ne kelljen Qiskit (az auditáláshoz elég a numpy + scipy).
    return max(1, int(np.ceil(t_s / dt_s)))


def arm(prefix: str, dt_list):
    """Egy kar counts-ai név szerint. Hiányzó áramkör → hiba (nem találgatunk)."""
    out = []
    for d in dt_list:
        name = f"{prefix}_d{d}"
        hits = [i for i, n in enumerate(names) if n == name]
        if len(hits) != 1:
            sys.exit(f"HIBA: '{name}' {len(hits)}× szerepel a raw_counts.json-ban (elvárt: 1)")
        c = counts_all[hits[0]]
        if sum(c.values()) != SHOTS:
            sys.exit(f"HIBA: '{name}' shot-összeg {sum(c.values())} != {SHOTS}")
        out.append(c)
    return out


def single(name: str):
    hits = [i for i, n in enumerate(names) if n == name]
    if len(hits) != 1:
        sys.exit(f"HIBA: '{name}' {len(hits)}× szerepel (elvárt: 1)")
    return counts_all[hits[0]]


# A delay-rácsot a beküldő script a PILLANATKÉP T1/T2-jéből számolta; ezt
# csak az áramkörök azonosítására használjuk, a fizikai jóslatra NEM.
T1_dt_list = [delay_dt(f * snap["T1"], DT) for f in cfg.calib_T1_delays_T1_frac]
T2_dt_list = [delay_dt(f * snap["T2"], DT) for f in cfg.calib_T2_delays_T2_frac]
p1_dt_list = [delay_dt(f * snap["T2"], DT) for f in cfg.phase1_delays_T2_frac]

# ── Kalibráció a job saját karjaiból ─────────────────────────────────────────

T1_times = np.array([d * DT for d in T1_dt_list])
T2_times = np.array([d * DT for d in T2_dt_list])
T1_res = fit_T1(T1_times, arm("T1", T1_dt_list), SHOTS)
T2_res = fit_T2_hahn(T2_times, arm("T2_hahn", T2_dt_list), SHOTS)
ro_res = fit_readout_error(single("readout_0"), single("readout_1"), SHOTS)
calib_verdict, calib_reasons = judge_calib_detail(T1_res, T2_res, cfg.calib_fit_tol_pct)

T1_calib = T1_res["T1"]
T2_calib = T2_res["T2"]
eps      = ro_res["readout_error"]

calib_out = {
    "verdict": calib_verdict,
    "invalid_reasons": calib_reasons,
    "analysis": "amended",
    "source": "job saját kalibrációs karjai (T1_*, T2_hahn_*, readout_*) a raw_counts.json-ból",
    "job_id": raw["job_id"],
    "T1_us": T1_calib * 1e6,
    "T2_us": T2_calib * 1e6,
    "eps": eps,
    "T1_ci_us": [v * 1e6 for v in T1_res["T1_ci"]],
    "T2_ci_us": [v * 1e6 for v in T2_res["T2_ci"]],
    "T1_chi2_red": T1_res.get("chi2_red"),
    "T2_chi2_red": T2_res.get("chi2_red"),
    "snapshot_T1_us": snap["T1"] * 1e6,
    "snapshot_T2_us": snap["T2"] * 1e6,
}
(DATA_DIR / "calib_result.json").write_text(json.dumps(calib_out, indent=2, ensure_ascii=False) + "\n")

print(f"Kalib (job saját karjai): T1={T1_calib*1e6:.1f}µs "
      f"CI=[{T1_res['T1_ci'][0]*1e6:.1f}, {T1_res['T1_ci'][1]*1e6:.1f}]  "
      f"T2_Hahn={T2_calib*1e6:.1f}µs "
      f"CI=[{T2_res['T2_ci'][0]*1e6:.1f}, {T2_res['T2_ci'][1]*1e6:.1f}]  "
      f"ε={eps:.4f}  → {calib_verdict}")
print(f"  (pillanatkép: T1={snap['T1']*1e6:.1f}µs  T2={snap['T2']*1e6:.1f}µs — a jóslathoz NEM használjuk)")
for r in calib_reasons:
    print(f"  INVALID ok: {r}")

if calib_verdict != "VALID":
    result = {"verdict": "INVALID", "analysis": "amended",
              "reason": "0. fázis (kalibráció) INVALID", "calib_invalid_reasons": calib_reasons}
    (DATA_DIR / "phase1_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print_verdict("1. fázis", result)
    sys.exit(0)

# ── 1. fázis analízis ────────────────────────────────────────────────────────

times_s = np.array([d * DT for d in p1_dt_list])

t_olv_meas, t_olv_pred, ci_low, ci_high, T_fits = [], [], [], [], []
fit_failed = False

for theta_deg in cfg.phase1_theta_deg:
    cps = arm(f"p1_th{int(theta_deg)}_b0", p1_dt_list)
    cms = arm(f"p1_th{int(theta_deg)}_b1", p1_dt_list)
    D_arr  = np.array([D_from_counts(cp, cm, SHOTS) for cp, cm in zip(cps, cms)])
    D_errs = np.ones(len(D_arr)) / np.sqrt(SHOTS)

    fit = fit_exponential(times_s, D_arr, D_errs,
                          bootstrap_n=cfg.phase1_bootstrap_n,
                          rng_seed=cfg.rng_seed)
    if not fit["success"]:
        print(f"  θ={theta_deg:.0f}°: az illesztés nem konvergált")
        fit_failed = True
        continue
    T_fit, a_fit, T_ci = fit["T_fit"], fit["a_fit"], fit["T_ci"]

    t_olv_m = t_readable_from_fit(a_fit, T_fit, cfg.phase1_D_min)
    # Jóslat: a job SAJÁT Hahn-T2-jével és saját ε-jával
    t_olv_p = predict_t_olv_phase1(theta_deg, T2_calib, eps, cfg.phase1_D_min)

    # 99% CI a mért t_olv-ra a T bootstrap-CI-jéből
    t_lo = t_readable_from_fit(a_fit, T_ci[0], cfg.phase1_D_min)
    t_hi = t_readable_from_fit(a_fit, T_ci[1], cfg.phase1_D_min)
    if not (t_hi > t_lo):
        print(f"  θ={theta_deg:.0f}°: nulla szélességű CI — az illesztés értelmetlen")
        fit_failed = True
        continue

    t_olv_meas.append(t_olv_m)
    t_olv_pred.append(t_olv_p)
    ci_low.append(t_lo)
    ci_high.append(t_hi)
    T_fits.append(T_fit)

    print(f"  θ={theta_deg:4.0f}°  D={[f'{v:.3f}' for v in D_arr]}")
    print(f"         T_fit={T_fit*1e6:.1f}µs  t_olv_meas={t_olv_m*1e6:.1f}µs  "
          f"t_olv_pred={t_olv_p*1e6:.1f}µs  CI=[{t_lo*1e6:.1f}, {t_hi*1e6:.1f}]µs")

if fit_failed:
    result = {"verdict": "INVALID", "analysis": "amended",
              "reason": "az 1. fázis illesztése nem konvergált / értelmetlen"}
else:
    result = judge_phase1(
        cfg.phase1_theta_deg, t_olv_meas, t_olv_pred,
        ci_low, ci_high, T_fits, T2_calib, cfg.phase1_holm_alpha
    )
    result["analysis"] = "amended"
    result["T_fit"] = T_fits
    result["prediction_inputs"] = {
        "source": "job saját kalibrációs karjai",
        "T2_hahn_s": T2_calib, "eps": eps,
    }
print_verdict("1. fázis", result)

(DATA_DIR / "phase1_result.json").write_text(
    json.dumps({k: (v if not isinstance(v, np.ndarray) else v.tolist())
                for k, v in result.items()}, indent=2, ensure_ascii=False) + "\n"
)
print(f"\nEredmény mentve: {DATA_DIR}/phase1_result.json")
