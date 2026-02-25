"""
LinkedInSource – 링크드인(LinkedIn) 채용 공고 크롤링 소스.

링크드인 기업 채용 페이지에 직접 접근하여 공고를 수집한다.
companies.yaml에서 source: "linkedin"으로 지정된 기업만 처리한다.

링크드인 URL 패턴:
- 기업 채용 페이지: https://www.linkedin.com/company/{company_slug}/jobs/
- 공개 채용 목록: https://www.linkedin.com/jobs/search/?f_C={company_id}

주의사항:
- 링크드인은 로그인 없이 접근 시 제한이 있을 수 있다.
- 공개 채용 페이지(jobs 탭)는 비로그인으로도 일부 접근 가능하다.
- 과도한 요청 시 차단될 수 있으므로 적절한 간격을 유지한다.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

from config_loader import CompanyConfig
from models import JobPosting
from sources.base import BaseSource

logger = logging.getLogger(__name__)

# 요청 헤더 (비로그인 접근)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 링크드인 company slug 추출
_COMPANY_SLUG_PATTERN = re.compile(r"/company/([^/]+)")


class LinkedInSource(BaseSource):
    """링크드인 채용 공고 수집 소스.

    링크드인 기업 채용 페이지에 비로그인으로 접근하여
    공개된 채용 공고 목록을 파싱한다.
    """

    name = "linkedin"

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        """링크드인 기업 채용 페이지에서 공고를 수집한다.

        비로그인 상태에서 접근 가능한 공개 채용 정보를 파싱한다.

        Args:
            company: 기업 설정 (name, url 등)

        Returns:
            수집된 채용 공고 목록
        """
        today = date.today().isoformat()
        jobs: list[JobPosting] = []

        # URL 정규화: /jobs/ 경로 확보
        url = company.url.rstrip("/")
        if not url.endswith("/jobs"):
            url += "/jobs/"
        else:
            url += "/"

        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # ── 공고 목록 파싱 ────────────────────────────────
        # 링크드인 비로그인 기업 채용 페이지의 공고 카드를 찾는다.
        job_cards = (
            soup.select("ul.jobs-search__results-list li")            # 검색 결과
            or soup.select("div.base-card")                           # 기본 카드
            or soup.select("a[data-tracking-control-name*='job']")    # 링크 폴백
        )

        for card in job_cards:
            try:
                # 제목 추출
                title_el = (
                    card.select_one("h3.base-search-card__title")
                    or card.select_one("h3[class*='title']")
                    or card.select_one("span.sr-only")
                )
                title = title_el.get_text(strip=True) if title_el else ""

                if not title:
                    continue

                # 링크 추출
                link_el = (
                    card.select_one("a.base-card__full-link")
                    or card.select_one("a[href*='linkedin.com/jobs']")
                    or (card if card.name == "a" else None)
                )
                href = link_el.get("href", "").split("?")[0] if link_el else ""

                # 위치 추출
                location_el = (
                    card.select_one("span.job-search-card__location")
                    or card.select_one("span[class*='location']")
                )
                location = location_el.get_text(strip=True) if location_el else ""

                # 게시일 추출
                date_el = card.select_one("time[datetime]")
                posted_date = date_el.get("datetime", today) if date_el else today

                jobs.append(
                    JobPosting(
                        source=self.name,
                        company=company.name,
                        title=title,
                        location=location,
                        url=href,
                        date_found=today,
                    )
                )
            except Exception as exc:
                logger.debug("[linkedin → %s] 카드 파싱 실패: %s", company.name, exc)
                continue

        logger.info(
            "[linkedin → %s] 페이지 파싱 완료 – %d건 발견",
            company.name,
            len(jobs),
        )
        return jobs
