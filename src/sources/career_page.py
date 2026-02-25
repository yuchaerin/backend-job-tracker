"""
CareerPageSource – 회사 공식 채용 페이지 범용 크롤링 소스.

회사가 자체 채용 사이트에 올린 공고를 직접 크롤링한다.
companies.yaml에서 source: "career"로 지정하고,
selectors에 CSS 셀렉터를 정의하면 어떤 사이트든 대응 가능하다.

companies.yaml 설정 예시:
─────────────────────────────────
companies:
  - name: "삼성SDS"
    source: "career"
    url: "https://www.samsungsds.com/kr/careers/jobs.html"
    selectors:
      job_list: "ul.job-list li"         # 공고 항목 컨테이너
      title: "a.job-title"              # 제목 (텍스트 추출)
      link: "a.job-title"              # 링크 (href 추출)
      location: "span.location"         # 근무지 (선택)
      experience: "span.career"         # 경력 조건 (선택)

  - name: "LG CNS"
    source: "career"
    url: "https://recruit.lgcns.com/careers"
    selectors:
      job_list: "div.recruit-list div.item"
      title: "h3.title"
      link: "a"
      location: "span.place"
─────────────────────────────────

selectors를 지정하지 않으면 일반적인 패턴을 자동으로 시도한다.
"""

from __future__ import annotations

import logging
from datetime import date

import requests
from bs4 import BeautifulSoup, Tag

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
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# selectors 미지정 시 자동으로 시도하는 폴백 셀렉터 목록
_FALLBACK_JOB_LIST = [
    "ul.job-list li",
    "div.recruit-list div.item",
    "table.job-table tbody tr",
    "div[class*='job'] div[class*='item']",
    "ul[class*='recruit'] li",
    "div[class*='career'] div[class*='list'] li",
    "div[class*='vacancy'] div[class*='item']",
]

_FALLBACK_TITLE = [
    "a[class*='title']",
    "h3[class*='title']",
    "h4[class*='title']",
    "a.str_tit",
    "td.title a",
    "a[href]",
    "strong",
]

_FALLBACK_LINK = [
    "a[href]",
]


class CareerPageSource(BaseSource):
    """회사 공식 채용 페이지 범용 크롤링 소스.

    companies.yaml의 selectors 설정으로 다양한 사이트 구조에 대응한다.
    selectors가 없으면 일반적인 CSS 패턴을 자동 시도한다.
    """

    name = "career"

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        """회사 공식 채용 페이지에서 공고를 수집한다.

        Args:
            company: 기업 설정 (name, url, selectors 등)

        Returns:
            수집된 채용 공고 목록
        """
        today = date.today().isoformat()
        jobs: list[JobPosting] = []
        sel = company.selectors  # YAML에서 정의한 셀렉터

        resp = requests.get(company.url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # ── 1. 공고 목록 컨테이너 찾기 ───────────────────
        job_items: list[Tag] = []

        if "job_list" in sel:
            # 사용자 지정 셀렉터 사용
            job_items = soup.select(sel["job_list"])
        else:
            # 폴백: 여러 패턴 시도
            for fallback in _FALLBACK_JOB_LIST:
                job_items = soup.select(fallback)
                if job_items:
                    logger.debug(
                        "[career → %s] 폴백 셀렉터 매칭: %s (%d건)",
                        company.name,
                        fallback,
                        len(job_items),
                    )
                    break

        if not job_items:
            logger.warning(
                "[career → %s] 공고 항목을 찾지 못함. selectors.job_list 설정을 확인하세요.",
                company.name,
            )
            return jobs

        # ── 2. 각 항목에서 정보 추출 ────────────────────
        base_url = _extract_base_url(company.url)

        for item in job_items:
            try:
                # 제목 추출
                title = _extract_text(item, sel.get("title"), _FALLBACK_TITLE)
                if not title:
                    continue

                # 링크 추출
                href = _extract_href(item, sel.get("link"), _FALLBACK_LINK)
                if href and not href.startswith("http"):
                    href = f"{base_url}{href}" if href.startswith("/") else f"{base_url}/{href}"

                # 위치 추출
                location = _extract_text(item, sel.get("location"), []) or ""

                # 경력 조건 추출 (필터링에 활용)
                exp_text = _extract_text(item, sel.get("experience"), []) or ""
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
                logger.debug("[career → %s] 항목 파싱 실패: %s", company.name, exc)
                continue

        logger.info(
            "[career → %s] 페이지 파싱 완료 – %d건 발견",
            company.name,
            len(jobs),
        )
        return jobs


# ── 헬퍼 함수 ─────────────────────────────────────────────────


def _extract_base_url(url: str) -> str:
    """URL에서 base URL(scheme + host)을 추출한다."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _extract_text(
    container: Tag,
    selector: str | None,
    fallbacks: list[str],
) -> str:
    """컨테이너에서 텍스트를 추출한다.

    지정 셀렉터 → 폴백 셀렉터 순으로 시도한다.
    """
    if selector:
        el = container.select_one(selector)
        if el:
            return el.get_text(strip=True)

    for fb in fallbacks:
        el = container.select_one(fb)
        if el:
            return el.get_text(strip=True)

    return ""


def _extract_href(
    container: Tag,
    selector: str | None,
    fallbacks: list[str],
) -> str:
    """컨테이너에서 href 링크를 추출한다."""
    if selector:
        el = container.select_one(selector)
        if el and el.get("href"):
            return el["href"]

    for fb in fallbacks:
        el = container.select_one(fb)
        if el and el.get("href"):
            return el["href"]

    return ""
