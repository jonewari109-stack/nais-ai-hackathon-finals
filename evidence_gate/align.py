"""행 대응 검사: 자료 식별자와 기준 식별자(예: 계통수 종 목록)의 구성·순서 진단."""

from __future__ import annotations


def diagnose(data_ids, reference_ids, limit=20):
    """구성·중복·순서 차이를 식별자 단위로 모두 보고한다. 판정은 하지 않는다."""
    def duplicates(values):
        seen, dup = set(), []
        for v in values:
            if v in seen and v not in dup:
                dup.append(v)
            seen.add(v)
        return dup

    data, reference = list(data_ids), list(reference_ids)
    data_set, reference_set = set(data), set(reference)
    report = {
        "data_count": len(data),
        "reference_count": len(reference),
        "empty_data_positions": [i + 1 for i, v in enumerate(data) if not v.strip()][:limit],
        "duplicate_data_ids": duplicates(data)[:limit],
        "duplicate_reference_ids": duplicates(reference)[:limit],
        "missing_in_data": [v for v in reference if v not in data_set][:limit],
        "extra_in_data": [v for v in data if v not in reference_set][:limit],
        "order_differences": [],
    }
    report["membership_ok"] = not (report["empty_data_positions"] or report["duplicate_data_ids"]
                                   or report["duplicate_reference_ids"] or report["missing_in_data"]
                                   or report["extra_in_data"])
    if report["membership_ok"]:
        diffs = [{"position": i + 1, "data_id": d, "reference_id": r}
                 for i, (d, r) in enumerate(zip(data, reference)) if d != r]
        report["order_differences_count"] = len(diffs)
        report["order_differences"] = diffs[:limit]
    return report


def reorder_indices(data_ids, reference_ids):
    """구성이 같을 때만: 기준 순서대로 자료 행을 놓는 0 기반 위치."""
    position = {v: i for i, v in enumerate(data_ids)}
    return [position[v] for v in reference_ids]
