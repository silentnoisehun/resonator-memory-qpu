"""
analyze_phase3.py — 3. fázis (BLP backflow) offline elemzése a nyers counts-okból.

Nem csatlakozik az IBM-hez, jobot nem indít. Bemenet: data/phase3/raw_counts.json,
job_meta.json. Kimenet: data/phase3/phase3_result.json.
Az elemzés a submit_phase3.py-ban lévővel azonos (ugyanaz a seed).

Az ítélet "TEXTBOOK" = a csatolt karban szignifikáns visszaáramlás van, ahogy
a tankönyvi fizika jósolja. Ez NEM anomália és nem új fizika.
"""
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import DEFAULT_CONFIG as cfg
from rawdata import load_raw, need, write_json
from analysis import blp_measure, judge_phase3, print_verdict, D_from_counts

C, meta, DATA_DIR = load_raw("phase3")
SHOTS   = meta["shots"]
k_steps = cfg.phase3_k_steps


def D_arm(arm):
    return np.array([D_from_counts(need(C, f"p3_{arm}_b0_k{k}"),
                                   need(C, f"p3_{arm}_b1_k{k}"), SHOTS)
                     for k in k_steps])


D_coupled, D_control = D_arm("coupled"), D_arm("control")
blp_c, blp_ctrl = blp_measure(D_coupled), blp_measure(D_control)

# Kontroll-eloszlás: a mért kontroll D(k) + shot-zaj nagyságú Gauss-zaj BLP-je
rng = np.random.default_rng(cfg.rng_seed)
boots = np.array([blp_measure(D_control + rng.normal(0, 1 / np.sqrt(SHOTS), size=len(D_control)))
                  for _ in range(cfg.phase3_bootstrap_n)])

result = judge_phase3(blp_c, boots, cfg.phase3_alpha)
k_min = int(np.argmin(D_coupled))
k_re  = k_min + int(np.argmax(D_coupled[k_min:]))
result.update({
    "job_id": meta["job_id"],
    "qubit_S": meta["qubit_S"], "qubit_E": meta["qubit_E"],
    "blp_control_measured": blp_ctrl,
    "p_value_resolution": f"< 1/{cfg.phase3_bootstrap_n} ha p_value = 0",
    "k_steps": list(k_steps),
    "D_coupled": D_coupled.tolist(), "D_control": D_control.tolist(),
    "D_coupled_min": {"k": k_steps[k_min], "D": float(D_coupled[k_min])},
    "D_coupled_regrowth_max": {"k": k_steps[k_re], "D": float(D_coupled[k_re])},
    "interpretation": "tankönyvi nem-markovi visszaáramlás (S–E csatolás, E nincs resetelve); nem anomália",
})

print(f"D_coupled: {[f'{v:.3f}' for v in D_coupled]}")
print(f"D_control: {[f'{v:.3f}' for v in D_control]}")
print(f"BLP csatolt = {blp_c:.4f}   BLP kontroll (mért) = {blp_ctrl:.4f}")
print_verdict("3. fázis", result)
write_json(DATA_DIR / "phase3_result.json", result)
