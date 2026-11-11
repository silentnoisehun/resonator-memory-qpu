"""
rawdata.py — nyers counts betöltése és integritás-ellenőrzése offline elemzéshez.

Nem csatlakozik az IBM-hez, tokent nem igényel. Csak a data/<fázis>/ alatti,
már kimért adatokat olvassa. Bármilyen eltérésnél megáll (nem találgat).
"""
import json, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_raw(phase_dir: str):
    """
    Visszaad: (counts_by_name: dict, meta: dict, data_dir: Path)

    Ellenőrzi:
      - raw_counts.job_id == job_meta.job_id   (a job_meta.json a mérvadó)
      - az áramkörnevek listájának SHA-256-ja == job_meta.pre_shuffle_hash
        (azaz a nevek és a sorrendjük megegyezik a beküldés előtt rögzítettel)
      - áramkörszám == job_meta.n_circuits, nincs duplikált név
      - minden áramkör shot-összege == job_meta.shots
    """
    d    = ROOT / "data" / phase_dir
    raw  = json.loads((d / "raw_counts.json").read_text())
    meta = json.loads((d / "job_meta.json").read_text())
    names, counts = raw["circuits"], raw["counts"]

    if raw["job_id"] != meta["job_id"]:
        raise SystemExit(f"HIBA [{phase_dir}]: raw_counts job_id {raw['job_id']} "
                         f"!= job_meta job_id {meta['job_id']}")
    h = hashlib.sha256(json.dumps(names).encode()).hexdigest()
    if h != meta["pre_shuffle_hash"]:
        raise SystemExit(f"HIBA [{phase_dir}]: az áramkörnevek hash-e nem egyezik "
                         f"a job_meta pre_shuffle_hash-ével")
    if len(names) != meta["n_circuits"] or len(counts) != len(names):
        raise SystemExit(f"HIBA [{phase_dir}]: áramkörszám {len(names)}/{len(counts)} "
                         f"!= {meta['n_circuits']}")
    if len(set(names)) != len(names):
        raise SystemExit(f"HIBA [{phase_dir}]: duplikált áramkörnév")
    for n, c in zip(names, counts):
        if sum(c.values()) != meta["shots"]:
            raise SystemExit(f"HIBA [{phase_dir}]: '{n}' shot-összeg "
                             f"{sum(c.values())} != {meta['shots']}")
    return dict(zip(names, counts)), meta, d


def need(counts_by_name: dict, name: str) -> dict:
    """Egy áramkör counts-a név szerint; ha hiányzik, hiba (nincs tartalék)."""
    if name not in counts_by_name:
        raise SystemExit(f"HIBA: hiányzó áramkör a raw_counts.json-ban: '{name}'")
    return counts_by_name[name]


def write_json(path: Path, obj: dict):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
