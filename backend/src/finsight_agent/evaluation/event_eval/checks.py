from __future__ import annotations

from .models import CheckResult, EventEvalCase, ReplayResult


def run_event_eval_checks(
    case: EventEvalCase,
    result: ReplayResult,
) -> list[CheckResult]:
    """运行首版确定性评测检查。"""

    checks = [
        _check_intent(case, result),
        _check_strategy(case, result),
        _check_degraded(case, result),
        _check_target_count(case, result),
        _check_response_shape(result),
        _check_target_keywords(case, result),
    ]
    return checks


def _check_intent(case: EventEvalCase, result: ReplayResult) -> CheckResult:
    status = "pass" if case.expected_intent == result.actual_intent else "fail"
    return CheckResult(
        check_name="intent_match",
        status=status,
        message=f"expected={case.expected_intent} actual={result.actual_intent}",
    )


def _check_strategy(case: EventEvalCase, result: ReplayResult) -> CheckResult:
    status = "pass" if case.expected_strategy == result.actual_strategy else "fail"
    return CheckResult(
        check_name="strategy_match",
        status=status,
        message=f"expected={case.expected_strategy} actual={result.actual_strategy}",
    )


def _check_degraded(case: EventEvalCase, result: ReplayResult) -> CheckResult:
    if not result.degraded:
        return CheckResult(
            check_name="degraded_policy",
            status="pass",
            message="未发生降级",
        )
    if case.allow_degraded:
        return CheckResult(
            check_name="degraded_policy",
            status="warn",
            message="样本允许降级，当前按告警处理",
        )
    return CheckResult(
        check_name="degraded_policy",
        status="fail",
        message="样本不允许降级，但实际发生降级",
    )


def _check_target_count(case: EventEvalCase, result: ReplayResult) -> CheckResult:
    if result.target_count >= case.min_target_count:
        return CheckResult(
            check_name="target_count",
            status="pass",
            message=f"target_count={result.target_count}",
        )
    return CheckResult(
        check_name="target_count",
        status="fail",
        message=(
            f"target_count={result.target_count} "
            f"< min_target_count={case.min_target_count}"
        ),
    )


def _check_response_shape(result: ReplayResult) -> CheckResult:
    has_summary = bool(result.summary.strip())
    status = "pass" if has_summary else "fail"
    return CheckResult(
        check_name="response_shape",
        status=status,
        message="summary present" if has_summary else "summary missing",
    )


def _check_target_keywords(case: EventEvalCase, result: ReplayResult) -> CheckResult:
    if not case.expected_target_keywords:
        return CheckResult(
            check_name="target_keywords",
            status="warn",
            message="未配置关键词检查",
        )

    joined = " ".join(result.target_keywords + [result.summary])
    matched = [
        keyword for keyword in case.expected_target_keywords if keyword and keyword in joined
    ]
    status = "pass" if matched else "warn"
    return CheckResult(
        check_name="target_keywords",
        status=status,
        message=f"matched={matched}",
    )
