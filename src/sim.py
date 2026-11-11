"""
sim.py — Aer szimuláció backend zajmodellel + "javított" pozitív kontroll
Máté + Maya (Sesame), 2026-11-11

Két mód:
  normal   — backend zajmodelljével (transpilált, ütemezett áromc.)
  improved — mesterségesen jobb T2 (T2 > 2*T1), pozitív kontroll ANOMALY-hoz

Függőségek: qiskit-aer, qiskit-ibm-runtime
"""

import numpy as np
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel
    AER_AVAILABLE = True
except ImportError:
    AER_AVAILABLE = False
    logger.warning("qiskit-aer nem elérhető — csak analitikus dryrun futtatható.")

try:
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    QISKIT_AVAILABLE = True
except ImportError:
    QISKIT_AVAILABLE = False


# ─── Zajmodell építés ─────────────────────────────────────────────────────────

def build_noise_model(backend_props: dict,
                       t2_scale: float = 1.0) -> "NoiseModel":
    """
    Zajmodell backend tulajdonságokból.
    t2_scale: 1.0 = normál, >1 = "javított" (pozitív kontroll).
    
    backend_props: {
        "T1": float [s], "T2": float [s],
        "readout_error": float,
        "gate_error_1q": float,
        "gate_error_2q": float,
        "qubit": int
    }
    """
    if not AER_AVAILABLE:
        return None

    from qiskit_aer.noise import (
        NoiseModel, depolarizing_error,
        thermal_relaxation_error, ReadoutError
    )

    nm = NoiseModel()
    T1 = backend_props["T1"]
    T2 = min(backend_props["T2"] * t2_scale, 2 * T1 - 1e-9)  # fizikai limit
    eps_ro = backend_props["readout_error"]
    g1  = backend_props.get("gate_error_1q", 1e-3)
    g2  = backend_props.get("gate_error_2q", 5e-3)
    q   = backend_props["qubit"]

    # 1-qubites kapuhiba
    err_1q = depolarizing_error(g1, 1)
    nm.add_all_qubit_quantum_error(err_1q, ["x", "y", "h", "ry"])

    # 2-qubites kapuhiba
    err_2q = depolarizing_error(g2, 2)
    nm.add_all_qubit_quantum_error(err_2q, ["cx", "rxx", "ryy"])

    # Kiolvasási hiba
    ro_err = ReadoutError([[1 - eps_ro, eps_ro], [eps_ro, 1 - eps_ro]])
    nm.add_all_qubit_readout_error(ro_err)

    return nm


# ─── Fő szimulátor ────────────────────────────────────────────────────────────

class AerRunner:
    """
    Aer-alapú szimulátor, ugyanazt az API-t adja, mint a run.py IBMRunner.

    force_analytic=True esetén mindig az analitikus fallbacket használja
    (dryrun-hoz ajánlott, az Aer Delay kaput nem relaxálja noise model nélkül).
    """
    def __init__(self, backend_props: dict, t2_scale: float = 1.0,
                 seed: int = 20261111, force_analytic: bool = False):
        self.props          = backend_props
        self.scale          = t2_scale
        self.seed           = seed
        self.force_analytic = force_analytic
        self._noise         = None
        if AER_AVAILABLE and not force_analytic:
            self._noise = build_noise_model(backend_props, t2_scale)
            self._sim   = AerSimulator(noise_model=self._noise,
                                       seed_simulator=seed)

    def run(self, circuits: list, shots: int = 1000) -> list:
        """
        Lefuttatja az áramköröket, visszaad list[dict] counts-okat.
        """
        if not AER_AVAILABLE or self.force_analytic:
            return self._analytic_run(circuits, shots)

        job     = self._sim.run(circuits, shots=shots)
        results = job.result()
        return [results.get_counts(i) for i in range(len(circuits))]

    def _analytic_run(self, circuits: list, shots: int) -> list:
        """
        Fallback ha Aer nincs: teljes analitikus közelítés minden arm-hoz.
        Dryrun-hoz elegendő.
        """
        T1   = self.props["T1"]
        T2   = self.props["T2"] * self.scale
        eps  = self.props["readout_error"]
        dt_s = 2.22e-10  # Heron dt ≈ 0.222 ns
        rng  = np.random.default_rng(self.seed)
        counts_list = []

        for circ in circuits:
            meta = getattr(circ, "metadata", {}) or {}
            arm  = meta.get("arm", "")

            # ── 0. fázis: kalibráció ──────────────────────────────────────────
            if "T1" in arm:
                # P(1→1) = exp(-t/T1)
                d_dt = meta.get("delay_dt", 0)
                t    = d_dt * dt_s
                p1   = np.exp(-t / T1)
                p1   = p1 * (1 - eps) + (1 - p1) * eps
                n1   = int(rng.binomial(shots, p1))
                counts_list.append({"0": shots - n1, "1": n1})

            elif "T2" in arm or "hahn" in arm.lower():
                # ⟨X⟩ = exp(-t/T2), p0 = (1 + exp(-t/T2)) / 2
                d_dt = meta.get("delay_dt", 0)
                t    = d_dt * dt_s
                p0   = 0.5 * (1 + np.exp(-t / T2))
                p0   = p0 * (1 - eps) + (1 - p0) * eps
                p1   = 1 - p0
                n1   = int(rng.binomial(shots, p1))
                counts_list.append({"0": shots - n1, "1": n1})

            elif "readout_0" in arm:
                p1 = eps
                n1 = int(rng.binomial(shots, p1))
                counts_list.append({"0": shots - n1, "1": n1})

            elif "readout_1" in arm:
                p1 = 1 - eps
                n1 = int(rng.binomial(shots, p1))
                counts_list.append({"0": shots - n1, "1": n1})

            # ── 1. fázis: signal és reference ────────────────────────────────
            elif arm == "signal" or arm == "reference":
                # D(t) = sin(θ) * exp(-t/T2)
                # p1 = 0.5 * (1 ∓ sin(θ)*exp(-t/T2)*(1-2ε))
                theta_deg = meta.get("theta_deg", 90.0)
                bit       = meta.get("bit", 0)
                d_dt      = meta.get("delay_dt", 0)
                t         = d_dt * dt_s
                decay     = np.sin(np.deg2rad(theta_deg)) * np.exp(-t / T2)
                signal    = decay * (1 - 2 * eps)
                # bit=0 → |+⟩, X-mérés p(0) = 0.5*(1+signal), p(1) = 0.5*(1-signal)
                # bit=1 → |−⟩, X-mérés p(0) = 0.5*(1-signal), p(1) = 0.5*(1+signal)
                if bit == 0:
                    p1 = 0.5 * (1 - signal)
                else:
                    p1 = 0.5 * (1 + signal)
                p1 = float(np.clip(p1, 0, 1))
                n1 = int(rng.binomial(shots, p1))
                counts_list.append({"0": shots - n1, "1": n1})

            # ── 2. fázis: DD ──────────────────────────────────────────────────
            elif arm == "DD":
                # T2_eff = T2 * N^(2/3)
                # Fizikai rendszerben (T2 <= 2*T1): T2_eff-et korlátozzuk 2*T1-re.
                # Ha T2 > 2*T1 (pozitív kontroll anomália), NEM korlátozzuk,
                # hogy a fit anomálisan nagy T2_N-t mutasson.
                N         = meta.get("N_pulses", 1)
                bit       = meta.get("bit", 0)
                d_dt      = meta.get("delay_dt", 0)
                t         = d_dt * dt_s
                T2_eff    = T2 * (N ** (2.0 / 3.0))
                if T2 <= 2 * T1:
                    T2_eff = min(T2_eff, 2 * T1 - 1e-12)
                decay     = np.exp(-t / T2_eff)
                signal    = decay * (1 - 2 * eps)
                if bit == 0:
                    p1 = 0.5 * (1 - signal)
                else:
                    p1 = 0.5 * (1 + signal)
                p1 = float(np.clip(p1, 0, 1))
                n1 = int(rng.binomial(shots, p1))
                counts_list.append({"0": shots - n1, "1": n1})

            # ── 3. fázis: csatolt és kontroll ────────────────────────────────
            elif arm == "coupled":
                k         = meta.get("k_steps", 0)
                phi       = meta.get("phi", 0.3927)
                bit       = meta.get("bit", 0)
                # decay_rate ≈ dt_s * 1000 / T2 (kb. 1 kapu per 1000 dt)
                decay_rate = dt_s * 1000.0 / T2
                # Nem-monoton: D(k) = exp(-k*dr) * |cos(2*phi*k)|
                D_k       = np.exp(-k * decay_rate) * abs(np.cos(2 * phi * k))
                signal    = D_k * (1 - 2 * eps)
                if bit == 0:
                    p1 = 0.5 * (1 - signal)
                else:
                    p1 = 0.5 * (1 + signal)
                p1 = float(np.clip(p1, 0, 1))
                n1 = int(rng.binomial(shots, p1))
                counts_list.append({"0": shots - n1, "1": n1})

            elif arm == "control":
                k         = meta.get("k_steps", 0)
                phi       = meta.get("phi", 0.3927)
                bit       = meta.get("bit", 0)
                decay_rate = dt_s * 1000.0 / T2
                # Monoton csökkenő: D(k) = exp(-k*decay_rate)
                D_k       = np.exp(-k * decay_rate)
                signal    = D_k * (1 - 2 * eps)
                if bit == 0:
                    p1 = 0.5 * (1 - signal)
                else:
                    p1 = 0.5 * (1 + signal)
                p1 = float(np.clip(p1, 0, 1))
                n1 = int(rng.binomial(shots, p1))
                counts_list.append({"0": shots - n1, "1": n1})

            # ── 1b fázis ─────────────────────────────────────────────────────
            elif arm == "single":
                bit        = meta.get("bit", 0)
                R          = meta.get("R", 0)
                round_time = 20e-6  # s
                p_err      = 1.0 - np.exp(-R * round_time / T1)
                # P(mért 1) ha bit=1: (1-p_err)*(1-eps) + p_err*eps
                # P(mért 1) ha bit=0: p_err*(1-eps) + (1-p_err)*eps
                if bit == 1:
                    p1 = (1 - p_err) * (1 - eps) + p_err * eps
                else:
                    p1 = p_err * (1 - eps) + (1 - p_err) * eps
                p1 = float(np.clip(p1, 0, 1))
                n1 = int(rng.binomial(shots, p1))
                counts_list.append({"0": shots - n1, "1": n1})

            elif arm in ("majority_only", "active_correction"):
                bit        = meta.get("bit", 0)
                R          = meta.get("R", 0)
                round_time = 20e-6  # s
                # Fizikai egységes hibaarány R körön át (kumulált)
                p_single   = 1.0 - np.exp(-R * round_time / T1)
                if arm == "majority_only":
                    # Hiba ha ≥2 bit flip: 3*p^2*(1-p) + p^3 (binomiális)
                    p_log = (3 * p_single**2 * (1 - p_single)
                             + p_single**3)
                else:
                    # active_correction: per-kör hibaarány (kisebb)
                    # p_round = 1 - exp(-round_time/T1) ≈ round_time/T1 kis értékre
                    p_round = 1.0 - np.exp(-round_time / T1)
                    # Logikai hiba per kör: ~3*p_round^2 (kétbites esemény)
                    p_log_round = 3 * p_round**2
                    # Akkumuláció R körön: P_L = 1 - (1-p_log_round)^R
                    p_log = 1.0 - (1.0 - p_log_round) ** R

                p_log = float(np.clip(p_log, 0, 1))
                # 3-bites kimenet: "000"=correct, "001","010","100"=1-bit hiba, stb.
                # Egyszerűsítés: az összes "hibás" eset p_log valószínűsége
                # bit=1 → helyes = "111", hiba = minden más
                # bit=0 → helyes = "000", hiba = minden más
                n_err   = int(rng.binomial(shots, p_log))
                n_ok    = shots - n_err
                if bit == 0:
                    # Helyes: "000", hibák elosztva (egyszerűsítve "111" legyen a fő hiba)
                    c = {"000": n_ok, "111": n_err}
                else:
                    # Helyes: "111", hibák elosztva
                    c = {"111": n_ok, "000": n_err}
                counts_list.append(c)

            else:
                # Ismeretlen arm: 50/50 fallback
                n1 = int(rng.binomial(shots, 0.5))
                counts_list.append({"0": shots - n1, "1": n1})

        return counts_list


# ─── Mock backend props (dryrun-hoz) ─────────────────────────────────────────

MOCK_BACKEND_PROPS = {
    "qubit":           0,
    "T1":              150e-6,    # 150 µs
    "T2":              100e-6,    # 100 µs
    "readout_error":   0.01,
    "gate_error_1q":   1e-3,
    "gate_error_2q":   5e-3,
    "dt":              2.22e-10,  # s
}

MOCK_BACKEND_PROPS_IMPROVED = {
    **MOCK_BACKEND_PROPS,
    "T2": 400e-6,   # T2 > 2*T1 → fizikailag lehetetlen → ANOMALY
}
