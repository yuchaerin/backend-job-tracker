"""
소스 플러그인 추상 클래스.

각 소스는 CompanyConfig 목록을 받아 해당 기업 채용 페이지만 크롤링한다.
경력 필터(ExperienceFilter)로 대상 공고만 걸러낸다.

새로운 채용 사이트를 추가하려면 이 클래스를 상속받아 구현한다.

사용 예시 (Wanted 소스 추가):
─────────────────────────────────
# src/sources/wanted.py

import requests
from sources.base import BaseSource
from models import JobPosting
from config_loader import CompanyConfig

class WantedSource(BaseSource):
    name = "wanted"

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        # 1. company.url (기업 채용 페이지)에 직접 접근
        # 2. 공고 목록을 파싱
        # 3. JobPosting 리스트로 반환
        resp = requests.get(company.url)
        ...
        return [
            JobPosting(
                source=self.name,
                company=company.name,
                title=item["position"],
                location=item["location"],
                url=item["url"],
            )
            for item in parsed_data
        ]
─────────────────────────────────

그 후 src/main.py의 SOURCE_REGISTRY에 등록하면 자동으로 실행된다.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from config_loader import CompanyConfig, ExperienceFilter
from models import JobPosting

logger = logging.getLogger(__name__)

# 네트워크 재시도 기본 설정
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 2  # 지수 백오프 밑


class BaseSource(ABC):
    """채용 공고 소스 추상 클래스.

    Attributes:
        name: 소스 식별 이름 (예: "wanted", "saramin") – companies.yaml의 source와 매칭
        max_retries: 실패 시 최대 재시도 횟수
        backoff_base: 지수 백오프 밑 (초)
    """

    name: str = "unknown"
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base: int = DEFAULT_BACKOFF_BASE

    @abstractmethod
    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        """특정 기업의 채용 공고를 수집하여 반환한다.

        구현 클래스에서 이 메서드를 오버라이드하여
        해당 기업 채용 페이지에 직접 접근하는 로직을 작성한다.

        Args:
            company: 기업 설정 (이름, URL 등)

        Returns:
            수집된 채용 공고 목록
        """
        ...

    def fetch_company_with_retry(self, company: CompanyConfig) -> list[JobPosting]:
        """재시도 로직이 포함된 기업별 수집 메서드.

        지수 백오프(exponential backoff)를 적용하여
        max_retries 회까지 재시도한다.
        """
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                jobs = self.fetch_company(company)
                logger.info(
                    "[%s → %s] 수집 성공 – %d건 (시도 %d/%d)",
                    self.name,
                    company.name,
                    len(jobs),
                    attempt,
                    self.max_retries,
                )
                return jobs
            except Exception as exc:
                last_error = exc
                wait = self.backoff_base ** attempt
                logger.warning(
                    "[%s → %s] 수집 실패 (시도 %d/%d): %s – %d초 후 재시도",
                    self.name,
                    company.name,
                    attempt,
                    self.max_retries,
                    exc,
                    wait,
                )
                if attempt < self.max_retries:
                    time.sleep(wait)

        logger.error(
            "[%s → %s] 최대 재시도 초과. 마지막 오류: %s",
            self.name,
            company.name,
            last_error,
        )
        return []

    def fetch_all_companies(
        self,
        companies: list[CompanyConfig],
        exp_filter: ExperienceFilter | None = None,
        skip_filter: bool = False,
    ) -> list[JobPosting]:
        """할당된 모든 기업의 공고를 수집하고 경력 필터를 적용한다.

        Args:
            companies: 이 소스에 할당된 기업 목록
            exp_filter: 경력 필터 설정 (None이면 필터 안 함)
            skip_filter: True이면 필터를 건너뜀 (mock 소스용)
        """
        all_jobs: list[JobPosting] = []

        for company in companies:
            jobs = self.fetch_company_with_retry(company)
            all_jobs.extend(jobs)

        # 경력 필터 적용
        if exp_filter and exp_filter.enabled and not skip_filter:
            before = len(all_jobs)
            all_jobs = _apply_experience_filter(all_jobs, exp_filter)
            logger.info(
                "[%s] 경력 필터 적용 – %d건 → %d건",
                self.name,
                before,
                len(all_jobs),
            )
        elif skip_filter:
            logger.info("[%s] 경력 필터 건너뜀 (skip_filter=True)", self.name)

        # 필터 통과 공고에 level 라벨 설정
        if exp_filter:
            for job in all_jobs:
                job.level = exp_filter.level_label

        return all_jobs


def _apply_experience_filter(
    jobs: list[JobPosting],
    exp_filter: ExperienceFilter,
) -> list[JobPosting]:
    """경력 키워드 기반으로 공고를 필터링한다.

    공고 제목에 키워드 중 하나라도 포함되면 매칭으로 판단한다.
    """
    filtered: list[JobPosting] = []
    keywords_lower = [kw.lower() for kw in exp_filter.keywords]

    for job in jobs:
        text = f"{job.title} {job.level}".lower()
        if any(kw in text for kw in keywords_lower):
            filtered.append(job)

    return filtered
