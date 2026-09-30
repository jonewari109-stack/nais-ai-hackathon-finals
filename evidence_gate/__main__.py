"""명령행: python -m evidence_gate check --spec 명세.json --data 자료.csv [--record 기록.jsonl]

종료 코드: 0 MATCH, 2 MISMATCH·NEEDS_REVIEW, 3 BLOCK.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .gate import evaluate
from .record import append_record, reusable_result

EXIT = {"MATCH": 0, "MISMATCH": 2, "NEEDS_REVIEW": 2, "BLOCK": 3}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="evidence_gate")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="명세와 자료로 결정론적 재계산·판정")
    check.add_argument("--spec", required=True, type=Path)
    check.add_argument("--data", required=True, type=Path)
    check.add_argument("--reference-ids", type=Path, help="row_alignment 기준 식별자(한 줄에 하나)")
    check.add_argument("--approve-reorder-by", help="재정렬을 승인한 사람. --approval-basis와 함께 사람이 직접 입력")
    check.add_argument("--approval-basis", help="재정렬 승인 근거")
    check.add_argument("--record", type=Path, help="판정 기록 JSONL(추가만)")
    args = parser.parse_args(argv)

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    data = args.data.read_bytes()
    reference_ids, reference_sha = None, None
    if args.reference_ids:
        raw = args.reference_ids.read_bytes()
        reference_sha = hashlib.sha256(raw).hexdigest()
        reference_ids = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
    approvals = {}
    if args.approve_reorder_by or args.approval_basis:
        approvals["reorder"] = {"approver": args.approve_reorder_by, "basis": args.approval_basis}

    result = evaluate(spec, data, reference_ids=reference_ids, approvals=approvals)
    if args.record:
        prior = reusable_result(args.record, result["spec_sha256"], result["data_sha256"], reference_sha)
        result["prior_run_same_inputs"] = prior["run_id"] if prior else None
        result = append_record(args.record, result, reference_sha256=reference_sha)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
