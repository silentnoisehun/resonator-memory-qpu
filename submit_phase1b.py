"""
submit_phase1b.py — 1b fázis bit-flip repetition code, éles QPU
5 szomszédos qubit lánc, ibm_kingston
"""
import sys, json, time, hashlib, logging
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from config import DEFAULT_CONFIG as cfg
from circuits import build_phase1b_circuits
from plan import Plan, shuffle_circuits
from analysis import judge_phase1b, print_verdict

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

TOKEN   = "fXrTMlExIJMOX8LjhqjtQo-Hpv3-aaxFCXJHW5wK0y_T"
CRN     = "crn:v1:bluemix:public:quantum-computing:us-east:a/850d7f5ad80c4beab980d2b4bdec250d:38cf48ed-daeb-4efb-b709-c8c25dbbbc7a::"
BACKEND = "ibm_kingston"
SHOTS   = cfg.shots_1b   # 2000
SEED    = cfg.rng_seed
DATA_DIR = Path("data/phase1b")
DATA_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("  1b FÁZIS — Bit-flip repetition code, QPU")
print(f"  Backend: {BACKEND}  shots={SHOTS}")
print("=" * 60)

svc     = QiskitRuntimeService(channel='ibm_quantum_platform', token=TOKEN, instance=CRN)
backend = svc.backend(BACKEND)
DT      = backend.dt or 4e-9
props_b = backend.properties()

# ── 5-qubit lánc kiválasztás ─────────────────────────────────────────────────

def qscore(q):
    qp  = backend.qubit_properties(q)
    t1  = qp.t1 or 0; t2 = qp.t2 or 0
    eps = props_b.readout_error(q) or 0.02
    return min(t1, t2) / (1 + 20 * eps)

cmap = list(backend.coupling_map)
adj = {}
for q0, q1 in cmap:
    adj.setdefault(q0, set()).add(q1)
    adj.setdefault(q1, set()).add(q0)

def find_chains(length=5):
    chains = []
    def dfs(path):
        if len(path) == length:
            chains.append(list(path)); return
        for nb in adj.get(path[-1], set()):
            if nb not in path:
                dfs(path + [nb])
    for start in range(backend.num_qubits):
        dfs([start])
    return chains

chains = find_chains(5)
best_chain, best_s = None, -1.0
for ch in chains:
    s = min(qscore(q) for q in ch)
    if s > best_s:
        best_s, best_chain = s, ch

DATA_Q, ANC_Q = best_chain[:3], best_chain[3:5]
# A build_phase1b_circuits lokális indexeket vár (0..4)
DATA_Q_LOCAL = [0, 1, 2]
ANC_Q_LOCAL  = [3, 4]
print(f"[select] Lánc: {best_chain}  score={best_s*1e6:.2f}")
print(f"         adat: {DATA_Q}  ancilla: {ANC_Q}")

snapshot = {
    "backend": BACKEND, "chain": best_chain,
    "data_qubits": DATA_Q, "anc_qubits": ANC_Q,
    "dt": DT, "shots": SHOTS,
    "snapshot_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
for q in best_chain:
    qp = backend.qubit_properties(q)
    snapshot[f"T1_q{q}"] = qp.t1
    snapshot[f"T2_q{q}"] = qp.t2
(DATA_DIR / "snapshot.json").write_text(json.dumps(snapshot, indent=2))

# ── Áramkörök ────────────────────────────────────────────────────────────────

all_circs_raw = build_phase1b_circuits(DATA_Q_LOCAL, ANC_Q_LOCAL, cfg.phase1b_R_rounds)
pre_hash = hashlib.sha256(
    json.dumps([c.name for c in all_circs_raw]).encode()
).hexdigest()
print(f"[plan] {len(all_circs_raw)} áramkör  pre-hash: {pre_hash[:16]}…")

plan = Plan(seed=SEED ^ 0x1B, phase="1b")
_ = plan.draw_bits("phase1b_placeholder", 10)
order = plan.shuffle_indices(len(all_circs_raw))
plan_sha = plan.seal(str(DATA_DIR / "plan_sealed.json"))

all_circs = shuffle_circuits(all_circs_raw, order)
n = len(all_circs)

# ── Transpilálás ─────────────────────────────────────────────────────────────

print("[transpile] …")
pm = generate_preset_pass_manager(
    optimization_level=1,
    backend=backend,
    initial_layout=best_chain   # logikai q0→q12, q1→q13, stb.
)
t_circs = pm.run(all_circs)
depths = [c.depth() for c in t_circs]
print(f"[transpile] min={min(depths)}  max={max(depths)}  átlag={sum(depths)/len(depths):.1f}")

# ── Beküldés ─────────────────────────────────────────────────────────────────

print(f"\n[submit] → {BACKEND}  n={n}  shots={SHOTS} …")
sampler = Sampler(backend)
job = sampler.run(t_circs, shots=SHOTS)
job_id = job.job_id()
print(f"[submit] job_id: {job_id}")

meta = {
    "job_id": job_id, "backend": BACKEND,
    "chain": best_chain, "data_qubits": DATA_Q, "anc_qubits": ANC_Q,
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
    db = result[i].data
    # 1b: több register — az összes bitet összefűzzük
    all_bits = {}
    for attr_name, reg in db.items():
        try:
            c = reg.get_counts()
            all_bits = c  # az utolsó (output) register counts-a kell
        except Exception:
            pass
    counts_shuffled.append(all_bits)

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

# ── 1b analízis ──────────────────────────────────────────────────────────────

idx_map = {name: i for i, name in enumerate(names_orig)}
n_R = len(cfg.phase1b_R_rounds)

err_active = []
err_single = []

for i_R, R in enumerate(cfg.phase1b_R_rounds):
    # single: bit=1 kell (p1b_single_b1_R{R})
    name_s = f"p1b_single_b1_R{R}"
    name_a = f"p1b_active_b1_R{R}"
    if name_s in idx_map:
        c_s = counts_orig[idx_map[name_s]]
        n1 = c_s.get("1", c_s.get("001", 0))
        n0 = c_s.get("0", c_s.get("000", SHOTS - n1))
        total = n1 + n0
        err_single.append((total - n1) / total if total > 0 else 0.5)
    else:
        err_single.append(0.5)

    if name_a in idx_map:
        c_a = counts_orig[idx_map[name_a]]
        # Többségi szavazás: 3-bites kimenet
        n_correct = sum(cnt for bits, cnt in c_a.items()
                        if bits.count("1") >= 2)  # bit=1 volt → 111 helyes
        total = sum(c_a.values())
        err_active.append((total - n_correct) / total if total > 0 else 0.5)
    else:
        err_active.append(0.5)

print(f"\nerr_single: {[f'{v:.3f}' for v in err_single]}")
print(f"err_active: {[f'{v:.3f}' for v in err_active]}")

result1b = judge_phase1b(err_active, err_single, cfg.phase1b_R_rounds,
                          SHOTS, cfg.phase1b_alpha)
print_verdict("1b fázis", result1b)

(DATA_DIR / "phase1b_result.json").write_text(json.dumps(
    {k: (float(v) if isinstance(v, (np.floating, float)) else v)
     for k, v in result1b.items()}, indent=2))

print(f"\nJob ID: {job_id}")
