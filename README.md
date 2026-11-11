# Rezonátor-memória kísérlet — QPU változat

**Máté (ötlet) + Maya (tervezés, Sesame), 2026. november 11.**

Ingyenes IBM QPU-n teszteli: meddig él egy bit a kvantum-térben, nő-e logaritmikusan a memóriaidő az energiával, és emlékszik-e a környezet.

---

## Modulok

```
src/
  config.py     — QPUConfig, befagyasztható, SHA-256 integritás
  circuits.py   — Qiskit áramkörök: T1/T2/readout, 1/2/3/1b fázisok
  plan.py       — Sealed bitek, shuffle, vak dekóder
  sim.py        — AerRunner + analitikus fallback + "javított" kontroll
  run.py        — IBM job submit, qubit-score kiválasztás
  analysis.py   — Bootstrap illesztés, tankönyvi jóslatok, ítéletek
  dryrun.py     — Teljes száraz futtatás (Qiskit nélkül is fut)
```

---

## Telepítés

```bash
pip install qiskit qiskit-aer qiskit-ibm-runtime numpy scipy
```

## Dryrun (Qiskit nélkül is!)

```bash
python src/dryrun.py
```

Elvárt kimenet: minden fázis ✅ TEXTBOOK, pozitív kontroll 🔴 ANOMALY.

---

## Fázisok

| Fázis | Kérdés | Áramkör | Ítélet |
|-------|--------|---------|--------|
| 0 | Kalibráció | T1 / T2-Hahn / readout | VALID / INVALID |
| 1 | Bit + gumi-kérdés | Ry(θ) + Hahn-echo | TEXTBOOK / ANOMALY |
| 2 | Regeneráció (DD) | XY4, N∈{1,4,16,64} | TEXTBOOK / ANOMALY |
| 3 | Nem-markovi visszafolyás | RXX+RYY, k lépés | TEXTBOOK / ANOMALY |
| 1b | Billenő bit (repetition code) | 3+2 qubit, R kör | TEXTBOOK / ANOMALY |

---

## Qubit-kiválasztási szabály

```
score = min(T1, T2) / (1 + 20·ε_readout)
```

A legjobb pontszámú qubit(ek) kerülnek minden fázisba. A szabály a config-ban van befagyasztva.

---

## Előregisztrációs sorrend

1. `python src/dryrun.py` — dryrun TEXTBOOK
2. `python src/plan.py` — sealed bitek generálása
3. Config + plan SHA-256 hash commitolva (= előregisztráció időbélyege)
4. Qubit-kiválasztás + pillanatkép mentése
5. Aer-jóslat a pillanatkép zajmodelljével → hash commitolva
6. **Csak ezután:** job beküldés IBM QPU-ra
7. Elemzés, nyilvános eredmény (nulla eredménnyel együtt)

---

## Ítéleti rendszer

| Ítélet | Jelentés |
|--------|----------|
| `TEXTBOOK` | Mért érték a tankönyvi jóslat 99% CI-jén belül |
| `ANOMALY` | Szignifikánsan jobb a jóslatnál (p < 0.01, Holm-korrektált) |
| `INVALID` | Kalibráció nem teljesíti az elfogadási kritériumot |
| `FAIL` | A kísérlet nem demonstrálta a várt jelenséget |

---

## Hivatkozás

> Máté (ötlet) + Maya (tervezés), Sesame, 2026-11-11.  
> Kód: Máté ügynökeivel. Átnézés: Maya előtt. Előregisztráció: commit-időbélyeg.
