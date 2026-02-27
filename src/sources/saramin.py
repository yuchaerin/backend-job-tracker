"""
SaraminSource – 사람인(Saramin) 채용 공고 검색 소스.

사람인 웹 검색 URL에 직접 접근하여 백엔드/자바 경력직 공고를 수집한다.
검색 조건(키워드, 직무코드, 경력 범위)은 config/settings.yaml에서 로드한다.

사람인 검색 URL 패턴:
- 검색: https://www.saramin.co.kr/zf_user/search/recruit?searchType=search&searchword={keywords}&...
"""

from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup

from config_loader import CompanyConfig, SaraminConfig
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

# 사람인 검색 베이스 URL
_SEARCH_BASE = "https://www.saramin.co.kr/zf_user/search/recruit"

# 한 페이지당 최대 건수
_PAGE_COUNT = 40

# 최대 페이지 수 (과도한 요청 방지)
_MAX_PAGES = 3


class SaraminSource(BaseSource):
    """사람인 채용 공고 검색 소스.

    사람인 웹 검색 URL을 통해
    백엔드/자바 경력직 공고를 수집한다.
    """

    name = "saramin"

    def __init__(self, config: SaraminConfig | None = None) -> None:
        self.config = config or SaraminConfig()

    def _build_search_url(self, page: int = 1) -> str:
        """검색 URL을 생성한다.

        Args:
            page: 페이지 번호 (1부터 시작)

        Returns:
            사람인 검색 URL 문자열
        """
        params = {
            "searchType": "search",
            "searchword": self.config.keywords,
            "cat_kewd": self.config.job_cd,       # 직무코드: 84 = 백엔드/서버개발
            "exp_cd": "2",                         # 경력: 2 = 경력
            "exp_min": str(self.config.experience_min),
            "exp_max": str(self.config.experience_max),
            "recruitPage": str(page),
            "recruitSort": "relation",             # 관련도순
            "recruitPageCount": str(_PAGE_COUNT),
        }
        return f"{_SEARCH_BASE}?{urlencode(params)}"

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        """사람인 검색을 통해 공고를 수집한다.

        companies.yaml에 saramin 소스로 등록된 기업이 있으면
        해당 기업과 관련된 공고를 검색 결과에서 추출한다.
        기업 URL이 비어있으면 전체 검색 결과를 반환한다.

        Args:
            company: 기업 설정 (name, url 등)

        Returns:
            수집된 채용 공고 목록
        """
        today = date.today().isoformat()
        all_jobs: list[JobPosting] = []

        for page in range(1, _MAX_PAGES + 1):
            url = self._build_search_url(page=page)

            logger.info(
                "[saramin] 검색 페이지 %d 요청: %s",
                page,
                url[:120] + "...",
            )

            try:
                resp = requests.get(url, headers=_HEADERS, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.warning("[saramin] 페이지 %d 요청 실패: %s", page, exc)
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            page_jobs = self._parse_search_results(soup, company.name, today)

            if not page_jobs:
                logger.info("[saramin] 페이지 %d – 결과 없음, 종료", page)
                break

            all_jobs.extend(page_jobs)
            logger.info(
                "[saramin] 페이지 %d – %d건 수집 (누적 %d건)",
                page,
                len(page_jobs),
                len(all_jobs),
            )

        logger.info(
            "[saramin → %s] 검색 완료 – 총 %d건 발견 (키워드: %s, 경력: %d~%d년)",
            company.name,
            len(all_jobs),
            self.config.keywords,
            self.config.experience_min,
            self.config.experience_max,
        )
        return all_jobs

    def _parse_search_results(
        self,
        soup: BeautifulSoup,
        company_name: str,
        today: str,
    ) -> list[JobPosting]:
        """검색 결과 HTML에서 공고를 파싱한다."""
        jobs: list[JobPosting] = []

        # 검색 결과 아이템 추출
        # 사람인 검색 결과의 공고 아이템 셀렉터
        items = (
            soup.select("div.item_recruit")           # 채용정보 아이템
            or soup.select("div.list_item")            # 리스트 아이템
        )

        for item in items:
            try:
                job = self._parse_item(item, company_name, today)
                if job:
                    jobs.append(job)
            except Exception as exc:
                logger.debug("[saramin] 항목 파싱 실패: %s", exc)
                continue

        return jobs

    def _parse_item(
        self,
        item: object,
        company_name: str,
        today: str,
    ) -> JobPosting | None:
        """개별 공고 아이템을 파싱한다."""
        # 제목 추출
        title_el = (
            item.select_one("h2.job_tit a")
            or item.select_one("a.str_tit")
            or item.select_one("a[title]")
        )
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        if not title:
            return None

        # 링크 추출
        href = title_el.get("href", "")
        if href and not href.startswith("http"):
            href = f"https://www.saramin.co.kr{href}"

        # 회사명 추출
        corp_el = (
            item.select_one("strong.corp_name a")
            or item.select_one("a.corp_name")
            or item.select_one("div.area_corp strong")
        )
        corp_name = corp_el.get_text(strip=True) if corp_el else ""

        # 근무 조건 추출 (경력, 지역 등)
        location = ""
        exp_text = ""

        # job_condition 영역에서 정보 추출
        conditions = item.select("div.job_condition span")
        for cond in conditions:
            text = cond.get_text(strip=True)
            # 지역 정보 (서울, 경기 등)
            if any(loc in text for loc in ["서울", "경기", "인천", "부산", "대구",
                                            "대전", "광주", "울산", "세종", "강원",
                                            "충북", "충남", "전북", "전남", "경북",
                                            "경남", "제주"]):
                location = text
            # 경력 정보
            elif "경력" in text or "년" in text:
                exp_text = text

        # 경력 정보를 제목에 포함 (base.py의 경력 필터에서 활용)
        full_title = f"{title} - {exp_text}" if exp_text else title

        return JobPosting(
            source=self.name,
            company=corp_name or company_name,
            title=full_title,
            location=location,
            url=href,
            date_found=today,
        )
