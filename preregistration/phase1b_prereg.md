# 1b fázis előregisztráció — Bit-flip repetition code

**Dátum:** 2026-11-11  
**Szerzők:** Máté + Maya (Sesame)  
**Kódbázis commit:** 2817de2  
**Dryrun állapot:** ✅ TEXTBOOK (err_active < err_single R=8-nál, p=1.5e-106)

---

## Kérdés

Csökkenti-e az aktív hibajavítás (3-qubites bit-flip repetition code) a hibaarányt a passzív többségi szavazáshoz és az egyetlen qubithez képest?

## Kísérlet felépítése

- **Adatqubitekek:** 3 db szomszédos lánc  
- **Segédqubitekek:** 2 db (paritásméréshez)  
- **Bit:** |000⟩ vagy |111⟩, sorsolt seed=20261111  
- **Körök R:** {0, 1, 2, 4, 8}, minden kör ≈ 20 µs  

### Három kar

| Kar | Leírás |
|-----|--------|
| `single` | Egyetlen qubit, R × 20µs delay, végső mérés |
| `majority_only` | 3 qubit, R × 20µs delay/qubit, többségi szavazás (nincs korrekció) |
| `active_correction` | 3 qubit + 2 ancilla, R körönként paritásmérés + feltételes korrekció |

## Tankönyvi jóslat

```
p_single(R) = 1 - exp(-R · 20µs / T1)

majority_only: P_L ≈ 3·p² - 2·p³   (binomiális, 2+ hiba kell)
active:        P_L ≈ 1 - (1 - 3·p_round²)^R   (per-kör korrekció)
```

| R | p_single (T1=150µs) | P_L majority | P_L active |
|---|---------------------|--------------|------------|
| 0 | 0 | 0 | 0 |
| 1 | 0.125 | 0.039 | 0.047 |
| 2 | 0.236 | 0.144 | 0.085 |
| 4 | 0.406 | 0.418 | 0.147 |
| 8 | 0.585 | 0.701 | 0.242 |

## Ítéleti szabályok

| Ítélet | Feltétel |
|--------|---------|
| **TEXTBOOK** | R=max-nál err_active < err_single, egyoldali binomtest p < 0.01 |
| **FAIL** | Nem szignifikáns különbség |
| **INVALID** | 0. fázis INVALID, vagy az if_else dinamikus kapu nem támogatott a backenden |

## Qubitlánc-választás

`run.py` `select_chain(length=5)`: a csatolási gráf 5-hosszú lineáris lánca, amelynek leggyengébb qubite a legjobb pontszámú; holtversenynél kisebb 2-qubites kapuhiba.

## Statisztika

- Shots: 2000/áramkör (`shots_1b`)  
- α = 0.01 (egyoldali binomtest)  
- Seed: 20261111

## SHA-256 referencia

```
src/config.py:   8d4a1d0f8e3163a054418fdf6c5c46e14cc36d7aa699630b9c5c9420a91622b0
src/circuits.py: bbc879ef9d9808cafebe582a98039985019b9779a162212fb3b7c0e34ad6c3cc
src/analysis.py: 691d6e6b1415efaa355a0b44a74113d9f2a51e1869703aa8af147fa0f8e7771f
```
