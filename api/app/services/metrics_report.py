from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GenerationJob

_TERMINAL_STATUSES = ("done", "failed", "cancelled")


def to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def summarize(values: Iterable[float]) -> dict[str, float]:
    data = [v for v in values if isinstance(v, (int, float))]
    if not data:
        return {}
    return {
        "count": float(len(data)),
        "min": min(data),
        "mean": mean(data),
        "p50": percentile(data, 0.50),
        "p95": percentile(data, 0.95),
        "max": max(data),
    }


def ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def fmt(stat: dict[str, float], unit: str) -> str:
    if not stat:
        return "n/a"
    return (
        f"mean={stat['mean']:.3f}{unit}, "
        f"p50={stat['p50']:.3f}{unit}, "
        f"p95={stat['p95']:.3f}{unit}, "
        f"min={stat['min']:.3f}{unit}, "
        f"max={stat['max']:.3f}{unit}"
    )


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    n = len(vector)
    if n == 0 or len(matrix) != n or any(len(row) != n for row in matrix):
        return None
    aug = [row[:] + [vector[idx]] for idx, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-10:
            return None
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        for k in range(col, n + 1):
            aug[col][k] /= scale
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if factor == 0:
                continue
            for k in range(col, n + 1):
                aug[row][k] -= factor * aug[col][k]
    return [aug[i][n] for i in range(n)]


def fit_complexity_model(samples: list[tuple[float, float, float, float]]) -> dict[str, Any]:
    # y ~ b0 + b1*chars_k + b2*files + b3*questions
    if len(samples) < 6:
        return {"sample_count": len(samples), "ready": False}
    x_rows: list[list[float]] = []
    y_vals: list[float] = []
    for y, chars_k, files, questions in samples:
        x_rows.append([1.0, chars_k, files, questions])
        y_vals.append(y)

    dim = 4
    xtx = [[0.0 for _ in range(dim)] for _ in range(dim)]
    xty = [0.0 for _ in range(dim)]
    for row, y in zip(x_rows, y_vals):
        for i in range(dim):
            xty[i] += row[i] * y
            for j in range(dim):
                xtx[i][j] += row[i] * row[j]

    coeffs = _solve_linear_system(xtx, xty)
    if coeffs is None:
        return {"sample_count": len(samples), "ready": False}

    predictions = [
        coeffs[0] + coeffs[1] * row[1] + coeffs[2] * row[2] + coeffs[3] * row[3]
        for row in x_rows
    ]
    y_mean = mean(y_vals)
    ss_res = sum((y - y_hat) ** 2 for y, y_hat in zip(y_vals, predictions))
    ss_tot = sum((y - y_mean) ** 2 for y in y_vals)
    r2 = 1.0 - ratio(ss_res, ss_tot) if ss_tot > 1e-12 else 0.0
    return {
        "sample_count": len(samples),
        "ready": True,
        "formula": "time_sec ~= b0 + b1*chars_k + b2*files + b3*questions",
        "coefficients": {
            "b0": round(coeffs[0], 6),
            "b1_chars_k": round(coeffs[1], 6),
            "b2_files": round(coeffs[2], 6),
            "b3_questions": round(coeffs[3], 6),
        },
        "r2": round(r2, 6),
    }


async def fetch_jobs(session: AsyncSession, limit: int) -> list[GenerationJob]:
    stmt = (
        select(GenerationJob)
        .where(GenerationJob.status.in_(_TERMINAL_STATUSES))
        .order_by(desc(GenerationJob.created_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def build_report(jobs: list[GenerationJob]) -> tuple[dict[str, Any], str]:
    providers = Counter()
    models = Counter()

    terminal_jobs = len(jobs)
    done_jobs = 0
    failed_jobs = 0
    cancelled_jobs = 0
    rate_limited_failures = 0

    e2e_seconds: list[float] = []
    sec_per_question: list[float] = []
    sec_per_1k_chars: list[float] = []
    quality_score: list[float] = []
    source_coverage_ratio: list[float] = []
    duplicate_rate: list[float] = []
    retries_per_job: list[float] = []
    failed_calls_per_job: list[float] = []
    complexity_samples: list[tuple[float, float, float, float]] = []

    for job in jobs:
        status = (job.status or "").strip().lower()
        if status == "done":
            done_jobs += 1
        elif status == "failed":
            failed_jobs += 1
        elif status == "cancelled":
            cancelled_jobs += 1

        if status == "failed":
            msg = (job.error_message or "").lower()
            if "429" in msg or "rate limit" in msg:
                rate_limited_failures += 1

        data = job.metrics_json or {}
        if not isinstance(data, dict):
            continue

        provider = data.get("llm_provider")
        if isinstance(provider, str) and provider:
            providers[provider] += 1
        model = data.get("llm_model")
        if isinstance(model, str) and model:
            models[model] += 1

        if status != "done":
            continue

        total_elapsed = to_float(data.get("total_elapsed_sec"))
        final_questions = to_float(data.get("final_questions"))
        input_text_chars_total = to_float(data.get("input_text_chars_total"))
        input_files = to_float(data.get("input_files"))
        requested_questions = to_float(data.get("requested_questions"))
        dedupe_removed = to_float(data.get("dedupe_removed"))
        generated_before = to_float(data.get("generated_questions_before_dedupe"))

        if total_elapsed is not None:
            e2e_seconds.append(total_elapsed)
        if total_elapsed is not None and final_questions and final_questions > 0:
            sec_per_question.append(total_elapsed / final_questions)
        if total_elapsed is not None and input_text_chars_total and input_text_chars_total > 0:
            chars_k = input_text_chars_total / 1000.0
            sec_per_1k_chars.append(total_elapsed / chars_k)
            if input_files and requested_questions and requested_questions > 0:
                complexity_samples.append((total_elapsed, chars_k, input_files, requested_questions))

        quality = to_float(data.get("quality_score"))
        if quality is not None:
            quality_score.append(quality)
        source_cov = to_float(data.get("source_coverage_ratio"))
        if source_cov is not None:
            source_coverage_ratio.append(source_cov)
        if dedupe_removed is not None and generated_before and generated_before > 0:
            duplicate_rate.append(dedupe_removed / generated_before)

        agent_metrics = data.get("agent_metrics")
        llm = agent_metrics.get("llm") if isinstance(agent_metrics, dict) else None
        if isinstance(llm, dict):
            retries = to_float(llm.get("retries_total"))
            failed_calls = to_float(llm.get("calls_failed"))
            if retries is not None:
                retries_per_job.append(retries)
            if failed_calls is not None:
                failed_calls_per_job.append(failed_calls)

    completion_rate = ratio(done_jobs, terminal_jobs)
    failed_rate = ratio(failed_jobs, terminal_jobs)
    cancelled_rate = ratio(cancelled_jobs, terminal_jobs)
    rate_limited_failure_rate = ratio(rate_limited_failures, max(1, failed_jobs))
    complexity_model = fit_complexity_model(complexity_samples)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jobs_analyzed": len(jobs),
        "terminal_jobs": terminal_jobs,
        "done_jobs": done_jobs,
        "failed_jobs": failed_jobs,
        "cancelled_jobs": cancelled_jobs,
        "completion_rate": round(completion_rate, 6),
        "failed_rate": round(failed_rate, 6),
        "cancelled_rate": round(cancelled_rate, 6),
        "rate_limited_failure_rate": round(rate_limited_failure_rate, 6),
        "providers": dict(providers),
        "models": dict(models),
        "e2e_seconds": summarize(e2e_seconds),
        "sec_per_question": summarize(sec_per_question),
        "sec_per_1k_chars": summarize(sec_per_1k_chars),
        "quality_score": summarize(quality_score),
        "source_coverage_ratio": summarize(source_coverage_ratio),
        "duplicate_rate": summarize(duplicate_rate),
        "retries_per_job": summarize(retries_per_job),
        "failed_calls_per_job": summarize(failed_calls_per_job),
        "complexity_model": complexity_model,
    }

    markdown_lines = [
        "# Generation Metrics Report",
        f"- Generated (UTC): {summary['generated_at']}",
        f"- Jobs analyzed: {summary['jobs_analyzed']}",
        f"- Providers: {summary['providers']}",
        f"- Models: {summary['models']}",
        "",
        "## Success & Reliability",
        f"- Completion rate: {summary['completion_rate'] * 100:.1f}%",
        f"- Failed rate: {summary['failed_rate'] * 100:.1f}%",
        f"- Cancelled rate: {summary['cancelled_rate'] * 100:.1f}%",
        f"- Rate-limited failures among failed: {summary['rate_limited_failure_rate'] * 100:.1f}%",
        f"- Retries per job: {fmt(summary['retries_per_job'], '')}",
        f"- Failed LLM calls per job: {fmt(summary['failed_calls_per_job'], '')}",
        "",
        "## Speed",
        f"- Time-to-value (E2E): {fmt(summary['e2e_seconds'], 's')}",
        f"- Seconds per question: {fmt(summary['sec_per_question'], 's')}",
        f"- Seconds per 1k chars: {fmt(summary['sec_per_1k_chars'], 's')}",
        "",
        "## Quality",
        f"- Quality score: {fmt(summary['quality_score'], '')}",
        f"- Source coverage ratio: {fmt(summary['source_coverage_ratio'], '')}",
        f"- Duplicate rate: {fmt(summary['duplicate_rate'], '')}",
        "",
        "## Complexity Model",
    ]
    if complexity_model.get("ready"):
        coeffs = complexity_model.get("coefficients", {})
        markdown_lines.append(f"- Formula: {complexity_model['formula']}")
        markdown_lines.append(f"- Samples: {complexity_model['sample_count']}")
        markdown_lines.append(f"- R2: {complexity_model.get('r2')}")
        markdown_lines.append(f"- b0: {coeffs.get('b0')}")
        markdown_lines.append(f"- b1 (chars_k): {coeffs.get('b1_chars_k')}")
        markdown_lines.append(f"- b2 (files): {coeffs.get('b2_files')}")
        markdown_lines.append(f"- b3 (questions): {coeffs.get('b3_questions')}")
    else:
        markdown_lines.append(
            f"- Not enough data to fit model (samples={complexity_model.get('sample_count', 0)}; need >= 6)."
        )
    markdown = "\n".join(markdown_lines)
    return summary, markdown
