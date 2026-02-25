"""
스토리지 모듈 – data/jobs.json 읽기/쓰기 및 변경 감지(diff).

이전 실행 결과를 JSON 파일로 영속화하고,
이번 실행 결과와 비교하여 DiffResult를 반환한다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from models import DiffResult, JobPosting

logger = logging.getLogger(__name__)

# 기본 데이터 저장 경로 (리포지토리 루트 기준)
DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.json"


def load_jobs(path: Path = DEFAULT_DATA_PATH) -> list[JobPosting]:
    """저장된 공고 목록을 불러온다.

    파일이 없거나 비어있으면 빈 리스트를 반환한다.
    """
    if not path.exists():
        logger.info("기존 데이터 파일이 없습니다: %s", path)
        return []

    try:
        raw = path.read_text(encoding="utf-8")
        data: list[dict[str, Any]] = json.loads(raw) if raw.strip() else []
        jobs = [JobPosting.from_dict(item) for item in data]
        logger.info("기존 공고 %d건 로드 완료", len(jobs))
        return jobs
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("데이터 파일 파싱 실패: %s", exc)
        return []


def save_jobs(jobs: list[JobPosting], path: Path = DEFAULT_DATA_PATH) -> None:
    """공고 목록을 JSON 파일로 저장한다.

    디렉토리가 없으면 자동 생성한다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [job.to_dict() for job in jobs]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("공고 %d건 저장 완료: %s", len(jobs), path)


def compute_diff(
    previous: list[JobPosting],
    current: list[JobPosting],
) -> DiffResult:
    """이전 공고와 현재 공고를 비교하여 DiffResult를 반환한다.

    고유키(unique_key)를 기준으로 신규/삭제/유지를 판별한다.
    """
    prev_keys = {job.unique_key: job for job in previous}
    curr_keys = {job.unique_key: job for job in current}

    new_jobs = [curr_keys[k] for k in curr_keys if k not in prev_keys]
    removed_jobs = [prev_keys[k] for k in prev_keys if k not in curr_keys]
    unchanged_jobs = [curr_keys[k] for k in curr_keys if k in prev_keys]

    logger.info(
        "변경 감지 결과 – 신규: %d, 삭제: %d, 유지: %d",
        len(new_jobs),
        len(removed_jobs),
        len(unchanged_jobs),
    )
    return DiffResult(
        new_jobs=new_jobs,
        removed_jobs=removed_jobs,
        unchanged_jobs=unchanged_jobs,
    )
