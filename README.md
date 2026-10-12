# 코리아 디스카운트 랩 — 사이트 만들기 설명서

코딩을 몰라도 따라 할 수 있게 순서대로 적었어요. 처음 한 번 설정하는 데 1~2시간 정도 걸리고, 그다음부터는 **평일 저녁마다 데이터가 자동으로 갱신**돼요.

## 이 사이트가 돌아가는 방식

```
[공공데이터포털 시세] ─┐
[OpenDART 재무]      ─┼─▶ GitHub Actions (매일 자동 실행) ─▶ data/site.json ─▶ Vercel (사이트 공개)
[네이버 뉴스]        ─┘                                                         │
                                                                    AI 버튼 ─▶ /api/ask ─▶ Claude API
```

- **GitHub**: 코드와 데이터를 보관하는 곳. 매일 데이터를 받아오는 로봇(Actions)도 여기서 돌아요.
- **Vercel**: GitHub에 있는 파일을 인터넷 사이트로 만들어 주는 곳. 무료 요금제로 충분해요.
- API 키를 하나도 넣지 않아도 사이트는 **예시 데이터**로 돌아가요. 키를 하나씩 넣을 때마다 실제 데이터로 바뀌어요.

## 폴더 구성

| 파일 | 하는 일 | 직접 고치나요? |
|---|---|---|
| `index.html` | 사이트 화면 전체 | 보통은 안 고쳐요 |
| `config/stocks.json` | 보여줄 종목, 해외 비교 기업 수치 | **네** |
| `config/reports.json` | 증권사 리포트 헤드라인 | **네** |
| `config/board.json` | 우선주·지주사·밸류업·한일 비교 설정 | **네** |
| `scripts/update_data.py` | 데이터를 받아 `data/site.json` 을 만드는 프로그램 | 아니요 |
| `data/site.json` | 사이트가 읽는 데이터 (자동 생성) | 아니요 |
| `api/ask.js` | AI 기능 서버 | 아니요 |
| `.github/workflows/update-data.yml` | 매일 자동 실행 설정 | 아니요 |

---

## 1단계. GitHub 저장소 만들기

1. [github.com](https://github.com) 에서 가입하고 로그인해요.
2. 오른쪽 위 **+** → **New repository**.
3. 이름에 `korea-discount-lab` 입력, **Public** 선택 → **Create repository**.
4. 만들어진 화면에서 **uploading an existing file** 링크를 눌러요.
5. 압축을 푼 폴더 안의 파일과 폴더(`index.html`, `README.md`, `package.json`, `api`, `config`, `data`, `scripts`)를 모두 끌어다 놓고 **Commit changes**.

> ⚠️ `.github` 폴더는 이름이 점(.)으로 시작해서 Mac Finder나 Windows 탐색기에서 안 보일 수 있어요. 끌어다 놓기가 안 되면:
> 저장소 화면에서 **Add file → Create new file** → 파일 이름 칸에 `.github/workflows/update-data.yml` 을 그대로 입력 → 압축 파일 안의 같은 파일 내용을 복사해서 붙여넣기 → **Commit changes**.

## 2단계. API 키 발급받기 (모두 무료)

| 키 이름 | 어디서 | 무엇에 쓰나 | 필수? |
|---|---|---|---|
| `DATA_GO_KR_KEY` | [공공데이터포털](https://www.data.go.kr) → "금융위원회_주식시세정보" 검색 → **활용신청** → 마이페이지에서 **일반 인증키(Decoding)** 복사 | 주가, 시가총액 | 실제 데이터를 쓰려면 필수 |
| `DART_API_KEY` | [OpenDART](https://opendart.fss.or.kr) → 인증키 신청 → 이메일 인증 | 매출·이익·자본 → PER, PBR, ROE | 권장 |
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | [네이버 개발자센터](https://developers.naver.com) → Application 등록 → 사용 API에서 **검색** 선택 | 관련 뉴스 | 선택 |

공공데이터포털 키는 승인 후 실제로 작동하기까지 1~2시간 걸릴 수 있어요.

## 3단계. GitHub에 키 저장하기

키는 절대 파일에 직접 쓰지 마세요. 공개 저장소라 누구나 볼 수 있어요.

1. 저장소 화면 → **Settings** → 왼쪽 **Secrets and variables** → **Actions**.
2. **New repository secret** 을 눌러 아래 이름 그대로 하나씩 저장해요.
   - `DATA_GO_KR_KEY`, `DART_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`

## 4단계. 자동 실행 권한 켜기

**Settings** → **Actions** → **General** → 맨 아래 **Workflow permissions** 에서 **Read and write permissions** 선택 → **Save**.
(이걸 켜야 로봇이 새 데이터를 저장할 수 있어요.)

## 5단계. 데이터 첫 수집

1. 저장소 위쪽 **Actions** 탭 → 왼쪽 **데이터 자동 갱신** → 오른쪽 **Run workflow** → 초록 버튼.
2. 1~2분 뒤 초록 체크가 뜨면 성공이에요. 빨간 X가 뜨면 눌러서 **데이터 수집** 단계의 로그를 보면 어떤 키가 문제인지 한국어로 나와요.
3. 이후에는 평일 한국시간 저녁 7시에 자동으로 실행돼요. (공공데이터포털 시세는 **전 영업일 기준**이라 실시간 주가가 아니에요.)

## 6단계. Vercel로 사이트 공개하기

1. [vercel.com](https://vercel.com) → **Continue with GitHub** 로 가입.
2. **Add New… → Project** → `korea-discount-lab` 옆 **Import**.
3. **Framework Preset** 은 **Other** 그대로 둬요.
4. **Environment Variables** 를 펼쳐서 AI 기능용 키를 넣어요.
   - 이름: `ANTHROPIC_API_KEY` / 값: [console.anthropic.com](https://console.anthropic.com) 에서 만든 API 키
   - AI 기능이 필요 없으면 이 단계는 건너뛰어도 돼요. 버튼을 누르면 "설정되지 않았어요"라고만 나와요.
5. **Deploy**. 1분 뒤 `korea-discount-lab-xxxx.vercel.app` 주소가 생겨요. 이게 내 사이트예요!

> 💸 Claude API는 사용한 만큼 요금이 나와요. console.anthropic.com 의 **Limits** 에서 월 사용 한도를 꼭 걸어 두세요. 서버에도 한 사람당 1시간 30회 제한을 넣어 뒀어요.

이후로는 GitHub에 파일이 바뀔 때마다(매일 데이터 갱신 포함) Vercel이 알아서 사이트를 다시 만들어요.

## 7단계. 콘텐츠 관리하기

모든 설정 파일은 GitHub 화면에서 파일을 열고 연필 아이콘(✏️)을 눌러 고친 뒤 **Commit changes** 하면 돼요. 다음 데이터 갱신 때 반영되고, 바로 보고 싶으면 5단계처럼 **Run workflow** 를 눌러요.

### 증권사 리포트 헤드라인 추가 (`config/reports.json`)

```json
"005930": [
  {"date": "2026-10-10", "broker": "OO증권", "title": "리포트 제목", "rating": "매수", "tp": 112000, "prev_tp": 105000, "url": "https://증권사-리포트-원문-주소"}
]
```

- **각 증권사 리서치센터의 공개 페이지**에서 확인한 내용만 넣고, `url` 에 원문 주소를 넣어요.
- 네이버 증권·한경 컨센서스 같은 **모음 사이트를 통째로 옮기거나 자동 수집하지 마세요.** 부정경쟁방지법 문제가 될 수 있어요.
- 리포트 PDF 본문 내용은 넣지 마세요. 제목·의견·목표가·링크만 넣어요.
- 지금 들어 있는 항목은 `"example": true` 라서 화면에 "예시"로 표시돼요. 실제 항목으로 바꾸면 이 줄은 지워요.

### 종목 추가 (`config/stocks.json`)

기존 종목 하나를 통째로 복사해서 `code`, `name`, `alias`(검색용 별명), `sector`, `peers` 를 고쳐요. 해외 피어의 PER·PBR·ROE·배당수익률은 그 회사 IR 자료나 [SEC EDGAR](https://www.sec.gov/edgar/search/)(미국), [EDINET](https://disclosure2.edinet-fsa.go.jp)(일본)을 보고 넣고, 맨 위 `peers_as_of` 에 확인한 날짜를 적어요.

### 지주사 지분율 (`config/board.json`)

`holdings` 의 `pct` 는 지주사가 가진 자회사 지분율(%)이에요. DART에서 지주사의 사업보고서 → **타법인 출자현황**을 보고 확인한 뒤, 맞게 고쳤으면 그 지주사의 `"example": true` 를 지워요.

---

## 자주 생기는 문제

| 증상 | 해결 |
|---|---|
| 사이트 상단에 "예시 데이터로 보는 중" | 3단계 `DATA_GO_KR_KEY` 를 확인하고 5단계를 다시 실행 |
| Actions가 빨간 X, 로그에 "받아온 종목이 없어" | 공공데이터포털 키가 아직 승인 전이거나, Encoding 키를 넣은 경우 → **Decoding 키**로 바꾸기 |
| Actions 로그에 `push` 오류 | 4단계 권한 설정 확인 |
| 재무 표가 "아직 없어요" | `DART_API_KEY` 확인 |
| AI 버튼이 "설정되지 않았어요" | Vercel → 프로젝트 → Settings → Environment Variables 에 `ANTHROPIC_API_KEY` 추가 후 **Redeploy** |

## 내 컴퓨터에서 미리 보기 (선택)

Python이 설치돼 있다면 폴더에서:

```bash
python scripts/update_data.py --sample   # 예시 데이터 만들기
python -m http.server 8000               # http://localhost:8000 접속
```

(이 방법으로는 AI 기능은 동작하지 않아요. AI는 Vercel에 올린 뒤 확인하세요.)

## 꼭 지킬 것

- 사이트 하단 문구처럼 **투자 권유가 아니라는 고지**를 유지하세요. 유료 종목 추천이나 1:1 투자 상담으로 확장하면 유사투자자문업 신고 등 별도 규제가 생길 수 있어요.
- 출시 전 한 번은 대학 창업지원센터 등에서 데이터 이용과 고지 문구를 법률적으로 확인받으세요.
