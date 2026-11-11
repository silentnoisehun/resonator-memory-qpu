"""
circuits.py — Qiskit áramkörök minden fázishoz
Máté + Maya (Sesame), 2026-11-11

Minden fázis-függvény visszaad egy lista[QuantumCircuit]-ot.
A teljes lista a plan.py-ban keveredik el rögzített seeddel.

Konvenciók:
  - X-bázisú mérés = H + measure
  - Hahn-echo = delay(t/2) + X + delay(t/2)
  - Minden áramkörnek van metadata dict-je: phase, arm, params
"""

import numpy as np
from typing import List, Tuple, Optional
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit.circuit import Delay


# ─── Segédfüggvények ──────────────────────────────────────────────────────────

def x_basis_measure(qc: QuantumCircuit, qubit: int, cbit: int):
    """H + measure → X-bázisú kiolvasás."""
    qc.h(qubit)
    qc.measure(qubit, cbit)


def hahn_echo(qc: QuantumCircuit, qubit: int, total_dt: int):
    """
    Hahn-echo: delay(total_dt/2) + X + delay(total_dt/2).
    total_dt: dt egységekben (dt ≈ 0.222 ns Heron gépeken).
    """
    half = total_dt // 2
    qc.delay(half, qubit, unit="dt")
    qc.x(qubit)
    qc.delay(total_dt - half, qubit, unit="dt")


def delay_dt(t_s: float, dt_s: float) -> int:
    """Másodpercből dt egység, felfelé kerekítve."""
    return max(1, int(np.ceil(t_s / dt_s)))


# ─── 0. fázis: kalibráció ────────────────────────────────────────────────────

def build_T1_circuits(qubit: int, delays_dt: List[int]) -> List[QuantumCircuit]:
    """T1 mérés: |1⟩ + késleltetés + mérés."""
    circs = []
    for d in delays_dt:
        qc = QuantumCircuit(1, 1, name=f"T1_d{d}")
        qc.x(0)
        qc.delay(d, 0, unit="dt")
        qc.measure(0, 0)
        qc.metadata = {"phase": "calib", "arm": "T1", "delay_dt": d, "qubit": qubit}
        circs.append(qc)
    return circs


def build_T2_hahn_circuits(qubit: int, delays_dt: List[int]) -> List[QuantumCircuit]:
    """T2 Hahn-echo: |+⟩ + delay/2 + X + delay/2 + X-mérés."""
    circs = []
    for d in delays_dt:
        qc = QuantumCircuit(1, 1, name=f"T2_hahn_d{d}")
        qc.h(0)
        hahn_echo(qc, 0, d)
        x_basis_measure(qc, 0, 0)
        qc.metadata = {"phase": "calib", "arm": "T2_hahn", "delay_dt": d, "qubit": qubit}
        circs.append(qc)
    return circs


def build_readout_error_circuits(qubit: int) -> List[QuantumCircuit]:
    """Kiolvasási hiba: |0⟩ és |1⟩ azonnali mérés."""
    circs = []
    for prep, label in [(None, "0"), ("x", "1")]:
        qc = QuantumCircuit(1, 1, name=f"readout_{label}")
        if prep:
            qc.x(0)
        qc.measure(0, 0)
        qc.metadata = {"phase": "calib", "arm": f"readout_{label}", "qubit": qubit}
        circs.append(qc)
    return circs


def build_calib_circuits(qubit: int, T1_delays_dt: List[int],
                          T2_delays_dt: List[int]) -> List[QuantumCircuit]:
    """Összesített kalibráció: T1 + T2_hahn + readout error."""
    return (build_T1_circuits(qubit, T1_delays_dt) +
            build_T2_hahn_circuits(qubit, T2_delays_dt) +
            build_readout_error_circuits(qubit))


# ─── 1. fázis: bit a térben ──────────────────────────────────────────────────

def build_phase1_circuits(qubit: int, theta_degs: List[float],
                           delays_dt: List[int]) -> List[QuantumCircuit]:
    """
    1. fázis: Ry(±θ) + Hahn-echo + X-mérés.
    Minden θ × bit (0/1) × delay kombináció.
    + Referencia kar: ismert |+⟩ / |−⟩, ugyanaz az echo.
    """
    circs = []
    for theta_deg in theta_degs:
        theta_rad = np.deg2rad(theta_deg)
        for bit in [0, 1]:
            sign   = 1 if bit == 0 else -1
            angle  = sign * theta_rad
            for d in delays_dt:
                qc = QuantumCircuit(1, 1, name=f"p1_th{int(theta_deg)}_b{bit}_d{d}")
                qc.ry(angle, 0)
                hahn_echo(qc, 0, d)
                x_basis_measure(qc, 0, 0)
                qc.metadata = {
                    "phase": "1", "arm": "signal",
                    "theta_deg": theta_deg, "bit": bit,
                    "delay_dt": d, "qubit": qubit
                }
                circs.append(qc)

        # Referencia: |+⟩ (bit=0) és |−⟩ (bit=1) ismert állapot
        for bit in [0, 1]:
            angle = (np.pi / 2) * (1 if bit == 0 else -1)
            for d in delays_dt:
                qc = QuantumCircuit(1, 1, name=f"p1_ref_b{bit}_d{d}")
                qc.ry(angle, 0)
                hahn_echo(qc, 0, d)
                x_basis_measure(qc, 0, 0)
                qc.metadata = {
                    "phase": "1", "arm": "reference",
                    "theta_deg": 90.0, "bit": bit,
                    "delay_dt": d, "qubit": qubit
                }
                circs.append(qc)
    return circs


# ─── 2. fázis: dinamikus csatolásmentesítés (DD) ─────────────────────────────

def build_XY4(qc: QuantumCircuit, qubit: int, N: int, tau_dt: int):
    """
    XY4 DD sorozat: N impulzus, egyenletesen elosztva tau_dt időre.
    N=1: egyszerű Hahn-echo.
    N=4k: valódi XY4 (X Y X Y sorrendben, váltakozva).
    """
    if N == 0:
        qc.delay(tau_dt, qubit, unit="dt")
        return
    spacing = tau_dt // (N + 1)
    gates   = ["x", "y"] * (N // 2 + 1)
    for i in range(N):
        qc.delay(spacing, qubit, unit="dt")
        if gates[i % 4] == "x":
            qc.x(qubit)
        else:
            qc.y(qubit)
    qc.delay(tau_dt - spacing * N, qubit, unit="dt")  # maradék


def build_phase2_circuits(qubit: int, N_list: List[int],
                           delays_dt: List[int]) -> List[QuantumCircuit]:
    """2. fázis: |±⟩ + DD(N) + X-mérés, minden N × bit × delay."""
    circs = []
    for N in N_list:
        for bit in [0, 1]:
            angle = np.pi / 2 * (1 if bit == 0 else -1)
            for d in delays_dt:
                qc = QuantumCircuit(1, 1, name=f"p2_N{N}_b{bit}_d{d}")
                qc.ry(angle, 0)
                build_XY4(qc, 0, N, d)
                x_basis_measure(qc, 0, 0)
                qc.metadata = {
                    "phase": "2", "arm": "DD",
                    "N_pulses": N, "bit": bit,
                    "delay_dt": d, "qubit": qubit
                }
                circs.append(qc)
    return circs


# ─── 3. fázis: nem-markovi visszafolyás ──────────────────────────────────────

def build_phase3_circuits(qubit_S: int, qubit_E: int,
                           phi: float, k_steps: List[int],
                           with_reset: bool = False) -> List[QuantumCircuit]:
    """
    3. fázis: S |±⟩ + k × (RXX + RYY) + S X-mérés.
    with_reset=True → kontroll kar: E reset minden lépés után.
    """
    circs = []
    arm   = "control" if with_reset else "coupled"

    for bit in [0, 1]:
        s_angle = np.pi / 2 * (1 if bit == 0 else -1)
        for k in k_steps:
            qc = QuantumCircuit(2, 1, name=f"p3_{arm}_b{bit}_k{k}")
            # S inicializáció
            qc.ry(s_angle, 0)  # S qubit
            # E: |0⟩ alapból indul
            for step in range(k):
                qc.rxx(phi, 0, 1)
                qc.ryy(phi, 0, 1)
                if with_reset:
                    qc.reset(1)
                    # Azonos időzítés: üres delay a csatolt karban
                    # (a nem-with_reset körben nincs reset, de azonos hossz)
            # S mérés X-bázisban
            qc.h(0)
            qc.measure(0, 0)
            qc.metadata = {
                "phase": "3", "arm": arm, "bit": bit,
                "k_steps": k, "phi": phi,
                "qubit_S": qubit_S, "qubit_E": qubit_E
            }
            circs.append(qc)
    return circs


def build_phase3_all(qubit_S: int, qubit_E: int,
                      phi: float, k_steps: List[int]) -> List[QuantumCircuit]:
    """Csatolt + kontroll kar együtt."""
    return (build_phase3_circuits(qubit_S, qubit_E, phi, k_steps, False) +
            build_phase3_circuits(qubit_S, qubit_E, phi, k_steps, True))


# ─── 1b fázis: bit-flip repetition code ──────────────────────────────────────

def build_phase1b_circuits(data_qubits: List[int],
                            anc_qubits: List[int],
                            R_rounds: List[int]) -> List[QuantumCircuit]:
    """
    1b fázis: 3 adatqubit + 2 segédqubit, bit-flip repetition code.
    Bit: |000⟩ vagy |111⟩ (sorsolt).
    R körönként: paritásmérés + feltételes korrekció.
    """
    assert len(data_qubits) == 3 and len(anc_qubits) == 2
    circs = []
    n_q   = 5  # 3 adat + 2 segéd

    for bit in [0, 1]:
        # Kontroll 1: egyetlen qubit, semmi más
        for R in R_rounds:
            qc = QuantumCircuit(n_q, 3, name=f"p1b_single_b{bit}_R{R}")
            if bit == 1:
                qc.x(data_qubits[0])
            # R kör = közelítőleg R × 20µs delay
            for _ in range(R):
                qc.delay(20000, data_qubits[0], unit="ns")
            qc.measure(data_qubits[0], 0)
            qc.metadata = {
                "phase": "1b", "arm": "single",
                "bit": bit, "R": R
            }
            circs.append(qc)

        # Kontroll 2: három qubit, csak végső többségi szavazás (nincs korrekció)
        for R in R_rounds:
            qc = QuantumCircuit(n_q, 3, name=f"p1b_majority_b{bit}_R{R}")
            for d in data_qubits:
                if bit == 1:
                    qc.x(d)
            for _ in range(R):
                for d in data_qubits:
                    qc.delay(20000, d, unit="ns")
            for i, d in enumerate(data_qubits):
                qc.measure(d, i)
            qc.metadata = {
                "phase": "1b", "arm": "majority_only",
                "bit": bit, "R": R
            }
            circs.append(qc)

        # Fő kar: aktív hibajavítással
        for R in R_rounds:
            # Közbenső mérés + feltételes korrekció (if_test)
            # Qiskit 1.x-ben: c_if / IfElseOp
            creg_anc = ClassicalRegister(2, name="anc")
            creg_out = ClassicalRegister(3, name="out")
            qc = QuantumCircuit(QuantumRegister(n_q, "q"),
                                creg_anc, creg_out,
                                name=f"p1b_active_b{bit}_R{R}")
            # Init
            if bit == 1:
                for d in data_qubits:
                    qc.x(d)
            # R kör
            for _ in range(R):
                # Paritásmérés: ancilla 0 méri d[0]⊕d[1], ancilla 1 méri d[1]⊕d[2]
                qc.cx(data_qubits[0], anc_qubits[0])
                qc.cx(data_qubits[1], anc_qubits[0])
                qc.cx(data_qubits[1], anc_qubits[1])
                qc.cx(data_qubits[2], anc_qubits[1])
                qc.measure(anc_qubits[0], creg_anc[0])
                qc.measure(anc_qubits[1], creg_anc[1])
                qc.reset(anc_qubits[0])
                qc.reset(anc_qubits[1])
                # Feltételes korrekció
                with qc.if_test((creg_anc, 0b01)):
                    qc.x(data_qubits[0])
                with qc.if_test((creg_anc, 0b10)):
                    qc.x(data_qubits[2])
                with qc.if_test((creg_anc, 0b11)):
                    qc.x(data_qubits[1])
            # Végső mérés
            for i, d in enumerate(data_qubits):
                qc.measure(d, creg_out[i])
            qc.metadata = {
                "phase": "1b", "arm": "active_correction",
                "bit": bit, "R": R
            }
            circs.append(qc)

    return circs
