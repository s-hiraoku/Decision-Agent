from __future__ import annotations

import json
import os
from pathlib import Path
from hashlib import sha256
import tempfile
from typing import Any, cast

from decision_agent.models import (
    Alternative,
    ArtifactReview,
    ArtifactReviewRequest,
    DecisionProfile,
    DecisionRecord,
    EvaluationCase,
    EvaluationRun,
    UserFeedback,
)


def load_profile(path: str | Path) -> DecisionProfile:
    return DecisionProfile.from_dict(_load_json(path))


def save_profile(profile: DecisionProfile, path: str | Path) -> None:
    _save_json(profile.to_dict(), path)


def load_request(path: str | Path) -> tuple[str, list[Alternative]]:
    data = _load_json(path)
    context = str(data.get("context", ""))
    alternatives = [Alternative.from_dict(item) for item in data.get("alternatives", [])]
    return context, alternatives


def load_review_request(path: str | Path) -> ArtifactReviewRequest:
    return ArtifactReviewRequest.from_dict(_load_json(path))


def load_review(path: str | Path) -> ArtifactReview:
    return ArtifactReview.from_dict(_load_json(path))


def load_feedback(path: str | Path) -> UserFeedback:
    return UserFeedback.from_dict(_load_json(path))


def load_decision_records(path: str | Path) -> tuple[DecisionRecord, ...]:
    record_path = Path(path)
    if not record_path.exists():
        return ()

    records: list[DecisionRecord] = []
    with record_path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                try:
                    records.append(DecisionRecord.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
    return tuple(records)


def load_legacy_profile_decision_records(path: str | Path) -> tuple[DecisionRecord, ...]:
    data = _load_json(path)
    return tuple(DecisionRecord.from_dict(item) for item in data.get("decision_records", []))


def load_evaluation_cases(path: str | Path) -> tuple[EvaluationCase, ...]:
    cases: list[EvaluationCase] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if line.strip():
                try:
                    cases.append(EvaluationCase.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                    raise ValueError(f"malformed evaluation case row {line_number}: {error}") from error
    return tuple(cases)


def load_evaluation_runs(path: str | Path) -> tuple[EvaluationRun, ...]:
    history_path = Path(path)
    if not history_path.exists():
        return ()

    runs: list[EvaluationRun] = []
    with history_path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                try:
                    runs.append(EvaluationRun.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
    return tuple(runs)


def append_evaluation_run(path: str | Path, run: EvaluationRun) -> None:
    history_path = Path(path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as file:
        json.dump(run.to_dict(), file, ensure_ascii=False)
        file.write("\n")


def previous_evaluation_run(
    runs: tuple[EvaluationRun, ...],
    *,
    cases_fingerprint: str,
    engine: str,
) -> EvaluationRun | None:
    for run in reversed(runs):
        if run.cases_fingerprint == cases_fingerprint and run.engine == engine:
            return run
    return None


def canonical_fingerprint(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_fingerprint(payload.encode("utf-8"))


def file_fingerprint(path: str | Path) -> str:
    return _sha256_fingerprint(Path(path).read_bytes())


def append_decision_record(path: str | Path, record: DecisionRecord) -> None:
    record_path = Path(path)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_fingerprint = _record_fingerprint(record)
    if any(_record_fingerprint(existing) == record_fingerprint for existing in load_decision_records(record_path)):
        return
    with record_path.open("a", encoding="utf-8") as file:
        json.dump(record.to_dict(), file, ensure_ascii=False)
        file.write("\n")


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return {str(key): value for key, value in cast("dict[Any, Any]", data).items()}


def _save_json(data: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output_path.parent,
            delete=False,
        ) as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")
            temp_name = file.name
        os.replace(temp_name, output_path)
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()


def _sha256_fingerprint(payload: bytes) -> str:
    return "sha256:" + sha256(payload).hexdigest()


def _record_fingerprint(record: DecisionRecord) -> str:
    data = record.to_dict()
    data.pop("id", None)
    data.pop("created_at", None)
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()
