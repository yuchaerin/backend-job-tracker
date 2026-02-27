"""
WantedSource – 원티드(Wanted) 채용 공고 검색 소스.

원티드 내부 웹 API를 통해 백엔드/자바 경력직 공고를 수집한다.
검색 조건(직군 태그, 경력 범위, 키워드)은 config/settings.yaml에서 로드한다.

원티드 API:
- 엔드포인트: https://www.wanted.co.kr/api/v4/jobs
- 인증 불필요 (웹 브라우저와 동일한 내부 API)
"""

from __future__ import annotations

import logging
from datetime import date

import requests

from config_loader import CompanyConfig, WantedConfig
from models import JobPosting
from sources.base import BaseSource

logger = logging.getLogger(__name__)

# 요청 헤더 (브라우저 위장)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.wanted.co.kr/",
    "wanted-user-country": "KR",
    "wanted-user-language": "ko",
}

# 원티드 API 베이스 URL
_API_BASE = "https://www.wanted.co.kr/api/v4/jobs"

# 공고 상세 페이지 URL 패턴
_JOB_URL_TEMPLATE = "https://www.wanted.co.kr/wd/{job_id}"

# 한 페이지당 건수
_LIMIT = 100

# 최대 페이지 수 (과도한 요청 방지)
_MAX_PAGES = 5


class WantedSource(BaseSource):
    """원티드 채용 공고 검색 소스.

    원티드 내부 웹 API를 통해
    개발 직군의 경력직 공고를 수집하고
    키워드 필터로 백엔드/자바 관련 공고만 추출한다.
    """

    name = "wanted"

    def __init__(self, config: WantedConfig | None = None) -> None:
        self.config = config or WantedConfig()
        # 키워드 리스트 (쉼표 구분 문자열 → 리스트)
        self._keywords = [
            kw.strip().lower()
            for kw in self.config.keywords.split(",")
            if kw.strip()
        ]

    def _build_api_params(self, offset: int = 0) -> dict:
        """API 요청 파라미터를 생성한다."""
        return {
            "tag_type_ids": self.config.tag_type_ids,
            "job_sort": "job.latest_order",
            "years": [self.config.years_min, self.config.years_max],
            "country": "kr",
            "locations": "all",
            "limit": _LIMIT,
            "offset": offset,
        }

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        """원티드 API를 통해 공고를 수집한다.

        검색 결과에서 키워드(자바, 백엔드 등)와 매칭되는 공고만 필터링한다.

        Args:
            company: 기업 설정 (name, url 등)

        Returns:
            수집된 채용 공고 목록
        """
        today = date.today().isoformat()
        all_jobs: list[JobPosting] = []

        for page in range(_MAX_PAGES):
            offset = page * _LIMIT
            params = self._build_api_params(offset=offset)

            logger.info(
                "[wanted] API 요청 – offset: %d, limit: %d",
                offset,
                _LIMIT,
            )

            try:
                resp = requests.get(
                    _API_BASE,
                    params=params,
                    headers=_HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                logger.warning("[wanted] API 요청 실패 (offset=%d): %s", offset, exc)
                break
            except ValueError as exc:
                logger.warning("[wanted] JSON 파싱 실패: %s", exc)
                break

            job_list = data.get("data", [])
            if not job_list:
                logger.info("[wanted] offset %d – 결과 없음, 종료", offset)
                break

            # 각 공고를 파싱하고 키워드 필터 적용
            page_jobs = self._parse_jobs(job_list, company.name, today)
            all_jobs.extend(page_jobs)

            logger.info(
                "[wanted] offset %d – 전체 %d건 중 키워드 매칭 %d건 (누적 %d건)",
                offset,
                len(job_list),
                len(page_jobs),
                len(all_jobs),
            )

            # 다음 페이지 없으면 종료
            if not data.get("links", {}).get("next"):
                break

        logger.info(
            "[wanted → %s] 검색 완료 – 총 %d건 (경력: %d~%d년, 키워드: %s)",
            company.name,
            len(all_jobs),
            self.config.years_min,
            self.config.years_max,
            self.config.keywords,
        )
        return all_jobs

    def _parse_jobs(
        self,
        job_list: list[dict],
        company_name: str,
        today: str,
    ) -> list[JobPosting]:
        """API 응답의 공고 목록을 파싱하고 키워드 필터를 적용한다."""
        jobs: list[JobPosting] = []

        for item in job_list:
            try:
                job = self._parse_item(item, company_name, today)
                if job:
                    jobs.append(job)
            except Exception as exc:
                logger.debug("[wanted] 항목 파싱 실패: %s", exc)
                continue

        return jobs

    def _parse_item(
        self,
        item: dict,
        default_company: str,
        today: str,
    ) -> JobPosting | None:
        """개별 공고 데이터를 파싱한다.

        키워드 필터를 적용하여 백엔드/자바 관련 공고만 반환한다.
        """
        position = item.get("position", "").strip()
        if not position:
            return None

        # 키워드 필터 적용 (제목에 키워드 중 하나라도 포함되어야 함)
        if self._keywords:
            text_lower = position.lower()
            if not any(kw in text_lower for kw in self._keywords):
                return None

        # 회사명
        company_data = item.get("company", {})
        corp_name = company_data.get("name", default_company)

        # 공고 ID → 상세 URL
        job_id = item.get("id")
        url = _JOB_URL_TEMPLATE.format(job_id=job_id) if job_id else ""

        # 위치 정보
        address = item.get("address", {})
        location = address.get("location", "")
        district = address.get("district", "")
        full_location = f"{location} {district}".strip() if district else location

        # 경력 범위를 제목에 포함 (base.py의 경력 필터에서 활용)
        annual_from = item.get("annual_from", 0)
        annual_to = item.get("annual_to", 0)
        exp_text = ""
        if annual_from or annual_to:
            if annual_to >= 100:
                exp_text = f"경력 {annual_from}년 이상"
            else:
                exp_text = f"경력 {annual_from}~{annual_to}년"

        full_title = f"{position} - {exp_text}" if exp_text else position

        return JobPosting(
            source=self.name,
            company=corp_name,
            title=full_title,
            location=full_location,
            url=url,
            date_found=today,
        )
