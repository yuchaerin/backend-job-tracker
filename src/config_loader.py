"""
설정 로더 모듈 – config/*.yaml 파일 읽기.

companies.yaml 에서 기업 목록을, settings.yaml 에서 필터 키워드 등을 로드한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 기본 설정 경로 (리포지토리 루트 기준)
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


# ── 데이터 클래스 ─────────────────────────────────────────────


@dataclass
class CompanyConfig:
    """기업 타겟 설정.

    Attributes:
        name: 회사명
        source: 소스 플러그인 이름 (예: wanted, saramin, career, mock)
        url: 기업 채용 페이지 URL
        selectors: CSS 셀렉터 설정 (career 소스용)
            - job_list: 공고 목록 컨테이너 셀렉터
            - title: 공고 제목 셀렉터
            - link: 링크 셀렉터 (없으면 title에서 href 추출)
            - location: 근무지 셀렉터 (선택)
            - experience: 경력 조건 셀렉터 (선택)
    """

    name: str
    source: str
    url: str = ""
    selectors: dict[str, str] = field(default_factory=dict)


@dataclass
class ExperienceFilter:
    """경력 필터 설정.

    Attributes:
        enabled: 필터 활성화 여부
        level_label: JOB_TRACKER.md에 표시할 경력 라벨
        keywords: 매칭 키워드 목록
    """

    enabled: bool = True
    level_label: str = "5-7년"
    keywords: list[str] = field(default_factory=lambda: ["5년", "6년", "7년", "5~7"])


@dataclass
class AppSettings:
    """애플리케이션 전체 설정.

    Attributes:
        companies: 기업 타겟 목록
        experience_filter: 경력 필터 설정
        mock_skip_filter: mock 소스 필터 건너뛰기 여부
    """

    companies: list[CompanyConfig] = field(default_factory=list)
    experience_filter: ExperienceFilter = field(default_factory=ExperienceFilter)
    mock_skip_filter: bool = True


# ── 로더 함수 ─────────────────────────────────────────────────


def _load_yaml(path: Path) -> dict[str, Any]:
    """YAML 파일을 딕셔너리로 로드한다."""
    if not path.exists():
        logger.warning("설정 파일이 없습니다: %s", path)
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def load_companies(path: Path | None = None) -> list[CompanyConfig]:
    """companies.yaml에서 기업 목록을 로드한다."""
    path = path or CONFIG_DIR / "companies.yaml"
    data = _load_yaml(path)
    raw_list = data.get("companies", [])

    companies = []
    for item in raw_list:
        if isinstance(item, dict) and "name" in item and "source" in item:
            companies.append(
                CompanyConfig(
                    name=item["name"],
                    source=item["source"].lower().strip(),
                    url=item.get("url", ""),
                    selectors=item.get("selectors", {}),
                )
            )
    logger.info("기업 설정 %d건 로드: %s", len(companies), path)
    return companies


def load_settings(path: Path | None = None) -> tuple[ExperienceFilter, bool]:
    """settings.yaml에서 필터 설정을 로드한다.

    Returns:
        (ExperienceFilter, mock_skip_filter) 튜플
    """
    path = path or CONFIG_DIR / "settings.yaml"
    data = _load_yaml(path)

    # 경력 필터
    ef_raw = data.get("experience_filter", {})
    exp_filter = ExperienceFilter(
        enabled=ef_raw.get("enabled", True),
        level_label=ef_raw.get("level_label", "5-7년"),
        keywords=ef_raw.get("keywords", ["5년", "6년", "7년", "5~7"]),
    )

    # mock 설정
    mock_raw = data.get("mock", {})
    mock_skip = mock_raw.get("skip_filter", True)

    logger.info(
        "필터 설정 로드 – 활성: %s, 키워드 %d개",
        exp_filter.enabled,
        len(exp_filter.keywords),
    )
    return exp_filter, mock_skip


def load_app_settings() -> AppSettings:
    """전체 설정을 한 번에 로드한다."""
    companies = load_companies()
    exp_filter, mock_skip = load_settings()
    return AppSettings(
        companies=companies,
        experience_filter=exp_filter,
        mock_skip_filter=mock_skip,
    )
