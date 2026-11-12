"""for_domain re-runs rules instead of slicing the frames from evaluate()."""
from checkerduck.model.models import Analysis, AnalysisDomain, AnalysisStatus, RuleEvaluation
from checkerduck.rules.debug import Run, label
from checkerduck.rules.rule_configuration import RuleConfiguration
from checkerduck.rules.seo_rule import EvalContext, SeoRule

import pandas as pd


class CountingRule(SeoRule):
    def __init__(self):
        super().__init__(name="Counting", weight=2.0)
        self.calls = 0

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        self.calls += 1
        return RuleEvaluation(
            eval_context.domain, self.name, score=0.25,
            critical_violation=True, details=f"call {self.calls} {eval_context.target_id}",
        )


class BoomRule(SeoRule):
    def __init__(self):
        super().__init__(name="Boom", weight=1.0)

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        raise RuntimeError(f"nope {eval_context.domain}")


def _run(rules: tuple[SeoRule, ...]) -> Run:
    labels = [label(r) for r in rules]
    index = pd.Index(["podscan.fm"], name="Domain")
    stale = pd.DataFrame({lab: [0.9] for lab in labels}, index=index)
    return Run(
        scores=stale,
        critical=pd.DataFrame({lab: [False] for lab in labels}, index=index),
        details=pd.DataFrame({lab: ["stale"] for lab in labels}, index=index),
        errors=pd.DataFrame({lab: [""] for lab in labels}, index=index),
        rules=rules,
        analysis=Analysis(
            target_id="x",
            name="",
            status=AnalysisStatus.PENDING,
            created_at="2026-11-11T00:00:00+00:00",
            completed_at=None,
            domains=[AnalysisDomain("podscan.fm", 0, "")],
            processed_domains=0,
            rule_configuration=RuleConfiguration(),
        ),
    )


def test_for_domain_recalculates_instead_of_reading_saved_frames():
    counting = CountingRule()
    run = _run((counting, BoomRule()))

    out = run.for_domain("podscan.fm")

    assert counting.calls == 1
    assert out.loc["Counting", "score"] == 0.25
    assert bool(out.loc["Counting", "critical"]) is True
    assert out.loc["Counting", "details"] == "call 1 x"
    assert out.loc["Counting", "error"] == ""
    assert out.loc["Counting", "name"] == "Counting"
    assert out.loc["Counting", "weight"] == 2.0
    assert pd.isna(out.loc["Boom", "score"])
    assert "RuntimeError: nope podscan.fm" in out.loc["Boom", "error"]
    # The batch snapshot is left alone.
    assert run.scores.loc["podscan.fm", "Counting"] == 0.9
    assert run.details.loc["podscan.fm", "Counting"] == "stale"
