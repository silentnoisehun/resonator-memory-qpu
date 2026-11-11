"""
config.py — QPU rezonátor-memória kísérlet konfigurációja
Máté + Maya (Sesame), 2026-11-11

FONTOS: a job beküldése előtt befagyasztani (commitolni) kell.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json, hashlib, time

VERSION = "1.0.0-qpu"
AUTHOR  = "Máté + Maya (Sesame), 2026-11-11"


@dataclass
class QPUConfig:
    # ── Backend ──────────────────────────────────────────────────────────────
    backend_name: str           = "ibm_sherbrooke"   # vagy ibm_brisbane stb.
    instance: str               = "ibm-q/open/main"
    shots: int                  = 1000
    shots_1b: int               = 2000               # 1b fázis több shot

    # ── Qubitválasztási szabály ───────────────────────────────────────────────
    # score = min(T1, T2) / (1 + 20·ε_readout)
    # Legjobb qubit (phase 0,1,2), legjobb szomszédos pár (3), legjobb lánc (1b)
    qubit_selection_rule: str   = "score = min(T1,T2) / (1 + 20*eps_readout)"

    # ── 0. fázis: kalibráció ─────────────────────────────────────────────────
    calib_T1_delays_T1_frac: List[float] = field(
        default_factory=lambda: [0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
    )
    calib_T2_delays_T2_frac: List[float] = field(
        default_factory=lambda: [0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
    )
    calib_fit_tol_pct: float    = 15.0   # illesztés relatív hiba küszöb

    # ── 1. fázis ─────────────────────────────────────────────────────────────
    phase1_theta_deg: List[float] = field(
        default_factory=lambda: [30.0, 60.0, 90.0]
    )
    # t = T2_submit × frac, kerekítve dt többszörösére
    phase1_delays_T2_frac: List[float] = field(
        default_factory=lambda: [0.0, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0]
    )
    phase1_D_min: float         = 0.1    # t_olv definíció küszöb
    phase1_bootstrap_n: int     = 2000
    phase1_holm_alpha: float    = 0.01

    # ── 2. fázis: DD (dinamikus csatolásmentesítés) ──────────────────────────
    phase2_N_pulses: List[int]  = field(
        default_factory=lambda: [1, 4, 16, 64]
    )
    phase2_delays_T1_frac: List[float] = field(
        default_factory=lambda: [0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5]
    )
    phase2_bootstrap_n: int     = 2000

    # ── 3. fázis: nem-markovi visszafolyás ───────────────────────────────────
    phase3_coupling_phi_rad: float  = 0.3927    # π/8
    phase3_k_steps: List[int]       = field(
        default_factory=lambda: list(range(17))  # 0..16
    )
    phase3_bootstrap_n: int         = 2000
    phase3_alpha: float             = 0.01

    # ── 1b fázis: bit-flip repetition code ───────────────────────────────────
    phase1b_R_rounds: List[int]  = field(
        default_factory=lambda: [0, 1, 2, 4, 8]
    )
    phase1b_round_dt_us: float   = 20.0    # µs / kör
    phase1b_alpha: float         = 0.01

    # ── Statisztika ───────────────────────────────────────────────────────────
    rng_seed: int               = 20261111

    # ── Kvóta ────────────────────────────────────────────────────────────────
    max_estimated_seconds: float = 300.0   # beküldési limit: 5 perc

    # ── Kimenet ──────────────────────────────────────────────────────────────
    data_dir: str               = "data"
    log_level: str              = "INFO"


def freeze_config(cfg: QPUConfig, path: str) -> str:
    d = asdict(cfg)
    d["_frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    d["_version"]   = VERSION
    blob = json.dumps(d, indent=2, sort_keys=True)
    sha  = hashlib.sha256(blob.encode()).hexdigest()
    d["_sha256"] = sha
    blob = json.dumps(d, indent=2, sort_keys=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(blob)
    return sha


def load_config(path: str) -> QPUConfig:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    stored = d.pop("_sha256", None)
    d.pop("_frozen_at", None); d.pop("_version", None)
    blob     = json.dumps(d, indent=2, sort_keys=True)
    computed = hashlib.sha256(blob.encode()).hexdigest()
    if stored and stored != computed:
        raise ValueError(f"Config hash mismatch: {stored} vs {computed}")
    fields = set(QPUConfig.__dataclass_fields__)
    return QPUConfig(**{k: v for k, v in d.items() if k in fields})


DEFAULT_CONFIG = QPUConfig()
