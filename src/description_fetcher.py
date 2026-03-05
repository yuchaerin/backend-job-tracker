"""
상세 페이지 크롤링 모듈 – 공고의 description(상세 설명)을 보강한다.

각 소스 플러그인의 fetch_description() 메서드에 위임하여
소스별 상세 페이지 크롤링 로직을 수행한다.
이전 실행에서 이미 description이 있는 공고는 건너뛴다.
"""

from __future__ import annotations

import logging
import time

from models import JobPosting
from sources.base import BaseSource

logger = logging.getLogger(__name__)

# 요청 간 딜레이 (초) – 사이트 부하/차단 방지
_REQUEST_DELAY = 0.5


def enrich_descriptions(
    jobs: list[JobPosting],
    source_registry: dict[str, BaseSource],
    company_selectors: dict[str, dict[str, str]] | None = None,
    previous_jobs: list[JobPosting] | None = None,
) -> None:
    """공고 목록에 description을 보강한다 (in-place).

    1. 이전 데이터에 description이 있으면 복사한다.
    2. description이 없는 공고만 해당 소스 플러그인의
       fetch_description()을 호출하여 상세 페이지를 크롤링한다.

    Args:
        jobs: description을 보강할 공고 목록
        source_registry: 소스 이름 → BaseSource 인스턴스 매핑
        company_selectors: 회사 이름 → selectors 딕셔너리 매핑 (companies.yaml에서 로드)
        previous_jobs: 이전 실행의 공고 목록 (description 재활용용)
    """
    company_selectors = company_selectors or {}

    # 이전 description 캐시 (unique_key → description)
    prev_desc: dict[str, str] = {}
    if previous_jobs:
        for job in previous_jobs:
            if job.description:
                prev_desc[job.unique_key] = job.description

    # 이전 데이터에서 description 복사
    need_fetch: list[JobPosting] = []
    for job in jobs:
        if job.description:
            continue
        if job.unique_key in prev_desc:
            job.description = prev_desc[job.unique_key]
        else:
            need_fetch.append(job)

    if not need_fetch:
        logger.info("[description] 모든 공고가 이미 description을 보유함")
        return

    logger.info(
        "[description] %d건의 신규 공고에서 상세 설명 수집 시작",
        len(need_fetch),
    )

    fetched = 0
    for i, job in enumerate(need_fetch, 1):
        source = source_registry.get(job.source)
        if not source:
            continue

        # 해당 회사의 selectors 전달
        selectors = company_selectors.get(job.company, {})
        desc = source.fetch_description(job, selectors=selectors)
        if desc:
            job.description = desc
            fetched += 1

        if i % 20 == 0:
            logger.info(
                "[description] 진행 %d/%d (수집 %d건)",
                i, len(need_fetch), fetched,
            )

        # 요청 간 딜레이
        time.sleep(_REQUEST_DELAY)

    logger.info(
        "[description] 완료 – %d/%d건 상세 설명 수집",
        fetched, len(need_fetch),
    )
