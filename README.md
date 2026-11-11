# Rezonátor-memória kísérlet — QPU változat

**Máté (ötlet) + Maya (tervezés, Sesame), 2026. november 11.**

Ingyenes IBM QPU-n teszteli: meddig él egy bit a kvantum-térben, nő-e logaritmikusan a memóriaidő az energiával, és emlékszik-e a környezet.

---

## Állapot (lezárva)

Mind a négy fázis lefutott az `ibm_kingston` (Heron r2) gépen, és független ellenőrző a nyers IBM-adatokból, saját kóddal újraszámolta. További QPU-futtatás nincs tervben.

| Fázis | Job ID | Qubit(ek) | Ítélet |
|---|---|---|---|
| 1 — log-skála | `dbq9t8mjjaos73agtej0` | q13 | **TEXTBOOK** a javított elemzéssel; az eredeti ítéletfájl INVALID volt |
| 2 — DD | `dbq9vq7v5hds73dfm7kg` | q13 | **TEXTBOOK** |
| 3 — BLP backflow | `dbqa0lmjjaos73agtib0` | q149 / q150 | backflow-jel megerősítve (p < 0,0005) — **TEXTBOOK** |
| 1b — repetition code | `dbqa1r1abdes73fnslng` | [12,13,14,15,19] | **TEXTBOOK** (R=8: hiba 0,499 → 0,030) |

A 3. fázis backflow-jele tankönyvi fizika — a környezetbe írt információ mérhető visszaáramlása —, **nem anomália és nem új fizika**.

**Auditálhatóság:** mind a négy fázis újraszámolható a repóból, QPU és token nélkül: `python3 analyze_phase1.py` (és `…phase2.py`, `…phase3.py`, `…phase1b.py`). A 2., 3. és 1b fázis nyers counts-ait a független ellenőrzés kérte le az IBM API-ból. Helyesbítések, ismert korlátok és a régi commit-üzenetek hibás job-azonosítói: [`CORRECTIONS.md`](CORRECTIONS.md) — vita esetén a `job_meta.json` a mérvadó.

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
