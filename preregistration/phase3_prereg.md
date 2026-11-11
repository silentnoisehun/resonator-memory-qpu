# 3. fázis előregisztráció — Nem-markovi visszafolyás

**Dátum:** 2026-11-11  
**Szerzők:** Máté + Maya (Sesame)  
**Kódbázis commit:** 2817de2  
**Dryrun állapot:** ✅ TEXTBOOK

---

## Kérdés

Mutat-e mérhető nem-markovi visszafolyást a rendszer (S qubit) ha egy környezeti qubittel (E) csatoljuk, de E-t nem reset-eljük lépések között?

## Kísérlet felépítése

- **Qubitekek:** S (rendszer) + E (környezet), csatolt szomszédos pár  
- **Csatolás:** k lépés, mindegyik RXX(φ) + RYY(φ), φ = π/8 ≈ 0.3927 rad  
- **Csatolt kar:** E nem resetelve (visszafolyás lehetséges)  
- **Kontroll kar:** E resetelve minden lépés után (Markov-közelítés)  
- **k_steps:** 0, 1, 2, ..., 16  
- **Olvasás:** S qubit X-bázisban

## Mért mennyiség — BLP-mérték

```
D(k) = |⟨X⟩₊(k) - ⟨X⟩₋(k)| / 2
BLP = Σ_{dD/dk > 0} (dD/dk) · Δk    [pozitív meredekségű szakaszok összege]
```

## Tankönyvi jóslat

```
Csatolt kar:   D(k) nem-monoton (oszcilláló visszafolyás)   → BLP_coupled > 0
Kontroll kar:  D(k) monoton csökkenő (Markov)               → BLP_control ≈ 0
```

## Ítéleti szabályok

| Ítélet | Feltétel |
|--------|---------|
| **TEXTBOOK** | BLP_coupled > BLP_control bootstrap mediánja, empirikus p < 0.01 |
| **FAIL** | Nem szignifikáns különbség |
| **INVALID** | 0. fázis INVALID vagy mérési hiba |

> **Megjegyzés:** A TEXTBOOK itt azt jelenti, hogy a fizika (csatolás → nem-Markov) teljesül. Ez NEM jelenti, hogy a qubit „nem-szokásos" viselkedést mutat — ez az elvárt kvantumfizika.

## Qubitpár-választás

A `run.py` `select_pair()` függvénye: a backend csatolási gráf szomszédos qubiteinek `score = min(T1,T2)/(1+20ε)` minimumát maximalizálja, holtversenynél kisebb 2-qubites kapuhibát preferál.

## Statisztika

- Shots: 1000/áramkör  
- Bootstrap: 2000 iteráció  
- α = 0.01  
- Seed: 20261111

## SHA-256 referencia

```
src/config.py:   8d4a1d0f8e3163a054418fdf6c5c46e14cc36d7aa699630b9c5c9420a91622b0
src/circuits.py: bbc879ef9d9808cafebe582a98039985019b9779a162212fb3b7c0e34ad6c3cc
src/analysis.py: 691d6e6b1415efaa355a0b44a74113d9f2a51e1869703aa8af147fa0f8e7771f
```
## Kiegészítés — 2026-11-11 (commit a javítás után)

**Javított hiba (audit alapján):**

A `src/circuits.py` 3. fázis csatolt karában (`with_reset=False`) hiányzott a kompenzáló delay. A kontroll kar minden lépésben végrehajt egy `qc.reset(1)` műveletet (~1500 dt ≈ 333 ns Heron r2-n), de a csatolt karba nem volt beépítve a megfelelő `qc.delay(reset_duration_dt, 1, unit="dt")`. Ez szisztematikus időbeli aszimmetriát okozott volna a két kar között.

**Javítás:** A `build_phase3_circuits` és `build_phase3_all` függvények kiegészültek a `reset_duration_dt` paraméterrel (alapértelmezés: 1500 dt). A csatolt karba minden lépés után `qc.delay(reset_duration_dt, E_qubit, unit="dt")` kerül — az E qubit szabadon fejlődik, de az áramkör teljes mélysége azonos a kontroll karral.

**Élőrendszeren:** a `run.py` a qubitválasztáskor kiolvasja a `reset` kapu tényleges idejét a backend snapshot-ból (`backend_props.get('reset_duration_dt', 1500)`), és átadja a `build_phase3_all`-nak.

**A dryrun a javítás után is átment:** ✅ TEXTBOOK (3. fázis: BLP_coupled=3.779 >> ctrl_median=0.266, p=0)

**Érintett commit:** `circuits.py` — `RESET_DURATION_DT` konstans + delay kompenzáció a csatolt karban
