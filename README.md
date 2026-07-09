# 이천 뉴스봇

이천시 전체 현안을 네이버 뉴스 API 또는 Google News RSS로 검색해 새 기사만 텔레그램 채널로 전송하는 봇입니다. 기본 설정은 누락을 줄이기 위해 `이천시`, `경기 이천`, `경기도 이천`을 함께 검색하고, 폭우·침수·화재·교통사고 같은 생활 속보 키워드를 보강합니다.

## 핵심 구조

| 항목 | 내용 |
| --- | --- |
| 수집 | 네이버 뉴스 검색 API 우선, API 키가 없으면 Google News RSS 사용 |
| 필터 | `keywords.txt`에서 검색어·포함어·제외어 관리 |
| 중복 방지 | `seen_links.json`에 본 기사 링크 저장 |
| 기록 | `articles.csv`에 전송 기사 누적 |
| 자동 실행 | GitHub Actions `workflow_dispatch` + cron-job.org 외부 호출 권장 |

## 파일

| 파일 | 용도 |
| --- | --- |
| `news_bot.py` | 뉴스 검색, 필터링, 텔레그램 전송 본체 |
| `keywords.txt` | 이천시 관련 검색어 목록 |
| `.env.example` | 로컬 실행용 환경변수 예시 |
| `get_chat_id.py` | 텔레그램 채널 chat_id 확인 |
| `.github/workflows/newsbot.yml` | GitHub Actions 자동 실행 워크플로 |
| `requirements.txt` | Python 의존성 |

## 로컬 테스트

현재 생성된 Telegram bot username은 `@Ichen_newsalert_bot`입니다. token은 절대 GitHub 저장소나 zip 파일에 넣지 말고, 로컬 `.env` 또는 GitHub Secrets에만 저장합니다.

```powershell
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python get_chat_id.py
python news_bot.py --once
```

`.env`에는 최소한 아래 두 값을 넣어야 합니다.

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

네이버 뉴스 검색 API를 쓰려면 아래 값도 넣습니다. 없으면 Google News RSS로 동작합니다.

```env
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
```

## GitHub Actions 운영

1. 이 폴더를 새 GitHub 저장소에 올립니다.
2. Telegram 채널에 `@Ichen_newsalert_bot`을 관리자로 추가하고, `메시지 게시` 권한을 줍니다.
3. 채널에 테스트 글을 하나 올린 뒤 로컬에서 `python get_chat_id.py`를 실행해 `-100...` 형식의 `TELEGRAM_CHAT_ID`를 확인합니다.
   - 현재 확인된 채널 ID: `-1003902938956`
4. 저장소 `Settings > Secrets and variables > Actions > New repository secret`에 아래 값을 등록합니다.

| Secret | 필수 여부 | 설명 |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | 필수 | BotFather에서 받은 봇 토큰 |
| `TELEGRAM_CHAT_ID` | 필수 | 텔레그램 채널 또는 개인 chat_id |
| `NAVER_CLIENT_ID` | 권장 | 네이버 개발자센터 검색 API Client ID |
| `NAVER_CLIENT_SECRET` | 권장 | 네이버 개발자센터 검색 API Client Secret |

5. 저장소 `Actions > 이천 뉴스봇 > Run workflow`로 1회 실행합니다.
6. 1시간마다 실행하려면 cron-job.org에서 GitHub Actions `workflow_dispatch` API를 호출하도록 설정합니다.

## Token 보안

Telegram bot token은 해당 봇을 제어할 수 있는 비밀값입니다. 대화창, 문서, GitHub 파일에 노출됐다면 BotFather에서 token을 재발급한 뒤 새 token만 GitHub Secrets에 등록하는 방식이 안전합니다.

## 키워드 관리

`keywords.txt`는 한 줄이 하나의 검색 규칙입니다.

```text
이천시 | 제외: 이천원, 이천만, 이천억
이천 SK하이닉스 | 포함: 이천, SK하이닉스
```

| 규칙 | 의미 |
| --- | --- |
| `제외` | 해당 단어가 있으면 전송하지 않음 |
| `포함` | 지정 단어 중 하나 이상이 있어야 전송 |
| `보호` | 제외 단어가 있어도 보호 단어가 있으면 전송 |

## 기본 키워드 설계

기본값은 세 묶음입니다.

- 기본 지역축: `이천시`, `경기 이천`, `경기도 이천`
- 재난·안전·생활 속보: 폭우, 호우, 침수, 화재, 사고, 교통사고, 도로 통제, 정전, 단수, 재난
- 공식 현안: 이천시청, 이천시의회, 이천시장
- 지역경제·산업 현안: 이천 하이닉스, 이천 SK하이닉스

`이천` 단독 검색은 금액 표현인 `이천만`, `이천억`, `이천원`과 충돌이 잦아 기본값에서 제외했습니다. 대신 `이천시`, `경기 이천`, `경기도 이천`처럼 지역성이 강한 표현은 제외어 없이 사용해 실제 이천시 기사 누락을 줄입니다.

## 운영 기준

- 속보성이 중요하면 `MAX_AGE_HOURS=12`로 줄입니다.
- 누락 방지가 중요하면 `MAX_AGE_HOURS=48`로 늘립니다.
- 기사량이 많으면 `MAX_PER_KEYWORD=1` 또는 `2`로 줄입니다.
- 이천시 전체 모니터링은 네이버 API 사용을 권장합니다. Google News RSS는 무료이지만 검색 결과 수와 정렬이 더 불안정할 수 있습니다.
