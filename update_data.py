"""
update_data.py — GitHub Actions 자동 갱신 스크립트
USDKRW: 한국은행 ECOS KeyStatisticList (간단 엔드포인트) + fallback: exchangerate-api
USDJPY: Yahoo Finance
"""

import os, re, json, requests, datetime, time

ECOS_KEY   = os.environ.get("ECOS_API_KEY", "")
START_DATE = "20220601"
TODAY      = datetime.date.today().strftime("%Y%m%d")
TODAY_DASH = datetime.date.today().strftime("%Y-%m-%d")

print(f"=== 갱신 시작 {TODAY_DASH} ===")
print(f"ECOS_KEY: {'설정됨 (' + ECOS_KEY[:4] + '...)' if ECOS_KEY else '❌ 없음'}")


# ── 1-A. USDKRW — ECOS StatisticSearch (일별 시계열) ──
def fetch_krw_ecos_series():
    """ECOS 일별 원달러 환율 시계열 (731Y001)"""
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch"
        f"/{ECOS_KEY}/json/kr/1/2000"
        f"/731Y001/DD/{START_DATE}/{TODAY}/0000001"
    )
    print(f"[ECOS-Series] 요청중...")
    r = requests.get(url, timeout=20)
    data = r.json()
    print(f"[ECOS-Series] 응답키: {list(data.keys())}")
    if "StatisticSearch" not in data:
        raise ValueError(f"StatisticSearch 없음: {list(data.keys())}")
    rows = data["StatisticSearch"]["row"]
    result = {}
    for row in rows:
        d, v = row.get("TIME",""), row.get("DATA_VALUE","")
        if v and v not in ("-",""):
            try:
                result[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = float(v.replace(",",""))
            except: pass
    if not result:
        raise ValueError("파싱 후 데이터 없음")
    print(f"[ECOS-Series] ✅ {len(result)}건")
    return result


# ── 1-B. USDKRW fallback — exchangerate.host (무료, 키 불필요) ──
def fetch_krw_fallback():
    """
    exchangerate.host API로 오늘 환율만 가져와서
    기존 HTML에 있는 데이터에 오늘 날짜만 추가하는 용도
    (ECOS 실패 시 임시 방편)
    """
    print("[Fallback] exchangerate.host 시도...")
    url = "https://api.exchangerate.host/latest?base=USD&symbols=KRW"
    r = requests.get(url, timeout=10)
    data = r.json()
    rate = data["rates"]["KRW"]
    result = {TODAY_DASH: round(rate, 2)}
    print(f"[Fallback] ✅ 오늘 USDKRW: {rate:.2f}")
    return result


# ── 2. USDJPY — Yahoo Finance ────────────────────
def fetch_jpy():
    end_ts   = int(time.time())
    start_ts = int(datetime.datetime(2022, 6, 1).timestamp())
    for host in ["query1", "query2"]:
        url = (
            f"https://{host}.finance.yahoo.com/v8/finance/chart/USDJPY=X"
            f"?period1={start_ts}&period2={end_ts}&interval=1d"
        )
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            d = r.json()["chart"]["result"][0]
            result = {}
            for ts, cl in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]):
                if cl:
                    dt = datetime.date.fromtimestamp(ts).strftime("%Y-%m-%d")
                    result[dt] = round(float(cl), 3)
            if result:
                print(f"[Yahoo] ✅ USDJPY {len(result)}건")
                return result
        except Exception as e:
            print(f"[Yahoo/{host}] {e}")
    raise RuntimeError("Yahoo Finance 실패")


# ── 3. 기존 HTML에서 데이터 추출 ─────────────────
def extract_existing(html_path="index.html"):
    """HTML 안의 기존 dates/jpyData/krwData 추출"""
    html = open(html_path, encoding="utf-8").read()
    def extract(var):
        m = re.search(rf'const {var}=(\[.*?\])', html, re.DOTALL)
        return json.loads(m.group(1)) if m else []
    dates = extract("dates")
    jpy   = extract("jpyData")
    krw   = extract("krwData")
    print(f"[Extract] 기존 데이터: {len(dates)}건 (최신: {dates[-1] if dates else 'N/A'})")
    return dates, jpy, krw


# ── 4. 데이터 병합 ───────────────────────────────
def merge(krw_d, jpy_d):
    common = sorted(set(krw_d) & set(jpy_d))
    if not common:
        raise ValueError("공통 날짜 없음")
    print(f"[Merge] {len(common)}건, 최신: {common[-1]}")
    return common, [jpy_d[d] for d in common], [krw_d[d] for d in common]


# ── 5. HTML 업데이트 ─────────────────────────────
def update_html(dates, jpy, krw, path="index.html"):
    html = open(path, encoding="utf-8").read()

    def rep(content, var, lst):
        pat = rf'(const {var}=)\[.*?\]'
        new, n = re.subn(pat, rf'\g<1>{json.dumps(lst)}', content, flags=re.DOTALL)
        print(f"  {'✅' if n else '⚠️ '} {var} ({len(lst)}건, 치환:{n}회)")
        return new if n else content

    html = rep(html, "dates",   dates)
    html = rep(html, "jpyData", jpy)
    html = rep(html, "krwData", krw)

    # 업데이트 타임스탬프
    stamp = f"<!-- last-updated: {TODAY_DASH} -->"
    if "<!-- last-updated:" in html:
        html = re.sub(r'<!-- last-updated:.*?-->', stamp, html)
    else:
        html = html.replace("</head>", f"{stamp}\n</head>", 1)

    open(path, "w", encoding="utf-8").write(html)
    print(f"[HTML] 저장 완료")


# ── 6. 배지 & KPI 업데이트 ──────────────────────
def update_badges(dates, jpy, krw, path="index.html"):
    html = open(path, encoding="utf-8").read()
    lj, lk, ld = jpy[-1], krw[-1], dates[-1]
    html = re.sub(r'USDJPY \d+\.\d+',          f'USDJPY {lj:.1f}', html)
    html = re.sub(r'USDKRW [\d,]+',             f'USDKRW {lk:,.0f}', html)
    html = re.sub(r'\d{4}\.\d{2}\.\d{2} 기준',  f'{ld.replace("-",".")} 기준', html)
    open(path, "w", encoding="utf-8").write(html)
    print(f"[Badge] JPY={lj:.1f} KRW={lk:,.0f} ({ld})")


# ── MAIN ─────────────────────────────────────────
if __name__ == "__main__":

    # --- KRW 수집 (ECOS 우선, 실패 시 기존 HTML 데이터 + 오늘 fallback) ---
    krw_d = None
    try:
        krw_d = fetch_krw_ecos_series()
    except Exception as e:
        print(f"[ECOS] 실패: {e}")
        print("[ECOS] → 기존 HTML 데이터 + fallback 환율 사용")
        try:
            ex_dates, ex_jpy, ex_krw = extract_existing()
            # 기존 데이터를 딕셔너리로 변환
            krw_d = dict(zip(ex_dates, ex_krw))
            jpy_d_existing = dict(zip(ex_dates, ex_jpy))
            # 오늘 날짜 fallback 추가
            today_krw = fetch_krw_fallback()
            krw_d.update(today_krw)
        except Exception as e2:
            print(f"[FATAL] KRW 완전 실패: {e2}")
            raise SystemExit(1)

    # --- JPY 수집 ---
    try:
        jpy_d = fetch_jpy()
    except Exception as e:
        print(f"[JPY] Yahoo 실패: {e}")
        # 기존 데이터 사용
        try:
            if 'jpy_d_existing' in dir():
                jpy_d = jpy_d_existing
                print("[JPY] 기존 HTML 데이터 사용")
            else:
                ex_dates, ex_jpy, _ = extract_existing()
                jpy_d = dict(zip(ex_dates, ex_jpy))
        except Exception as e2:
            print(f"[FATAL] JPY 완전 실패: {e2}")
            raise SystemExit(1)

    # --- 병합 & 업데이트 ---
    try:
        dates, jpy, krw = merge(krw_d, jpy_d)
        update_html(dates, jpy, krw)
        update_badges(dates, jpy, krw)
        print("=== 완료 ✅ ===")
    except Exception as e:
        print(f"[FATAL] 병합/업데이트 실패: {e}")
        raise SystemExit(1)
