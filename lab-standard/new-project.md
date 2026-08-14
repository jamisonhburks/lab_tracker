# New Project — scaffolding flow

Trigger: a human says **"I'm making a new project about ___"**. Execute these steps in
order. Confirm the two decisions marked **[ASK]**; infer the rest and state what you inferred.

## 0. Understand the ask (don't scaffold blind)

Read [`project-structure.md`](project-structure.md) and [`promotion.md`](promotion.md) now
if you have not. Then extract from the human's sentence:

- the **domain / question** ("about ___"),
- the **data modality** (tabular EHR? longitudinal events OMOP/MEDS? waveform/ECG?
  genomic/PRS/GWAS? ML-methods work?) — this drives method selection later,
- whether this is **exploratory** (no specific hypothesis yet) or **targeted**.

**[ASK]** Where should the project directory live, and what is its short slug? (default:
a new sibling dir `../<slug>/`, kept as its own git repo so it can promote independently.)

## 1. Create the skeleton

Create the directory tree from [`project-structure.md`](project-structure.md). At minimum:
`data/{raw,processed,external}/`, `hypotheses/`, `experiments/`, `reports/`, `campaigns/`,
`notes/`, `literature/`, `src/`. Add a `.gitignore` that excludes `data/raw/`,
`data/processed/`, large artifacts, and `__pycache__/`.

## 2. Drop in the standard-carrying files

Copy from [`templates/`](templates/), filling the `{{placeholders}}`:

- `templates/project-CLAUDE.md`  → `<project>/CLAUDE.md`
  This is the load-bearing step: it makes **every future session in this directory**
  follow the lab standard without being told. Point its links back to this substrate repo.
- `templates/project-README.md`  → `<project>/README.md`
  Fill title, question, modality, status = `scaffolding`.

## 3. Register intent as the first tracked artifact

Do **not** invent a hypothesis yet if the ask is exploratory. Instead:

- Write `notes/00_charter.md` (local semantic): the question, why it matters, the data you
  expect, the modality, and 2–4 candidate directions. This is private thinking — no gate.
- If the ask is already **targeted** (a specific link to test), go straight to
  [`hypothesis-workflow.md`](hypothesis-workflow.md) and produce `hypotheses/H001_*.yaml`
  at `status: draft`.

## 4. Ground the charter against the shared substrate (do this before committing to a direction)

Use the substrate so you don't rediscover known results or chase hub artifacts — see
[`using-the-substrate.md`](using-the-substrate.md). For each candidate direction:

- `list_active_work` — is the lab (or a past you) already doing this? Don't duplicate.
- `query_curated_findings` — has the lab already concluded something here?
- `ground_claim` / `find_paths` — is there a mechanistic path in the trustworthy KG?
- `check_novelty` — already published, or a new juxtaposition?

Record what you find in `notes/00_charter.md`. Prune directions that are duplicated or
already-consensus; keep the ones that are grounded-but-unpublished or genuinely novel.

## 5. Hand off

Tell the human what you created, what you inferred, and the surviving candidate
directions with their grounding/novelty verdicts. Recommend the strongest one to
formalize first, and point them to [`hypothesis-workflow.md`](hypothesis-workflow.md).

Set the README status to `active` once a first hypothesis reaches `approved`.

## Definition of done

- [ ] Directory tree matches `project-structure.md`.
- [ ] `<project>/CLAUDE.md` and `README.md` exist and point back to this substrate.
- [ ] `notes/00_charter.md` records the question + grounding/novelty findings.
- [ ] Candidate directions checked against `list_active_work` + `query_curated_findings`.
- [ ] No hypothesis was fabricated to fill the slot; `H001` exists only if the ask was targeted.
