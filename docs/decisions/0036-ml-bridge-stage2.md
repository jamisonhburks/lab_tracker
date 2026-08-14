# ADR-0036: ML bridge breadth (Stage 2) — more disease↔modality↔task↔architecture coverage

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
`method_select.recommend_methods` turns "what method for this data?" into a traversal of the
fused ML graph's bridge (disease → modality → suited architectures → tasks → losses → metrics
→ caveats). Stage 1 seeded 61 real, arXiv-attributed methods but only a *thin* bridge: two
diseases (AF, T2D), ~five modalities (ECG, generic imaging, genomic, EHR-events, EHR-tabular),
three tasks. So `recommend_methods` returned "no data modality linked" for most of the lab's
actual domains — ophthalmology (the glaucoma work), neuroimaging, histopathology, EEG,
clinical NLP — even though the relevant architectures were already in the graph.

## Decision
Broaden the curated bridge (Stage 2) as a single appended block in `ml_seed.py` — no schema
change, same predicates the traversal already keys on. Added:

- **6 diseases** wired to how they're actually studied: glaucoma → fundus/OCT/genomic;
  Alzheimer's → MRI/genomic/EHR; heart failure → EHR-events/ECG; sepsis → EHR-events;
  diabetic retinopathy → fundus; epilepsy → EEG.
- **6 modalities**: retinal fundus, OCT, volumetric MRI/CT, histopathology WSI, EEG, clinical
  text (with the finer imaging modalities marked `subtype_of` the generic imaging node).
- **7 tasks** (image-clf, detection, regression, forecasting, representation/SSL, generation,
  clinical NER), **5 losses** (CE, BCE, Dice, MSE, InfoNCE), **7 metrics** (accuracy, F1,
  Dice/IoU, AUPRC, MAE/R², sens/spec, FID), **6 caveats** (class imbalance, domain/scanner
  shift, label noise, small-N, gigapixel-WSI, high-dim p≫n).
- **~100 edges** connecting existing architectures (ResNet/DenseNet/EfficientNet/ViT/Swin/
  ConvNeXt/U-Net/Faster-RCNN/YOLO/Mask-RCNN/GRU/BERT/GCN/GraphSAGE/GAT/XGBoost/SimCLR/MoCo/
  BYOL/MAE/DDPM/LatentDiffusion/GAN/VAE) to the new modalities/tasks/losses/metrics/caveats.

Regenerated the committed seed (`python ml_seed.py`, live arXiv authorship + retries).

## Rationale & evidence
- **Every new `METHOD:*` edge points at a method that already exists in `CURATED`**, so it
  resolves to a real, arXiv-attributed node — the bridge stays grounded, not invented.
- **Appended as one block, not inlined**, so the diff is a single reviewable unit and the
  Stage-1 curation is untouched.
- **Verified**: seed grew 281→**318 nodes / 316→419 edges**, all **61 methods preserved** (no
  title-guard drop), 4 benchmarks. `recommend_methods("glaucoma")` now returns fundus (ResNet/
  DenseNet/EfficientNet, CE loss, acc/AUROC/F1, domain-shift + label-noise caveats), OCT
  (ResNet/U-Net), and genomic (GCN/XGBoost/GraphSAGE/GAT); histopathology → ViT/Swin/MAE with
  the gigapixel-WSI caveat; EEG → Transformer/GRU/ResNet; clinical text → BERT/Transformer.

## Consequences
- `recommend_methods` (and `propose_experiment`, which calls it) now cover the lab's real
  modalities — the glaucoma project's fundus/OCT/genomic choices are graph-grounded, not ad hoc.
- The bridge is still *curated*; Stage 4 (bulk ingestion, ADR-0037) adds breadth of *methods*
  from external corpora, complementary to this breadth of *bridge*.
- Caveats now flow into method selection (e.g. WSI tiling, scanner domain shift), nudging
  design toward the right pre-registered validity checks.
