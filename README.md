# 이천 뉴스봇

이천시 전체 현안을 네이버 뉴스 검색 API로 검색해 새 기사만 텔레그램 채널로 전송하는 봇입니다. 기본 설정은 `이천시`, `경기 이천`, `경기도 이천`으로 지역 현안을 넓게 잡고, 지역경제 핵심축인 `이천 하이닉스`를 보강합니다.

## 핵심 구조

| 항목 | 내용 |
| --- | --- |
| 수집 | 네이버 뉴스 검색 API 전용 |
| 필터 | `keywords.txt`에서 검색어·포함어·제외어 관리 |
| 검색 깊이 | 키워드별 최신순 최대 1,000건까지 페이지네이션 |
| 중복 방지 | `seen_links.json`에 본 기사 링크 저장 |
| 기록 | `articles.csv`에 전송 기사 누적 |
| 자동 실행 | GitHub Actions `workflow_dispatch` + cron-job.org 10분 주기 외부 호출 |

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

네이버 뉴스 검색 API를 사용하므로 아래 값이 필수입니다.

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
| `NAVER_CLIENT_ID` | 필수 | 네이버 개발자센터 검색 API Client ID |
| `NAVER_CLIENT_SECRET` | 필수 | 네이버 개발자센터 검색 API Client Secret |

5. 저장소 `Actions > 이천 뉴스봇 > Run workflow`로 1회 수동 실행할 수 있습니다.
6. 자동 실행은 cron-job.org에서 GitHub Actions `workflow_dispatch` API를 10분마다 호출하도록 설정합니다.

## cron-job.org 설정

GitHub 자체 `schedule`은 지연되거나 빠질 수 있으므로 사용하지 않습니다. cron-job.org가 아래 GitHub API를 10분마다 `POST`로 호출하게 설정합니다.

| 항목 | 값 |
| --- | --- |
| URL | `https://api.github.com/repos/linphyca-sys/icheon-news-bot/actions/workflows/newsbot.yml/dispatches` |
| Method | `POST` |
| Schedule | 10분마다 |
| Body | `{"ref":"main"}` |

필수 headers:

```text
Authorization: Bearer <GitHub PAT>
Accept: application/vnd.github+json
User-Agent: icheon-news-bot-cron
Content-Type: application/json
```

GitHub PAT는 fine-grained token으로 만들고, 저장소는 `linphyca-sys/icheon-news-bot`만 선택합니다. 권한은 `Actions: Read and write`만 부여합니다.

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
- 지역경제·산업 현안: `이천 하이닉스`

`이천` 단독 검색은 금액 표현인 `이천만`, `이천억`, `이천원`과 충돌이 잦아 기본값에서 제외했습니다. 대신 `이천시`, `경기 이천`, `경기도 이천`처럼 지역성이 강한 표현은 제외어 없이 사용해 실제 이천시 기사 누락을 줄입니다.

## 운영 기준

- 검색 간격은 cron-job.org 기준 10분입니다.
- 네이버 API는 한 번에 최대 100건을 반환하므로, 봇은 `start=1,101,201...901` 방식으로 키워드별 최대 1,000건까지 확인합니다.
- `MAX_PER_KEYWORD=0`, `FIRST_RUN_SEND=0`은 건수 제한 없음이라는 뜻입니다. 누락 방지를 위해 전송 제한을 두지 않습니다.
- 속보성이 중요하면 `MAX_AGE_HOURS=12`로 줄입니다.
- 누락 방지가 중요하면 `MAX_AGE_HOURS=48`로 늘립니다.
- 기사량이 많으면 `MAX_PER_KEYWORD=1` 또는 `2`로 줄입니다.
- 이천시 전체 모니터링은 네이버 뉴스 검색 API 기준으로만 운영합니다.
