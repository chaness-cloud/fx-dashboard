"""
update_data.py — GitHub Actions 자동 갱신
ECOS 실패 시 Yahoo Finance(KRW) + Yahoo Finance(JPY) fallback
"""
import os, re, json, requests, datetime, time

ECOS_KEY   = os.environ.get("ECOS_API_KEY", "")
TODAY_DASH = datetime.date.today().strftime("%Y-%m-%d")
print(f"=== 갱신 시작 {TODAY_DASH} ===")

# ── 1. USDKRW — ECOS (일별 시계열) ──────────────
def fetch_krw_ecos():
    TODAY = datetime.date.today().strftime("%Y%m%d")
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch"
        f"/{ECOS_KEY}/json/kr/1/2000"
        f"/731Y001/DD/20220601/{TODAY}/0000001"
    )
    r = requests.get(url, timeout=20)
    data = r.json()
    # 응답 전체 출력 (디버깅)
    print(f"[ECOS] 응답 전체: {str(data)[:300]}")
    rows = data["StatisticSearch"]["row"]
    result = {}
    for row in rows:
        d, v = row.get("TIME",""), row.get("DATA_VALUE","")
        if v and v not in ("-",""):
            result[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = float(v.replace(",",""))
    print(f"[ECOS] ✅ {len(result)}건")
    return result

# ── 2. USDKRW fallback — Yahoo Finance ──────────
def fetch_krw_yahoo():
    end_ts   = int(time.time())
    start_ts = int(datetime.datetime(2022,6,1).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/KRW=X"
        f"?period1={start_ts}&period2={end_ts}&interval=1d"
    )
    r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
    d = r.json()["chart"]["result"][0]
    result = {}
    for ts, cl in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]):
        if cl:
            dt = datetime.date.fromtimestamp(ts).strftime("%Y-%m-%d")
            result[dt] = round(float(cl), 2)
    print(f"[Yahoo-KRW] ✅ {len(result)}건")
    return result

# ── 3. USDJPY — Yahoo Finance ────────────────────
def fetch_jpy():
    end_ts   = int(time.time())
    start_ts = int(datetime.datetime(2022,6,1).timestamp())
    for host in ["query1","query2"]:
        try:
            url = (
                f"https://{host}.finance.yahoo.com/v8/finance/chart/USDJPY=X"
                f"?period1={start_ts}&period2={end_ts}&interval=1d"
            )
            r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
            d = r.json()["chart"]["result"][0]
            result = {}
            for ts, cl in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]):
                if cl:
                    dt = datetime.date.fromtimestamp(ts).strftime("%Y-%m-%d")
                    result[dt] = round(float(cl), 3)
            if result:
                print(f"[Yahoo-JPY] ✅ {len(result)}건")
                return result
        except Exception as e:
            print(f"[Yahoo-JPY/{host}] {e}")
    raise RuntimeError("JPY 수집 실패")

# ── 4. 병합 ──────────────────────────────────────
def merge(krw_d, jpy_d):
    common = sorted(set(krw_d) & set(jpy_d))
    print(f"[Merge] {len(common)}건, 최신: {common[-1]}")
    return common, [jpy_d[d] for d in common], [krw_d[d] for d in common]

# ── 5. HTML 업데이트 ─────────────────────────────
def update_html(dates, jpy, krw, path="index.html"):
    html = open(path, encoding="utf-8").read()
    def rep(content, var, lst):
        pat = rf'(const {var}=)\[.*?\]'
        new, n = re.subn(pat, rf'\g<1>{json.dumps(lst)}', content, flags=re.DOTALL)
        print(f"  {'✅' if n else '⚠️ '} {var} ({len(lst)}건)")
        return new if n else content
    html = rep(html, "dates",   dates)
    html = rep(html, "jpyData", jpy)
    html = rep(html, "krwData", krw)
    stamp = f"<!-- last-updated: {TODAY_DASH} -->"
    html = re.sub(r'<!-- last-updated:.*?-->', stamp, html) \
           if "<!-- last-updated:" in html \
           else html.replace("</head>", f"{stamp}\n</head>", 1)
    open(path, "w", encoding="utf-8").write(html)
    print("[HTML] 저장 완료")

# ── 6. 배지 업데이트 ─────────────────────────────
def update_badges(dates, jpy, krw, path="index.html"):
    html = open(path, encoding="utf-8").read()
    lj, lk, ld = jpy[-1], krw[-1], dates[-1]
    html = re.sub(r'USDJPY \d+\.\d+',         f'USDJPY {lj:.1f}', html)
    html = re.sub(r'USDKRW [\d,]+',            f'USDKRW {lk:,.0f}', html)
    html = re.sub(r'\d{4}\.\d{2}\.\d{2} 기준', f'{ld.replace("-",".")} 기준', html)
    open(path, "w", encoding="utf-8").write(html)
    print(f"[Badge] JPY={lj:.1f} KRW={lk:,.0f} ({ld})")

# ── MAIN ─────────────────────────────────────────
if __name__ == "__main__":
    # KRW: ECOS 시도 → 실패 시 Yahoo fallback
    krw_d = None
    try:
        krw_d = fetch_krw_ecos()
    except Exception as e:
        print(f"[ECOS] 실패({e}) → Yahoo fallback")
        try:
            krw_d = fetch_krw_yahoo()
        except Exception as e2:
            print(f"[FATAL] KRW 완전 실패: {e2}")
            raise SystemExit(1)

    # JPY
    try:
        jpy_d = fetch_jpy()
    except Exception as e:
        print(f"[FATAL] JPY 실패: {e}")
        raise SystemExit(1)

    dates, jpy, krw = merge(krw_d, jpy_d)
    update_html(dates, jpy, krw)
    update_badges(dates, jpy, krw)
    print("=== 완료 ✅ ===")
