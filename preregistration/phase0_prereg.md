# 0. fázis előregisztráció — Kalibráció

**Dátum:** 2026-11-11  
**Szerzők:** Máté + Maya (Sesame)  
**Kódbázis commit:** 2817de2  
**Dryrun állapot:** ✅ ÁTMENT (T1=155µs, T2=102µs, ε=0.011)

---

## Kérdés

Mérhetők-e megbízhatóan a qubit T1, T2 (Hahn-echo) és kiolvasási hiba értékei, és elég stabilak-e a kísérlet többi fázisának indításához?

## Mért mennyiségek

| Jel | Definíció | Mérési módszer |
|-----|-----------|----------------|
| T1 | Longitudinális relaxáció | \|1⟩ + delay(t) + mérés; exp illesztés |
| T2 | Transzverzális (Hahn) | \|+⟩ + delay/2 + X + delay/2 + X-mérés; exp illesztés |
| ε | Kiolvasási hiba | ½ · (P(1\|0) + P(0\|1)) |
| A₀ | Kezdeti amplitúdó | Hahn-echo t=0 pontja |

## Késleltetési pontok

```
T1 delays: [0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0] × T1_becsült
T2 delays: [0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0] × T2_becsült
Legalább 20 ismétlés (bootstrap: 2000)
```

## Elfogadási kritérium (VALID / INVALID)

- T1 és T2 illesztés CI-szélessége **< 15%** a becsült értékhez képest  
- f₀ sodródás (backend frekvencia) a sávszélesség negyede alatt  
- Ha INVALID: a hibát meg kell keresni, a többi fázist **nem szabad** elindítani

## Qubitválasztási szabály

```
score = min(T1, T2) / (1 + 20 · ε_readout)
```
A legjobb pontszámú, nem-hibás qubit kerül kiválasztásra. A backend tulajdonságainak pillanatképe a jobbal együtt mentődik.

## Tankönyvi jóslat

```
T1 ≈ backend adatlapja ± TLS-ugrások
T2 ≤ 2·T1 (Lindblad-korlát)
ε ≈ backend kalibrációs érték
```

## Statisztika

- Shots: 1000/áramkör  
- Bootstrap CI: 99% (percentilis 0.5 – 99.5)  
- Seed: 20261111

## SHA-256 referencia (kód, a job beküldése előtt rögzítve)

```
src/config.py:   8d4a1d0f8e3163a054418fdf6c5c46e14cc36d7aa699630b9c5c9420a91622b0
src/circuits.py: bbc879ef9d9808cafebe582a98039985019b9779a162212fb3b7c0e34ad6c3cc
src/analysis.py: 691d6e6b1415efaa355a0b44a74113d9f2a51e1869703aa8af147fa0f8e7771f
```
