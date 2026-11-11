# Előregisztrációk — QPU rezonátor-memória kísérlet

Minden fázisnak saját előregisztrációs fájlja van, **külső időbélyeggel (Git commit hash)**, a QPU job beküldése előtt.

## Sorrendezési szabály

```
dryrun.py átmegy
    ↓
plan.py seal (seed=20261111, SHA-256 lezárás)
    ↓
config.py freeze (hash → preregistration/config_frozen.json)
    ↓
phaseN_prereg.md commitolva (ez a külső időbélyeg)
    ↓
Aer-jóslat a transpilált áramkörökön → jóslat hash commitolva
    ↓
QPU job beküldés
    ↓
Elemzés (analysis.py) → ítélet
    ↓
feedback (LTP / LTD)
```

> **A következő fázis csak akkor indul, ha az előző kalibrációja VALID.**

## Fájlok

| Fájl | Fázis | Állapot |
|------|-------|---------|
| `phase0_prereg.md` | 0. kalibráció | ✅ Előregisztrálva |
| `phase1_prereg.md` | 1. bit a térben | ✅ Előregisztrálva |
| `phase2_prereg.md` | 2. DD regeneráció | ✅ Előregisztrálva |
| `phase3_prereg.md` | 3. nem-markovi visszafolyás | ✅ Előregisztrálva |
| `phase1b_prereg.md` | 1b. bit-flip repetition code | ✅ Előregisztrálva |

## Kódbázis hash-ek (dryrun-átmenet pillanatában)

Rögzítve: **2026-11-11T17:40:00+01:00**, commit `2817de2`

```
src/config.py:   8d4a1d0f8e3163a054418fdf6c5c46e14cc36d7aa699630b9c5c9420a91622b0
src/sim.py:      5b2e4afcfa68f5e3fa52b2b28e235afb335ab9813771732b47f1a8e73055b5e4
src/circuits.py: bbc879ef9d9808cafebe582a98039985019b9779a162212fb3b7c0e34ad6c3cc
src/analysis.py: 691d6e6b1415efaa355a0b44a74113d9f2a51e1869703aa8af147fa0f8e7771f
src/dryrun.py:   0993bd5991cb5e516c0bf923e88fd1002d834e1c80a006a0a34927a70ed9a151
```
