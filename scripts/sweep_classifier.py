"""Automated parameter sweep for the !! and ! classifier.

Uses domain-informed search: screen motifs first (one-by-one), then
run Optuna TPE (Bayesian optimization) on the reduced space of numeric
thresholds + selected motifs. Much faster convergence than naive TPE
over the full 71-dimensional space.

Phases:
  1 — Motif screening (evaluate each motif independently)
  2 — Bayesian optimization with TPE on thresholds + selected motifs
  3 — Leave-One-Game-Out cross-validation on top candidates

Usage: uv run python3 scripts/sweep_classifier.py [--trials N]
"""

from __future__ import annotations

import copy
import importlib.util
import json
from typing import Any
import pathlib
import time
from dataclasses import dataclass, field

import optuna

from chess_self_coach.classifier import (
    DEFAULT_CONFIG,
    COMPLEXITY_BUDGET,
    COMPLEXITY_LAMBDA,
    classify_move,
    count_config_complexity,
    _compute_f1,
)
from chess_self_coach.config import tactics_data_path


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class GameData:
    """Pre-loaded data for one ground truth game."""

    game_id: str
    moves: list[dict[str, Any]]
    brilliant_indices: set[int]
    great_indices: set[int]
    tactics: list[dict[str, Any] | None]


@dataclass
class PreloadedData:
    """All data needed to evaluate a config, loaded once."""

    games: list[GameData]
    total_moves: int = 0
    all_motif_names: list[str] = field(default_factory=list)


@dataclass
class ScoreResult:
    """Result of evaluating one config."""

    brilliant_tp: int
    brilliant_fp: int
    brilliant_fn: int
    brilliant_f1: float
    great_tp: int
    great_fp: int
    great_fn: int
    great_f1: float
    macro_f1: float
    complexity: int
    penalty: float
    score: float


# ── Preloading ───────────────────────────────────────────────────────────────


def preload_data() -> PreloadedData:
    """Load ground truth, cases, and tactics once."""
    gt_path = pathlib.Path("tests/e2e/fixtures/classification_ground_truth.json")
    with open(gt_path) as f:
        gt_data = json.load(f)

    spec = importlib.util.spec_from_file_location(
        "cases", "tests/e2e/classification_cases.py"
    )
    assert spec and spec.loader
    cases_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases_mod)
    games_gt: list[dict[str, Any]] = cases_mod.GAMES  # type: ignore[attr-defined]

    gt_by_id = {g["game_id"]: g for g in gt_data["games"]}

    # Load tactics
    tactics_by_game: dict[str, list[dict[str, Any]]] = {}
    tp = tactics_data_path()
    if tp.exists():
        with open(tp) as f:
            tactics_by_game = json.load(f).get("games", {})

    games: list[GameData] = []
    total_moves = 0
    all_motifs: set[str] = set()

    for game_gt in games_gt:
        gid = game_gt["game_id"]
        gt_game = gt_by_id.get(gid)
        if not gt_game:
            continue
        moves = gt_game["moves"]
        total_moves += len(moves)

        # Find tactics by numeric ID
        num_id = gid.split("_")[-1]
        game_tactics_list: list[dict[str, Any]] | None = None
        for url, tac in tactics_by_game.items():
            if num_id in url:
                game_tactics_list = tac
                break

        tactics: list[dict[str, Any] | None] = []
        for i in range(len(moves)):
            t = game_tactics_list[i] if game_tactics_list and i < len(game_tactics_list) else None
            tactics.append(t)
            if t:
                for k, v in t.items():
                    if k != "_pv" and v is True:
                        all_motifs.add(k)

        games.append(GameData(
            game_id=gid,
            moves=moves,
            brilliant_indices=set(game_gt.get("brilliant_indices", [])),
            great_indices=set(game_gt.get("great_indices", [])),
            tactics=tactics,
        ))

    # Sorted for deterministic Optuna parameter ordering
    return PreloadedData(
        games=games,
        total_moves=total_moves,
        all_motif_names=sorted(all_motifs - {"isSacrifice", "isMissedCapture"}),
    )


# ── Evaluation ───────────────────────────────────────────────────────────────


def evaluate_config(
    config: dict[str, Any],
    data: PreloadedData,
    exclude_game: str | None = None,
) -> ScoreResult:
    """Evaluate a config against ground truth (fast, in-process).

    Args:
        config: Classifier parameters to test.
        data: Pre-loaded ground truth data.
        exclude_game: Game ID to exclude (for LOGO cross-validation).
    """
    total_brilliant = {"tp": 0, "fp": 0, "fn": 0}
    total_great = {"tp": 0, "fp": 0, "fn": 0}

    for game in data.games:
        if exclude_game and game.game_id == exclude_game:
            continue

        classifications: list[dict[str, Any] | None] = []
        for i, m in enumerate(game.moves):
            side = m.get("side", "white" if i % 2 == 0 else "black")
            prev = game.moves[i - 1] if i > 0 else None
            tact = game.tactics[i]
            classifications.append(classify_move(m, side, prev, tact, config))

        for i, cls in enumerate(classifications):
            predicted = cls["c"] if cls else "other"
            if predicted not in ("brilliant", "great"):
                predicted = "other"
            expected = (
                "brilliant" if i in game.brilliant_indices
                else "great" if i in game.great_indices
                else "other"
            )
            for cat, expected_cat, stats in [
                ("brilliant", "brilliant", total_brilliant),
                ("great", "great", total_great),
            ]:
                if expected == expected_cat and predicted == expected_cat:
                    stats["tp"] += 1
                elif predicted == expected_cat and expected != expected_cat:
                    stats["fp"] += 1
                elif expected == expected_cat and predicted != expected_cat:
                    stats["fn"] += 1

    _, _, brilliant_f1 = _compute_f1(total_brilliant["tp"], total_brilliant["fp"], total_brilliant["fn"])
    _, _, great_f1 = _compute_f1(total_great["tp"], total_great["fp"], total_great["fn"])
    macro_f1 = (brilliant_f1 + great_f1) / 2

    _, _, _, complexity = count_config_complexity(config)
    penalty = COMPLEXITY_LAMBDA * complexity / COMPLEXITY_BUDGET
    score = macro_f1 - penalty

    return ScoreResult(
        brilliant_tp=total_brilliant["tp"],
        brilliant_fp=total_brilliant["fp"],
        brilliant_fn=total_brilliant["fn"],
        brilliant_f1=brilliant_f1,
        great_tp=total_great["tp"],
        great_fp=total_great["fp"],
        great_fn=total_great["fn"],
        great_f1=great_f1,
        macro_f1=macro_f1,
        complexity=complexity,
        penalty=penalty,
        score=score,
    )


# ── Motif screening ──────────────────────────────────────────────────────────


@dataclass
class MotifResult:
    """Result of testing one motif as brilliant or great trigger."""

    motif: str
    role: str  # "brilliant" or "great"
    delta: float
    result: ScoreResult


def screen_motifs(data: PreloadedData, baseline: ScoreResult) -> list[MotifResult]:
    """Screen each motif independently as brilliant or great trigger.

    Fast one-by-one evaluation: 32 motifs x 2 roles = 64 evaluations.
    Returns sorted by delta (best first).
    """
    results: list[MotifResult] = []

    for motif in data.all_motif_names:
        # Test as brilliant motif
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["brilliant_motifs"] = ["isSacrifice", motif]
        r = evaluate_config(cfg, data)
        results.append(MotifResult(motif=motif, role="brilliant", delta=r.score - baseline.score, result=r))

        # Test as great motif
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["great_motifs"] = [motif]
        r = evaluate_config(cfg, data)
        results.append(MotifResult(motif=motif, role="great", delta=r.score - baseline.score, result=r))

    results.sort(key=lambda x: x.delta, reverse=True)
    return results


# ── Optuna objective ─────────────────────────────────────────────────────────


def create_objective(
    data: PreloadedData,
    selected_brilliant_motifs: list[str],
    selected_great_motifs: list[str],
):
    """Create an Optuna objective over thresholds + pre-screened motifs.

    The search space is reduced: only 7 numeric thresholds + a few
    binary motif toggles (those that passed screening). TPE converges
    fast on this small space.
    """

    def objective(trial: optuna.Trial) -> float:
        config: dict[str, Any] = {
            "brilliant_epl_max": trial.suggest_float("brilliant_epl_max", -0.03, 0.0),
            "brilliant_wp_min": trial.suggest_float("brilliant_wp_min", 0.05, 0.50),
            "brilliant_wp_max": trial.suggest_float("brilliant_wp_max", 0.80, 1.0),
            "great_epl_max": trial.suggest_float("great_epl_max", 0.0, 0.05),
            "great_opp_epl_min": trial.suggest_float("great_opp_epl_min", 0.05, 0.30),
            "great_filter_recapture": True,
            "miss_epl_min": trial.suggest_float("miss_epl_min", 0.02, 0.10),
            "miss_opp_epl_min": trial.suggest_float("miss_opp_epl_min", 0.05, 0.25),
        }

        # Only toggle motifs that passed screening
        brilliant_motifs = ["isSacrifice"]
        for motif in selected_brilliant_motifs:
            if trial.suggest_categorical(f"brilliant_{motif}", [False, True]):
                brilliant_motifs.append(motif)

        great_motifs: list[str] = []
        for motif in selected_great_motifs:
            if trial.suggest_categorical(f"great_{motif}", [False, True]):
                great_motifs.append(motif)

        config["brilliant_motifs"] = brilliant_motifs
        config["great_motifs"] = great_motifs

        return evaluate_config(config, data).score

    return objective


# ── LOGO cross-validation ────────────────────────────────────────────────────


def logo_validate(
    data: PreloadedData,
    candidates: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, float, float, float]]:
    """Leave-One-Game-Out cross-validation on candidate configs.

    Returns:
        List of (label, full_score, logo_score, divergence) tuples.
    """
    results: list[tuple[str, float, float, float]] = []

    for label, config in candidates:
        full = evaluate_config(config, data)

        logo_scores: list[float] = []
        for game in data.games:
            r = evaluate_config(config, data, exclude_game=game.game_id)
            logo_scores.append(r.score)

        logo_avg = sum(logo_scores) / len(logo_scores) if logo_scores else 0.0
        divergence = full.score - logo_avg
        results.append((label, full.score, logo_avg, divergence))

    return results


# ── Helpers ──────────────────────────────────────────────────────────────────


def _trial_to_config(
    trial: optuna.trial.FrozenTrial,
    selected_brilliant: list[str],
    selected_great: list[str],
) -> dict[str, Any]:
    """Reconstruct a config dict from a completed Optuna trial."""
    params = trial.params

    brilliant_motifs = ["isSacrifice"]
    great_motifs: list[str] = []
    for motif in selected_brilliant:
        if params.get(f"brilliant_{motif}", False):
            brilliant_motifs.append(motif)
    for motif in selected_great:
        if params.get(f"great_{motif}", False):
            great_motifs.append(motif)

    return {
        "brilliant_epl_max": params["brilliant_epl_max"],
        "brilliant_wp_min": params["brilliant_wp_min"],
        "brilliant_wp_max": params["brilliant_wp_max"],
        "brilliant_motifs": brilliant_motifs,
        "great_epl_max": params["great_epl_max"],
        "great_opp_epl_min": params["great_opp_epl_min"],
        "great_filter_recapture": True,
        "great_motifs": great_motifs,
        "miss_epl_min": params["miss_epl_min"],
        "miss_opp_epl_min": params["miss_opp_epl_min"],
    }


def _fmt_score(r: ScoreResult) -> str:
    """Format a score result as a compact string."""
    return (
        f"score={r.score:.3f} (F1={r.macro_f1:.3f} - penalty={r.penalty:.3f}) "
        f"[B: TP={r.brilliant_tp} FP={r.brilliant_fp} FN={r.brilliant_fn} F1={r.brilliant_f1:.3f}] "
        f"[G: TP={r.great_tp} FP={r.great_fp} FN={r.great_fn} F1={r.great_f1:.3f}]"
    )


# ── Report ───────────────────────────────────────────────────────────────────


def print_report(
    baseline: ScoreResult,
    motif_results: list[MotifResult],
    selected_brilliant: list[str],
    selected_great: list[str],
    study: optuna.Study,
    best_config: dict[str, Any],
    best_score: ScoreResult,
    logo_results: list[tuple[str, float, float, float]],
    elapsed: float,
) -> None:
    """Print the full sweep report to stdout."""
    print(f"\n{'='*70}")
    print("CLASSIFIER SWEEP REPORT (Screening + Optuna TPE)")
    print(f"{'='*70}")

    print(f"\nBASELINE: {_fmt_score(baseline)}")

    # Motif screening results
    print(f"\n--- Phase 1: Motif screening ({len(motif_results)} evaluations) ---")
    brilliant_motifs = [r for r in motif_results if r.role == "brilliant"]
    great_motifs = [r for r in motif_results if r.role == "great"]

    print("  BRILLIANT motifs (top 5):")
    for r in sorted(brilliant_motifs, key=lambda x: x.delta, reverse=True)[:5]:
        sign = "+" if r.delta >= 0 else ""
        print(f"    {sign}{r.delta:.4f}  {r.motif}")
    print("  GREAT motifs (top 5):")
    for r in sorted(great_motifs, key=lambda x: x.delta, reverse=True)[:5]:
        sign = "+" if r.delta >= 0 else ""
        print(f"    {sign}{r.delta:.4f}  {r.motif}")

    n_selected = len(selected_brilliant) + len(selected_great)
    if n_selected > 0:
        print(f"  Selected for TPE: {n_selected} motifs "
              f"(brilliant: {selected_brilliant}, great: {selected_great})")
    else:
        print("  No motifs improved the score — TPE will optimize thresholds only")

    # Optimization history
    n_dims = 7 + len(selected_brilliant) + len(selected_great)
    print(f"\n--- Phase 2: Bayesian optimization ({len(study.trials)} trials, {n_dims} dimensions) ---")
    print(f"  Best trial: #{study.best_trial.number}")
    print(f"  Best score: {study.best_value:.4f} (delta: {study.best_value - baseline.score:+.4f})")

    print(f"\n  Score progression (every 10 trials):")
    best_so_far = float("-inf")
    trials = study.trials  # Cache to avoid O(n²) re-creation
    n_trials = len(trials)
    for i, trial in enumerate(trials):
        if trial.value is not None and trial.value > best_so_far:
            best_so_far = trial.value
        if (i + 1) % 10 == 0 or i == n_trials - 1:
            print(f"    Trial {i+1:>4d}: best_so_far={best_so_far:.4f}")

    # Config diff
    print(f"\n--- Best config found ---")
    print(f"  Result: {_fmt_score(best_score)}")

    print("\n  Changes vs DEFAULT:")
    for k in sorted(DEFAULT_CONFIG.keys()):
        default_val = DEFAULT_CONFIG[k]
        new_val = best_config.get(k, default_val)
        if new_val != default_val:
            if isinstance(default_val, float) and isinstance(new_val, float):
                print(f"    {k}: {default_val} -> {new_val:.4f}")
            else:
                print(f"    {k}: {default_val} -> {new_val}")

    if best_config == DEFAULT_CONFIG:
        print("    (no changes — DEFAULT_CONFIG is already optimal)")

    # Top 5 trials
    print(f"\n  Top 5 trials:")
    sorted_trials = sorted(trials, key=lambda t: t.value or float("-inf"), reverse=True)
    for trial in sorted_trials[:5]:
        print(f"    #{trial.number:>3d}: score={trial.value:.4f}")

    # LOGO validation
    print(f"\n--- Leave-One-Game-Out validation ---")
    for label, full, logo, div in logo_results:
        flag = " *** OVERFITTING RISK ***" if abs(div) > 0.03 else ""
        print(f"  {label:20s}  full={full:.3f}  LOGO={logo:.3f}  div={div:+.3f}{flag}")

    # Brilliant stability warning
    total_brilliant_labels = baseline.brilliant_tp + baseline.brilliant_fn
    if total_brilliant_labels < 10:
        print(f"\n  WARNING: Only {total_brilliant_labels} brilliant labels — F1 is inherently unstable")

    # Full config
    print(f"\n{'='*70}")
    print("BEST CONFIG:")
    print(f"{'='*70}")
    print(f"  Score: {best_score.score:.3f} (baseline: {baseline.score:.3f}, delta: {best_score.score - baseline.score:+.3f})")
    print(f"\n  Config dict:")
    for k in sorted(best_config.keys()):
        print(f"    {k!r}: {best_config[k]!r},")

    print(f"\nTotal sweep time: {elapsed:.1f}s")
    print(f"{'='*70}")


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    """Run the full sweep pipeline."""
    import argparse

    parser = argparse.ArgumentParser(description="Optimize classifier with Bayesian search (Optuna TPE)")
    parser.add_argument("--trials", type=int, default=2000,
                        help="Number of Optuna trials (default: 2000)")
    args = parser.parse_args()

    t0 = time.monotonic()

    print("Loading data...")
    data = preload_data()
    t_load = time.monotonic() - t0
    print(f"  {len(data.games)} games, {data.total_moves} moves, "
          f"{len(data.all_motif_names)} motifs ({t_load:.1f}s)")

    print("\nBaseline evaluation...")
    baseline = evaluate_config(DEFAULT_CONFIG, data)
    print(f"  {_fmt_score(baseline)}")

    # Phase 1: Motif screening
    print(f"\nPhase 1: Motif screening...")
    t_screen = time.monotonic()
    motif_results = screen_motifs(data, baseline)
    n_motifs = len(motif_results)
    print(f"  {n_motifs} evaluations ({time.monotonic() - t_screen:.1f}s)")

    # Select motifs that improved score (delta > 0)
    selected_brilliant = [r.motif for r in motif_results if r.role == "brilliant" and r.delta > 0]
    selected_great = [r.motif for r in motif_results if r.role == "great" and r.delta > 0]
    n_selected = len(selected_brilliant) + len(selected_great)
    n_dims = 7 + n_selected
    print(f"  {n_selected} motifs selected → {n_dims}-dimensional search space")

    # Phase 2: Bayesian optimization with TPE
    print(f"\nPhase 2: Optuna TPE ({args.trials} trials, {n_dims} dims)...")
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )

    # Seed with DEFAULT_CONFIG as the first trial
    default_params: dict[str, Any] = {
        "brilliant_epl_max": float(DEFAULT_CONFIG["brilliant_epl_max"]),  # type: ignore[arg-type]
        "brilliant_wp_min": float(DEFAULT_CONFIG["brilliant_wp_min"]),  # type: ignore[arg-type]
        "brilliant_wp_max": float(DEFAULT_CONFIG["brilliant_wp_max"]),  # type: ignore[arg-type]
        "great_epl_max": float(DEFAULT_CONFIG["great_epl_max"]),  # type: ignore[arg-type]
        "great_opp_epl_min": float(DEFAULT_CONFIG["great_opp_epl_min"]),  # type: ignore[arg-type]
        "miss_epl_min": float(DEFAULT_CONFIG["miss_epl_min"]),  # type: ignore[arg-type]
        "miss_opp_epl_min": float(DEFAULT_CONFIG["miss_opp_epl_min"]),  # type: ignore[arg-type]
    }
    for motif in selected_brilliant:
        default_params[f"brilliant_{motif}"] = False
    for motif in selected_great:
        default_params[f"great_{motif}"] = False
    study.enqueue_trial(default_params)

    t_opt = time.monotonic()
    study.optimize(
        create_objective(data, selected_brilliant, selected_great),
        n_trials=args.trials,
        show_progress_bar=False,
    )
    t_opt_elapsed = time.monotonic() - t_opt
    print(f"  {len(study.trials)} trials in {t_opt_elapsed:.1f}s "
          f"({t_opt_elapsed / len(study.trials) * 1000:.0f}ms/trial)")

    # Reconstruct best config
    best_config = _trial_to_config(study.best_trial, selected_brilliant, selected_great)
    best_score = evaluate_config(best_config, data)

    # Phase 3: LOGO cross-validation
    print(f"\nPhase 3: LOGO cross-validation...")
    t_logo = time.monotonic()
    candidates: list[tuple[str, dict[str, Any]]] = [
        ("baseline", copy.deepcopy(DEFAULT_CONFIG)),
        ("best_found", copy.deepcopy(best_config)),
    ]
    logo_results = logo_validate(data, candidates)
    print(f"  {len(candidates)} candidates x {len(data.games)} folds ({time.monotonic() - t_logo:.1f}s)")

    elapsed = time.monotonic() - t0

    print_report(
        baseline=baseline,
        motif_results=motif_results,
        selected_brilliant=selected_brilliant,
        selected_great=selected_great,
        study=study,
        best_config=best_config,
        best_score=best_score,
        logo_results=logo_results,
        elapsed=elapsed,
    )

    # Save results to JSON
    output = {
        "baseline": {
            "score": baseline.score,
            "macro_f1": baseline.macro_f1,
            "brilliant": {"tp": baseline.brilliant_tp, "fp": baseline.brilliant_fp, "fn": baseline.brilliant_fn},
            "great": {"tp": baseline.great_tp, "fp": baseline.great_fp, "fn": baseline.great_fn},
        },
        "best_config": best_config,
        "best_score": best_score.score,
        "best_macro_f1": best_score.macro_f1,
        "delta": best_score.score - baseline.score,
        "logo_results": [
            {"label": label, "full": full, "logo": logo, "divergence": div}
            for label, full, logo, div in logo_results
        ],
        "motif_screening": [
            {"motif": r.motif, "role": r.role, "delta": r.delta}
            for r in motif_results if r.delta > -0.01  # only interesting ones
        ],
        "selected_motifs": {"brilliant": selected_brilliant, "great": selected_great},
        "n_trials": len(study.trials),
        "best_trial": study.best_trial.number,
        "elapsed_seconds": elapsed,
    }

    out_path = pathlib.Path("/tmp/sweep_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
