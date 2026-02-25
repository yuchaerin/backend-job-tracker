"""
이메일 알림 모듈.

SMTP를 통해 신규 공고 알림 메일을 발송한다.
기본은 비활성화(ENABLE_EMAIL=false)이며,
환경변수를 설정하면 새 공고 발견 시 자동으로 메일을 보낸다.

필요한 환경변수:
    ENABLE_EMAIL  : "true" 일 때만 메일 발송 (기본 "false")
    SMTP_HOST     : SMTP 서버 호스트 (예: smtp.gmail.com)
    SMTP_PORT     : SMTP 포트 (예: 587)
    SMTP_USER     : SMTP 인증 사용자
    SMTP_PASS     : SMTP 인증 비밀번호
    MAIL_FROM     : 발신자 이메일
    MAIL_TO       : 수신자 이메일 (콤마 구분으로 복수 지정 가능)
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from models import JobPosting

logger = logging.getLogger(__name__)

# 메일 본문에 포함할 최대 공고 수
MAX_MAIL_ITEMS = 20


def is_email_enabled() -> bool:
    """이메일 알림이 활성화되어 있는지 확인한다."""
    return os.getenv("ENABLE_EMAIL", "false").lower() == "true"


def _build_html_body(new_jobs: list[JobPosting]) -> str:
    """신규 공고 목록을 HTML 본문으로 변환한다."""
    display = new_jobs[:MAX_MAIL_ITEMS]
    rows = ""
    for job in display:
        link = f'<a href="{job.url}">링크</a>' if job.url else "-"
        rows += (
            f"<tr>"
            f"<td>{job.date_found}</td>"
            f"<td>{job.source}</td>"
            f"<td>{job.company}</td>"
            f"<td>{job.title}</td>"
            f"<td>{job.level}</td>"
            f"<td>{job.location}</td>"
            f"<td>{link}</td>"
            f"</tr>\n"
        )

    html = f"""\
<html>
<body>
<h2>📋 백엔드 이직공고 신규 알림</h2>
<p>신규 공고 <strong>{len(new_jobs)}건</strong>이 발견되었습니다.</p>
{"<p>(상위 " + str(MAX_MAIL_ITEMS) + "건만 표시)</p>" if len(new_jobs) > MAX_MAIL_ITEMS else ""}
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<thead>
<tr>
<th>DateFound</th><th>Source</th><th>Company</th>
<th>Title</th><th>Level</th><th>Location</th><th>Link</th>
</tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
<br>
<p><em>이 메일은 backend-job-tracker에 의해 자동 발송되었습니다.</em></p>
</body>
</html>
"""
    return html


def send_email(new_jobs: list[JobPosting]) -> None:
    """신규 공고 알림 이메일을 발송한다.

    ENABLE_EMAIL 환경변수가 "true"가 아니면 아무 작업도 하지 않는다.
    필수 환경변수가 누락되면 경고 로그만 남기고 건너뛴다.
    """
    if not is_email_enabled():
        logger.debug("이메일 알림 비활성화 상태 – 건너뜀")
        return

    if not new_jobs:
        logger.info("신규 공고 없음 – 이메일 발송 안 함")
        return

    # 환경변수 읽기
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    mail_from = os.getenv("MAIL_FROM", "")
    mail_to = os.getenv("MAIL_TO", "")

    missing = [
        name
        for name, val in [
            ("SMTP_HOST", smtp_host),
            ("SMTP_USER", smtp_user),
            ("SMTP_PASS", smtp_pass),
            ("MAIL_FROM", mail_from),
            ("MAIL_TO", mail_to),
        ]
        if not val
    ]
    if missing:
        logger.warning("이메일 설정 누락: %s – 발송 건너뜀", ", ".join(missing))
        return

    recipients = [addr.strip() for addr in mail_to.split(",") if addr.strip()]

    # 메일 구성
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Job Tracker] 신규 공고 {len(new_jobs)}건 알림"
    msg["From"] = mail_from
    msg["To"] = ", ".join(recipients)

    html_body = _build_html_body(new_jobs)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # SMTP 발송
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(mail_from, recipients, msg.as_string())
        logger.info("이메일 발송 완료 → %s (신규 %d건)", ", ".join(recipients), len(new_jobs))
    except Exception as exc:
        logger.error("이메일 발송 실패: %s", exc)
