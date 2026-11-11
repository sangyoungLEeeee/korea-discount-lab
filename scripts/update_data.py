"""
코리아 디스카운트 랩 — 데이터 자동 수집 스크립트

매일 GitHub Actions가 이 파일을 실행해서 data/site.json 을 새로 만듭니다.
사용하는 무료 데이터:
  - 주가: 공공데이터포털 금융위원회_주식시세정보 (환경변수 DATA_GO_KR_KEY가 있을 때)
          없으면 Yahoo Finance (키·가입 필요 없음, yfinance 패키지 사용)
  - 재무: OpenDART (환경변수 DART_API_KEY) — 없으면 재무 표가 비어 있음
  - 뉴스: 네이버 검색 API (NAVER_CLIENT_ID, NAVER_CLIENT_SECRET가 있을 때)
          없으면 Google 뉴스 RSS (키 필요 없음)

직접 실행:  python scripts/update_data.py            (실제 데이터)
           python scripts/update_data.py --sample   (항상 예시 데이터)
Yahoo 주가를 쓰려면 yfinance 패키지가 필요합니다:  pip install yfinance
"""
import io
import json
import math
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config")
OUT = os.path.join(ROOT, "data", "site.json")
KST = timezone(timedelta(hours=9))

PRICE_URL = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
DART = "https://opendart.fss.or.kr/api"
NAVER_NEWS = "https://openapi.naver.com/v1/search/news.json"
GOOGLE_NEWS = "https://news.google.com/rss/search"


def log(*a):
    print("[update]", *a, flush=True)


def load(name):
    with open(os.path.join(CONFIG, name), encoding="utf-8") as f:
        return json.load(f)


def http_get(url, params=None, headers=None, raw=False, tries=3):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": "korea-discount-lab/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
            return body if raw else json.loads(body.decode("utf-8"))
        except Exception as e:  # 네트워크 오류는 잠깐 쉬고 다시 시도
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"요청 실패: {url[:120]} ({last})")


def num(x):
    """'1,234' 같은 문자열을 숫자로. 비어 있으면 None."""
    if x is None:
        return None
    s = str(x).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- 시세 (공공데이터포털)
def fetch_prices(code, key, days=400):
    """한 종목의 일별 시세를 오래된 날짜부터 정렬해서 돌려줍니다."""
    begin = (datetime.now(KST).date() - timedelta(days=days)).strftime("%Y%m%d")
    rows, page = [], 1
    while True:
        js = http_get(PRICE_URL, {
            "serviceKey": key, "resultType": "json", "likeSrtnCd": code,
            "beginBasDt": begin, "numOfRows": 500, "pageNo": page,
        })
        body = js.get("response", {}).get("body", {})
        items = body.get("items", {}) or {}
        item = items.get("item", []) if isinstance(items, dict) else []
        if isinstance(item, dict):
            item = [item]
        rows += [x for x in item if x.get("srtnCd") == code]
        total = int(body.get("totalCount", 0) or 0)
        if page * 500 >= total or not item:
            break
        page += 1
    bars = []
    for x in sorted(rows, key=lambda r: r["basDt"]):
        d = x["basDt"]
        bars.append({
            "t": f"{d[:4]}-{d[4:6]}-{d[6:]}",
            "o": num(x.get("mkp")), "h": num(x.get("hipr")), "l": num(x.get("lopr")),
            "c": num(x.get("clpr")), "v": num(x.get("trqu")),
        })
    name = rows[0].get("itmsNm") if rows else None
    mcap = num(sorted(rows, key=lambda r: r["basDt"])[-1].get("mrktTotAmt")) if rows else None
    # 거래정지일처럼 시가가 0인 날은 종가로 채움
    for b in bars:
        for k in ("o", "h", "l"):
            if not b[k]:
                b[k] = b["c"]
    return {"bars": bars, "name": name, "mcap": mcap}


# ---------------------------------------------------------------- 시세 (Yahoo Finance, 키 없음)
def fetch_prices_yahoo(code, days=400):
    """KOSPI는 .KS, KOSDAQ은 .KQ 로 찾아봅니다. 시가총액은 상장주식수 × 종가."""
    import yfinance as yf  # GitHub Actions에서 설치됨
    for suffix in (".KS", ".KQ"):
        t = yf.Ticker(code + suffix)
        df = t.history(period=f"{days}d", interval="1d", auto_adjust=False)
        if df is None or df.empty:
            continue
        bars = []
        for idx, r in df.iterrows():
            c = float(r["Close"])
            if not c or math.isnan(c):
                continue
            o, h, l = (float(r[k]) if r[k] and not math.isnan(r[k]) else c for k in ("Open", "High", "Low"))
            v = float(r["Volume"]) if not math.isnan(r["Volume"]) else 0
            bars.append({"t": idx.strftime("%Y-%m-%d"), "o": round(o), "h": round(max(h, o, c)), "l": round(min(l, o, c)), "c": round(c), "v": round(v)})
        if not bars:
            continue
        shares = None
        try:
            shares = t.fast_info["shares"]
        except Exception:
            pass
        mcap = shares * bars[-1]["c"] if shares else None
        return {"bars": bars, "name": code, "mcap": mcap}  # Yahoo는 한글 이름이 없어서 설정 파일 이름을 씀
    raise RuntimeError(f"Yahoo에서 {code}를 찾지 못했어요")


# ---------------------------------------------------------------- 재무 (OpenDART)
def dart_corp_codes(key):
    raw = http_get(f"{DART}/corpCode.xml", {"crtfc_key": key}, raw=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        xml = z.read(z.namelist()[0])
    out = {}
    for el in ET.fromstring(xml).iter("list"):
        sc = (el.findtext("stock_code") or "").strip()
        if sc:
            out[sc] = el.findtext("corp_code")
    return out


ACCOUNTS = {"rev": ["매출액", "수익(매출액)", "영업수익"], "op": ["영업이익", "영업이익(손실)"],
            "ni": ["당기순이익", "당기순이익(손실)"], "eq": ["자본총계"]}


def fetch_financials(corp_code, key):
    """최근 사업보고서 기준 3개년 매출·영업이익·순이익·자본(연결, 억원)."""
    this_year = datetime.now(KST).year
    for y in (this_year - 1, this_year - 2):
        js = http_get(f"{DART}/fnlttSinglAcnt.json", {
            "crtfc_key": key, "corp_code": corp_code, "bsns_year": str(y), "reprt_code": "11011"})
        if js.get("status") != "000":
            continue
        lst = [x for x in js.get("list", []) if x.get("fs_div") == "CFS"] or js.get("list", [])
        res = {"years": [y - 2, y - 1, y]}
        for k, names in ACCOUNTS.items():
            row = next((x for x in lst if x.get("account_nm") in names), None)
            vals = [None, None, None]
            if row:
                vals = [num(row.get("bfefrmtrm_amount")), num(row.get("frmtrm_amount")), num(row.get("thstrm_amount"))]
            res[k] = [round(v / 1e8) if v is not None else None for v in vals]  # 원 → 억원
        return res
    return None


def fetch_common_shares(corp_code, key):
    """최근 사업보고서 기준 보통주 발행주식 수. Yahoo 주식 수는 우선주가 섞이는 경우가 있어 DART 값을 우선 사용."""
    this_year = datetime.now(KST).year
    for y in (this_year - 1, this_year - 2):
        js = http_get(f"{DART}/stockTotqySttus.json", {
            "crtfc_key": key, "corp_code": corp_code, "bsns_year": str(y), "reprt_code": "11011"})
        if js.get("status") != "000":
            continue
        row = next((x for x in js.get("list", []) if (x.get("se") or "").replace(" ", "") == "보통주"), None)
        if row:
            n = num(row.get("istc_totqy"))
            if n:
                return n
    return None


# ---------------------------------------------------------------- 뉴스 (네이버 검색 API)
def fetch_news(name, cid, secret):
    js = http_get(NAVER_NEWS, {"query": f"{name} 주가", "display": 5, "sort": "date"},
                  headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret, "User-Agent": "korea-discount-lab/1.0"})
    clean = lambda s: re.sub(r"<[^>]+>", "", s or "").replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    out = []
    for it in js.get("items", []):
        try:
            d = datetime.strptime(it["pubDate"], "%a, %d %b %Y %H:%M:%S %z").strftime("%m.%d")
        except Exception:
            d = ""
        out.append({"date": d, "title": clean(it.get("title")), "summary": clean(it.get("description"))[:120],
                    "url": it.get("originallink") or it.get("link")})
    return out


def fetch_news_google(name):
    """Google 뉴스 RSS — 키 없이 제목·출처·링크만 가져옵니다."""
    raw = http_get(GOOGLE_NEWS, {"q": f"{name} 주가", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}, raw=True)
    out = []
    for it in list(ET.fromstring(raw).iter("item"))[:5]:
        title = it.findtext("title") or ""
        src = it.findtext("source") or ""
        if src and title.endswith(" - " + src):
            title = title[: -len(" - " + src)]
        try:
            d = datetime.strptime(it.findtext("pubDate"), "%a, %d %b %Y %H:%M:%S %Z").strftime("%m.%d")
        except Exception:
            d = ""
        out.append({"date": d, "title": title, "summary": src, "url": it.findtext("link") or ""})
    return out


# ---------------------------------------------------------------- 계산
def valuation(mcap_won, fin, kr_div):
    if not mcap_won or not fin:
        return {"per": None, "pbr": None, "roe": None, "div": kr_div}
    mcap = mcap_won / 1e8  # 억원
    ni, eq = fin["ni"][2], fin["eq"][2]
    per = round(mcap / ni, 1) if ni and ni > 0 else None
    pbr = round(mcap / eq, 2) if eq and eq > 0 else None
    roe = round(ni / eq * 100, 1) if ni and eq and eq > 0 else None
    return {"per": per, "pbr": pbr, "roe": roe, "div": kr_div}


def build_board(board, price_of, sample):
    names = {}
    pref = []
    for p in board["pref_pairs"]:
        c, q = price_of(p["common"]), price_of(p["pref"])
        if not c or not q or not c["bars"] or not q["bars"]:
            continue
        cm = {b["t"]: b["c"] for b in c["bars"]}
        gaps = [1 - b["c"] / cm[b["t"]] for b in q["bars"][-250:] if b["t"] in cm and cm[b["t"]]]
        if not gaps:
            continue
        gap, avg = gaps[-1] * 100, sum(gaps) / len(gaps) * 100
        if sample:  # 예시 시세는 두 종목이 따로 움직여서 평균이 의미 없음 → 그럴듯한 값으로 대체
            avg = gap + (int(p["pref"]) % 7) - 3
        pref.append({"common": p.get("common_name") or c["name"], "pref": p.get("pref_name") or q["name"], "cp": c["bars"][-1]["c"], "pp": q["bars"][-1]["c"],
                     "gap": round(gap, 1), "gap_avg": round(avg, 1)})
    nav = []
    for h in board["holdcos"]:
        me = price_of(h["code"])
        if not me or not me["mcap"]:
            continue
        val = 0
        for x in h["holdings"]:
            ch = price_of(x["code"])
            if ch and ch["mcap"]:
                val += ch["mcap"] * x["pct"] / 100
        if sample and val:  # 예시 모드에서는 할인율이 그럴듯하게 나오도록 시가총액을 만듦
            me = dict(me, mcap=val * (0.35 + (int(h["code"]) % 20) / 100))
        if val:
            nav.append({"name": h["name"], "nav": round(val / 1e12, 1), "mcap": round(me["mcap"] / 1e12, 1),
                        "disc": round((1 - me["mcap"] / val) * 100, 1), "example": bool(h.get("example"))})
    return {"pref": pref, "nav": nav, "valueup": board["valueup"], "jpkr": board["jpkr"]}


# ---------------------------------------------------------------- 예시 데이터
SAMPLE_PRICE = {"035420": 198700, "005930": 84300, "000660": 218500, "005380": 236000, "373220": 368000,
                "005935": 69800, "005387": 184000, "051910": 312000, "051915": 171500, "066570": 98400, "066575": 52100,
                "090430": 132000, "090435": 47900}
SAMPLE_NAME = {"005930": "삼성전자", "005935": "삼성전자우", "005380": "현대차", "005387": "현대차2우B", "051910": "LG화학",
               "051915": "LG화학우", "066570": "LG전자", "066575": "LG전자우", "090430": "아모레퍼시픽", "090435": "아모레퍼시픽우"}
SAMPLE_FIN = {
    "005930": [[2589355, 3008700, 3215400], [65670, 326500, 452800], [154871, 281400, 378900], [3631622, 3802000, 4098000]],
    "000660": [[327657, 661930, 1018300], [-77303, 234673, 402100], [-91375, 197969, 318700], [473289, 591000, 829000]],
    "005380": [[1626636, 1752312, 1838400], [151269, 142396, 149600], [122723, 132301, 130800], [930000, 1030000, 1110000]],
    "035420": [[96706, 107377, 111200], [14888, 19793, 21300], [10183, 19021, 17800], [229000, 251000, 265000]],
    "373220": [[337455, 256196, 272400], [21632, 5754, 14100], [12372, -10380, 3900], [262000, 271000, 290000]],
}
SAMPLE_MCAP = {"035420": 31.5e12, "005930": 502e12, "000660": 159e12, "005380": 49.4e12, "373220": 86.1e12}


def sample_series(code, price, seed):
    r = random.Random(seed)
    n, c, raw = 260, 100.0, []
    drift, segs = [], 0
    while len(drift) < n:
        ln, d = 35 + r.randint(0, 50), (r.random() - 0.45) * 0.006
        drift += [d] * ln
    end = datetime(2026, 10, 9).date()
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    for i in range(n):
        prev = c
        ret = drift[i] + 0.017 * r.gauss(0, 1)
        c = prev * math.exp(ret)
        o = prev * math.exp(0.004 * r.gauss(0, 1))
        h = max(o, c) * math.exp(abs(0.008 * r.gauss(0, 1)))
        l = min(o, c) * math.exp(-abs(0.008 * r.gauss(0, 1)))
        v = 1e6 * math.exp(0.35 * r.gauss(0, 1)) * (1 + 1.6 * abs(ret) / 0.017)
        raw.append((o, h, l, c, v))
    k = price / raw[-1][3]
    tick = 500 if price >= 200000 else 100 if price >= 50000 else 50
    rd = lambda x: max(tick, round(x * k / tick) * tick)
    bars = []
    for i, (o, h, l, cc, v) in enumerate(raw):
        o, h, l, cc = rd(o), rd(h), rd(l), rd(cc)
        bars.append({"t": days[i].isoformat(), "o": o, "h": max(h, o, cc), "l": min(l, o, cc), "c": cc, "v": round(v)})
    return bars


def sample_price_of(code):
    p = SAMPLE_PRICE.get(code, 50000)
    bars = sample_series(code, p, int(code) % 9973)
    return {"bars": bars, "name": SAMPLE_NAME.get(code, code), "mcap": SAMPLE_MCAP.get(code, p * 5e7)}


SAMPLE_NEWS = {
    "005930": [["10.10", "3분기 잠정 영업이익 시장 예상 상회", "메모리 가격 반등과 모바일 판매가 실적을 견인했다는 평가."], ["10.08", "HBM 신제품 고객 인증 소식", "품질 테스트 통과 보도로 외국인 순매수 확대."]],
    "000660": [["10.09", "HBM4 샘플 공급 개시", "차세대 제품 조기 공급으로 기술 격차 유지 평가."]],
    "005380": [["10.07", "9월 미국 판매 역대 최대", "하이브리드 모델이 판매 증가를 이끌었다."], ["10.02", "자사주 소각 공시", "올해 두 번째 소각으로 주주환원 의지 확인."]],
    "035420": [["10.08", "AI 검색 서비스 이용자 확대", "검색 체류시간이 늘며 광고 효율 개선 기대."]],
    "373220": [["10.09", "미국 ESS 대형 수주 공시", "유틸리티 업체와 다년 공급 계약 체결."]],
}


# ---------------------------------------------------------------- 메인
def main():
    force_sample = "--sample" in sys.argv
    stocks_cfg, reports_cfg, board_cfg = load("stocks.json"), load("reports.json"), load("board.json")
    key_price, key_dart = os.getenv("DATA_GO_KR_KEY"), os.getenv("DART_API_KEY")
    nid, nsec = os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET")
    sample = force_sample
    source = "sample" if sample else ("data.go.kr" if key_price else "yahoo")
    log(f"주가 출처: {source}")

    cache, shares_cache = {}, {}
    corp = {}
    if key_dart and not sample:
        try:
            corp = dart_corp_codes(key_dart)
            log(f"DART 회사코드 {len(corp)}개 불러옴")
        except Exception as e:
            log("DART 회사코드 실패:", e)

    def dart_mcap(code, close):
        """DART 보통주 수 × 종가. 실패하면 None."""
        if code not in corp:
            return None
        if code not in shares_cache:
            try:
                shares_cache[code] = fetch_common_shares(corp[code], key_dart)
            except Exception as e:
                log(f"{code} 주식 수 실패: {e}")
                shares_cache[code] = None
        n = shares_cache[code]
        return n * close if n else None

    def price_of(code):
        if code not in cache:
            try:
                if sample:
                    cache[code] = sample_price_of(code)
                elif key_price:
                    cache[code] = fetch_prices(code, key_price)
                else:
                    cache[code] = fetch_prices_yahoo(code)
                    time.sleep(0.5)  # Yahoo에 너무 빠르게 요청하지 않도록
                    m = dart_mcap(code, cache[code]["bars"][-1]["c"])
                    if m:
                        cache[code]["mcap"] = m
            except Exception as e:
                log(f"{code} 시세 실패: {e}")
                cache[code] = None
        return cache[code]

    out = {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "sample": sample, "price_source": source,
           "peers_as_of": stocks_cfg.get("peers_as_of"), "stocks": {}}
    for s in stocks_cfg["stocks"]:
        code = s["code"]
        p = price_of(code)
        if not p or not p["bars"]:
            log(f"{s['name']}: 시세가 없어 건너뜁니다.")
            continue
        fin = None
        if sample:
            f = SAMPLE_FIN.get(code)
            if f:
                fin = {"years": [2023, 2024, 2025], "rev": f[0], "op": f[1], "ni": f[2], "eq": f[3]}
        elif code in corp:
            try:
                fin = fetch_financials(corp[code], key_dart)
            except Exception as e:
                log(f"{s['name']} 재무 실패: {e}")
        news = []
        if sample:
            news = [{"date": n[0], "title": n[1], "summary": n[2], "url": ""} for n in SAMPLE_NEWS.get(code, [])]
        else:
            try:
                news = fetch_news(s["name"], nid, nsec) if nid and nsec else fetch_news_google(s["name"])
            except Exception as e:
                log(f"{s['name']} 뉴스 실패: {e}")
        out["stocks"][code] = {
            "name": s["name"], "alias": s.get("alias", []), "mkt": s.get("mkt", ""), "sector": s.get("sector", ""),
            "bars": p["bars"][-260:], "mcap": p["mcap"], "fin": fin,
            "me": valuation(p["mcap"], fin, s.get("kr_div")),
            "peers": s.get("peers", []),
            "reports": sorted(reports_cfg["reports"].get(code, []), key=lambda r: r["date"], reverse=True),
            "news": news,
        }
        log(f"{s['name']}: 시세 {len(p['bars'])}일, 재무 {'있음' if fin else '없음'}, 뉴스 {len(news)}건")

    if not out["stocks"]:
        log("받아온 종목이 없어 기존 데이터를 그대로 둡니다. API 키를 확인해 주세요.")
        sys.exit(1)  # 실패로 표시하고 기존 site.json 은 덮어쓰지 않음
    out["order"] = list(out["stocks"].keys())  # 화면에 보여줄 순서 (설정 파일 순서)
    out["board"] = build_board(board_cfg, price_of, sample)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    log(f"완료: {OUT} ({len(out['stocks'])}종목)")


if __name__ == "__main__":
    main()
