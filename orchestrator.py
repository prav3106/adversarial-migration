#!/usr/bin/env python3
"""
orchestrator.py — Resolution loop for adversarial migration.

Each `run` is one round:
  1. Fix requests left by the previous round count as fix attempts; they are
     archived.
  2. Every active program is hunted, wave by wave (programs within a wave run
     in parallel). All programs are re-hunted every round, so a fix that breaks
     another program (e.g. via shared code) is caught as a regression.
  3. Clean hunt -> PASSED (accept A if still in play, else B).
     Finding    -> one fix request per blamed translator. A translator that has
                   used all its attempts is dropped; if both are dropped the
                   program is marked NEEDS_HUMAN_REVIEW.
  4. The round is appended to reports/run_log.json.

Between rounds, translators are fixed (by Bob subagents), then `run` again.

Usage:
    python orchestrator.py run [--budget 200] [--serial]
    python orchestrator.py report
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
GRAPH = ROOT / "dictionary" / "dependency_graph.json"
FINDINGS = ROOT / "reports" / "findings"
BASELINE = ROOT / "reports" / "baseline"
FIX_DIR = ROOT / "reports" / "fix_requests"
ARCHIVE = FIX_DIR / "archive"
LOG = ROOT / "reports" / "run_log.json"
BENCH = ROOT / "reports" / "BENCHMARK.md"

MAX_ATTEMPTS = 3
BLAME = {
    "a_wrong": ["a"],
    "b_wrong": ["b"],
    "both_wrong_same": ["a", "b"],
    "both_wrong_different": ["a", "b"],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_log() -> dict[str, Any]:
    if LOG.exists():
        return json.loads(LOG.read_text())
    return {"programs": {}, "rounds": []}


def save_log(log: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(log, indent=2))


def program_state(log: dict[str, Any], prog: str) -> dict[str, Any]:
    return log["programs"].setdefault(prog, {
        "status": "PENDING",
        "variants": ["a", "b"],
        "attempts": {"a": 0, "b": 0},
        "accepted": None,
        "history": [],
    })


def load_waves() -> list[list[str]]:
    graph = json.loads(GRAPH.read_text())
    by_wave: dict[int, list[str]] = {}
    for prog, info in graph.items():
        by_wave.setdefault(info["wave"], []).append(prog)
    return [sorted(by_wave[w]) for w in sorted(by_wave)]


# ---------------------------------------------------------------------------
# Hunting
# ---------------------------------------------------------------------------

def hunt(prog: str, budget: int, variants: list[str]) -> dict[str, Any]:
    path = FINDINGS / f"{prog}.json"
    path.unlink(missing_ok=True)  # never read a stale result
    proc = subprocess.run(
        [sys.executable, "-m", "prosecutor.hunt", prog,
         "--budget", str(budget), "--variants", *variants],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1) or not path.exists():
        raise RuntimeError(
            f"Hunt for {prog} crashed (exit {proc.returncode}):\n{proc.stderr[-3000:]}"
        )
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Fix requests
# ---------------------------------------------------------------------------

def write_fix_request(prog: str, variant: str, finding: dict[str, Any], attempt: int) -> Path:
    FIX_DIR.mkdir(parents=True, exist_ok=True)
    other = "b" if variant == "a" else "a"
    lines = [
        f"# Fix request: translation/{variant}/{prog}.py (attempt {attempt} of {MAX_ATTEMPTS})",
        "",
        "The prosecutor found an input where your output differs from the real "
        f"COBOL program (classification: `{finding['classification']}`).",
        "",
        "## Minimal failing input",
        "```json",
        json.dumps(finding["minimal_input"], indent=2),
        "```",
        "",
        "## Fields that differ (raw bytes, hex)",
        "",
        "| Field | Golden (real COBOL) | Yours |",
        "|---|---|---|",
    ]
    for d in finding["diff"]:
        lines.append(
            f"| {d['field']} | `{d.get('golden_hex', '?')}` ({d.get('golden', '?')}) "
            f"| `{d.get(variant + '_hex', '?')}` ({d.get(variant, '?')}) |"
        )
    lines += [
        "",
        "## Full output records (hex)",
        f"- Golden: `{finding['golden']}`",
        f"- Yours:  `{finding.get(variant + '_output')}`",
        "",
        "## Rules",
        f"- Edit only files in translation/{variant}/.",
        f"- Do not read translation/{other}/, golden_master/, tests/, prosecutor/, "
        "or reports/ (except this file).",
        "- Fix the underlying cause (encoding or arithmetic semantics), not this one input. "
        "Never special-case values.",
        "- Check the whole class of inputs this bug belongs to (every sign, every digit, "
        "every field using the same encoding), not just this example.",
        "- If the cause is in shared code, fix it there; other programs may share the mistake.",
        "- Keep run(record: dict) -> bytes unchanged.",
        "- Do not compare against golden outputs. The prosecutor re-verifies after your fix.",
        "",
    ]
    path = FIX_DIR / f"{prog}_{variant}.md"
    path.write_text("\n".join(lines))
    return path


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_run(budget: int, serial: bool) -> int:
    log = load_log()
    rnd = len(log["rounds"]) + 1

    # 1. Fix requests from the previous round count as attempts.
    if FIX_DIR.exists():
        for req in sorted(FIX_DIR.glob("*.md")):
            prog, variant = req.stem.rsplit("_", 1)
            program_state(log, prog)["attempts"][variant] += 1
            ARCHIVE.mkdir(parents=True, exist_ok=True)
            shutil.move(str(req), str(ARCHIVE / f"round{rnd - 1}_{req.name}"))

    print(f"=== Round {rnd} ===", flush=True)
    summary: list[str] = []
    new_requests: list[str] = []

    for wave_idx, progs in enumerate(load_waves()):
        active = [p for p in progs if program_state(log, p)["status"] != "NEEDS_HUMAN_REVIEW"]
        if not active:
            continue
        mode = "serial" if serial else "parallel"
        print(f"Wave {wave_idx}: hunting {', '.join(active)} ({mode})", flush=True)

        jobs = {p: list(program_state(log, p)["variants"]) for p in active}
        if serial:
            results = {p: hunt(p, budget, v) for p, v in jobs.items()}
        else:
            with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
                futures = {p: ex.submit(hunt, p, budget, v) for p, v in jobs.items()}
                results = {p: fut.result() for p, fut in futures.items()}

        for prog in active:
            state = program_state(log, prog)
            res = results[prog]
            entry: dict[str, Any] = {
                "round": rnd, "wave": wave_idx, "timestamp": now(),
                "variants": list(state["variants"]),
            }

            if not res["found"]:
                state["status"] = "PASSED"
                state["accepted"] = "a" if "a" in state["variants"] else "b"
                entry.update(result="clean", inputs_tested=res["inputs_tested"])
                line = (f"{prog}: PASSED (accepted {state['accepted'].upper()}, "
                        f"{res['inputs_tested']} inputs tested)")
            else:
                f = res["finding"]
                blamed = [v for v in BLAME.get(f["classification"], ["a", "b"])
                          if v in state["variants"]]
                entry.update(
                    result=f["classification"],
                    minimal_input=f["minimal_input"],
                    fields=[d["field"] for d in f["diff"]],
                )
                requested, dropped = [], []
                for v in blamed:
                    if state["attempts"][v] >= MAX_ATTEMPTS:
                        state["variants"].remove(v)
                        dropped.append(v)
                    else:
                        path = write_fix_request(prog, v, f, state["attempts"][v] + 1)
                        requested.append(v)
                        new_requests.append(str(path.relative_to(ROOT)))
                entry.update(fix_requests=requested, dropped=dropped)

                if not state["variants"]:
                    state["status"] = "NEEDS_HUMAN_REVIEW"
                    line = f"{prog}: NEEDS_HUMAN_REVIEW (both translators used {MAX_ATTEMPTS} attempts)"
                else:
                    state["status"] = "NEEDS_FIX" if requested else "PENDING"
                    fields = ", ".join(entry["fields"])
                    line = f"{prog}: {f['classification']} on {fields}"
                    if requested:
                        line += f" -> fix requested from {', '.join(v.upper() for v in requested)}"
                    if dropped:
                        line += f" | dropped {', '.join(v.upper() for v in dropped)} (attempts exhausted)"

            state["history"].append(entry)
            summary.append(line)
            print("  " + line, flush=True)

    log["rounds"].append({"round": rnd, "timestamp": now(), "budget": budget, "summary": summary})
    save_log(log)

    print()
    if new_requests:
        print("Fix requests written:")
        for r in new_requests:
            print(f"  {r}")
        print("Fix them, then run `python orchestrator.py run` again.")
    else:
        print("No open fix requests. All programs resolved.")
    return 0


def _classification(path: Path) -> str | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    return d["finding"]["classification"] if d.get("found") else "clean"


def cmd_report() -> int:
    log = load_log()
    a_bugs, b_bugs = [], []
    lines = [
        "# Benchmark",
        "",
        f"Generated {now()}",
        "",
        "## Per program",
        "",
        "| Program | Wave | Single-pass result (baseline) | Final status | Accepted "
        "| Fix attempts A / B | Rounds |",
        "|---|---|---|---|---|---|---|",
    ]
    for wave_idx, progs in enumerate(load_waves()):
        for prog in progs:
            base = _classification(BASELINE / f"{prog}.json") or "not recorded"
            if base in ("a_wrong", "both_wrong_same", "both_wrong_different"):
                a_bugs.append(prog)
            if base in ("b_wrong", "both_wrong_same", "both_wrong_different"):
                b_bugs.append(prog)
            st = log["programs"].get(prog, {})
            att = st.get("attempts", {"a": 0, "b": 0})
            rounds = len({h["round"] for h in st.get("history", [])})
            acc = (st.get("accepted") or "-").upper()
            lines.append(
                f"| {prog} | {wave_idx} | {base} | {st.get('status', 'NOT RUN')} | {acc} "
                f"| {att['a']} / {att['b']} | {rounds} |"
            )
    lines += [
        "",
        "## Summary",
        "",
        f"- Translator A (careful single pass) shipped silent behavior changes in: "
        f"{', '.join(a_bugs) or 'none'}",
        f"- Translator B (careful single pass) shipped silent behavior changes in: "
        f"{', '.join(b_bugs) or 'none'}",
        "- Baseline hunts stop at the first finding per program, so these are lower bounds.",
        "",
        "## Rounds",
        "",
    ]
    for r in log["rounds"]:
        lines.append(f"### Round {r['round']} ({r['timestamp']}, budget {r['budget']})")
        lines += [f"- {s}" for s in r["summary"]]
        lines.append("")
    BENCH.write_text("\n".join(lines))
    print(f"Wrote {BENCH.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Adversarial migration orchestrator.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="Run one round: hunt all programs, write fix requests.")
    r.add_argument("--budget", type=int, default=200)
    r.add_argument("--serial", action="store_true", help="Hunt one program at a time.")
    sub.add_parser("report", help="Write reports/BENCHMARK.md.")
    args = p.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args.budget, args.serial)
    return cmd_report()


if __name__ == "__main__":
    sys.exit(main())