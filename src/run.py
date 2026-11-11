"""
run.py — IBM Quantum job beküldés, qubit-kiválasztás, eredménymentés
Máté + Maya (Sesame), 2026-11-11
"""

import json, time, logging
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

try:
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
    IBM_AVAILABLE = True
except ImportError:
    IBM_AVAILABLE = False
    logger.warning("qiskit-ibm-runtime nem elérhető.")


# ─── Qubit-kiválasztás ────────────────────────────────────────────────────────

def qubit_score(T1: float, T2: float, eps_readout: float) -> float:
    """score = min(T1, T2) / (1 + 20·ε_readout)"""
    return min(T1, T2) / (1.0 + 20.0 * eps_readout)


def get_backend_snapshot(backend) -> dict:
    """
    Pillanatkép a backend tulajdonságaiból.
    Visszaad: {qubit_idx: {T1, T2, readout_error, gate_error_1q, dt}}
    """
    props = backend.properties()
    dt    = backend.dt or 2.22e-10
    snap  = {}
    for q in range(backend.num_qubits):
        try:
            T1  = props.qubit_property(q, "T1").value
            T2  = props.qubit_property(q, "T2").value
            eps = props.qubit_property(q, "readout_error").value
            snap[q] = {"T1": T1, "T2": T2, "readout_error": eps,
                       "gate_error_1q": 1e-3, "dt": dt}
        except Exception:
            pass
    return snap


def select_qubit(snapshot: dict) -> Tuple[int, dict]:
    """Legjobb egyedi qubit score alapján."""
    best_q, best_s, best_props = -1, -1.0, {}
    for q, props in snapshot.items():
        s = qubit_score(props["T1"], props["T2"], props["readout_error"])
        if s > best_s:
            best_s, best_q, best_props = s, q, props
    logger.info("Kiválasztott qubit: %d  score=%.3g", best_q, best_s)
    return int(best_q), best_props


def select_qubit_pair(snapshot: dict, coupling_map: list) -> Tuple[int, int]:
    """
    Legjobb szomszédos qubit-pár:
    score_pair = min(score(q0), score(q1))
    """
    best_pair, best_s = (-1, -1), -1.0
    for q0, q1 in coupling_map:
        if q0 not in snapshot or q1 not in snapshot:
            continue
        s0 = qubit_score(**{k: snapshot[q0][k]
                            for k in ["T1", "T2", "readout_error"]})
        s1 = qubit_score(**{k: snapshot[q1][k]
                            for k in ["T1", "T2", "readout_error"]})
        s  = min(s0, s1)
        if s > best_s:
            best_s, best_pair = s, (q0, q1)
    return best_pair


def select_qubit_chain(snapshot: dict, coupling_map: list,
                       n: int = 5) -> List[int]:
    """
    Legjobb lánc n szomszédos qubitből.
    Brute-force: az összes lehetséges lánc közül a legjobb min-score-ú.
    """
    # Szomszédsági lista
    adj = {}
    for q0, q1 in coupling_map:
        adj.setdefault(q0, []).append(q1)
        adj.setdefault(q1, []).append(q0)

    def dfs_chains(start, length):
        if length == 1:
            return [[start]]
        chains = []
        for nb in adj.get(start, []):
            for chain in dfs_chains(nb, length - 1):
                if start not in chain:
                    chains.append([start] + chain)
        return chains

    best_chain, best_s = [], -1.0
    for start in snapshot:
        for chain in dfs_chains(start, n):
            if any(q not in snapshot for q in chain):
                continue
            s = min(qubit_score(**{k: snapshot[q][k]
                                   for k in ["T1", "T2", "readout_error"]})
                    for q in chain)
            if s > best_s:
                best_s, best_chain = s, chain
    return best_chain


# ─── Reset-időtartam a backendről ─────────────────────────────────────────────

def get_reset_duration_dt(backend, qubit: int) -> Optional[int]:
    """
    A `reset` művelet tényleges időtartama dt egységben az adott qubiten,
    a backend Target-jéből (backend.target["reset"][(qubit,)].duration, s).

    Visszaad None-t, ha a backend nem közli (nincs `reset` a Targetben,
    nincs duration, vagy nincs dt). Ilyenkor a hívó a
    circuits.RESET_DURATION_DT alapértéket (1500 dt) használja — a 3. fázis
    csatolt karjában a kompenzáló delay ekkor csak közelítő.
    Csak metaadatot olvas; jobot nem indít.
    """
    try:
        dt  = backend.dt
        dur = backend.target["reset"][(qubit,)].duration
        if not dt or dur is None or dur <= 0:
            return None
        return int(round(dur / dt))
    except Exception:
        return None


# ─── Counts kinyerés név szerinti regiszterből ────────────────────────────────

def counts_from_register(databin, register: str) -> dict:
    """
    SamplerV2 pub-eredmény (`result[i].data`) egy NÉV SZERINT megadott
    klasszikus regiszterének counts-a.

    Ha a regiszter hiányzik, KeyError — szándékosan nincs tartalék
    ("első" / "utolsó" regiszter), mert több regiszteres áramkörnél
    (1b aktív kar: `anc` + `out`) a találgatás csendben rossz biteket adna.
    """
    available = list(databin.keys())
    if register not in available:
        raise KeyError(
            f"A(z) '{register}' klasszikus regiszter hiányzik az eredményből "
            f"(elérhető: {available}). Az elemzés megáll, nem választ másikat.")
    return dict(databin[register].get_counts())


# ─── Job beküldés ─────────────────────────────────────────────────────────────

def estimate_job_seconds(n_circuits: int, shots: int,
                          avg_circuit_depth: int = 50,
                          dt: float = 2.22e-10) -> float:
    """Becsült futásidő: n_circuits × shots × depth × dt + overhead."""
    exec_time = n_circuits * shots * avg_circuit_depth * dt
    overhead  = n_circuits * 0.5  # ~0.5s / áramkör overhead
    return exec_time + overhead


def submit_job(circuits: list, shots: int, backend,
               seed: int = 20261111, dry: bool = False):
    """
    IBM job beküldés.
    dry=True → csak szimulál, nem küld be.
    """
    if not IBM_AVAILABLE:
        raise RuntimeError("qiskit-ibm-runtime nem elérhető")
    if dry:
        logger.info("DRY RUN — nem küldünk be job-ot")
        return None

    sampler = Sampler(backend)
    job     = sampler.run(circuits, shots=shots)
    logger.info("Job beküldve: %s", job.job_id())
    return job


# ─── Eredmény mentés ──────────────────────────────────────────────────────────

def save_results(counts_list: list, circuits: list,
                 snapshot: dict, path: str,
                 extra_meta: dict = None):
    """
    Menti a nyers counts-okat + áramkör metadata + backend snapshot-ot.
    """
    out = {
        "saved_at":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "snapshot":    snapshot,
        "extra":       extra_meta or {},
        "results":     []
    }
    for counts, circ in zip(counts_list, circuits):
        out["results"].append({
            "circuit_name": circ.name,
            "metadata":     getattr(circ, "metadata", {}),
            "counts":       counts,
        })
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(out, indent=2), encoding="utf-8")
    logger.info("Eredmények mentve: %s", path)
