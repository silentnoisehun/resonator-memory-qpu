# 2. fázis előregisztráció — DD regeneráció

**Dátum:** 2026-11-11  
**Szerzők:** Máté + Maya (Sesame)  
**Kódbázis commit:** 2817de2  
**Dryrun állapot:** ✅ TEXTBOOK

---

## Kérdés

Meghosszabbítja-e az XY4 dinamikus csatolásmentesítés (DD) a T2 időt? Skálázódik-e N-nel?

## Kísérlet felépítése

- **Inicializáció:** Ry(±π/2) → |±⟩  
- **DD sorozat:** XY4, N ∈ {1, 4, 16, 64} pulzus  
- **Késleltetések:** [0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5] × T1_calib  
- **Olvasás:** X-bázis

## Tankönyvi jóslat

```
T2_N ≈ T2 · N^(2/3)   (empirikus DD skálázás)
Fizikai korlát: T2_N ≤ 2·T1
```

| N | T2_N jóslat (T2=100µs, T1=150µs) |
|---|-----------------------------------|
| 1 | 100 µs |
| 4 | 252 µs → ≤ 300µs (korlátoz) |
| 16 | 635 µs → ≤ 300µs (korlátoz) |
| 64 | 1600 µs → ≤ 300µs (korlátoz) |

## Ítéleti szabályok

| Ítélet | Feltétel |
|--------|---------|
| **TEXTBOOK** | Minden T2_N ≤ 2·T1 (CI-en belül), anomaly_flags=False |
| **ANOMALY** | Bármely N-nél T2_N_ci_low > 2·T1_ci_high (fizikailag lehetetlen tartomány) |
| **INVALID** | 0. fázis INVALID vagy illesztés nem konvergál |

## Pozitív kontroll (szimuláción)

MOCK_BACKEND_PROPS_IMPROVED (T2=400µs > 2·T1=300µs) esetén az elemzésnek ANOMALY-t kell adnia. Ez a dryrun-ban ✅ teljesül.

## Statisztika

- Shots: 1000/áramkör  
- Bootstrap: 2000 iteráció, 99% CI  
- Seed: 20261111

## SHA-256 referencia

```
src/config.py:   8d4a1d0f8e3163a054418fdf6c5c46e14cc36d7aa699630b9c5c9420a91622b0
src/circuits.py: bbc879ef9d9808cafebe582a98039985019b9779a162212fb3b7c0e34ad6c3cc
src/analysis.py: 691d6e6b1415efaa355a0b44a74113d9f2a51e1869703aa8af147fa0f8e7771f
```
