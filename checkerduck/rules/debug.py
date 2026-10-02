"""Harness for debugging a rule set: evaluate every rule against every domain
and hand back one wide table. Driven from notebooks/rules_debug.ipynb.

Deliberately calls rule.eval() rather than rule.safe_eval(): safe_eval turns a
crash into score 0.0, which is indistinguishable from a rule that legitimately
scored 0. Here a crash becomes NaN plus the traceback, so tuning never chases a
zero that was really an exception.
"""
from __future__ import annotations

import json
import logging
import pathlib
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from checkerduck.db import dao
from checkerduck.rules.seo_rule import EvalContext, SeoRule

log = logging.getLogger(__name__)

OVERALL, WEIGHTED, CRITICAL, ERRORS = "overall", "weighted", "critical", "errors"
COMMENT = "comment"
DOMAIN = "Domain"   # index name, so the frame's first header cell is labelled
SUMMARY_COLS = (OVERALL, WEIGHTED, CRITICAL, ERRORS)


def label(rule: SeoRule) -> str:
    """Stable, reasonably short column identity for a rule.

    Derived from the class name because rule.name is not unique -- SpamWordsAnchorsRule
    and ForbiddenWordsAnchorRule are both called "Spam Words in Anchors". The redundant
    "Rule" suffix is dropped purely to narrow the table; the result is still unique.
    """
    return type(rule).__name__.removesuffix("Rule")


EXTRACT_TABLES = ("batch_analysis", "ahrefs_org_traffic_country", "domain_categories",
                  "ahrefs_metrics_history", "ahrefs_top_pages", "ahrefs_backlinks",
                  "anchors_forbidden_words", "ahrefs_organic_keywords")


def project_root(marker: str = "pyproject.toml") -> pathlib.Path:
    """The repo root, so notebook paths need not be absolute.

    Anchored on this file first, because a notebook's cwd depends on the
    frontend -- the repo root in some, notebooks/ in others -- and anything
    resolved against the cwd silently points at different files. Falls back to
    walking up from the cwd when the package is installed outside the repo.
    """
    here = pathlib.Path(__file__).resolve().parents[2]   # checkerduck/rules/debug.py
    if (here / marker).exists():
        return here
    for candidate in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents]:
        if (candidate / marker).exists():
            return candidate
    raise FileNotFoundError(
        f"no {marker} found at {here}, in {pathlib.Path.cwd()}, or any parent")


def coverage(target_id: str) -> pd.DataFrame:
    """What the extractor actually left behind for this target, per table.

    A rule is only as good as its input: an empty table here explains a column
    of zeros or ERRs far better than reading the rule code does.
    """
    rows = []
    for table in EXTRACT_TABLES:
        r = dao.select_one(
            f"select count(*) n, count(distinct domain) d from {table} where target_id = ?",
            (target_id,))
        rows.append({"table": table, "rows": r["n"], "domains": r["d"]})
    return pd.DataFrame(rows).set_index("table").rename_axis("Table")


def missing_domains(target_id: str, domains: Sequence[str]) -> list[str]:
    """Input domains with no batch_analysis row -- never extracted for this target."""
    have = {r["domain"] for r in dao.select_all(
        "select distinct domain from batch_analysis where target_id = ?", (target_id,))}
    return [d for d in domains if d not in have]


_THREAD_UNSAFE = ("torch", "sentence_transformers")


def holds_model(rule: SeoRule) -> bool:
    """True if the rule carries a torch / SentenceTransformer object.

    Such rules must run single-threaded. On Apple Silicon sentence-transformers
    runs on MPS, and Metal command buffers cannot be shared between threads:
    concurrent encode() trips a Metal assertion and SIGABRTs the whole process,
    taking the notebook kernel with it. It is not a memory problem -- peak RSS
    for Qwen3-Embedding-0.6B is under 1 GB.
    """
    attrs = list(vars(rule).values()) + list(vars(type(rule)).values())
    return any(type(a).__module__.split(".")[0] in _THREAD_UNSAFE for a in attrs)


class Comments:
    """Free-text note per domain, persisted to a JSON file beside the notebook.

    Survives kernel restarts and re-runs, and is deliberately kept out of the
    database: these are your annotations, not extracted data. Every write saves
    immediately, so an interrupted editing session keeps what you already typed.
    """

    def __init__(self, path: str | pathlib.Path = "rule_comments.json"):
        self.path = pathlib.Path(path)
        self._notes: dict[str, str] = (
            json.loads(self.path.read_text()) if self.path.exists() else {})

    def __getitem__(self, domain: str) -> str:
        return self._notes.get(domain, "")

    def __setitem__(self, domain: str, text: str) -> None:
        text = (text or "").strip()
        if text:
            self._notes[domain] = text
        else:
            self._notes.pop(domain, None)
        self.save()

    def __contains__(self, domain: str) -> bool:
        return domain in self._notes

    def __len__(self) -> int:
        return len(self._notes)

    def __repr__(self) -> str:
        return f"Comments({str(self.path)!r}, {len(self)} notes)"

    def update(self, notes: Mapping[str, str]) -> None:
        """Set several at once: comments.update({"a.com": "thin content", ...})."""
        for domain, text in notes.items():
            text = (text or "").strip()
            if text:
                self._notes[domain] = text
            else:
                self._notes.pop(domain, None)
        self.save()

    def reload(self) -> None:
        """Re-read the file, picking up edits made outside this kernel."""
        self._notes = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._notes, indent=1, sort_keys=True) + "\n")

    def series(self) -> pd.Series:
        return pd.Series(self._notes, dtype="object", name=COMMENT)

    def prompt(self, domains: Sequence[str], only_empty: bool = False) -> None:
        """Type a note per domain. Enter keeps the current value, '-' clears it.

        Interrupt the cell to stop early -- everything typed so far is saved.
        """
        for domain in domains:
            if only_empty and self[domain]:
                continue
            current = self[domain]
            try:
                text = input(f"{domain} [{current}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\nstopped; {len(self)} notes saved to {self.path}")
                return
            if text == "-":
                self[domain] = ""
            elif text:
                self[domain] = text
        print(f"{len(self)} notes saved to {self.path}")

    def to_csv(self, path: str | pathlib.Path) -> None:
        """Dump for bulk editing in a spreadsheet, then read_csv it back."""
        self.series().rename_axis("domain").to_frame().to_csv(path)

    def read_csv(self, path: str | pathlib.Path) -> None:
        df = pd.read_csv(path).fillna("")
        self.update(dict(zip(df["domain"], df[COMMENT])))


def legend(rules: Sequence[SeoRule]) -> pd.DataFrame:
    """Column name -> each rule's own metadata. Usable before a run."""
    return pd.DataFrame([
        {"column": label(r), "class": type(r).__name__, "name": r.name,
         "weight": r.weight, "area": r.area, "deal_breaker": r.deal_breaker} for r in rules
    ]).set_index("column")


@dataclass(frozen=True)
class Run:
    """One evaluation of one rule set over one set of domains."""
    scores: pd.DataFrame     # domain x rule -> float (NaN when the rule raised)
    critical: pd.DataFrame   # domain x rule -> bool
    details: pd.DataFrame    # domain x rule -> str
    errors: pd.DataFrame     # domain x rule -> traceback, "" when it ran
    rules: tuple[SeoRule, ...]

    def legend(self) -> pd.DataFrame:
        """Column name -> the rule's own metadata."""
        return legend(self.rules)

    def table(self, sort_by: str = OVERALL, ascending: bool = False,
              hide_constant: bool = False, comments: Comments | None = None) -> pd.DataFrame:
        """Domains on rows, one column per rule, summary columns first.

        Best-first by default. Pass any rule's column name as sort_by to sort by
        that rule alone, and ascending=True to put the worst offenders on top.
        hide_constant drops rule columns that scored every domain the same -- the
        quickest way to make a wide table fit. Pass a Comments store to get your
        notes as the leading column.
        """
        summary = pd.DataFrame({
            OVERALL: self.scores.mean(axis=1),
            WEIGHTED: self._weighted(),
            CRITICAL: self.critical.sum(axis=1).astype(int),
            ERRORS: (self.errors != "").sum(axis=1).astype(int),
        })
        scores = self.scores
        if hide_constant:
            # Summary columns stay computed over the full set; only the display
            # drops rules that scored every domain identically (or not at all).
            scores = scores[[c for c in scores.columns
                             if scores[c].nunique(dropna=True) > 1]]
        wide = pd.concat([summary, scores], axis=1)
        if comments is not None:
            # Leading column: visible without scrolling, and never sorted on.
            wide.insert(0, COMMENT, comments.series().reindex(wide.index).fillna(""))
        if sort_by not in wide.columns:
            raise KeyError(f"{sort_by!r} not a column; pick one of {list(wide.columns)}")
        return wide.sort_values(sort_by, ascending=ascending, kind="stable")

    def _weighted(self) -> pd.Series:
        """Weighted mean over the rules that actually produced a score."""
        w = pd.Series({label(r): r.weight for r in self.rules}).reindex(self.scores.columns)
        ran = self.scores.notna()
        return (self.scores.fillna(0) * w).sum(axis=1) / (ran * w).sum(axis=1)

    def for_domain(self, domain: str) -> pd.DataFrame:
        """Every rule's full output for one domain -- the drill-down view."""
        out = pd.DataFrame({
            "score": self.scores.loc[domain],
            "critical": self.critical.loc[domain],
            "details": self.details.loc[domain],
            "error": self.errors.loc[domain],
        })
        return out.join(self.legend()[["name", "weight", "area"]]).rename_axis("Rule")

    def failures(self) -> pd.DataFrame:
        """Every (domain, rule) pair whose eval() raised, with the traceback."""
        e = self.errors
        rows = [(d, c, e.at[d, c]) for d in e.index for c in e.columns if e.at[d, c]]
        return pd.DataFrame(rows, columns=["domain", "rule", "error"])

    def diff(self, before: Run, sort_by: str = OVERALL) -> pd.DataFrame:
        """Score change from `before` to this run: the tuning feedback loop.

        Only rows that actually moved are returned.
        """
        a, b = before.table(), self.table()
        numeric = set(b.select_dtypes("number").columns)
        cols = [c for c in b.columns if c in a.columns and c in numeric and c != ERRORS]
        delta = (b[cols] - a[cols].reindex(b.index)).dropna(how="all")
        moved = delta.loc[(delta.abs() > 1e-9).any(axis=1)]
        return moved.sort_values(sort_by, kind="stable") if sort_by in moved else moved


def evaluate(target_id: str, rules: Sequence[SeoRule],
             domains: Sequence[str] | None = None, workers: int = 8) -> Run:
    """Run every rule against every domain. Fans out per domain, as production does.

    workers is forced to 1 when any rule holds a torch model; see holds_model().
    """
    if workers > 1 and (heavy := [label(r) for r in rules if holds_model(r)]):
        log.warning("forcing workers=1: %s hold a torch model, and concurrent "
                    "inference aborts the process", heavy)
        workers = 1
    if domains is None:
        domains = [d.domain for d in dao.get_analysis(target_id).domains]
    domains = list(dict.fromkeys(domains))  # dedupe, keep order: it becomes the index
    labels = [label(r) for r in rules]
    if len(set(labels)) != len(labels):
        raise ValueError(f"the same rule class appears twice: {labels}")

    def one(domain: str) -> dict[str, tuple]:
        ctx = EvalContext(target_id, domain)
        row = {}
        for rule in rules:
            try:
                ev = rule.eval(ctx)
                row[label(rule)] = (float(ev.score), bool(ev.critical_violation),
                                    ev.details or "", "")
            except Exception:
                row[label(rule)] = (float("nan"), False, "", traceback.format_exc(limit=4))
        return row

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = dict(zip(domains, pool.map(one, domains)))

    def frame(i: int, dtype: str) -> pd.DataFrame:
        return pd.DataFrame({lab: {d: rows[d][lab][i] for d in domains} for lab in labels},
                            index=pd.Index(list(domains), name=DOMAIN)).astype(dtype)

    log.info("evaluated %d rules over %d domains", len(rules), len(domains))
    return Run(frame(0, "float"), frame(1, "bool"), frame(2, "object"),
               frame(3, "object"), tuple(rules))


# ------------------------------------------------------------------ rendering

def style(table: pd.DataFrame, low: float = 0.4, high: float = 0.7, scroll: bool = False):
    """Opt-in colour coding: red below `low`, amber below `high`, green above.

    Heavy -- a CSS class per cell -- so pass a slice rather than 200 rows, e.g.
    style(run.table().head(30)). scroll=True additionally wraps it in a scrolling
    box, which looks right but does not respond to trackpad wheel events in every
    frontend; show() is the fast, natively scrollable default.
    """
    # Pick score columns by dtype, not by name: the comment column is text and
    # must not reach colour(), and counts are flags rather than scores.
    numeric = list(table.select_dtypes("number").columns)
    scores = [c for c in numeric if c not in (CRITICAL, ERRORS)]
    flags = [c for c in (CRITICAL, ERRORS) if c in numeric]

    def colour(v):
        if pd.isna(v):
            return "background-color:#ede9fe;color:#5b21b6"  # rule raised
        if v < low:
            return "background-color:#fee2e2;color:#991b1b"
        if v < high:
            return "background-color:#fef3c7;color:#92400e"
        return "background-color:#dcfce7;color:#166534"

    styled = (table.style
              .map(colour, subset=scores)
              .format("{:.2f}", subset=scores, na_rep="ERR")
              .set_sticky(axis="index")
              .set_table_styles([
                  # width:max-content is the load-bearing one. Without it an
                  # inherited `table {width: 100%}` shrinks the table to the
                  # container, so the wrapper never has anything to scroll.
                  {"selector": "", "props": [("width", "max-content"),
                                             ("min-width", "max-content")]},
                  {"selector": "th, td",
                   "props": [("white-space", "nowrap"), ("padding", "2px 6px"),
                             ("font-size", "11px"), ("text-align", "right")]},
                  {"selector": "th.row_heading",
                   "props": [("text-align", "left"), ("background-color", "#f8fafc")]},
                  {"selector": "thead th", "props": [("background-color", "#f1f5f9")]},
              ], overwrite=False))   # keep the sticky rules set_sticky just added
    if flags:
        styled = (styled
                  .map(lambda v: "background-color:#fee2e2;color:#991b1b" if v else "",
                       subset=flags)
                  .format("{:d}", subset=flags))
    if not scroll:
        return styled
    try:
        from IPython.display import HTML
    except ImportError:          # headless: the caller gets the plain Styler
        return styled
    return HTML('<div style="overflow:auto;max-width:100%;max-height:70vh;'
                'resize:vertical;border:1px solid #e2e8f0">'
                f'{styled.to_html()}</div>')


def show(table: pd.DataFrame, decimals: int = 2, flatten: bool = True) -> pd.DataFrame:
    """Return the frame itself, so the notebook frontend renders it natively.

    A plain DataFrame is what Jupyter and Deepnote scroll with a trackpad and, in
    Deepnote, sort by clicking a header. The style() path below builds one CSS
    class per cell (~190 KB of HTML for 200x15) and renders inside a nested div
    that swallows wheel events -- correct colours, sluggish table.

    flatten moves the index into an ordinary column. An index renders as <th>
    header cells, which PyCharm (and several other grids) leave out when you copy
    a selection -- you get every column except the domain. As a <td> column it
    copies with everything else. Pass flatten=False to keep it as the index.

    Rules that raised show as NaN rather than a string, so the column stays
    numeric and sorts properly.
    """
    out = table.round(decimals)
    return out.reset_index() if flatten and out.index.name else out


def review(comments: Comments, domains: Sequence[str], note_width: str = "520px"):
    """Dropdown of domains beside a text box, wired to the JSON store.

    Selecting a domain re-reads the file and shows that domain's note; typing
    saves on blur or Enter (not per keystroke, so it is one file write per edit).
    Needs ipywidgets, which Jupyter and Deepnote both render.
    """
    try:
        import ipywidgets as widgets
    except ImportError as e:
        raise ImportError("review() needs ipywidgets: %pip install ipywidgets") from e

    picker = widgets.Dropdown(options=list(domains), description="domain",
                              layout=widgets.Layout(width="360px"))
    note = widgets.Textarea(placeholder="note for this domain...",
                            continuous_update=False,   # fire on blur/Enter, not per keypress
                            layout=widgets.Layout(width=note_width, height="70px"))
    status = widgets.HTML()

    def _status(msg: str = "", colour: str = "#64748b") -> None:
        status.value = (f'<span style="color:{colour}">{msg}</span>'
                        f'<span style="color:#94a3b8"> &middot; {len(comments)} notes '
                        f'in {comments.path.name}</span>')

    def load(*_):
        comments.reload()
        # Muted so assigning .value does not immediately save the value back.
        note.unobserve(save, names="value")
        note.value = comments[picker.value]
        note.observe(save, names="value")
        _status()

    def save(change):
        comments[picker.value] = change["new"]
        _status(f"saved {picker.value}", "#166534")

    picker.observe(load, names="value")
    note.observe(save, names="value")
    load()
    return widgets.VBox([widgets.HBox([picker, note]), status])

