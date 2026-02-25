"""
SaraminSource – 사람인(Saramin) 채용 공고 크롤링 소스.

사람인 기업 채용 페이지에 직접 접근하여 백엔드 공고를 수집한다.
companies.yaml에서 source: "saramin"으로 지정된 기업만 처리한다.

사람인 URL 패턴:
- 기업 정보(채용공고 탭): https://www.saramin.co.kr/zf_user/company-info/view?csn={company_csn}&tab=recruit
- 기업 채용 목록: https://www.saramin.co.kr/zf_user/jobs/list/job-category?company_cd={company_cd}
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

# 요청 헤더
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.saramin.co.kr/",
}


class SaraminSource(BaseSource):
    """사람인 채용 공고 수집 소스.

    기업 채용 페이지 URL에 직접 접근하여
    채용 중인 공고 목록을 파싱한다.
    """

    name = "saramin"

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        """사람인 기업 채용 페이지에서 공고를 수집한다.

        Args:
            company: 기업 설정 (name, url 등)

        Returns:
            수집된 채용 공고 목록
        """
        today = date.today().isoformat()
        jobs: list[JobPosting] = []

        # URL에 채용공고 탭 파라미터 추가 (없는 경우)
        url = company.url
        if "tab=" not in url and "company-info" in url:
            url += "&tab=recruit" if "?" in url else "?tab=recruit"

        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # ── 채용공고 목록 파싱 ───────────────────────────
        # 사람인 기업 채용 탭의 공고 리스트를 찾는다.
        job_items = (
            soup.select("div.recruit_list div.info_recruit")  # 기업정보 채용탭
            or soup.select("div.list_body div.list_item")     # 채용목록 페이지
            or soup.select("a.str_tit")                       # 제목 링크 폴백
        )

        for item in job_items:
            try:
                # 제목 추출
                title_el = (
                    item.select_one("a.str_tit")
                    or item.select_one("h2.job_tit a")
                    or item.select_one("a[title]")
                )

                if title_el:
                    title = title_el.get_text(strip=True)
                    href = title_el.get("href", "")
                elif item.name == "a":
                    title = item.get_text(strip=True)
                    href = item.get("href", "")
                else:
                    continue

                if not title:
                    continue

                # 절대 URL 변환
                if href and not href.startswith("http"):
                    href = f"https://www.saramin.co.kr{href}"

                # 위치 추출
                location = ""
                loc_el = (
                    item.select_one("p.work_place")
                    or item.select_one("span.work_place")
                    or item.select_one("div.job_condition span:nth-child(1)")
                )
                if loc_el:
                    location = loc_el.get_text(strip=True)

                # 경력 조건 추출 (필터링에 활용)
                exp_text = ""
                exp_el = (
                    item.select_one("p.career")
                    or item.select_one("span.career")
                    or item.select_one("div.job_condition span:nth-child(2)")
                )
                if exp_el:
                    exp_text = exp_el.get_text(strip=True)

                # 경력 조건을 제목에 포함 (필터링 지원)
                full_title = f"{title} - {exp_text}" if exp_text else title

                jobs.append(
                    JobPosting(
                        source=self.name,
                        company=company.name,
                        title=full_title,
                        location=location,
                        url=href,
                        date_found=today,
                    )
                )
            except Exception as exc:
                logger.debug("[saramin → %s] 항목 파싱 실패: %s", company.name, exc)
                continue

        logger.info(
            "[saramin → %s] 페이지 파싱 완료 – %d건 발견",
            company.name,
            len(jobs),
        )
        return jobs
