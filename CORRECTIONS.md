# CORRECTIONS — helyesbítések és ismert ellentmondások

A git-történetet nem írjuk át. Ez a fájl sorolja fel, hol tér el egy korábbi
commit-üzenet, komment vagy eredményfájl a valóságtól.

**Szabály: vita esetén mindig a `data/<fázis>/job_meta.json` a mérvadó**
(job-azonosító, backend, qubitek), a számokra pedig a `raw_counts.json`.
Commit-üzenet, README vagy kódkomment ezeket nem írja felül.

## 1. Job-azonosítók és qubitek

| Fázis | Commit | A commit-üzenetben | Valódi (`job_meta.json`) | Egyezik? |
|---|---|---|---|---|
| 1 | `52eef8b` | job `dbq9t8mjjaos73agtej0`, q13 | job `dbq9t8mjjaos73agtej0`, q13 | igen |
| 2 | `54317fb` | job `cxh5qrqr0k3g0082m660`, q13 | job `dbq9vq7v5hds73dfm7kg`, q13 | **job ID nem** |
| 3 | `d4a6602` | job `cxh5r9mr0k3g0082m690`, q12–q13 | job `dbqa0lmjjaos73agtib0`, S = q149, E = q150 | **job ID és qubitpár sem** |
| 1b | `1e54cf8` | job `cxh5s3cr0k3g0082m6b0`, lánc [12,13,14,15,19] | job `dbqa1r1abdes73fnslng`, lánc [12,13,14,15,19] | **job ID nem** |

Mindegyik job backendje `ibm_kingston`. A `cxh5…` azonosítók egyik
`job_meta.json`-ban sem szerepelnek.

## 2. Commit-üzenetekben szereplő ítéletek és p-értékek

| Commit | Állítás | Helyesbítés |
|---|---|---|
| `52eef8b`, `8d34929` | 1. fázis: TEXTBOOK; kalib VALID | Az akkori ítéletfájl **INVALID** volt (elszállt kalib-fit: T1 = 1,65e11 µs, ε = 0, nulla szélességű CI; a jóslat a pillanatkép T2 = 664,8 µs-ával számolt; az `in_band` tautológia volt). Javított elemzés: `e39606d` — ugyanazokból a nyers adatokból TEXTBOOK. |
| `d4a6602` | 3. fázis: p = 0,0045 | A független ellenőrzés szerint p < 0,0005 (csatolt BLP = 0,4190, reset-kontroll BLP = 0,0000). A repóból jelenleg nem ellenőrizhető (ld. 4. pont). |
| `1e54cf8` | 1b: p = 1,17e-71 | A repóból jelenleg nem ellenőrizhető (ld. 4. pont). |

## 3. 1. fázis — a javított elemzés számai és eltérései

`python3 analyze_phase1.py` (offline; csak numpy + scipy kell) a
`data/phase1/raw_counts.json`-ból:

- kalib a job saját karjaiból: T1 = 344,2 µs (99% CI 326,8–362,1; χ²_red = 5,4),
  T2_Hahn = 361,6 µs (CI 314,6–415,3), ε = 0,0185 → VALID
- mért t_olv = 565,2 / 788,9 / 814,3 µs; jóslat = 568,3 / 766,9 / 819,0 µs
  (θ = 30° / 60° / 90°); mind a 99% CI-n belül → **TEXTBOOK**

Eltérések a független ellenőrző által közölt számoktól (nem igazítottuk hozzá):

- **T1:** az ellenőrző ≈ 370 µs-t közölt, ez az illesztő 344 µs-t ad. A T1-kar
  nem tisztán exponenciális (χ²_red = 5,4); a becslő megválasztásától függően
  294–381 µs jön ki ugyanabból a 8 pontból. A T1 nem lép be az 1. fázis ítéletébe.
- **Jóslat:** az ellenőrző ≈ 568 / 769 / 822 µs-t közölt; itt 60°-nál és 90°-nál
  2–3 µs-mal kisebb (T2 = 361,6 µs és ε = 0,0185 mellett).
- `t_anomaly[60°] = true`: T_fit (371 µs) > T2_calib (362 µs). Ez puszta
  pontösszehasonlítás, nem a preregisztrációban leírt Holm-korrigált teszt;
  a szabályt nem módosítottuk, egyetlen jelzés nem változtat az ítéleten.
- Az `src/analysis.py` SHA-256-ja a javítás óta nem egyezik a
  `preregistration/` fájlokban rögzítettel. A javítás utólagos (post-hoc).
  (Az `src/circuits.py` SHA-ja már a `b3d6c00` audit-javítás óta eltér.)

## 4. Hiányzó nyers adatok (2., 3., 1b fázis) — NYITOTT

A `.gitignore` korábban a teljes `data/` mappát kizárta. Az 1. fázis fájljai
kényszerítve fel lettek véve, a többi fázisból viszont csak a `job_meta.json`,
`plan_sealed.json` és `snapshot.json` került fel. **Hiányzik:**

- `data/phase2/`: `raw_counts.json`, `calib_result.json`, `phase2_result.json`
- `data/phase3/`: `raw_counts.json`, `phase3_result.json`
- `data/phase1b/`: `raw_counts.json`, `phase1b_result.json`

A `.gitignore` kivétele megszűnt, de a fájlok csak azon a gépen léteznek, ahol
a jobok futottak — onnan kell feltölteni őket (`git add data/ && git commit`).
Amíg ez nem történik meg, a 2., 3. és 1b fázis ítélete **a repóból nem
auditálható**; a README-ben szereplő ítéletek a független ellenőrzőtől származnak.

## 5. 3. fázis — reset-időtartam

- A `data/phase3/snapshot.json` `"reset_duration_dt": 1500` mezője a kódbeli
  alapérték, **nem** a backendről kiolvasott adat. A tényleges reset-időtartam
  a lefutott jobhoz nincs rögzítve.
- A kódkomment és a preregisztráció kiegészítése „1500 dt ≈ 333 ns"-t ír; ez
  0,222 ns-os dt-t feltételez. A pillanatkép szerint dt = 4 ns, így a csatolt
  kar kompenzáló késleltetése lépésenként **6,0 µs** volt. Hogy ez mennyire
  egyezik a kontroll kar reset-idejével, a repó adataiból nem állapítható meg.
- A preregisztráció kiegészítése szerint a `run.py` olvassa ki a reset idejét;
  a lefutott jobnál ez nem így történt. A `7076d8d` commit óta a
  `submit_phase3.py` a backend Targetből olvas, tartalékként az alapértékkel.

## 6. Egyéb

- **1b regiszterválasztás:** a counts-kinyerés korábban „az utolsó regisztert"
  vette; `f4f1892` óta név szerint az `out`-ot, hiányzó regiszternél hibával áll meg.
- **Beégetett API-token:** a `52eef8b`…`1e54cf8` commitok scriptjeiben nyílt
  szövegű IBM Quantum token van. A munkafából eltávolítva (`8ef0e10`), de a
  történetben látszik — **a tokent vissza kell vonni az IBM-nél.**
- `src/config.py` alapértelmezett `backend_name`-je `ibm_sherbrooke`; minden
  job ténylegesen az `ibm_kingston`-on futott (ld. `job_meta.json`).
