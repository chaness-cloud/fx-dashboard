"""
update_data.py — GitHub Actions 자동 갱신 스크립트
ECOS API 정확한 URL 형식:
  /StatisticSearch/{key}/json/kr/{행시작}/{행끝}/{통계표}/{주기}/{시작일}/{종료일}/{항목코드}
"""

import os, re, json, requests, datetime, time

ECOS_KEY   = os.environ.get("ECOS_API_KEY", "")
START_DATE = "20220601"
TODAY      = datetime.date.today().strftime("%Y%m%d")
TODAY_DASH = datetime.date.today().strftime("%Y-%m-%d")

print(f"ECOS_KEY: {'설정됨 (' + ECOS_KEY[:4] + '...)' if ECOS_KEY else '❌ 없음'}")

# ── 1. USDKRW — ECOS ────────────────────────────
def fetch_krw():
    # ECOS URL 형식: /행시작/행끝/통계표코드/주기/시작일/종료일/항목코드
    candidates = [
        ("731Y001", "0000001"),   # 서울외환 매매기준율 USD
        ("731Y001", "0000003"),   # 서울외환 재정환율
        ("036Y001", "0000001"),   # 원/달러 환율
    ]
    for stat, item in candidates:
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch"
            f"/{ECOS_KEY}/json/kr/1/2000"
            f"/{stat}/DD/{START_DATE}/{TODAY}/{item}"
        )
        print(f"[ECOS] {stat}/{item} 요청...")
        try:
            r = requests.get(url, timeout=20)
            print(f"[ECOS] HTTP {r.status_code}")
            data = r.json()
            top_keys = list(data.keys())
            print(f"[ECOS] 응답키: {top_keys}")

            if "RESULT" in data:
                print(f"[ECOS] 오류: {data['RESULT'].get('MESSAGE','')}")
                continue

            if "StatisticSearch" in data:
                rows = data["StatisticSearch"].get("row", [])
                print(f"[ECOS] row 수: {len(rows)}")
                if rows:
                    result = {}
                    for row in rows:
                        d = row.get("TIME","")
                        v = row.get("DATA_VALUE","")
                        if v and v not in ("-",""):
                            try:
                                dt = f"{d[:4]}-{d[4:6]}-{d[6:]}"
                                result[dt] = float(v.replace(",",""))
                            except:
                                pass
                    if result:
                        print(f"[ECOS] ✅ {len(result)}건 수신")
                        return result

        except Exception as e:
            print(f"[ECOS] 예외: {e}")

    raise RuntimeError("ECOS 모든 코드 실패")


# ── 2. USDJPY — Yahoo Finance ────────────────────
def fetch_jpy():
    end_ts   = int(time.time())
    start_ts = int(datetime.datetime(2022,6,1).timestamp())
    for host in ["query1", "query2"]:
        url = (
            f"https://{host}.finance.yahoo.com/v8/finance/chart/USDJPY=X"
            f"?period1={start_ts}&period2={end_ts}&interval=1d"
        )
        try:
            r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
            d = r.json()["chart"]["result"][0]
            result = {}
            for ts, cl in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]):
                if cl:
                    dt = datetime.date.fromtimestamp(ts).strftime("%Y-%m-%d")
                    result[dt] = round(float(cl), 3)
            if result:
                print(f"[Yahoo] ✅ {len(result)}건")
                return result
        except Exception as e:
            print(f"[Yahoo/{host}] {e}")
    raise RuntimeError("Yahoo 실패")


# ── 3. 병합 ──────────────────────────────────────
def merge(krw_d, jpy_d):
    common = sorted(set(krw_d) & set(jpy_d))
    print(f"[Merge] {len(common)}건, 최신: {common[-1]}")
    return common, [jpy_d[d] for d in common], [krw_d[d] for d in common]


# ── 4. HTML 갱신 ─────────────────────────────────
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
    html = re.sub(r'<!-- last-updated:.*?-->', stamp, html) if "<!-- last-updated:" in html \
           else html.replace("</head>", f"{stamp}\n</head>", 1)

    open(path, "w", encoding="utf-8").write(html)
    print(f"[HTML] 저장 완료")


# ── 5. 배지 갱신 ─────────────────────────────────
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
    print(f"=== 갱신 시작 {TODAY_DASH} ===")
    try:    krw_d = fetch_krw()
    except Exception as e: print(f"[FATAL] KRW: {e}"); raise SystemExit(1)
    try:    jpy_d = fetch_jpy()
    except Exception as e: print(f"[FATAL] JPY: {e}"); raise SystemExit(1)
    dates, jpy, krw = merge(krw_d, jpy_d)
    update_html(dates, jpy, krw)
    update_badges(dates, jpy, krw)
    print("=== 완료 ✅ ===")
