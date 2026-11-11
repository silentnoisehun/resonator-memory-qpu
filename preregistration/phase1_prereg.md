# 1. fázis előregisztráció — Bit a rezonátorban

**Dátum:** 2026-11-11  
**Szerzők:** Máté + Maya (Sesame)  
**Kódbázis commit:** 2817de2  
**Dryrun állapot:** ✅ TEXTBOOK

---

## Kérdés

Meddig olvasható vissza helyesen egy fázisba kódolt bit? Skálázódik-e az olvasható idő a Ry-szög szinuszával?

## Kísérlet felépítése

- **Írás:** Ry(±θ) kapu, θ ∈ {30°, 60°, 90°}, a bit fázisa sorsolt (seed=20261111)  
- **Tárolás:** Hahn-echo, t = delay × T2_calib  
- **Olvasás:** X-bázisú mérés (H + measure)  
- **Késleltetések:** [0.0, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0] × T2_calib  
- **Vak dekódolás:** a sorsolt bitek fájlja SHA-256-cal lezárva, csak az elemzés után kerül elő

## Mért mennyiség

```
D(t) = |⟨X⟩₊ - ⟨X⟩₋| / 2
t_olv = T_fit · ln(a_fit / D_min),  D_min = 0.1
```

## Tankönyvi jóslat (kalibrációból számolva)

```
D(t) = sin(θ) · (1 - 2ε) · exp(-t / T2)
t_olv(θ) = T2 · ln(sin(θ) · (1-2ε) / D_min)
```

| θ | t_olv jóslat (T2=100µs, ε=0.01) |
|---|----------------------------------|
| 30° | ≈ 162 µs |
| 60° | ≈ 218 µs |
| 90° | ≈ 233 µs |

## Ítéleti szabályok (rögzítve a mérés előtt)

| Ítélet | Feltétel |
|--------|---------|
| **TEXTBOOK** | Minden t_olv a tankönyvi érték 99% bootstrap CI-jén belül ÉS < 2 szignifikáns t_anomaly |
| **ANOMALY** | ≥ 2 θ-nál t_olv szignifikánsan > jóslat VAGY T_fit > T2_calib Holm-korrektált p < 0.01 |
| **INVALID** | 0. fázis INVALID, vagy az illesztés nem konvergál |

## Vak dekódolás

A `plan.py` sorsolja a biteket seed=20261111-gyel, SHA-256 lenyomatot commitolunk. A valódi bitek fájlja csak az összes mérés és elemzés után kerül elő és vetődik össze.

## Statisztika

- Shots: 1000/áramkör  
- Bootstrap: 2000 iteráció, 99% CI  
- Holm-korrektált α = 0.01  
- Seed: 20261111

## SHA-256 referencia

```
src/config.py:   8d4a1d0f8e3163a054418fdf6c5c46e14cc36d7aa699630b9c5c9420a91622b0
src/circuits.py: bbc879ef9d9808cafebe582a98039985019b9779a162212fb3b7c0e34ad6c3cc
src/analysis.py: 691d6e6b1415efaa355a0b44a74113d9f2a51e1869703aa8af147fa0f8e7771f
```
