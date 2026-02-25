"""
WantedSource – 원티드(Wanted) 채용 공고 크롤링 소스.

원티드 기업 채용 페이지에 직접 접근하여 백엔드 공고를 수집한다.
companies.yaml에서 source: "wanted"로 지정된 기업만 처리한다.

원티드 URL 패턴:
- 기업 채용 페이지: https://www.wanted.co.kr/company/{company_id}/jobs
- API 엔드포인트: https://www.wanted.co.kr/api/v4/companies/{company_id}/jobs
"""

from __future__ import annotations

import logging
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from config_loader import CompanyConfig
from models import JobPosting
from sources.base import BaseSource

logger = logging.getLogger(__name__)

# 요청 헤더 (봇 차단 우회)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 원티드 기업 ID 추출 패턴
_COMPANY_ID_PATTERN = re.compile(r"/company/(\d+)")


class WantedSource(BaseSource):
    """원티드 채용 공고 수집 소스.

    기업 채용 페이지 URL에서 company_id를 추출하고,
    원티드 웹페이지를 파싱하여 공고 목록을 수집한다.
    """

    name = "wanted"

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        """원티드 기업 채용 페이지에서 공고를 수집한다.

        Args:
            company: 기업 설정 (name, url 등)

        Returns:
            수집된 채용 공고 목록
        """
        today = date.today().isoformat()
        jobs: list[JobPosting] = []

        # 기업 채용 페이지에 접근
        resp = requests.get(
            company.url,
            headers=_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # ── 공고 카드 파싱 ────────────────────────────────
        # 원티드 채용 페이지의 공고 카드를 찾는다.
        # 여러 셀렉터를 시도하여 호환성을 높인다.
        job_cards = (
            soup.select("div.JobCard_container__REty8")       # 2024+ 클래스
            or soup.select("div[class*='JobCard']")           # 유동적 클래스
            or soup.select("a[href*='/wd/']")                 # 링크 기반 폴백
        )

        for card in job_cards:
            try:
                # 제목 추출
                title_el = (
                    card.select_one("p.JobCard_title__HBpZf")
                    or card.select_one("p[class*='title']")
                    or card.select_one("strong")
                )
                title = title_el.get_text(strip=True) if title_el else ""

                if not title:
                    continue

                # 링크 추출
                link_el = card if card.name == "a" else card.select_one("a[href*='/wd/']")
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"https://www.wanted.co.kr{href}"

                # 위치 추출
                location_el = (
                    card.select_one("span.JobCard_location__2EOr5")
                    or card.select_one("span[class*='location']")
                )
                location = location_el.get_text(strip=True) if location_el else ""

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
                logger.debug("[wanted → %s] 카드 파싱 실패: %s", company.name, exc)
                continue

        logger.info(
            "[wanted → %s] 페이지 파싱 완료 – %d건 발견",
            company.name,
            len(jobs),
        )
        return jobs
