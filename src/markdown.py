"""
마크다운 생성 모듈 – JOB_TRACKER.md 파일 생성.

DiffResult와 전체 공고 목록을 받아 구조화된 마크다운 문서를 생성한다.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from models import DiffResult, JobPosting

logger = logging.getLogger(__name__)

# JOB_TRACKER.md 기본 경로
DEFAULT_MD_PATH = Path(__file__).resolve().parent.parent / "JOB_TRACKER.md"

# 신규 공고 섹션에 표시할 최대 건수
MAX_NEW_DISPLAY = 20

# 기술 스택 분석 – 상위 N개 기술만 개별 표시하고 나머지는 '그 외'로 묶는다.
TOP_TECH_COUNT = 5

# bar 차트 최대 블록 수 (가장 많은 기술의 블록 길이)
BAR_MAX_BLOCKS = 30

KST = ZoneInfo("Asia/Seoul")

# ── 기술 키워드 사전 ──────────────────────────────────────────
# (표시명, 매칭 패턴 목록)  – 패턴은 re.IGNORECASE 로 매칭된다.
# 순서가 우선도를 뜻하지 않음; 빈도 기준으로 정렬한다.
TECH_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Java",        [r"\bjava\b"]),
    ("Spring",      [r"\bspring\b", r"\bspring\s*boot\b"]),
    ("Kotlin",      [r"\bkotlin\b"]),
    ("Python",      [r"\bpython\b"]),
    ("Node.js",     [r"\bnode\.?js\b", r"\bnodejs\b", r"\bnest\.?js\b", r"\bnestjs\b"]),
    ("Go",          [r"\bgo\b(?!ogle)", r"\bgolang\b"]),
    ("TypeScript",  [r"\btypescript\b", r"\bts\b"]),
    ("AWS",         [r"\baws\b"]),
    ("Kubernetes",  [r"\bkubernetes\b", r"\bk8s\b"]),
    ("Docker",      [r"\bdocker\b"]),
    ("Kafka",       [r"\bkafka\b"]),
    ("MySQL",       [r"\bmysql\b"]),
    ("PostgreSQL",  [r"\bpostgresql\b", r"\bpostgres\b"]),
    ("MongoDB",     [r"\bmongodb\b", r"\bmongo\b"]),
    ("Redis",       [r"\bredis\b"]),
    ("MSA",         [r"\bmsa\b", r"\bmicro\s*service\b"]),
    ("JPA",         [r"\bjpa\b"]),
    ("React",       [r"\breact\b"]),
    ("GraphQL",     [r"\bgraphql\b"]),
    ("C#",          [r"\bc#\b", r"\b\.net\b"]),
]

# 사전 컴파일된 패턴 캐시
_COMPILED_PATTERNS: list[tuple[str, list[re.Pattern[str]]]] = [
    (name, [re.compile(p, re.IGNORECASE) for p in patterns])
    for name, patterns in TECH_KEYWORDS
]


def _analyze_tech_stack(
    jobs: list[JobPosting],
    top_n: int = TOP_TECH_COUNT,
) -> list[tuple[str, int, float]]:
    """공고 제목에서 기술 키워드를 추출해 빈도를 계산한다.

    Returns:
        [(기술명, 공고수, 퍼센트), ...] 상위 top_n 개 + '그 외' 1건
    """
    total = len(jobs)
    if total == 0:
        return []

    counter: Counter[str] = Counter()
    for job in jobs:
        text = f"{job.title} {job.description}"
        matched: set[str] = set()
        for name, patterns in _COMPILED_PATTERNS:
            if name in matched:
                continue
            for pat in patterns:
                if pat.search(text):
                    matched.add(name)
                    break
        for m in matched:
            counter[m] += 1

    if not counter:
        return []

    ranked = counter.most_common()
    top = ranked[:top_n]
    rest = ranked[top_n:]

    result: list[tuple[str, int, float]] = []
    for name, cnt in top:
        pct = cnt / total * 100
        result.append((name, cnt, pct))

    if rest:
        rest_count = sum(c for _, c in rest)
        rest_pct = rest_count / total * 100
        result.append(("그 외", rest_count, rest_pct))

    return result


def _tech_bar_chart(stats: list[tuple[str, int, float]]) -> list[str]:
    """기술 스택 통계를 마크다운 수평 bar 차트 줄 목록으로 변환한다."""
    if not stats:
        return ["_기술 키워드가 감지되지 않았습니다._"]

    max_pct = max(pct for _, _, pct in stats) if stats else 1
    name_width = max(len(name) for name, _, _ in stats)

    lines: list[str] = ["```"]
    for name, cnt, pct in stats:
        bar_len = int(pct / max_pct * BAR_MAX_BLOCKS) if max_pct > 0 else 0
        bar_len = max(bar_len, 1)  # 최소 1블록
        bar = "\u2588" * bar_len
        label = f"{name:<{name_width}}"
        lines.append(f"  {label}  {bar} {pct:.0f}% ({cnt}건)")
    lines.append("```")
    return lines


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

    # ── Backend 공고 분석 ───────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 📊 Backend 공고 분석")
    lines.append("")
    lines.append(f"> 전체 **{len(sorted_jobs)}건**의 공고에서 언급된 기술 스택 빈도입니다.")
    lines.append("")
    tech_stats = _analyze_tech_stack(sorted_jobs)
    lines.extend(_tech_bar_chart(tech_stats))
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
