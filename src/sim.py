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
    """
    def __init__(self, backend_props: dict, t2_scale: float = 1.0,
                 seed: int = 20261111):
        self.props   = backend_props
        self.scale   = t2_scale
        self.seed    = seed
        self._noise  = None
        if AER_AVAILABLE:
            self._noise = build_noise_model(backend_props, t2_scale)
            self._sim   = AerSimulator(noise_model=self._noise,
                                       seed_simulator=seed)

    def run(self, circuits: list, shots: int = 1000) -> list:
        """
        Lefuttatja az áramköröket, visszaad list[dict] counts-okat.
        """
        if not AER_AVAILABLE:
            return self._analytic_run(circuits, shots)

        job     = self._sim.run(circuits, shots=shots)
        results = job.result()
        return [results.get_counts(i) for i in range(len(circuits))]

    def _analytic_run(self, circuits: list, shots: int) -> list:
        """
        Fallback ha Aer nincs: egyszerű analitikus közelítés.
        Csak a dryrun-hoz elegendő.
        """
        T1  = self.props["T1"]
        T2  = self.props["T2"] * self.scale
        eps = self.props["readout_error"]
        rng = np.random.default_rng(self.seed)
        counts_list = []

        for circ in circuits:
            meta = getattr(circ, "metadata", {}) or {}
            arm  = meta.get("arm", "")
            d_dt = meta.get("delay_dt", 0)
            dt_s = 2.22e-10  # Heron dt ≈ 0.222 ns

            if "T1" in arm:
                # P(1→1) = exp(-t/T1)
                t  = d_dt * dt_s
                p1 = np.exp(-t / T1)
                p1 = p1 * (1 - eps) + (1 - p1) * eps
            elif "T2" in arm or "hahn" in arm.lower():
                t  = d_dt * dt_s
                p0 = 0.5 * (1 + np.exp(-t / T2))  # X-bázisban |0⟩ valószínűség
                p0 = p0 * (1 - eps) + (1 - p0) * eps
                p1 = 1 - p0
            elif "readout_0" in arm:
                p1 = eps
            elif "readout_1" in arm:
                p1 = 1 - eps
            else:
                # Általános: 50/50
                p1 = 0.5

            n1 = int(rng.binomial(shots, p1))
            n0 = shots - n1
            counts_list.append({"0": n0, "1": n1} if n0 >= 0 else {"0": 0, "1": shots})

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
