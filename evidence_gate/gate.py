"""명세 + 자료 → 판정. MATCH / MISMATCH / BLOCK / NEEDS_REVIEW.

- BLOCK: 명세 미완성·근거 위치 없음·자료 지문 불일치·자료 문제로 계산할 수 없음
- NEEDS_REVIEW: 회귀 계수는 맞지만 표준오차·t·자유도가 다름
사람 승인은 approvals로만 들어오며 자동으로 만들지 않는다.
"""

from __future__ import annotations

import hashlib

from . import align, compute
from .compute import GateError
from .spec import spec_sha256, validate


def _within(computed, reported, tolerance):
    return abs(computed - reported) <= tolerance


def _result(spec, data_sha, verdict, reason, **extra):
    return {"claim_id": spec.get("claim_id") if isinstance(spec, dict) else None,
            "method": spec.get("method") if isinstance(spec, dict) else None,
            "verdict": verdict, "reason_code": reason,
            "spec_sha256": spec_sha256(spec) if isinstance(spec, dict) else None,
            "data_sha256": data_sha, **extra}


def evaluate(spec, data, *, reference_ids=None, approvals=None):
    """data는 원자료 바이트. reference_ids는 row_alignment 기준 식별자 목록."""
    approvals = approvals or {}
    data_sha = hashlib.sha256(data).hexdigest()
    check = validate(spec)
    if not check["ready"]:
        return _result(spec, data_sha, "BLOCK", "SPEC_NOT_READY", validation=check)
    if spec["data_fingerprint"] != data_sha:
        return _result(spec, data_sha, "BLOCK", "STALE_DATA",
                       message="명세에 등록된 자료 지문과 현재 자료 바이트가 다름. 이전 결과를 쓰지 말고 다시 확인해야 함",
                       registered_sha256=spec["data_fingerprint"])
    try:
        header, rows = compute.read_csv(data)
        selected = compute.select_rows(header, rows, spec["filters"])
        method = spec["method"]
        if method == "row_count":
            return _scalar(spec, data_sha, len(selected), {"rows_selected": len(selected)})
        if method == "mean":
            table, info = compute.numeric_table(header, selected, [spec["variable"]],
                                                spec["missing_tokens"], spec["missing_policy"])
            return _scalar(spec, data_sha, compute.mean([r[0] for r in table]), info)
        if method == "ols_regression":
            table, info = compute.numeric_table(header, selected, [spec["outcome"], *spec["predictors"]],
                                                spec["missing_tokens"], spec["missing_policy"])
            return _ols(spec, data_sha, compute.ols(table, spec["predictors"]), info)
        return _alignment(spec, data_sha, header, selected, reference_ids, approvals)
    except GateError as exc:
        return _result(spec, data_sha, "BLOCK", exc.code, message=str(exc), details=exc.details)


def _scalar(spec, data_sha, value, info):
    verdict = "MATCH" if _within(value, spec["reported_value"], spec["tolerance"]) else "MISMATCH"
    return _result(spec, data_sha, verdict, "COMPUTED", computed=value,
                   reported=spec["reported_value"], tolerance=spec["tolerance"], details=info)


def _ols(spec, data_sha, fit, info):
    tolerance, comparisons = spec["tolerance"], []
    coefficient_ok, other_ok = True, True
    for term, reported in spec["reported"].items():
        computed = fit["terms"][term]
        row = {"term": term}
        for stat in ("b", "se", "t"):
            if reported[stat] is None:
                continue
            ok = computed[stat] is not None and _within(computed[stat], reported[stat], tolerance)
            row[stat] = {"computed": computed[stat], "reported": reported[stat], "match": ok}
            if stat == "b":
                coefficient_ok &= ok
            else:
                other_ok &= ok
        comparisons.append(row)
    df_match = None if spec["reported_df"] is None else spec["reported_df"] == fit["df"]
    if not coefficient_ok:
        verdict, reason = "MISMATCH", "COEFFICIENT_MISMATCH"
    elif not other_ok or df_match is False:
        verdict, reason = "NEEDS_REVIEW", "COEFFICIENT_MATCH_OTHER_DIFFERS"
    else:
        verdict, reason = "MATCH", "COMPUTED"
    return _result(spec, data_sha, verdict, reason, computed={"terms": fit["terms"], "df": fit["df"], "n": fit["n"]},
                   comparisons=comparisons, df={"computed": fit["df"], "reported": spec["reported_df"], "match": df_match},
                   tolerance=tolerance, details=info)


def _alignment(spec, data_sha, header, selected, reference_ids, approvals):
    if reference_ids is None:
        raise GateError("REFERENCE_MISSING", "기준 식별자 목록이 주어지지 않음")
    column = spec["data_id_column"]
    if column not in header:
        raise GateError("COLUMN_NOT_FOUND", "식별자 열이 자료에 없음", {"columns": [column]})
    data_ids = [row[column] for _, row in selected]
    report = align.diagnose(data_ids, reference_ids)
    if not report["membership_ok"]:
        return _result(spec, data_sha, "BLOCK", "ROW_MEMBERSHIP_MISMATCH", details=report)
    if data_ids == list(reference_ids):
        return _result(spec, data_sha, "MATCH", "ROWS_ALIGNED", details=report)
    approval = approvals.get("reorder")
    if not (isinstance(approval, dict) and approval.get("approver") and approval.get("basis")):
        return _result(spec, data_sha, "BLOCK", "ROW_ORDER_REORDER_REQUIRED",
                       message="구성은 같지만 순서가 다름. 식별자 기준 재정렬을 사람이 승인해야 계산을 이어갈 수 있음",
                       details=report)
    return _result(spec, data_sha, "MATCH", "ROWS_REORDERED_WITH_APPROVAL", details=report,
                   approval={"type": "reorder", "approver": approval["approver"], "basis": approval["basis"]},
                   reorder_indices=align.reorder_indices(data_ids, reference_ids))
