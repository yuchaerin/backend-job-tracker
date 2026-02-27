"""
메인 실행 모듈.

config/companies.yaml에 정의된 기업 목록을 기반으로
각 소스 플러그인을 통해 채용 공고를 수집하고,
이전 데이터와 비교(diff) 후 JOB_TRACKER.md와 data/jobs.json을 갱신한다.
신규 공고가 있고 이메일이 활성화된 경우 알림을 발송한다.

실행:
    python src/main.py
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from pathlib import Path

# ── sys.path에 src 디렉토리 추가 (패키지 임포트 지원) ──────────
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config_loader import AppSettings, CompanyConfig, load_app_settings
from markdown import write_markdown
from models import JobPosting
from notify.emailer import send_email
from sources.base import BaseSource
from sources.career_page import CareerPageSource
from sources.greetinghr import GreetingHRSource
from sources.linkedin import LinkedInSource
from sources.mock_source import MockSource
from sources.playwright_source import PlaywrightSource
from sources.saramin import SaraminSource
from sources.wanted import WantedSource
from storage import compute_diff, load_jobs, save_jobs

# ── 로깅 설정 ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 소스 레지스트리 ────────────────────────────────────────────
# 소스 이름(companies.yaml의 source 필드)과 소스 인스턴스를 매핑한다.
# 새 소스를 추가하면 여기에 등록하라.
# saramin/wanted는 설정 의존적이므로 build_source_registry()에서 초기화된다.
_STATIC_SOURCES: dict[str, BaseSource] = {
    "mock": MockSource(),
    "linkedin": LinkedInSource(),
    "career": CareerPageSource(),        # 회사 공식 채용 페이지 범용 크롤러
    "greetinghr": GreetingHRSource(),    # GreetingHR 플랫폼 (카카오페이 등)
    "playwright": PlaywrightSource(),    # SPA 사이트 (JS 렌더링 필요)
}


def build_source_registry(settings: AppSettings) -> dict[str, BaseSource]:
    """설정에 따라 소스 레지스트리를 생성한다."""
    registry = dict(_STATIC_SOURCES)
    registry["saramin"] = SaraminSource(config=settings.saramin_config)
    registry["wanted"] = WantedSource(config=settings.wanted_config)
    return registry


def collect_all(settings: AppSettings) -> list[JobPosting]:
    """설정에 따라 모든 소스에서 공고를 수집하여 합친다.

    1. companies.yaml의 기업을 source별로 그룹핑한다.
    2. 각 소스 플러그인에 해당 기업 목록을 전달한다.
    3. 경력 필터를 적용한다.
    4. 중복을 제거한다.
    """
    # 기업을 소스별로 그룹핑
    source_groups: dict[str, list[CompanyConfig]] = defaultdict(list)
    for company in settings.companies:
        source_groups[company.source].append(company)

    # 설정 기반 소스 레지스트리 생성
    source_registry = build_source_registry(settings)

    all_jobs: list[JobPosting] = []

    for source_name, companies in source_groups.items():
        source = source_registry.get(source_name)
        if source is None:
            logger.warning(
                "소스 '%s'가 레지스트리에 없음 – 해당 기업 %d개 건너뜀: %s",
                source_name,
                len(companies),
                [c.name for c in companies],
            )
            continue

        logger.info(
            "━━━ [%s] 수집 시작 – 기업 %d개 ━━━",
            source_name,
            len(companies),
        )

        # mock 소스는 필터 건너뛰기 설정 적용
        skip_filter = settings.mock_skip_filter if source_name == "mock" else False

        jobs = source.fetch_all_companies(
            companies=companies,
            exp_filter=settings.experience_filter,
            skip_filter=skip_filter,
        )
        all_jobs.extend(jobs)

    # 중복 제거 (unique_key 기준, 먼저 나온 것 유지)
    seen: dict[str, JobPosting] = {}
    for job in all_jobs:
        if job.unique_key not in seen:
            seen[job.unique_key] = job
    deduped = list(seen.values())

    logger.info(
        "전체 수집 완료 – 원본: %d건, 중복 제거 후: %d건",
        len(all_jobs),
        len(deduped),
    )
    return deduped


def run() -> None:
    """메인 실행 흐름."""
    logger.info("=" * 60)
    logger.info("백엔드 이직공고 트래커 실행 시작")
    logger.info("=" * 60)

    # 0. 설정 로드
    settings = load_app_settings()

    if not settings.companies:
        logger.warning("config/companies.yaml에 기업이 없습니다. 종료합니다.")
        return

    # 1. 이전 데이터 로드
    previous_jobs = load_jobs()

    # 2. 모든 소스에서 수집
    current_jobs = collect_all(settings)

    # 3. 변경 감지
    diff = compute_diff(previous_jobs, current_jobs)

    # 4. 전체 목록 = 신규 + 유지 (삭제된 것은 제외)
    all_current = diff.all_current_jobs

    # 5. 데이터 저장
    save_jobs(all_current)

    # 6. JOB_TRACKER.md 갱신
    write_markdown(diff, all_current)

    # 7. 이메일 알림 (신규 공고가 있을 때만)
    if diff.new_jobs:
        send_email(diff.new_jobs)

    # 8. 요약 출력
    logger.info("=" * 60)
    logger.info(
        "실행 완료 – 신규: %d건, 삭제: %d건, 유지: %d건, 전체: %d건",
        len(diff.new_jobs),
        len(diff.removed_jobs),
        len(diff.unchanged_jobs),
        len(all_current),
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
