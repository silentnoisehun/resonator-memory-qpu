"""
submit_phase1.py — 1. fázis éles QPU beküldés
ibm_kingston, qubit 13 (T1=412µs, T2=664µs, ε=0.0020)

Sorrend:
  1. Plan seal (bitek + sorrend lezárva, SHA-256)
  2. Áramkörök felépítve + pre-shuffle hash
  3. Shuffle (rögzített seed)
  4. Transpilálás
  5. Job beküldés
  6. Polling + mentés
"""
import sys, json, time, hashlib, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from config import DEFAULT_CONFIG as cfg
from circuits import build_calib_circuits, build_phase1_circuits, delay_dt
from plan import Plan, shuffle_circuits
from analysis import (fit_T1, fit_T2_hahn, fit_readout_error, judge_calib,
                      predict_t_olv_phase1, fit_exponential, t_readable_from_fit,
                      print_verdict)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ── Kapcsolat ────────────────────────────────────────────────────────────────

TOKEN   = "***REMOVED***"
CRN     = "crn:v1:bluemix:public:quantum-computing:us-east:a/850d7f5ad80c4beab980d2b4bdec250d:38cf48ed-daeb-4efb-b709-c8c25dbbbc7a::"
BACKEND = "ibm_kingston"
QUBIT   = 13
SHOTS   = cfg.shots
SEED    = cfg.rng_seed
DATA_DIR = Path("data/phase1")
DATA_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("  1. FÁZIS — QPU beküldés")
print(f"  Backend: {BACKEND}  Qubit: {QUBIT}")
print("=" * 60)

svc     = QiskitRuntimeService(channel='ibm_quantum_platform', token=TOKEN, instance=CRN)
backend = svc.backend(BACKEND)
DT      = backend.dt or 2.22e-10

# ── Backend snapshot ─────────────────────────────────────────────────────────

qp      = backend.qubit_properties(QUBIT)
props_b = backend.properties()
T1_ref  = qp.t1
T2_ref  = qp.t2
eps_ref = props_b.readout_error(QUBIT)

snapshot = {
    "backend": BACKEND, "qubit": QUBIT,
    "T1": T1_ref, "T2": T2_ref,
    "readout_error": eps_ref,
    "dt": DT,
    "snapshot_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
(DATA_DIR / "snapshot.json").write_text(json.dumps(snapshot, indent=2))
print(f"\n[snapshot] T1={T1_ref*1e6:.1f}µs  T2={T2_ref*1e6:.1f}µs  ε={eps_ref:.4f}")

# ── Plan seal ────────────────────────────────────────────────────────────────

plan = Plan(seed=SEED, phase="1")
_ = plan.draw_bits("phase1_bits_placeholder", 10)   # placeholder, a valódi bitekhez a dryrun-hoz hasonló logika kellene

T1_dt_list = [delay_dt(f * T1_ref, DT) for f in cfg.calib_T1_delays_T1_frac]
T2_dt_list = [delay_dt(f * T2_ref, DT) for f in cfg.calib_T2_delays_T2_frac]
p1_dt_list = [delay_dt(f * T2_ref, DT) for f in cfg.phase1_delays_T2_frac]

calib_circs = build_calib_circuits(QUBIT, T1_dt_list, T2_dt_list)
phase1_circs = build_phase1_circuits(QUBIT, cfg.phase1_theta_deg, p1_dt_list)
all_circs_raw = calib_circs + phase1_circs

# Pre-shuffle hash
pre_hash = hashlib.sha256(
    json.dumps([c.name for c in all_circs_raw]).encode()
).hexdigest()
print(f"[plan] pre-shuffle hash: {pre_hash[:16]}…")

order = plan.shuffle_indices(len(all_circs_raw))
plan_sha = plan.seal(str(DATA_DIR / "plan_sealed.json"))
print(f"[plan] sealed SHA: {plan_sha[:16]}…")

all_circs = shuffle_circuits(all_circs_raw, order)
n = len(all_circs)
print(f"[circuits] összesen: {n} áramkör  ({len(calib_circs)} kalib + {len(phase1_circs)} phase1)")

# ── Transpilálás ─────────────────────────────────────────────────────────────

print("\n[transpile] Optimalizálás…")
pm = generate_preset_pass_manager(optimization_level=1, backend=backend)
t_circs = pm.run(all_circs)
depths = [c.depth() for c in t_circs]
print(f"[transpile] mélység: min={min(depths)}  max={max(depths)}  átlag={sum(depths)/len(depths):.1f}")

# ── Becsült futásidő ─────────────────────────────────────────────────────────

est_s = n * SHOTS * (sum(depths)/len(depths)) * DT + n * 0.5
print(f"[quota] becsült futásidő: {est_s:.0f}s  (limit: {cfg.max_estimated_seconds}s)")
if est_s > cfg.max_estimated_seconds * 10:   # 10× tágabb limit az egész fázisnak
    print("FIGYELEM: nagyon hosszú job!")

# ── Beküldés ─────────────────────────────────────────────────────────────────

print(f"\n[submit] Beküldés → {BACKEND}  shots={SHOTS} …")
sampler = Sampler(backend)
job = sampler.run(t_circs, shots=SHOTS)
job_id = job.job_id()
print(f"[submit] job_id: {job_id}")

meta = {
    "job_id": job_id,
    "backend": BACKEND,
    "qubit": QUBIT,
    "shots": SHOTS,
    "n_circuits": n,
    "plan_sha": plan_sha,
    "pre_shuffle_hash": pre_hash,
    "snapshot": snapshot,
    "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
(DATA_DIR / "job_meta.json").write_text(json.dumps(meta, indent=2))
print(f"[meta] mentve → {DATA_DIR}/job_meta.json")

# ── Polling ──────────────────────────────────────────────────────────────────

print("\n[poll] Várakozás a job eredményére…")
while True:
    status = job.status()
    print(f"  [{time.strftime('%H:%M:%S')}] status: {status}")
    if status in ("DONE", "ERROR", "CANCELLED"):
        break
    time.sleep(15)

if str(status) != "DONE":
    print(f"[HIBA] Job nem sikerült: {status}")
    sys.exit(1)

# ── Eredmény feldolgozás ─────────────────────────────────────────────────────

print("\n[result] Eredmények lekérése…")
result = job.result()

# SamplerV2: result[i].data.meas.get_counts()
counts_shuffled = []
for i in range(n):
    try:
        pub_res = result[i]
        counts = pub_res.data.meas.get_counts()
    except Exception as e:
        print(f"  [warn] counts[{i}] hiba: {e}")
        counts = {}
    counts_shuffled.append(counts)

# Visszarendezés az eredeti sorrendbe
inv_order = [0] * n
for new_i, old_i in enumerate(order):
    inv_order[old_i] = new_i
counts_orig = [counts_shuffled[inv_order[i]] for i in range(n)]

# Mentés
raw_out = {
    "job_id": job_id,
    "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "circuits": [c.name for c in all_circs_raw],
    "counts": counts_orig,
}
(DATA_DIR / "raw_counts.json").write_text(json.dumps(raw_out, indent=2))
print(f"[result] raw_counts mentve ({n} db)")

# ── Kalib analízis (gyors) ───────────────────────────────────────────────────

n_T1 = len(T1_dt_list)
n_T2 = len(T2_dt_list)
T1_counts  = counts_orig[:n_T1]
T2_counts  = counts_orig[n_T1:n_T1+n_T2]
ro_0, ro_1 = counts_orig[n_T1+n_T2], counts_orig[n_T1+n_T2+1]

T1_times = [d * DT for d in T1_dt_list]
T2_times = [d * DT for d in T2_dt_list]

import numpy as np
T1_res  = fit_T1(np.array(T1_times), T1_counts, SHOTS)
T2_res  = fit_T2_hahn(np.array(T2_times), T2_counts, SHOTS)
ro_res  = fit_readout_error(ro_0, ro_1, SHOTS)
verdict = judge_calib(T1_res, T2_res, cfg.calib_fit_tol_pct)

print(f"\n[calib] T1={T1_res.get('T1',0)*1e6:.1f}µs  "
      f"T2={T2_res.get('T2',0)*1e6:.1f}µs  "
      f"ε={ro_res['readout_error']:.4f}  → {verdict}")

calib_out = {
    "verdict": verdict,
    "T1_us": T1_res.get("T1", 0) * 1e6,
    "T2_us": T2_res.get("T2", 0) * 1e6,
    "eps":   ro_res["readout_error"],
    "T1_ci_us": [v*1e6 for v in T1_res.get("T1_ci", (0,0))],
    "T2_ci_us": [v*1e6 for v in T2_res.get("T2_ci", (0,0))],
}
(DATA_DIR / "calib_result.json").write_text(json.dumps(calib_out, indent=2))

print("\n" + "=" * 60)
print(f"  Kalib ítélet: {verdict}")
if verdict != "VALID":
    print("  FIGYELEM: kalibráció INVALID! Az 1. fázis adatok megbízhatatlanok.")
print("=" * 60)
print(f"\nMinden adat: {DATA_DIR.absolute()}")
print(f"Job ID:      {job_id}")
