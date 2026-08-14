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

## 1–2. Skeleton + standard-carrying files (one command)

Steps 1 and 2 are pure boilerplate, so run the helper instead of hand-creating files:

```sh
python scaffold.py new "<Project Title>" --slug <slug> --modality <modality> [--git-init]
```

This builds the standard tree (`data/{raw,processed,external}/`, `hypotheses/`,
`experiments/`, `reports/`, `campaigns/`, `notes/`, `literature/`, `src/`), a `.gitignore`,
and — filling the `{{placeholders}}` — the two **load-bearing** files:

- `<project>/CLAUDE.md` (from `templates/project-CLAUDE.md`) — makes **every future session in
  this directory** follow the lab standard without being told; its substrate path is computed
  for you.
- `<project>/README.md` (from `templates/project-README.md`) — title, modality, status `scaffolding`.
- `<project>/notes/00_charter.md` — a **stub with the Step-4 substrate checks as a checklist**.

Doing it by hand is fine too (copy from [`templates/`](templates/), fill the placeholders) —
the helper just does exactly that, deterministically, so names match what the shared tier keys off.

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
