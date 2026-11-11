"""
analyze_phase1b.py — 1b fázis (bit-flip repetition code) offline elemzése.

Nem csatlakozik az IBM-hez, jobot nem indít.
Bemenet:  data/phase1b/raw_counts_all_registers.json  (regiszterenkénti counts)
          data/phase1b/raw_counts.json                (keresztellenőrzéshez)
          data/phase1b/job_meta.json
Kimenet:  data/phase1b/phase1b_result.json

Regiszterválasztás — NÉV SZERINT, találgatás nélkül:
  aktív kar (p1b_active_*)       → `out`  (a végső adatbitek; `anc` a szindróma)
  single / majority kar          → `c`    (egyetlen regiszter)
Ha a várt regiszter hiányzik, az elemzés hibával megáll.
"""
import sys, json
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import DEFAULT_CONFIG as cfg
from rawdata import load_raw, need, write_json
from analysis import judge_phase1b, print_verdict

C_flat, meta, DATA_DIR = load_raw("phase1b")
SHOTS = meta["shots"]

allreg = json.loads((DATA_DIR / "raw_counts_all_registers.json").read_text())
if allreg["job_id"] != meta["job_id"]:
    sys.exit("HIBA: raw_counts_all_registers.json job_id != job_meta job_id")
REGS = dict(zip(allreg["circuits"], allreg["registers_per_circuit"]))
if list(REGS) != list(C_flat):
    sys.exit("HIBA: a két raw fájl áramkörlistája eltér")


def register_counts(name: str) -> dict:
    """A megnevezett áramkör elemzendő regisztere, név szerint."""
    regs = need(REGS, name)
    want = "out" if name.startswith("p1b_active_") else "c"
    if want not in regs:
        sys.exit(f"HIBA: '{name}': a(z) '{want}' regiszter hiányzik "
                 f"(elérhető: {sorted(regs)}). Nem választunk másikat.")
    c = regs[want]
    if sum(c.values()) != SHOTS:
        sys.exit(f"HIBA: '{name}'/{want} shot-összeg {sum(c.values())} != {SHOTS}")
    if c != C_flat[name]:
        sys.exit(f"HIBA: '{name}': a(z) '{want}' regiszter eltér a raw_counts.json-tól")
    return c


def err_single(c: dict, bit: int) -> float:
    # A `c` regiszter 0. bitje (a bitstring jobb széle) az egyetlen mért adatqubit.
    wrong = sum(n for s, n in c.items() if int(s[-1]) != bit)
    return wrong / SHOTS


def err_majority(c: dict, bit: int) -> float:
    wrong = sum(n for s, n in c.items() if (1 if s.count("1") >= 2 else 0) != bit)
    return wrong / SHOTS


R_list = cfg.phase1b_R_rounds
table = {}
for bit in (0, 1):
    table[f"bit{bit}"] = {
        "single":   [err_single(register_counts(f"p1b_single_b{bit}_R{R}"), bit) for R in R_list],
        "majority": [err_majority(register_counts(f"p1b_majority_b{bit}_R{R}"), bit) for R in R_list],
        "active":   [err_majority(register_counts(f"p1b_active_b{bit}_R{R}"), bit) for R in R_list],
    }
    print(f"bit={bit}  R={R_list}")
    for arm in ("single", "majority", "active"):
        print(f"   {arm:9s}: {[f'{v:.4f}' for v in table[f'bit{bit}'][arm]]}")

# Preregisztrált teszt: bit=1 ág, R=max, aktív vs. single (egyoldali binomiális)
result = judge_phase1b(table["bit1"]["active"], table["bit1"]["single"],
                       R_list, SHOTS, cfg.phase1b_alpha)
result["significant"] = bool(result["significant"])
result.update({
    "job_id": meta["job_id"], "chain": meta["chain"],
    "register_used": {"active": "out", "single": "c", "majority": "c"},
    "tested_branch": "bit=1",
    "error_rates": table,
    "caveat": ("A single és majority kar körönként 20 µs várakozást tartalmaz; az aktív "
               "kar köreiben nincs ilyen késleltetés (csak CX + mérés + reset + feltételes X), "
               "így a karok teljes időtartama nem azonos."),
})
print_verdict("1b fázis", result)
write_json(DATA_DIR / "phase1b_result.json", result)
