"""
submit_phase3.py — 3. fázis nem-markovi visszafolyás, éles QPU
Qubitpár: ibm_kingston, legjobb szomszédos pár (score alapján)
"""
import sys, json, time, hashlib, logging
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from config import DEFAULT_CONFIG as cfg
from circuits import build_phase3_all, delay_dt, RESET_DURATION_DT
from plan import Plan, shuffle_circuits
from analysis import (blp_measure, judge_phase3, print_verdict,
                      counts_to_expectation, D_from_counts)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

TOKEN   = "***REMOVED***"
CRN     = "crn:v1:bluemix:public:quantum-computing:us-east:a/850d7f5ad80c4beab980d2b4bdec250d:38cf48ed-daeb-4efb-b709-c8c25dbbbc7a::"
BACKEND = "ibm_kingston"
SHOTS   = cfg.shots
SEED    = cfg.rng_seed
DATA_DIR = Path("data/phase3")
DATA_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("  3. FÁZIS — Nem-markovi visszafolyás, QPU")
print(f"  Backend: {BACKEND}")
print("=" * 60)

svc     = QiskitRuntimeService(channel='ibm_quantum_platform', token=TOKEN, instance=CRN)
backend = svc.backend(BACKEND)
DT      = backend.dt or 4e-9
props_b = backend.properties()

# ── Legjobb qubitpár kiválasztás ─────────────────────────────────────────────

def qscore(q):
    qp  = backend.qubit_properties(q)
    t1  = qp.t1 or 0; t2 = qp.t2 or 0
    eps = props_b.readout_error(q) or 0.02
    return min(t1, t2) / (1 + 20 * eps)

cmap = list(backend.coupling_map)
best_pair, best_s = (13, 14), -1.0
for q0, q1 in cmap:
    s = min(qscore(q0), qscore(q1))
    if s > best_s:
        best_s, best_pair = s, (q0, q1)

Q_S, Q_E = best_pair
print(f"[select] Legjobb pár: q{Q_S}-q{Q_E}  score={best_s*1e6:.2f}")

qp_s = backend.qubit_properties(Q_S)
qp_e = backend.qubit_properties(Q_E)
snapshot = {
    "backend": BACKEND, "qubit_S": Q_S, "qubit_E": Q_E,
    "T1_S": qp_s.t1, "T2_S": qp_s.t2,
    "T1_E": qp_e.t1, "T2_E": qp_e.t2,
    "readout_error_S": props_b.readout_error(Q_S),
    "dt": DT, "reset_duration_dt": RESET_DURATION_DT,
    "snapshot_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
(DATA_DIR / "snapshot.json").write_text(json.dumps(snapshot, indent=2))
print(f"[snapshot] S: T1={qp_s.t1*1e6:.1f}µs T2={qp_s.t2*1e6:.1f}µs  "
      f"E: T1={qp_e.t1*1e6:.1f}µs T2={qp_e.t2*1e6:.1f}µs")

# ── Áramkörök ────────────────────────────────────────────────────────────────

all_circs_raw = build_phase3_all(
    Q_S, Q_E,
    phi=cfg.phase3_coupling_phi_rad,
    k_steps=cfg.phase3_k_steps,
    reset_duration_dt=RESET_DURATION_DT,
)
pre_hash = hashlib.sha256(
    json.dumps([c.name for c in all_circs_raw]).encode()
).hexdigest()
print(f"[plan] {len(all_circs_raw)} áramkör  pre-hash: {pre_hash[:16]}…")

plan = Plan(seed=SEED ^ 0x03, phase="3")
_ = plan.draw_bits("phase3_placeholder", 10)
order = plan.shuffle_indices(len(all_circs_raw))
plan_sha = plan.seal(str(DATA_DIR / "plan_sealed.json"))

all_circs = shuffle_circuits(all_circs_raw, order)
n = len(all_circs)

# ── Transpilálás ─────────────────────────────────────────────────────────────

print("[transpile] …")
pm = generate_preset_pass_manager(optimization_level=1, backend=backend)
t_circs = pm.run(all_circs)
depths = [c.depth() for c in t_circs]
print(f"[transpile] mélység: min={min(depths)}  max={max(depths)}  átlag={sum(depths)/len(depths):.1f}")

# ── Beküldés ─────────────────────────────────────────────────────────────────

print(f"\n[submit] → {BACKEND}  n={n}  shots={SHOTS} …")
sampler = Sampler(backend)
job = sampler.run(t_circs, shots=SHOTS)
job_id = job.job_id()
print(f"[submit] job_id: {job_id}")

meta = {
    "job_id": job_id, "backend": BACKEND,
    "qubit_S": Q_S, "qubit_E": Q_E,
    "shots": SHOTS, "n_circuits": n,
    "plan_sha": plan_sha, "pre_shuffle_hash": pre_hash,
    "shuffle_order": order, "snapshot": snapshot,
    "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
(DATA_DIR / "job_meta.json").write_text(json.dumps(meta, indent=2))

# ── Polling ──────────────────────────────────────────────────────────────────

print("[poll] Várakozás…")
while True:
    status = job.status()
    print(f"  [{time.strftime('%H:%M:%S')}] {status}")
    if str(status) in ("DONE", "ERROR", "CANCELLED", "JobStatus.DONE"):
        break
    time.sleep(15)

if str(status) not in ("DONE", "JobStatus.DONE"):
    print(f"HIBA: {status}"); sys.exit(1)

# ── Counts ───────────────────────────────────────────────────────────────────

result = job.result()
counts_shuffled = []
for i in range(len(result)):
    db  = result[i].data
    reg = next(v for _, v in db.items())
    counts_shuffled.append(reg.get_counts())

inv = [0] * n
for new_i, old_i in enumerate(order):
    inv[old_i] = new_i
counts_orig = [counts_shuffled[inv[i]] for i in range(n)]

names_orig = [c.name for c in all_circs_raw]
(DATA_DIR / "raw_counts.json").write_text(
    json.dumps({"job_id": job_id,
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "circuits": names_orig, "counts": counts_orig}, indent=2))
print(f"[result] raw_counts mentve ({n} db)")

# ── 3. fázis analízis ────────────────────────────────────────────────────────

idx_map = {name: i for i, name in enumerate(names_orig)}
k_steps = cfg.phase3_k_steps

# D(k) a csatolt és kontroll karban
D_coupled = []
D_control = []
for k in k_steps:
    # csatolt: b0 és b1 átlagából
    cp0 = counts_orig[idx_map.get(f"p3_coupled_b0_k{k}", 0)] if f"p3_coupled_b0_k{k}" in idx_map else {"0":500,"1":500}
    cp1 = counts_orig[idx_map.get(f"p3_coupled_b1_k{k}", 0)] if f"p3_coupled_b1_k{k}" in idx_map else {"0":500,"1":500}
    D_coupled.append(D_from_counts(cp0, cp1, SHOTS))

    ct0 = counts_orig[idx_map.get(f"p3_control_b0_k{k}", 0)] if f"p3_control_b0_k{k}" in idx_map else {"0":500,"1":500}
    ct1 = counts_orig[idx_map.get(f"p3_control_b1_k{k}", 0)] if f"p3_control_b1_k{k}" in idx_map else {"0":500,"1":500}
    D_control.append(D_from_counts(ct0, ct1, SHOTS))

D_coupled = np.array(D_coupled)
D_control = np.array(D_control)
blp_c = blp_measure(D_coupled)

# Bootstrap kontroll BLP
rng = np.random.default_rng(SEED)
blp_boots = []
for _ in range(cfg.phase3_bootstrap_n):
    noise = rng.normal(0, 1/np.sqrt(SHOTS), size=len(D_control))
    blp_boots.append(blp_measure(D_control + noise))
blp_boots = np.array(blp_boots)

result3 = judge_phase3(blp_c, blp_boots, cfg.phase3_alpha)
print(f"\nD_coupled: {[f'{v:.3f}' for v in D_coupled]}")
print(f"D_control: {[f'{v:.3f}' for v in D_control]}")
print_verdict("3. fázis", result3)

(DATA_DIR / "phase3_result.json").write_text(json.dumps(
    {k: (float(v) if isinstance(v, (np.floating, float)) else
         v.tolist() if isinstance(v, np.ndarray) else v)
     for k, v in result3.items()}, indent=2))

print(f"\nJob ID: {job_id}")
