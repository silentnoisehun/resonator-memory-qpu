"""
fetch_results.py — Lekéri a job eredményét és menti raw_counts.json-ba
"""
import sys, json, time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from qiskit_ibm_runtime import QiskitRuntimeService

TOKEN   = "fXrTMlExIJMOX8LjhqjtQo-Hpv3-aaxFCXJHW5wK0y_T"
CRN     = "crn:v1:bluemix:public:quantum-computing:us-east:a/850d7f5ad80c4beab980d2b4bdec250d:38cf48ed-daeb-4efb-b709-c8c25dbbbc7a::"
DATA_DIR = Path("data/phase1")

meta     = json.loads((DATA_DIR / "job_meta.json").read_text())
JOB_ID   = meta["job_id"]
N        = meta["n_circuits"]
ORDER    = meta.get("shuffle_order")  # ha el lett mentve
PLAN_SHA = meta["plan_sha"]

print(f"Job ID: {JOB_ID}  n={N}")

svc = QiskitRuntimeService(channel='ibm_quantum_platform', token=TOKEN, instance=CRN)
job = svc.job(JOB_ID)

status = job.status()
print(f"Status: {status}")
if str(status) not in ("DONE", "JobStatus.DONE"):
    print("Még nem kész, várjunk...")
    while str(job.status()) not in ("DONE", "ERROR", "CANCELLED", "JobStatus.DONE"):
        time.sleep(5)
        print(f"  {job.status()}")

result = job.result()
print(f"Pub count: {len(result)}")

# Counts kinyerése
counts_list = []
for i in range(len(result)):
    try:
        pub_res = result[i]
        # SamplerV2 / új API: data.meas.get_counts()
        try:
            c = pub_res.data.meas.get_counts()
        except AttributeError:
            # régi API
            c = dict(pub_res.data.c.get_counts())
        counts_list.append(c)
    except Exception as e:
        print(f"  [warn] counts[{i}]: {e}")
        counts_list.append({})

print(f"Counts kinyerve: {len(counts_list)} db")
print(f"Első 3 counts: {counts_list[:3]}")

# Shuffle visszarendezés
plan_data = json.loads((DATA_DIR / "plan_sealed.json").read_text())
order = plan_data["data"]["shuffle_order"]
n = len(order)
inv_order = [0] * n
for new_i, old_i in enumerate(order):
    inv_order[old_i] = new_i

# Áramkör nevek az eredeti sorrendben
from circuits import (build_calib_circuits, build_phase1_circuits, delay_dt)
from config import DEFAULT_CONFIG as cfg

snap = json.loads((DATA_DIR / "snapshot.json").read_text())
DT = snap["dt"]
T1_ref = snap["T1"]
T2_ref = snap["T2"]
QUBIT = snap["qubit"]

T1_dt_list = [delay_dt(f * T1_ref, DT) for f in cfg.calib_T1_delays_T1_frac]
T2_dt_list = [delay_dt(f * T2_ref, DT) for f in cfg.calib_T2_delays_T2_frac]
p1_dt_list = [delay_dt(f * T2_ref, DT) for f in cfg.phase1_delays_T2_frac]

calib_circs  = build_calib_circuits(QUBIT, T1_dt_list, T2_dt_list)
phase1_circs = build_phase1_circuits(QUBIT, cfg.phase1_theta_deg, p1_dt_list)
all_circs_raw = calib_circs + phase1_circs

names_orig = [c.name for c in all_circs_raw]

# Visszarendezés
if len(counts_list) == n:
    counts_orig = [counts_list[inv_order[i]] for i in range(n)]
else:
    print(f"WARN: counts hossza {len(counts_list)} != {n}, nincs visszarendezés")
    counts_orig = counts_list

raw_out = {
    "job_id": JOB_ID,
    "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "circuits": names_orig,
    "counts": counts_orig,
}
(DATA_DIR / "raw_counts.json").write_text(json.dumps(raw_out, indent=2))
print(f"\n✅ raw_counts.json mentve ({len(counts_orig)} db)")
print(f"Minta[0]: {counts_orig[0]}")
print(f"Minta[10]: {counts_orig[10]}")
