"""
데이터 모델 정의 모듈.

채용 공고(JobPosting)의 구조를 정의하고,
직렬화/역직렬화 및 고유키 해시 생성 로직을 포함한다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class JobPosting:
    """채용 공고 데이터 모델.

    Attributes:
        source: 공고 출처 (예: Wanted, Saramin, LinkedIn)
        company: 회사명
        title: 공고 제목
        level: 경력 수준 (예: "5-7년")
        location: 근무 지역
        url: 공고 상세 링크 (없을 수 있음)
        date_found: 최초 발견 일자 (YYYY-MM-DD)
        unique_key: 중복 판별용 고유키 (자동 생성)
    """

    source: str
    company: str
    title: str
    level: str = "5-7년"
    location: str = ""
    url: str = ""
    date_found: str = field(default_factory=lambda: date.today().isoformat())
    unique_key: str = ""

    def __post_init__(self) -> None:
        """고유키가 없으면 자동으로 생성한다."""
        if not self.unique_key:
            self.unique_key = self._generate_key()

    def _generate_key(self) -> str:
        """(source, company, title, location, url) 조합으로 고유키를 생성한다.

        url이 비어있거나 변동 가능한 경우 해시로 대체한다.
        """
        raw = f"{self.source}|{self.company}|{self.title}|{self.location}|{self.url}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환한다."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobPosting:
        """딕셔너리에서 JobPosting 인스턴스를 생성한다."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DiffResult:
    """변경 감지 결과 모델.

    Attributes:
        new_jobs: 이번 실행에서 새로 발견된 공고 목록
        removed_jobs: 이전에는 있었지만 이번에 사라진 공고 목록
        unchanged_jobs: 변경 없이 유지된 공고 목록
    """

    new_jobs: list[JobPosting] = field(default_factory=list)
    removed_jobs: list[JobPosting] = field(default_factory=list)
    unchanged_jobs: list[JobPosting] = field(default_factory=list)

    @property
    def all_current_jobs(self) -> list[JobPosting]:
        """현재 유효한 전체 공고 목록 (신규 + 유지)."""
        return self.new_jobs + self.unchanged_jobs

    @property
    def has_changes(self) -> bool:
        """변경 사항이 있는지 여부."""
        return bool(self.new_jobs or self.removed_jobs)
