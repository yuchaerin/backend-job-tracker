# 📋 Backend Job Tracker

> **백엔드 5~7년차 이직공고**를 하루 2번 자동으로 수집하여 `JOB_TRACKER.md`에 정리하는 프로젝트입니다.
>
> 서버 없이 **GitHub Actions** 스케줄만으로 운영됩니다.

---

## 📂 프로젝트 구조

```
backend-job-tracker/
├── .github/workflows/
│   └── job-tracker.yml          # GitHub Actions 스케줄 워크플로우
├── config/
│   ├── companies.yaml           # 🎯 수집 대상 기업 목록
│   └── settings.yaml            # ⚙️ 경력 필터 키워드 설정
├── data/
│   └── jobs.json                # 수집된 공고 데이터 (자동 생성)
├── src/
│   ├── __init__.py
│   ├── main.py                  # 메인 실행 엔트리포인트
│   ├── config_loader.py         # YAML 설정 로더
│   ├── models.py                # 데이터 모델 (JobPosting, DiffResult)
│   ├── storage.py               # JSON 데이터 읽기/쓰기 및 diff 로직
│   ├── markdown.py              # JOB_TRACKER.md 마크다운 생성
│   ├── notify/
│   │   ├── __init__.py
│   │   └── emailer.py           # 이메일 알림 (SMTP)
│   └── sources/
│       ├── __init__.py
│       ├── base.py              # 소스 플러그인 추상 클래스
│       └── mock_source.py       # 샘플 소스 (테스트/데모용)
├── JOB_TRACKER.md               # 수집 결과 문서 (자동 갱신)
├── README.md
└── requirements.txt
```

---

## 🚀 로컬 실행 방법

### 사전 요구사항

- **Python 3.11** 이상

### 설치 및 실행

```bash
# 1. 리포지토리 클론
git clone https://github.com/yuchaerin/backend-job-tracker.git
cd backend-job-tracker

# 2. (선택) 가상환경 생성
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 실행
python src/main.py
```

실행하면 다음 파일이 생성/갱신됩니다:

| 파일 | 설명 |
|------|------|
| `data/jobs.json` | 수집된 공고 데이터 (JSON) |
| `JOB_TRACKER.md` | 가독성 좋은 마크다운 문서 |

---

## 🎯 기업 타겟 설정

### companies.yaml

`config/companies.yaml`에 수집 대상 기업을 정의합니다:

```yaml
companies:
  - name: "카카오"
    source: "wanted"                                    # 소스 플러그인 이름
    url: "https://www.wanted.co.kr/company/1234/jobs"   # 기업 채용 페이지 URL

  - name: "네이버"
    source: "saramin"
    url: "https://www.saramin.co.kr/zf_user/company-info/view?csn=1234567890"
```

| 필드 | 설명 |
|------|------|
| `name` | 회사명 (JOB_TRACKER.md에 표시) |
| `source` | 소스 플러그인 이름 (`main.py`의 `SOURCE_REGISTRY`와 매칭) |
| `url` | 기업 채용 페이지 직접 링크 |

> **기업을 추가하려면?** `companies.yaml`에 항목만 추가하면 됩니다. 코드 수정 불필요!

### settings.yaml – 경력 필터

`config/settings.yaml`에서 경력 필터 키워드를 관리합니다:

```yaml
experience_filter:
  enabled: true
  level_label: "5-7년"
  keywords:
    - "5년"
    - "6년"
    - "7년"
    - "5~7"
    - "경력 5년 이상"
    - "5+ years"
```

공고 제목에 키워드 중 하나라도 포함되면 매칭으로 판단합니다.

---

## 🔌 새 소스 추가 방법

### 1단계: 소스 파일 생성

```python
# src/sources/wanted.py

import requests
from sources.base import BaseSource
from models import JobPosting
from config_loader import CompanyConfig


class WantedSource(BaseSource):
    name = "wanted"  # companies.yaml의 source 필드와 일치

    def fetch_company(self, company: CompanyConfig) -> list[JobPosting]:
        resp = requests.get(company.url)
        # 파싱 로직...
        return [JobPosting(source=self.name, company=company.name, ...)]
```

### 2단계: SOURCE_REGISTRY에 등록

```python
# src/main.py
from sources.wanted import WantedSource

SOURCE_REGISTRY: dict[str, BaseSource] = {
    "mock": MockSource(),
    "wanted": WantedSource(),  # ← 추가
}
```

### 3단계: companies.yaml에 기업 추가

```yaml
companies:
  - name: "카카오"
    source: "wanted"
    url: "https://www.wanted.co.kr/company/1234/jobs"
```

> **참고**: `BaseSource`에는 지수 백오프 재시도 로직이 내장되어 있어,
> 네트워크 실패 시 자동으로 최대 3회 재시도합니다.

---

## ⚙️ GitHub Actions 동작 설명

### 스케줄

워크플로우는 **KST(한국 표준시) 기준 12:00, 18:00**에 자동 실행됩니다.

```yaml
schedule:
  - cron: "0 3 * * *"   # KST 12:00 (UTC 03:00)
  - cron: "0 9 * * *"   # KST 18:00 (UTC 09:00)
```

### 실행 흐름

```
1. 리포지토리 체크아웃
2. Python 3.11 설정
3. 의존성 설치
4. python src/main.py 실행
5. JOB_TRACKER.md / data/jobs.json 변경 시에만 커밋 & 푸시
```

### 수동 실행

GitHub 리포지토리 → **Actions** → **Job Tracker** → **Run workflow** 버튼으로 수동 실행 가능합니다.

---

## 📧 이메일 알림 설정 (선택)

이메일 알림은 **기본 비활성화**입니다. 활성화하려면 아래 환경변수를 GitHub Secrets에 등록하세요.

### GitHub Secrets 설정 방법

1. GitHub 리포지토리 → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭 후 아래 항목을 각각 추가:

| Secret 이름 | 설명 | 예시 값 |
|-------------|------|---------|
| `ENABLE_EMAIL` | 이메일 활성화 | `true` |
| `SMTP_HOST` | SMTP 서버 호스트 | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 포트 | `587` |
| `SMTP_USER` | SMTP 사용자 | `your-email@gmail.com` |
| `SMTP_PASS` | SMTP 비밀번호/앱 비밀번호 | `xxxx xxxx xxxx xxxx` |
| `MAIL_FROM` | 발신자 이메일 | `your-email@gmail.com` |
| `MAIL_TO` | 수신자 이메일 (콤마 구분) | `me@gmail.com` |

### Gmail 사용 시 주의사항

Gmail을 사용하려면 **앱 비밀번호**를 생성해야 합니다:

1. Google 계정 → **보안** → **2단계 인증** 활성화
2. **앱 비밀번호** 생성 → 16자리 코드를 `SMTP_PASS`에 입력

### 로컬 테스트

```bash
export ENABLE_EMAIL=true
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=your-email@gmail.com
export SMTP_PASS="xxxx xxxx xxxx xxxx"
export MAIL_FROM=your-email@gmail.com
export MAIL_TO=me@gmail.com

python src/main.py
```

---

## 🔧 중복 제거 로직

공고의 고유키는 `(source, company, title, location, url)` 조합의 **SHA-256 해시 앞 16자리**로 생성됩니다.

- URL이 있으면: 5가지 필드 조합으로 해시
- URL이 없거나 변동 가능하면: 나머지 필드만으로 해시

동일한 고유키를 가진 공고는 자동으로 중복 제거됩니다.

---

## 📝 라이선스

개인 프로젝트 용도로 자유롭게 사용하세요.
