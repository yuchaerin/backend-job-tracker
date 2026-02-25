"""
PlaywrightSource – SPA(Single Page Application) 채용 사이트 크롤링 소스.

JavaScript 렌더링이 필요한 채용 페이지(React/Vue/Angular SPA)를
Playwright 헤드리스 브라우저로 렌더링한 후 HTML을 파싱한다.

대상 사이트:
- 카카오 (careers.kakao.com) – React SPA
- LG CNS (careers.lg.com) – React SPA
- 현대오토에버 (recruit.hyundai-autoever.com)
- 롯데이노베이트 (lotteinnovate.com) – Next.js SPA
- 네이버 (recruit.navercorp.com) – SSR + JS 렌더링 필요
- 네이버클라우드/ 네이버파이낸셜 / 네이버웹툰
- 한화인 / 삼성SDS

companies.yaml 설정 예시:
─────────────────────────────────
  - name: "카카오"
    source: "playwright"
    url: "https://careers.kakao.com/jobs"
    selectors:
      job_list: "ul.list_jobs li"
      title: "a.tit_jobs"
      link: "a.tit_jobs"
─────────────────────────────────

selectors를 지정하지 않으면 자동으로 일반적인 패턴을 시도한다.

의존성:
    pip install playwright
    playwright install chromium
"""

from __future__ import annotations

import logging
from datetime import date
from urllib.parse import urljoin, urlparse

from config_loader import CompanyConfig
from models import JobPosting
from sources.base import BaseSource

logger = logging.getLogger(__name__)

# Playwright 가용 여부 플래그
_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning(
        "playwright 패키지가 설치되지 않음. "
        "SPA 사이트 크롤링을 사용하려면: pip install playwright && playwright install chromium"
    )

# selectors 미지정 시 자동으로 시도하는 폴백 셀렉터 목록
_FALLBACK_JOB_LIST = [
    "ul[class*='job'] li",
    "ul[class*='list'] li",
    "div[class*='job'] div[class*='item']",
    "div[class*='recruit'] div[class*='item']",
    "table[class*='job'] tbody tr",
    "table[class*='recruit'] tbody tr",
    "div.card",
    "li.card",
    "div[class*='position'] div[class*='item']",
    "a[class*='job']",
    "a[class*='card']",
]

_FALLBACK_TITLE = [
    "a[class*='title']",
    "a[class*='tit']",
    "h3[class*='title']",
    "h4[class*='title']",
    "strong[class*='title']",
    "span[class*='title']",
    "td.title a",
    "a[href]",
    "strong",
    "h3",
    "h4",
]

_FALLBACK_LINK = [
    "a[href]",
]


class PlaywrightSource(BaseSource):
    """SPA 채용 페이지를 Playwright로 렌더링 후 크롤링하는 소스.

    JavaScript 실행이 필요한 React/Vue/Angular/Next.js 기반 사이트를 지원한다.
    """

    name = "playwright"

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        """Playwright로 채용 페이지를 렌더링하고 공고를 수집한다."""
        if not _PLAYWRIGHT_AVAILABLE:
            logger.error(
                "[playwright → %s] playwright가 설치되지 않아 건너뜀. "
                "pip install playwright && playwright install chromium",
                company.name,
            )
            return []

        today = date.today().isoformat()
        jobs: list[JobPosting] = []
        sel = company.selectors

        try:
            html = self._render_page(company.url)
        except Exception as exc:
            logger.error(
                "[playwright → %s] 페이지 렌더링 실패: %s",
                company.name,
                exc,
            )
            return []

        # BeautifulSoup으로 렌더링된 HTML 파싱
        from bs4 import BeautifulSoup, Tag

        soup = BeautifulSoup(html, "html.parser")

        # ── 1. 공고 목록 컨테이너 찾기 ───────────────────
        job_items: list[Tag] = []

        if "job_list" in sel:
            job_items = soup.select(sel["job_list"])
        else:
            for fallback in _FALLBACK_JOB_LIST:
                job_items = soup.select(fallback)
                if job_items:
                    logger.debug(
                        "[playwright → %s] 폴백 셀렉터 매칭: %s (%d건)",
                        company.name,
                        fallback,
                        len(job_items),
                    )
                    break

        if not job_items:
            logger.warning(
                "[playwright → %s] 공고 항목을 찾지 못함. "
                "selectors.job_list 설정을 확인하세요. (url: %s)",
                company.name,
                company.url,
            )
            return jobs

        # ── 2. 각 항목에서 정보 추출 ────────────────────
        base_url = _extract_base_url(company.url)

        for item in job_items:
            try:
                # 제목 추출 ("자체"이면 컨테이너 자체 텍스트)
                title_sel = sel.get("title")
                if title_sel == "자체":
                    title = item.get_text(strip=True)
                else:
                    title = _extract_text(item, title_sel, _FALLBACK_TITLE)
                if not title:
                    continue

                # 링크 추출 ("자체"이면 컨테이너 자체 href)
                link_sel = sel.get("link")
                if link_sel == "자체":
                    href = item.get("href", "") if item.name == "a" else ""
                else:
                    href = _extract_href(item, link_sel, _FALLBACK_LINK)
                if href and not href.startswith("http"):
                    href = urljoin(company.url, href)

                location = _extract_text(item, sel.get("location"), []) or ""
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
                logger.debug("[playwright → %s] 항목 파싱 실패: %s", company.name, exc)
                continue

        logger.info(
            "[playwright → %s] Playwright 파싱 완료 – %d건 발견",
            company.name,
            len(jobs),
        )
        return jobs

    @staticmethod
    def _render_page(url: str, wait_ms: int = 3000, scroll_count: int = 5) -> str:
        """Playwright로 페이지를 렌더링하고 HTML을 반환한다.

        SPA에서 동적으로 로딩되는 공고를 가져오기 위해
        스크롤 + 대기를 반복한다.

        Args:
            url: 렌더링할 URL
            wait_ms: 각 단계별 대기 시간 (밀리초)
            scroll_count: 스크롤 반복 횟수

        Returns:
            렌더링된 HTML 문자열
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="ko-KR",
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()

            try:
                # networkidle 대기 (타임아웃 시 무시하고 진행)
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception:
                    logger.debug("[playwright] networkidle 타임아웃, 계속 진행")

                # 초기 렌더링 대기
                page.wait_for_timeout(wait_ms)

                # 스크롤로 동적 콘텐츠 로딩 유도
                for _ in range(scroll_count):
                    page.evaluate("window.scrollBy(0, 800)")
                    page.wait_for_timeout(1000)

                # 최종 대기 (AJAX 완료)
                page.wait_for_timeout(wait_ms)

                html = page.content()
            finally:
                context.close()
                browser.close()

        return html


# ── 헬퍼 함수 ─────────────────────────────────────────────────


def _extract_base_url(url: str) -> str:
    """URL에서 base URL(scheme + host)을 추출한다."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _extract_text(container, selector, fallbacks):
    """컨테이너에서 텍스트를 추출한다."""
    if selector:
        el = container.select_one(selector)
        if el:
            return el.get_text(strip=True)

    for fb in fallbacks:
        el = container.select_one(fb)
        if el:
            return el.get_text(strip=True)

    # 컨테이너 자체의 텍스트 (a 태그 등)
    return ""


def _extract_href(container, selector, fallbacks):
    """컨테이너에서 href 링크를 추출한다."""
    # 컨테이너 자체가 a 태그인 경우
    if container.name == "a" and container.get("href"):
        return container["href"]

    if selector:
        el = container.select_one(selector)
        if el and el.get("href"):
            return el["href"]

    for fb in fallbacks:
        el = container.select_one(fb)
        if el and el.get("href"):
            return el["href"]

    return ""
