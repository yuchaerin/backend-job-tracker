"""
GreetingHR Source – GreetingHR 플랫폼 기반 채용 페이지 크롤링 소스.

카카오페이, 카카오모빌리티, 카카오게임즈 등 GreetingHR을 사용하는
기업의 채용 공고를 수집한다.

GreetingHR 사이트 HTML 구조:
─────────────────────────────────
<ul class="sc-xxx">
  <a href="/ko/o/196005">         ← 공고 링크
    <li class="sc-xxx">            ← 카드 컨테이너
      <div>
        <span class="sc-xxx">     ← 공고 제목
        </span>
      </div>
      <div class="sc-xxx">        ← 경력/직군/고용형태 정보
        <span>비즈니스</span>
        <span>경력 3년 이상</span>
        <span>정규직</span>
        <span>카카오페이</span>
      </div>
    </li>
  </a>
</ul>
─────────────────────────────────

companies.yaml 설정 예시:
  - name: "카카오페이"
    source: "greetinghr"
    url: "https://kakaopay.career.greetinghr.com/ko/main"
"""

from __future__ import annotations

import logging
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config_loader import CompanyConfig
from models import JobPosting
from sources.base import BaseSource

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class GreetingHRSource(BaseSource):
    """GreetingHR 플랫폼 기반 채용 페이지 크롤링 소스.

    카카오페이, 카카오모빌리티, 카카오게임즈 등 GreetingHR을 사용하는
    기업의 채용 공고를 수집한다.
    """

    name = "greetinghr"

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        """GreetingHR 채용 페이지에서 공고를 수집한다."""
        today = date.today().isoformat()
        jobs: list[JobPosting] = []

        resp = requests.get(company.url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # ── 공고 링크 찾기: href에 "/ko/o/" 패턴 ──────────
        job_links = soup.find_all("a", href=lambda h: h and "/ko/o/" in h)

        if not job_links:
            logger.warning(
                "[greetinghr → %s] 공고 링크를 찾지 못함 (url: %s)",
                company.name,
                company.url,
            )
            return jobs

        base_url = f"{resp.url.split('/ko/')[0]}" if "/ko/" in resp.url else resp.url.rsplit("/", 1)[0]

        for link_tag in job_links:
            try:
                href = link_tag.get("href", "")
                full_url = urljoin(company.url, href)

                # 카드 내부에서 정보 추출
                # 첫 번째 span (클래스에 title 관련 패턴) = 공고 제목
                spans = link_tag.find_all("span")
                if not spans:
                    continue

                title = spans[0].get_text(strip=True)
                if not title:
                    continue

                # 나머지 span 들에서 경력/직군/고용형태 추출
                # GreetingHR 구조: [제목, 직군, 경력, 고용형태, 회사명] 순
                meta_texts = [s.get_text(strip=True) for s in spans[1:] if s.get_text(strip=True)]

                # 경력 정보 추출 (예: "경력 3년 이상", "신입")
                experience = ""
                for text in meta_texts:
                    if any(kw in text for kw in ["경력", "신입", "년 이상", "년이상"]):
                        experience = text
                        break

                # 직군/카테고리 추출 (보통 첫 번째 meta 텍스트)
                category = meta_texts[0] if meta_texts else ""

                # 제목에 경력 정보 추가 (필터링에 활용)
                full_title = f"{title} - {experience}" if experience else title

                jobs.append(
                    JobPosting(
                        source=self.name,
                        company=company.name,
                        title=full_title,
                        location=category,  # 직군/카테고리를 location에 저장
                        url=full_url,
                        date_found=today,
                    )
                )
            except Exception as exc:
                logger.debug("[greetinghr → %s] 항목 파싱 실패: %s", company.name, exc)
                continue

        logger.info(
            "[greetinghr → %s] GreetingHR 파싱 완료 – %d건 발견",
            company.name,
            len(jobs),
        )
        return jobs
