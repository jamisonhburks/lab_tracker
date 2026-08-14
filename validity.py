"""validity — pre-registered, hypothesis-ORTHOGONAL interim checks ("is it working?").

Gates verify the experiment's MACHINERY, never the hypothesis-relevant result — so they
catch pipeline bugs (empty arms, wrong data scale, dead positive controls, live negative
controls) WITHOUT enabling p-hacking. They are declared in the hypothesis spec's
`validity_gates` block (pre-registration) and run INTERIM:

  - a `halt` gate that fails raises ValidityError -> the experiment stops before it can
    produce conclusions (the run is marked invalid, not "negative");
  - a `flag` gate that fails records a warning that surfaces in the evaluation.

Key discipline: gates must be ORTHOGONAL to the tested hypothesis. Good gates: both arms
present; data on the expected (log) scale; a positive-control gene with a robust,
hypothesis-INDEPENDENT effect behaves as known; negative-control genes stay null. A gate
must never be a check on the hypothesis-relevant genes themselves — that would let
interim results steer the analysis, which is exactly what pre-registration forbids.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class GateResult:
    name: str
    passed: bool
    severity: str   # "halt" | "flag"
    detail: str


class ValidityError(Exception):
    """A halt-severity gate failed — the experiment is INVALID (a bug), stop the run."""

    def __init__(self, result: GateResult):
        self.result = result
        super().__init__(f"HALT gate failed — {result.name}: {result.detail}")


class Gates:
    """Collects interim validity-gate results; halts the run on a failed halt gate."""

    def __init__(self, logger=None):
        self.results: list = []
        self.logger = logger

    def _emit(self, r: GateResult) -> GateResult:
        self.results.append(r)
        msg = f"[validity:{r.severity}] {r.name}: {'PASS' if r.passed else 'FAIL'} — {r.detail}"
        if self.logger:
            (self.logger.info if r.passed else self.logger.warning)(msg)
        if not r.passed and r.severity == "halt":
            raise ValidityError(r)
        return r

    # --- gate primitives (all hypothesis-orthogonal) ---------------------------

    def cohort_integrity(self, arm_counts: dict, min_per_arm: int = 1, severity: str = "halt"):
        """Both study arms present, each ≥ min_per_arm. Catches empty/mislabeled arms
        (e.g. the AD='AA' coding bug that produced 0 cases)."""
        under = {k: v for k, v in arm_counts.items() if v < min_per_arm}
        passed = len(arm_counts) >= 2 and not under
        detail = f"arms={arm_counts}, min_per_arm={min_per_arm}" + (f"; UNDER-MIN: {under}" if under else "")
        return self._emit(GateResult("cohort_integrity", passed, severity, detail))

    def data_scale(self, values, kind: str = "log", max_expected: float = 30.0, severity: str = "halt"):
        """Values are finite and on the expected scale (e.g. log-space max ≲ 30).
        Catches un-logged / mis-scaled expression matrices."""
        import numpy as np
        arr = np.asarray(list(values), dtype=float)
        arr = arr[np.isfinite(arr)]
        mx = float(arr.max()) if arr.size else float("nan")
        passed = arr.size > 0 and mx <= max_expected
        detail = f"kind={kind}, observed_max={mx:.2f}, max_expected={max_expected}"
        return self._emit(GateResult("data_scale", passed, severity, detail))

    def negative_control(self, name: str, frac_significant: float, max_frac: float = 0.10,
                         severity: str = "flag"):
        """Genes with NO expected effect stay null — validates FDR control, orthogonal to
        the hypothesis genes. Fails if too many negative controls are called significant."""
        passed = frac_significant <= max_frac
        detail = f"{name}: frac_significant={frac_significant:.3f} (max {max_frac})"
        return self._emit(GateResult(f"negative_control[{name}]", passed, severity, detail))

    def positive_control(self, gene: str, observed_dir: str, expected_dir: str,
                         significant=None, severity: str = "flag"):
        """A gene with a robust, hypothesis-INDEPENDENT effect behaves as known (right
        direction, ideally significant) — proves the pipeline can detect a real effect."""
        passed = (observed_dir == expected_dir) and (significant is not False)
        detail = (f"{gene}: observed {observed_dir}, expected {expected_dir}"
                  + (f", significant={significant}" if significant is not None else ""))
        return self._emit(GateResult(f"positive_control[{gene}]", passed, severity, detail))

    def custom(self, name: str, passed: bool, detail: str, severity: str = "flag"):
        return self._emit(GateResult(name, passed, severity, detail))

    # --- reporting -------------------------------------------------------------

    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def invalidated(self) -> bool:
        return any((not r.passed) and r.severity == "halt" for r in self.results)

    def summary(self) -> str:
        p = sum(r.passed for r in self.results)
        tail = "  [INVALID — halt gate failed]" if self.invalidated() else \
               ("  [flags present]" if not self.all_passed() else "")
        return f"validity gates: {p}/{len(self.results)} passed{tail}"

    def save(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([asdict(r) for r in self.results], indent=2), encoding="utf-8")
        return path
