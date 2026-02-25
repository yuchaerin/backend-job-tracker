"""
MockSource – 테스트/데모용 샘플 소스.

실제 네트워크 호출 없이, companies.yaml에 정의된 기업별로
하드코딩된 예시 데이터를 반환한다.
외부 API 키 없이도 프로젝트 동작을 확인할 수 있다.
"""

from __future__ import annotations

from datetime import date

from config_loader import CompanyConfig
from models import JobPosting
from sources.base import BaseSource

# 기업명 → 예시 공고 매핑 (데모 데이터)
_MOCK_DATA: dict[str, list[dict[str, str]]] = {
    "네이버": [
        {"title": "백엔드 엔지니어 (Java/Kotlin) - 경력 5년 이상", "location": "성남시 분당구"},
        {"title": "서버 플랫폼 개발자 (6년 이상)", "location": "성남시 분당구"},
    ],
    "카카오": [
        {"title": "서버 개발자 (Spring Boot) - 5~7년", "location": "성남시 판교"},
        {"title": "Backend Engineer - 경력 5년", "location": "성남시 판교"},
    ],
    "라인플러스": [
        {"title": "Platform Backend Engineer (5+ years)", "location": "서울시 강남구"},
    ],
    "쿠팡": [
        {"title": "Backend Software Engineer - 경력 6년 이상", "location": "서울시 송파구"},
    ],
    "토스": [
        {"title": "Server Developer (MSA) - 5~7년차", "location": "서울시 강남구"},
    ],
}

# 설정에 없는 기업에 사용할 기본 데이터
_DEFAULT_MOCK = [
    {"title": "백엔드 개발자 - 경력 5년 이상", "location": "서울"},
]


class MockSource(BaseSource):
    """companies.yaml에 등록된 기업별 하드코딩 공고를 반환하는 데모 소스."""

    name = "mock"

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        """기업 설정에 맞는 예시 공고를 반환한다."""
        today = date.today().isoformat()
        mock_items = _MOCK_DATA.get(company.name, _DEFAULT_MOCK)

        return [
            JobPosting(
                source=self.name,
                company=company.name,
                title=item["title"],
                level="5-7년",
                location=item["location"],
                url=f"{company.url}/{i+1}" if company.url else "",
                date_found=today,
            )
            for i, item in enumerate(mock_items)
        ]


# ─────────────────────────────────────────────────────────────
# 새로운 소스를 추가하려면?
#
# 1. 이 파일을 참고하여 src/sources/<source_name>.py 를 생성한다.
# 2. BaseSource 를 상속받고, name 속성과 fetch_company() 메서드를 구현한다.
# 3. src/main.py 의 SOURCE_REGISTRY 딕셔너리에 소스 이름을 등록한다.
# 4. config/companies.yaml 에 해당 소스 이름으로 기업을 추가한다.
#
# 예시: wanted, saramin, linkedin, jumpit 등
# 자세한 가이드는 base.py 상단 docstring과 README.md를 참고하라.
# ─────────────────────────────────────────────────────────────
