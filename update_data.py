"""
update_data.py
--------------
GitHub Actions에서 매일 자동 실행되는 데이터 갱신 스크립트.
- ECOS API  → USDKRW (한국은행 서울외환 매매기준율)
- Yahoo Finance → USDJPY
"""

import os
import re
import json
import requests
import datetime

# ── 설정 ──────────────────────────────────────────
ECOS_KEY   = os.environ.get("ECOS_API_KEY", "")
START_DATE = "20220601"
TODAY      = datetime.date.today().strftime("%Y%m%d")
TODAY_DASH = datetime.date.today().strftime("%Y-%m-%d")

print(f"ECOS_KEY 확인: {'설정됨 (' + ECOS_KEY[:4] + '...)' if ECOS_KEY else '❌ 없음'}")

# ── 1. USDKRW — 한국은행 ECOS ─────────────────────
def fetch_krw():
    candidates = [
        ("731Y001", "0000001"),
        ("036Y001", "0000003"),
        ("731Y001", "0000003"),
    ]
    for stat_code, item_code in candidates:
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch"
            f"/{ECOS_KEY}/json/kr/1/5000"
            f"/{stat_code}/DD/{START_DATE}/{TODAY}/{item_code}"
        )
        print(f"[ECOS] 시도: {stat_code}/{item_code}")
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()
            print(f"[ECOS] 응답 키: {list(data.keys())}")
            if "RESULT" in data:
                msg = data["RESULT"].get("MESSAGE","")
                print(f"[ECOS] 오류응답: {msg} → 다음 코드")
                continue
            if "StatisticSearch" not in data:
                print(f"[ECOS] StatisticSearch 없음: {str(data)[:200]}")
                continue
            rows = data["StatisticSearch"]["row"]
            if not rows:
                print("[ECOS] row 비어있음 → 다음 코드")
                continue
            result = {}
            for row in rows:
                date = row.get("TIME","")
                val  = row.get("DATA_VALUE","")
                if val and val not in ("-",""):
                    try:
                        dt = f"{date[:4]}-{date[4:6]}-{date[6:]}"
                        result[dt] = float(val.replace(",",""))
                    except Exception:
                        pass
            if result:
                print(f"[ECOS] ✅ USDKRW {len(result)}건 (코드: {stat_code}/{item_code})")
                return result
            print("[ECOS] 파싱 후 데이터 없음 → 다음 코드")
        except Exception as e:
            print(f"[ECOS] 예외: {e} → 다음 코드")
    raise RuntimeError("ECOS API: 모든 통계코드 시도 실패")


# ── 2. USDJPY — Yahoo Finance ──────────────────────
def fetch_jpy():
    import time
    end_ts   = int(time.time())
    start_ts = int(datetime.datetime(2022,6,1).timestamp())
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/USDJPY=X?period1={start_ts}&period2={end_ts}&interval=1d",
        f"https://query2.finance.yahoo.com/v8/finance/chart/USDJPY=X?period1={start_ts}&period2={end_ts}&interval=1d",
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            data       = r.json()["chart"]["result"][0]
            timestamps = data["timestamp"]
            closes     = data["indicators"]["quote"][0]["close"]
            result = {}
            for ts, cl in zip(timestamps, closes):
                if cl is None:
                    continue
                dt = datetime.date.fromtimestamp(ts).strftime("%Y-%m-%d")
                result[dt] = round(float(cl), 3)
            if result:
                print(f"[Yahoo] ✅ USDJPY {len(result)}건")
                return result
        except Exception as e:
            print(f"[Yahoo] 오류: {e} → 다음 URL")
    raise RuntimeError("Yahoo Finance: 모든 URL 시도 실패")


# ── 3. 병합 ──────────────────────────────────────
def merge(krw_dict, jpy_dict):
    common = sorted(set(krw_dict) & set(jpy_dict))
    dates  = common
    krw    = [krw_dict[d] for d in common]
    jpy    = [jpy_dict[d] for d in common]
    print(f"[Merge] 공통 {len(dates)}건 (최신: {dates[-1]})")
    return dates, jpy, krw


# ── 4. HTML 업데이트 ──────────────────────────────
def update_html(dates, jpy, krw, html_path="index.html"):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    def replace_var(content, var_name, new_list):
        pattern = rf'(const {var_name}=)\[.*?\]'
        replacement = rf'\g<1>{json.dumps(new_list, ensure_ascii=False)}'
        new_content, n = re.subn(pattern, replacement, content, flags=re.DOTALL)
        print(f"  {'✅' if n else '⚠️ '} {var_name} ({len(new_list)}건, 치환:{n})")
        return new_content if n else content

    html = replace_var(html, "dates",   dates)
    html = replace_var(html, "jpyData", jpy)
    html = replace_var(html, "krwData", krw)

    stamp = f"<!-- last-updated: {TODAY_DASH} -->"
    if "<!-- last-updated:" in html:
        html = re.sub(r'<!-- last-updated:.*?-->', stamp, html)
    else:
        html = html.replace("</head>", f"{stamp}\n</head>", 1)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[HTML] 저장 완료")


# ── 5. 배지 업데이트 ──────────────────────────────
def update_badges(dates, jpy, krw, html_path="index.html"):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    lj, lk, ld = jpy[-1], krw[-1], dates[-1]
    html = re.sub(r'USDJPY \d+\.\d+',     f'USDJPY {lj:.1f}', html)
    html = re.sub(r'USDKRW [\d,]+',       f'USDKRW {lk:,.0f}', html)
    html = re.sub(r'\d{4}\.\d{2}\.\d{2} 기준', f'{ld.replace("-",".")} 기준', html)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Badge] JPY={lj:.1f}, KRW={lk:,.0f} ({ld})")


# ── MAIN ─────────────────────────────────────────
if __name__ == "__main__":
    print(f"=== 데이터 갱신 시작 ({TODAY_DASH}) ===")
    try:
        krw_dict = fetch_krw()
    except Exception as e:
        print(f"[FATAL] KRW 실패: {e}")
        raise SystemExit(1)
    try:
        jpy_dict = fetch_jpy()
    except Exception as e:
        print(f"[FATAL] JPY 실패: {e}")
        raise SystemExit(1)
    dates, jpy, krw = merge(krw_dict, jpy_dict)
    update_html(dates, jpy, krw)
    update_badges(dates, jpy, krw)
    print("=== 완료 ✅ ===")
