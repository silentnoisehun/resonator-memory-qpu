# CORRECTIONS — helyesbítések és ismert ellentmondások

A git-történetet nem írjuk át (egyetlen, dokumentált kivétel: 7. pont). Ez a fájl sorolja fel, hol tér el egy korábbi
commit-üzenet, komment vagy eredményfájl a valóságtól.

**Szabály: vita esetén mindig a `data/<fázis>/job_meta.json` a mérvadó**
(job-azonosító, backend, qubitek), a számokra pedig a `raw_counts.json`.
Commit-üzenet, README vagy kódkomment ezeket nem írja felül.

## 1. Job-azonosítók és qubitek

| Fázis | Commit | A commit-üzenetben | Valódi (`job_meta.json`) | Egyezik? |
|---|---|---|---|---|
| 1 | `ea0fa8d` | job `dbq9t8mjjaos73agtej0`, q13 | job `dbq9t8mjjaos73agtej0`, q13 | igen |
| 2 | `2eb6a43` | job `cxh5qrqr0k3g0082m660`, q13 | job `dbq9vq7v5hds73dfm7kg`, q13 | **job ID nem** |
| 3 | `9c1cf74` | job `cxh5r9mr0k3g0082m690`, q12–q13 | job `dbqa0lmjjaos73agtib0`, S = q149, E = q150 | **job ID és qubitpár sem** |
| 1b | `39d44fe` | job `cxh5s3cr0k3g0082m6b0`, lánc [12,13,14,15,19] | job `dbqa1r1abdes73fnslng`, lánc [12,13,14,15,19] | **job ID nem** |

Mindegyik job backendje `ibm_kingston`. A `cxh5…` azonosítók egyik
`job_meta.json`-ban sem szerepelnek.

## 2. Commit-üzenetekben szereplő ítéletek és p-értékek

| Commit | Állítás | Helyesbítés |
|---|---|---|
| `ea0fa8d`, `7288337` | 1. fázis: TEXTBOOK; kalib VALID | Az akkori ítéletfájl **INVALID** volt (elszállt kalib-fit: T1 = 1,65e11 µs, ε = 0, nulla szélességű CI; a jóslat a pillanatkép T2 = 664,8 µs-ával számolt; az `in_band` tautológia volt). Javított elemzés: `5a8f0ec` — ugyanazokból a nyers adatokból TEXTBOOK. |
| `9c1cf74` | 3. fázis: p = 0,0045 | A nyers adatokból: 2000 bootstrap-mintából 0 éri el a csatolt BLP-t, azaz p < 0,0005 (ld. 4. pont). |
| `39d44fe` | 1b: p = 1,17e-71 | Nem reprodukálható; a p-érték a gépi pontosság alatt van (ld. 4. pont). Az ítélet (TEXTBOOK) egyezik. |

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

## 4. Nyers adatok a 2., 3. és 1b fázishoz — PÓTOLVA

A `.gitignore` korábban a teljes `data/` mappát kizárta, ezért a 2., 3. és 1b
fázis `raw_counts.json` és eredményfájljai sosem kerültek fel. A kizárás megszűnt.

- A `raw_counts.json` fájlok **nem az eredeti futtató gépről** származnak: a
  független ellenőrzés kérte le őket közvetlenül az IBM Quantum API-ból, és a
  `job_meta.json` `shuffle_order`-je alapján állította vissza az eredeti
  sorrendet (ld. a fájlok `source` mezőjét). Az eredeti gépen mentett példányok
  nincsenek a repóban, így a kettő egyezése innen nem ellenőrizhető.
- Integritás: mindhárom fájl `job_id`-ja egyezik a `job_meta.json`-nal, az
  áramkörnevek listájának SHA-256-ja egyezik a beküldés előtt rögzített
  `pre_shuffle_hash`-sel, és minden áramkör shot-összege stimmel
  (`src/rawdata.py` ezt minden elemzés előtt ellenőrzi).
- Az eredményfájlok (`calib_result.json`, `phase*_result.json`) ezekből
  készültek az offline elemzőkkel: `python3 analyze_phase2.py`,
  `analyze_phase3.py`, `analyze_phase1b.py` (QPU és token nélkül futnak).

Újraszámolt számok és eltérések az ellenőrző által közöltektől:

| Fázis | Mennyiség | Ellenőrző | Repo-elemző | Megjegyzés |
|---|---|---|---|---|
| 2 | T1 | 382 µs (CI 367–399) | 381,7 µs (CI 362,3–402,1) | A repo CI-je 99%-os (preregisztrált); 95%-on 366–397 jön ki, az ellenőrzőé ennek felel meg |
| 2 | T2_Hahn, ε | 382 µs; 0,0190 | 381,9 µs; 0,0190 | egyezik |
| 2 | T2_N (N=1/4/16/64) | 381/231/303/409 µs | 381,3/230,8/303,1/409,3 µs | egyezik |
| 2 | anomália-küszöb (2·T1_CI_felső) | 798 µs | 804 µs | a CI-szint különbségéből adódik; egyik T2_N sem közelíti meg |
| 3 | BLP csatolt / kontroll | 0,4190 / 0,0000 | 0,4190 / 0,0000 | egyezik; D-min 0,051 @k=7, újranövés 0,388 @k=14 |
| 3 | p | < 0,0005 | 0/2000 bootstrap | egyezik |
| 1b | bit=1, R=8: single/majority/active | 0,499/0,425/0,030 | 0,4990/0,4255/0,0305 | egyezik |
| 1b | bit=0, aktív kar | ≤ 0,005 | max 0,0055 (R=2: 11/2000) | **fél ezrelékkel túllépi** |

Ítéletek ezekből: 2. fázis TEXTBOOK, 3. fázis TEXTBOOK (visszaáramlás
megerősítve), 1b TEXTBOOK.

Korlátok, amelyeket az ítélet nem tükröz (nem szépítve):

- **2. fázis, N=4:** az előjeles kontraszt negatívba megy (−0,346), χ²_red = 18,8.
  Ez koherens forgás, nem exponenciális lecsengés; a 231 µs itt nem
  értelmezhető koherenciaidőként. Az ítéletet nem érinti (a szabály csak azt
  nézi, hogy T2_N nem haladja-e meg szignifikánsan a 2·T1-et).
- **1b:** a single és majority kar körönként 20 µs várakozást tartalmaz, az
  aktív kar köreiben nincs ilyen késleltetés. A karok teljes időtartama ezért
  nem azonos; a „0,499 → 0,030" nem azonos tárolási időre vonatkozó
  összehasonlítás. A preregisztrált teszt (R=max, aktív < single) így is teljesül.
- **1b p-érték:** a binomiális teszt p-értéke a lebegőpontos pontosság alatt van
  (0,0-ként jön ki); a `39d44fe` üzenetében szereplő 1,17e-71 nem reprodukálható.

## 5. 3. fázis — reset-időtartam

- A `data/phase3/snapshot.json` `"reset_duration_dt": 1500` mezője a kódbeli
  alapérték, **nem** a backendről kiolvasott adat. A tényleges reset-időtartam
  a lefutott jobhoz nincs rögzítve.
- A kódkomment és a preregisztráció kiegészítése „1500 dt ≈ 333 ns"-t ír; ez
  0,222 ns-os dt-t feltételez. A pillanatkép szerint dt = 4 ns, így a csatolt
  kar kompenzáló késleltetése lépésenként **6,0 µs** volt. Hogy ez mennyire
  egyezik a kontroll kar reset-idejével, a repó adataiból nem állapítható meg.
- A preregisztráció kiegészítése szerint a `run.py` olvassa ki a reset idejét;
  a lefutott jobnál ez nem így történt. A `03ec163` commit óta a
  `submit_phase3.py` a backend Targetből olvas, tartalékként az alapértékkel.

## 6. Egyéb

- **1b regiszterválasztás:** a counts-kinyerés korábban „az utolsó regisztert"
  vette; `2d0bdfd` óta név szerint az `out`-ot, hiányzó regiszternél hibával áll meg.
- **Beégetett API-token:** ld. a 7. pontot.
- `src/config.py` alapértelmezett `backend_name`-je `ibm_sherbrooke`; minden
  job ténylegesen az `ibm_kingston`-on futott (ld. `job_meta.json`).

## 7. Történet-átírás (token-eltávolítás), 2026-11-11

A `submit_phase*.py` és a `fetch_results.py` korábbi változataiban nyílt
szövegű IBM Quantum API-token szerepelt. A git-történetet ezért **egyszer,
kizárólag emiatt** átírtuk: `git filter-repo --replace-text` a token pontos
karaktersorozatát minden commitban `***REMOVED***`-ra cserélte.

- Más nem változott: fájlstruktúra, szerzők, dátumok, a commit-üzenetek
  tárgysorai és a kísérleti adatok azonosak; az ágak csúcsán a fájlfa
  bájtra megegyezik az átírás előttivel.
- Egyetlen mellékhatás az üzenetekben: a `git filter-repo` két commit-üzenetben
  a régi commit-hash hivatkozásokat az újakra írta át.
- Az első érintett committól kezdve **minden commit-hash megváltozott**; az
  előtte lévő négy commit (`208f557`, `2817de2`, `30ad905`, `b3d6c00`) változatlan.
  Ebben a fájlban minden hivatkozás már az új hash-ekre mutat.
- A munkafa scriptjei a tokent az `IBM_QUANTUM_TOKEN` környezeti változóból
  olvassák (`375e572`); ez nem változott.
- A fejléc „a git-történetet nem írjuk át" elve minden másra továbbra is
  érvényes: ez az egy kivétel biztonsági okból történt, és itt dokumentált.

| Régi hash | Új hash |
|---|---|
| `52eef8b` | `ea0fa8d` |
| `8d34929` | `7288337` |
| `54317fb` | `2eb6a43` |
| `d4a6602` | `9c1cf74` |
| `1e54cf8` | `39d44fe` |
| `e39606d` | `5a8f0ec` |
| `f4f1892` | `2d0bdfd` |
| `7076d8d` | `03ec163` |
| `8ef0e10` | `375e572` |
| `a6304c7` | `b5bfc67` |
| `1a4c8f6` | `9a4e53a` |
| `1e220c2` | `59e0b56` |
| `9b8491a` | `c17a804` |
| `da126af` | `910f607` |
| `1c8f5fa` | `e105042` |
| `bc91bc2` | `45d3a4d` |

**A történet-átírás nem helyettesíti a token visszavonását.** A régi commitok
a GitHubon hash alapján (és az 1. számú pull request hivatkozásán keresztül)
továbbra is elérhetők lehetnek, és bármely korábbi klónban megvannak. A tokent
kiszivárgottnak kell tekinteni, és az IBM-nél vissza kell vonni.
