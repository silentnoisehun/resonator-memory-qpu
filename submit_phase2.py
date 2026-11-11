"""
submit_phase2.py — 2. fázis DD regeneráció, éles QPU beküldés
ibm_kingston, qubit 13
"""
import os, sys, json, time, hashlib, logging
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from config import DEFAULT_CONFIG as cfg
from circuits import build_calib_circuits, build_phase2_circuits, delay_dt
from plan import Plan, shuffle_circuits
from analysis import (fit_T1, fit_T2_hahn, fit_readout_error, judge_calib,
                      judge_phase2, fit_exponential, print_verdict,
                      counts_to_expectation, D_from_counts)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

# A token SOHA nem kerülhet a repóba: környezeti változóból olvassuk.
# (A korábban ide beégetett token a git-történetben látszik → vissza kell vonni.)
TOKEN   = os.environ["IBM_QUANTUM_TOKEN"]
CRN     = "crn:v1:bluemix:public:quantum-computing:us-east:a/850d7f5ad80c4beab980d2b4bdec250d:38cf48ed-daeb-4efb-b709-c8c25dbbbc7a::"
BACKEND = "ibm_kingston"
QUBIT   = 13
SHOTS   = cfg.shots
SEED    = cfg.rng_seed
DATA_DIR = Path("data/phase2")
DATA_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("  2. FÁZIS — DD regeneráció, QPU beküldés")
print(f"  Backend: {BACKEND}  Qubit: {QUBIT}")
print("=" * 60)

svc     = QiskitRuntimeService(channel='ibm_quantum_platform', token=TOKEN, instance=CRN)
backend = svc.backend(BACKEND)
DT      = backend.dt or 4e-9

# ── Snapshot ─────────────────────────────────────────────────────────────────

qp      = backend.qubit_properties(QUBIT)
props_b = backend.properties()
T1_ref  = qp.t1
T2_ref  = qp.t2
eps_ref = props_b.readout_error(QUBIT)

snapshot = {
    "backend": BACKEND, "qubit": QUBIT,
    "T1": T1_ref, "T2": T2_ref,
    "readout_error": eps_ref, "dt": DT,
    "snapshot_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
(DATA_DIR / "snapshot.json").write_text(json.dumps(snapshot, indent=2))
print(f"\n[snapshot] T1={T1_ref*1e6:.1f}µs  T2={T2_ref*1e6:.1f}µs  ε={eps_ref:.4f}")

# ── Áramkörök ────────────────────────────────────────────────────────────────

T1_dt_list = [delay_dt(f * T1_ref, DT) for f in cfg.calib_T1_delays_T1_frac]
T2_dt_list = [delay_dt(f * T2_ref, DT) for f in cfg.calib_T2_delays_T2_frac]
p2_dt_list = [delay_dt(f * T1_ref, DT) for f in cfg.phase2_delays_T1_frac]

calib_circs  = build_calib_circuits(QUBIT, T1_dt_list, T2_dt_list)
phase2_circs = build_phase2_circuits(QUBIT, cfg.phase2_N_pulses, p2_dt_list)
all_circs_raw = calib_circs + phase2_circs

pre_hash = hashlib.sha256(
    json.dumps([c.name for c in all_circs_raw]).encode()
).hexdigest()
print(f"[plan] pre-shuffle hash: {pre_hash[:16]}…  ({len(all_circs_raw)} áramkör)")

# ── Plan seal ────────────────────────────────────────────────────────────────

plan = Plan(seed=SEED ^ 0x02, phase="2")
_ = plan.draw_bits("phase2_placeholder", 10)
order = plan.shuffle_indices(len(all_circs_raw))
plan_sha = plan.seal(str(DATA_DIR / "plan_sealed.json"))
print(f"[plan] sealed SHA: {plan_sha[:16]}…")

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
    "job_id": job_id, "backend": BACKEND, "qubit": QUBIT,
    "shots": SHOTS, "n_circuits": n,
    "plan_sha": plan_sha, "pre_shuffle_hash": pre_hash,
    "shuffle_order": order,
    "snapshot": snapshot,
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

# ── Counts kinyerés ──────────────────────────────────────────────────────────

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

# ── Kalib analízis ───────────────────────────────────────────────────────────

n_T1 = len(T1_dt_list); n_T2 = len(T2_dt_list)
T1_counts = counts_orig[:n_T1]
T2_counts = counts_orig[n_T1:n_T1+n_T2]
ro_0, ro_1 = counts_orig[n_T1+n_T2], counts_orig[n_T1+n_T2+1]

T1_times = np.array([d * DT for d in T1_dt_list])
T2_times = np.array([d * DT for d in T2_dt_list])
T1_res  = fit_T1(T1_times, T1_counts, SHOTS)
T2_res  = fit_T2_hahn(T2_times, T2_counts, SHOTS)
ro_res  = fit_readout_error(ro_0, ro_1, SHOTS)
verdict = judge_calib(T1_res, T2_res, cfg.calib_fit_tol_pct)

T1_m = T1_res.get("T1", T1_ref)
T2_m = T2_res.get("T2", T2_ref)
T1_ci = T1_res.get("T1_ci", (T1_m*0.9, T1_m*1.1))
eps   = ro_res["readout_error"]
print(f"\n[kalib] T1={T1_m*1e6:.1f}µs  T2={T2_m*1e6:.1f}µs  ε={eps:.4f}  → {verdict}")

calib_out = {"verdict": verdict,
             "T1_us": T1_m*1e6, "T2_us": T2_m*1e6, "eps": eps,
             "T1_ci_us": [v*1e6 for v in T1_ci],
             "T2_ci_us": [v*1e6 for v in T2_res.get("T2_ci",(T2_m*0.9,T2_m*1.1))]}
(DATA_DIR / "calib_result.json").write_text(json.dumps(calib_out, indent=2))

# ── 2. fázis analízis ────────────────────────────────────────────────────────

idx_map = {name: i for i, name in enumerate(names_orig)}
n_calib = n_T1 + n_T2 + 2  # T1 + T2_hahn + readout_0 + readout_1
times_s = np.array([d * DT for d in p2_dt_list])

T2_N_list, T2_N_ci_low = [], []
for N in cfg.phase2_N_pulses:
    D_vals = []
    for d in p2_dt_list:
        np_ = f"p2_N{N}_b0_d{d}"
        nm  = f"p2_N{N}_b1_d{d}"
        if np_ in idx_map and nm in idx_map:
            cp = counts_orig[idx_map[np_]]
            cm = counts_orig[idx_map[nm]]
            D_vals.append(D_from_counts(cp, cm, SHOTS))
        else:
            D_vals.append(0.0)
    D_arr  = np.array(D_vals)
    D_errs = np.ones(len(D_arr)) / np.sqrt(SHOTS)
    fit = fit_exponential(times_s, D_arr, D_errs,
                          bootstrap_n=cfg.phase2_bootstrap_n,
                          rng_seed=SEED)
    T2_N = fit["T_fit"] if fit["success"] else T2_m
    ci   = fit["T_ci"]  if fit["success"] else (0, T2_m*3)
    T2_N_list.append(T2_N)
    T2_N_ci_low.append(ci[0])
    print(f"  N={N:3d}: T2_N={T2_N*1e6:.1f}µs  D={[f'{v:.3f}' for v in D_vals]}")

result2 = judge_phase2(T2_N_list, T2_N_ci_low, T1_m, T1_ci[1], cfg.phase2_N_pulses)
print_verdict("2. fázis", result2)
(DATA_DIR / "phase2_result.json").write_text(json.dumps(
    {k: (v if not isinstance(v, (np.ndarray, np.floating)) else float(v))
     for k, v in result2.items()}, indent=2))

print(f"\nJob ID: {job_id}")
print(f"Adatok: {DATA_DIR.absolute()}")
