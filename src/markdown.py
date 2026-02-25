"""
마크다운 생성 모듈 – JOB_TRACKER.md 파일 생성.

DiffResult와 전체 공고 목록을 받아 구조화된 마크다운 문서를 생성한다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from models import DiffResult, JobPosting

logger = logging.getLogger(__name__)

# JOB_TRACKER.md 기본 경로
DEFAULT_MD_PATH = Path(__file__).resolve().parent.parent / "JOB_TRACKER.md"

# 신규 공고 섹션에 표시할 최대 건수
MAX_NEW_DISPLAY = 20

KST = ZoneInfo("Asia/Seoul")


def _job_table_row(job: JobPosting) -> str:
    """공고 1건을 마크다운 테이블 행으로 변환한다."""
    link = f"[링크]({job.url})" if job.url else "-"
    return (
        f"| {job.date_found} | {job.source} | {job.company} "
        f"| {job.title} | {job.level} | {job.location} | {link} |"
    )


def _table_header() -> str:
    """마크다운 테이블 헤더를 반환한다."""
    return (
        "| DateFound | Source | Company | Title | Level | Location | Link |\n"
        "|-----------|--------|---------|-------|-------|----------|------|"
    )


def generate_markdown(
    diff: DiffResult,
    all_jobs: list[JobPosting],
) -> str:
    """JOB_TRACKER.md 전체 내용을 생성한다.

    Args:
        diff: 이번 실행의 변경 감지 결과
        all_jobs: 최신순으로 정렬된 전체 공고 목록
    """
    now_kst = datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M:%S KST")

    # 최신순 정렬
    sorted_jobs = sorted(all_jobs, key=lambda j: j.date_found, reverse=True)

    lines: list[str] = []

    # ── 상단 프로젝트 설명 ──────────────────────────
    lines.append("# 📋 백엔드 이직공고 트래커")
    lines.append("")
    lines.append("> **백엔드 5~7년차 이직공고**를 자동으로 수집하여 정리합니다.")
    lines.append(">")
    lines.append("> - 실행 스케줄: 매일 **12:00 / 18:00 (KST)** (GitHub Actions)")
    lines.append(f"> - 마지막 업데이트: `{now_kst}`")
    lines.append(f"> - 전체 공고 수: **{len(sorted_jobs)}건**")
    lines.append("")

    # ── New (최근 추가) ─────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 🆕 New (최근 추가)")
    lines.append("")
    if diff.new_jobs:
        display = diff.new_jobs[:MAX_NEW_DISPLAY]
        lines.append(f"> 이번 실행에서 **{len(diff.new_jobs)}건**의 신규 공고가 발견되었습니다.")
        if len(diff.new_jobs) > MAX_NEW_DISPLAY:
            lines.append(f"> (상위 {MAX_NEW_DISPLAY}건만 표시)")
        lines.append("")
        lines.append(_table_header())
        for job in display:
            lines.append(_job_table_row(job))
    else:
        lines.append("_이번 실행에서 신규 공고가 없습니다._")
    lines.append("")

    # ── All Jobs (전체) ─────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 📑 All Jobs (전체)")
    lines.append("")
    if sorted_jobs:
        lines.append(_table_header())
        for job in sorted_jobs:
            lines.append(_job_table_row(job))
    else:
        lines.append("_수집된 공고가 없습니다._")
    lines.append("")

    return "\n".join(lines)


def write_markdown(
    diff: DiffResult,
    all_jobs: list[JobPosting],
    path: Path = DEFAULT_MD_PATH,
) -> None:
    """마크다운 파일을 생성/덮어쓴다."""
    content = generate_markdown(diff, all_jobs)
    path.write_text(content, encoding="utf-8")
    logger.info("JOB_TRACKER.md 갱신 완료: %s", path)
