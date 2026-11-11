"""
analysis.py — Bootstrap illesztések, tankönyvi jóslatok, ítéletek
Máté + Maya (Sesame), 2026-11-11

Ítéletek: TEXTBOOK | ANOMALY | INVALID
"""

import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import binomtest
from typing import List, Tuple, Optional


# ─── Segéd ────────────────────────────────────────────────────────────────────

def counts_to_expectation(counts: dict, shots: int) -> float:
    """counts {'0':n0,'1':n1} → ⟨X⟩ = (n0-n1)/shots  (X-bázis: 0↔+1, 1↔-1)"""
    n0 = counts.get("0", 0)
    n1 = counts.get("1", 0)
    return (n0 - n1) / shots


def D_from_counts(counts_plus: dict, counts_minus: dict, shots: int) -> float:
    """D = |⟨X⟩₊ - ⟨X⟩₋| / 2"""
    xp = counts_to_expectation(counts_plus, shots)
    xm = counts_to_expectation(counts_minus, shots)
    return abs(xp - xm) / 2.0


# ─── Exponenciális illesztés + bootstrap ─────────────────────────────────────

def _exp_decay(t, a, T):
    return a * np.exp(-t / T)


def fit_exponential(times_s: np.ndarray,
                    D_vals: np.ndarray,
                    D_errs: np.ndarray,
                    bootstrap_n: int = 2000,
                    rng_seed: int = 42) -> dict:
    """
    D(t) = a·exp(-t/T) illesztés + bootstrap CI.
    Visszaad: {T_fit, a_fit, T_ci, success}

    AMENDED (2026-11-11 utáni javítás): az illesztés dimenziótlan időben
    (u = t / t_max) történik. Az eredeti kód másodpercben illesztett
    (T ~ 1e-4), ahol a curve_fit numerikus Jacobi-lépése a T paraméterre
    gyakorlatilag nulla volt: az optimalizáló vagy a kezdőértéken ragadt
    (T2 = t_max/2), vagy elszállt (T1 = 1.65e5 s), és mindkettő
    "success"-ként, nulla szélességű CI-vel jött vissza.
    A modell és a súlyozás változatlan; csak az idő egysége más.
    """
    rng     = np.random.default_rng(rng_seed)
    times_s = np.asarray(times_s, dtype=float)
    D_vals  = np.asarray(D_vals, dtype=float)
    t_scale = float(np.max(times_s))
    fail = {"T_fit": np.nan, "a_fit": np.nan,
            "T_ci": (np.nan, np.nan), "a_ci": (np.nan, np.nan),
            "success": False}
    if not np.isfinite(t_scale) or t_scale <= 0:
        return fail
    u = times_s / t_scale
    try:
        popt, pcov = curve_fit(_exp_decay, u, D_vals,
                               p0=[D_vals[0] + 1e-6, 0.5],
                               sigma=D_errs + 1e-9, absolute_sigma=True,
                               maxfev=5000)
        a_fit, Tu_fit = popt
    except Exception:
        return fail
    if not (np.isfinite(a_fit) and np.isfinite(Tu_fit)):
        return fail

    # Bootstrap (parametrikus: Gauss-zaj a mért pontokon, ugyanaz a modell
    # ÉS ugyanaz a súlyozás, mint a fő illesztésben — az eredeti kód a
    # bootstrap-illesztéseket súlyozatlanul futtatta, így a T1-nél a
    # pontbecslés és a CI két különböző becslőből származott volna.
    # Egyenletes hibáknál (D-illesztések, Hahn) ez nem változtat semmit.)
    T_boots = []
    for _ in range(bootstrap_n):
        D_boot = D_vals + rng.normal(0, D_errs + 1e-9)
        try:
            po, _ = curve_fit(_exp_decay, u, D_boot,
                              p0=[a_fit, Tu_fit],
                              sigma=D_errs + 1e-9, absolute_sigma=True,
                              maxfev=2000)
            T_boots.append(po[1])
        except Exception:
            T_boots.append(Tu_fit)

    T_boots = np.array(T_boots) * t_scale
    T_ci    = (float(np.percentile(T_boots, 0.5)),
               float(np.percentile(T_boots, 99.5)))

    resid    = (D_vals - _exp_decay(u, a_fit, Tu_fit)) / (D_errs + 1e-9)
    dof      = max(1, len(D_vals) - 2)
    chi2_red = float(np.sum(resid ** 2) / dof)

    return {"T_fit": float(Tu_fit * t_scale), "a_fit": float(a_fit),
            "T_ci": T_ci, "t_max": t_scale, "chi2_red": chi2_red,
            "success": True}


def t_readable_from_fit(a_fit: float, T_fit: float, D_min: float = 0.1) -> float:
    """t_olv = T · ln(a / D_min)"""
    if a_fit <= D_min or T_fit <= 0:
        return 0.0
    return float(T_fit * np.log(a_fit / D_min))


# ─── 0. fázis: kalibráció illesztés ──────────────────────────────────────────

def fit_T1(delays_s: np.ndarray, counts_list: List[dict],
           shots: int) -> dict:
    """T1 illesztés a P(1) lecsengésre: P(1)(t) = a·exp(-t/T1), binomiális hibákkal."""
    p1 = np.array([c.get("1", 0) / shots for c in counts_list])
    p1 = np.clip(p1, 1e-6, 1 - 1e-6)
    err = np.sqrt(p1 * (1 - p1) / shots)
    res = fit_exponential(delays_s, p1, err)
    res["T1"] = res.pop("T_fit")
    res["T1_ci"] = res.pop("T_ci")
    return res


def fit_T2_hahn(delays_s: np.ndarray, counts_list: List[dict],
                shots: int) -> dict:
    """
    T2 Hahn-echo illesztés: ⟨X⟩(t) = a·exp(-t/T2).

    AMENDED: az előjeles ⟨X⟩-re illesztünk. Az eredeti |⟨X⟩| a lecsengés
    farkán (ahol ⟨X⟩ a zajon belül 0) felfelé torzít, mert a negatív
    zajt pozitívba hajtja → szisztematikusan hosszabb T2.
    """
    xvals = np.array([counts_to_expectation(c, shots) for c in counts_list])
    err   = np.ones(len(xvals)) / np.sqrt(shots)
    res   = fit_exponential(delays_s, xvals, err)
    res["T2"] = res.pop("T_fit")
    res["T2_ci"] = res.pop("T_ci")
    return res


def fit_readout_error(counts_0: dict, counts_1: dict, shots: int) -> dict:
    """ε = (P(1|0) + P(0|1)) / 2"""
    p10 = counts_0.get("1", 0) / shots   # P(mért 1 | prep 0)
    p01 = counts_1.get("0", 0) / shots   # P(mért 0 | prep 1)
    eps = (p10 + p01) / 2.0
    return {"readout_error": eps, "P10": p10, "P01": p01}


def fit_sanity(T: float, T_ci, t_max: Optional[float]) -> List[str]:
    """
    Értelmességi ellenőrzés egy időállandó-illesztésre.
    Üres lista = rendben; különben az okok listája.
    """
    problems = []
    try:
        lo, hi = float(T_ci[0]), float(T_ci[1])
    except Exception:
        return ["CI hiányzik"]
    if not (np.isfinite(T) and np.isfinite(lo) and np.isfinite(hi)):
        return ["nem véges érték (NaN/inf)"]
    if T <= 0:
        problems.append("T <= 0")
    if not (hi > lo):
        problems.append("nulla szélességű CI (a fit nem mozdult / nem konvergált)")
    if not (lo <= T <= hi):
        problems.append("a pontbecslés a saját CI-jén kívül esik")
    if t_max is not None and t_max > 0 and T > 10.0 * t_max:
        problems.append("T a fittelési tartományon kívül (> 10 × leghosszabb delay)")
    return problems


def judge_calib_detail(T1_res: dict, T2_res: dict,
                       tol_pct: float = 15.0) -> Tuple[str, List[str]]:
    """
    VALID / INVALID a kalibrációra + az INVALID okai.

    AMENDED: az eredeti változat csak a relatív CI-szélességet nézte, így a
    nulla szélességű CI (0% < 15%) és a T1 = 1.65e11 µs is VALID-ot kapott.
    Most előbb értelmességi ellenőrzés fut (fit_sanity); ha bármelyik
    illesztés értelmetlen, a kalibráció automatikusan INVALID.
    """
    reasons = []
    if not T1_res.get("success"):
        reasons.append("T1: az illesztés nem konvergált")
    if not T2_res.get("success"):
        reasons.append("T2: az illesztés nem konvergált")
    if reasons:
        return "INVALID", reasons
    T1, T1_ci = T1_res["T1"], T1_res["T1_ci"]
    T2, T2_ci = T2_res["T2"], T2_res["T2_ci"]
    reasons += [f"T1: {r}" for r in fit_sanity(T1, T1_ci, T1_res.get("t_max"))]
    reasons += [f"T2: {r}" for r in fit_sanity(T2, T2_ci, T2_res.get("t_max"))]
    if reasons:
        return "INVALID", reasons
    T1_err = (T1_ci[1] - T1_ci[0]) / (2 * T1) * 100
    T2_err = (T2_ci[1] - T2_ci[0]) / (2 * T2) * 100
    if T1_err >= tol_pct:
        reasons.append(f"T1: CI fél-szélesség {T1_err:.1f}% >= {tol_pct}%")
    if T2_err >= tol_pct:
        reasons.append(f"T2: CI fél-szélesség {T2_err:.1f}% >= {tol_pct}%")
    return ("INVALID" if reasons else "VALID"), reasons


def judge_calib(T1_res: dict, T2_res: dict, tol_pct: float = 15.0) -> str:
    """VALID / INVALID a kalibrációra (ld. judge_calib_detail)."""
    return judge_calib_detail(T1_res, T2_res, tol_pct)[0]


# ─── 1. fázis ─────────────────────────────────────────────────────────────────

def predict_t_olv_phase1(theta_deg: float, T2: float,
                          eps_readout: float, D_min: float = 0.1) -> float:
    """
    Tankönyvi jóslat:
    D(t) = sin(θ)·(1-2ε)·exp(-t/T2)
    t_olv = T2·ln(sin(θ)·(1-2ε) / D_min)
    """
    a = np.sin(np.deg2rad(theta_deg)) * (1 - 2 * eps_readout)
    if a <= D_min:
        return 0.0
    return float(T2 * np.log(a / D_min))


def holm_correct(p_values: List[float], alpha: float) -> List[bool]:
    n       = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    rej     = [False] * n
    for rank, (i, p) in enumerate(indexed):
        if p <= alpha / (n - rank):
            rej[i] = True
        else:
            break
    return rej


def judge_phase1(theta_degs: List[float],
                 t_olv_meas: List[float],
                 t_olv_pred: List[float],
                 ci_low: List[float],
                 ci_high: List[float],
                 T2_fit_list: List[float],
                 T2_calib: float,
                 alpha: float = 0.01) -> dict:
    """
    TEXTBOOK: minden t_olv a logaritmikus jóslat 99% CI-jén belül.
    ANOMALY: ≥2 θ-nál szignifikánsan nagyobb t_olv VAGY
             T_fit > T2_calib (Holm-korrektált p < 0.01).

    AMENDED: in_band akkor igaz, ha a [ci_low, ci_high] sáv a mért ÉS a
    jósolt t_olv-t is tartalmazza. Az eredeti kód csak a mért értéket
    nézte; a QPU-elemzésben a sáv a mért érték saját bootstrap CI-je, így
    a feltétel tautológia volt (a jóslat szóba sem került), és in_band
    akkor is true lett, amikor a jóslat a CI-n kívül esett.
    (A dryrunban a sáv a jóslat körüli ±30%, ott a mért értéket teszteli —
    az új feltétel mindkét használatot helyesen kezeli.)
    """
    in_band    = [bool(lo <= m <= hi and lo <= p <= hi) for m, p, lo, hi in
                  zip(t_olv_meas, t_olv_pred, ci_low, ci_high)]
    # T_fit vs T2_calib egyoldali teszt: H0: T_fit <= T2
    # Közelítés: ha T_fit - T2 > 0 és a CI alsó határa > T2_calib → sig
    t_anomaly  = [bool(T_f > T2_calib) for T_f in T2_fit_list]
    n_t_anom   = sum(t_anomaly)
    n_out      = sum(not b for b in in_band)

    if all(in_band) and n_t_anom < 2:
        verdict = "TEXTBOOK"
    elif n_out >= 2 or n_t_anom >= 2:
        verdict = "ANOMALY"
    else:
        verdict = "TEXTBOOK"

    return dict(verdict=verdict, theta_degs=theta_degs,
                t_olv_meas=t_olv_meas, t_olv_pred=t_olv_pred,
                ci_low=ci_low, ci_high=ci_high,
                in_band=in_band, t_anomaly=t_anomaly)


# ─── 2. fázis ─────────────────────────────────────────────────────────────────

def judge_phase2(T2_N_list: List[float], T2_N_ci_low: List[float],
                 T1_meas: float, T1_ci_high: float,
                 N_list: List[int]) -> dict:
    """
    TEXTBOOK: minden T2_N ≤ 2·T1 a CI-en belül.
    ANOMALY:  bármely N-nél T2_N_ci_low > 2·T1_ci_high.
    """
    limit    = 2 * T1_meas
    anomalies = [lo > 2 * T1_ci_high
                 for lo in T2_N_ci_low]
    in_limit  = [t <= limit for t in T2_N_list]
    verdict   = "ANOMALY" if any(anomalies) else "TEXTBOOK"

    return dict(verdict=verdict, N_list=N_list,
                T2_N_list=T2_N_list, T1_meas=T1_meas,
                limit_2T1=limit, in_limit=in_limit,
                anomaly_flags=anomalies)


# ─── 3. fázis ─────────────────────────────────────────────────────────────────

def blp_measure(D_k: np.ndarray, dk: float = 1.0) -> float:
    """BLP nemMarkovi mérték: pozitív meredekségű szakaszok összege."""
    dD = np.diff(D_k)
    return float(np.sum(dD[dD > 0]) * dk)


def judge_phase3(blp_coupled: float,
                 blp_control_boots: np.ndarray,
                 alpha: float = 0.01) -> dict:
    """
    TEXTBOOK: csatolt BLP szignifikánsan nagyobb a kontrollnál.
    p-érték: empirikus a bootstrap eloszlásból.
    """
    p_val   = float(np.mean(blp_control_boots >= blp_coupled))
    verdict = "TEXTBOOK" if p_val < alpha else "FAIL"
    ci_ctrl = (float(np.percentile(blp_control_boots, 0.5)),
               float(np.percentile(blp_control_boots, 99.5)))

    return dict(verdict=verdict, blp_coupled=blp_coupled,
                blp_ctrl_median=float(np.median(blp_control_boots)),
                blp_ctrl_ci=ci_ctrl, p_value=p_val)


# ─── 1b fázis ─────────────────────────────────────────────────────────────────

def majority_vote(counts: dict, shots: int) -> float:
    """Három-bites többségi szavazás hibaaránya."""
    err = 0
    total = 0
    for bitstr, cnt in counts.items():
        ones = bitstr.count("1")
        voted = 1 if ones >= 2 else 0
        # Ha a bit 0 volt (001,010,100 → hiba; 000 → ok)
        # Ezt a hívó dönti el a bit ismeretében
        total += cnt
    return 0.0  # placeholder — a hívó számolja


def judge_phase1b(err_active: List[float],
                  err_single: List[float],
                  R_rounds: List[int],
                  n_shots: int,
                  alpha: float = 0.01) -> dict:
    """
    Működik, ha R=max után err_active < err_single (egyoldali p < alpha).
    """
    R_max   = max(R_rounds)
    idx_max = R_rounds.index(R_max)
    ea      = err_active[idx_max]
    es      = err_single[idx_max]

    k_a  = int(round(ea * n_shots))
    res  = binomtest(k_a, n_shots, es, alternative="less")
    pval = float(res.pvalue)
    sig  = pval < alpha

    verdict = "TEXTBOOK" if sig else "FAIL"
    return dict(verdict=verdict, R_rounds=R_rounds,
                err_active=err_active, err_single=err_single,
                p_value=pval, significant=sig)


# ─── Riport ───────────────────────────────────────────────────────────────────

def print_verdict(phase: str, result: dict):
    v    = result.get("verdict", "?")
    icon = {"TEXTBOOK": "✅", "ANOMALY": "🔴",
            "INVALID": "⛔", "FAIL": "❌", "VALID": "✅"}.get(v, "❓")
    print(f"\n{'─'*60}")
    print(f"  {icon}  {phase}: {v}")
    for k, val in result.items():
        if k == "verdict":
            continue
        if isinstance(val, float):
            print(f"     {k}: {val:.4g}")
        else:
            print(f"     {k}: {val}")
    print(f"{'─'*60}")
