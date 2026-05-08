"""
update_data.py
--------------
GitHub Actions에서 매일 자동 실행되는 데이터 갱신 스크립트.
- ECOS API  → USDKRW (한국은행 서울외환 매매기준율)
- Yahoo Finance → USDJPY
- 두 데이터를 합쳐 index.html 안의 JS 변수를 업데이트
"""

import os
import re
import json
import requests
import datetime
from datetime import timedelta

# ── 설정 ──────────────────────────────────────────
ECOS_KEY   = os.environ.get("ECOS_API_KEY", "VEEZ0ODH4SO0AQH8OICV")
START_DATE = "20220601"
TODAY      = datetime.date.today().strftime("%Y%m%d")
TODAY_DASH = datetime.date.today().strftime("%Y-%m-%d")

# ── 1. USDKRW — 한국은행 ECOS ─────────────────────
def fetch_krw():
    """서울외환시장 매매기준율 (731Y001 / 0000001)"""
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch"
        f"/{ECOS_KEY}/json/kr/1/5000"
        f"/731Y001/DD/{START_DATE}/{TODAY}/0000001"
    )
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    rows = r.json()["StatisticSearch"]["row"]
    # {날짜: 종가} 딕셔너리
    result = {}
    for row in rows:
        date = row["TIME"]  # "20220601" 형식
        val  = row["DATA_VALUE"]
        if val and val != "-":
            dt = f"{date[:4]}-{date[4:6]}-{date[6:]}"  # "2022-06-01"
            result[dt] = float(val)
    print(f"[ECOS] USDKRW {len(result)}건 수신")
    return result

# ── 2. USDJPY — Yahoo Finance ──────────────────────
def fetch_jpy():
    """Yahoo Finance 비공식 API (무료, 키 불필요)"""
    import time
    end_ts   = int(time.time())
    start_ts = int(datetime.datetime(2022, 6, 1).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/USDJPY=X"
        f"?period1={start_ts}&period2={end_ts}&interval=1d"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    data      = r.json()["chart"]["result"][0]
    timestamps = data["timestamp"]
    closes     = data["indicators"]["quote"][0]["close"]
    result = {}
    for ts, cl in zip(timestamps, closes):
        if cl is None:
            continue
        dt = datetime.date.fromtimestamp(ts).strftime("%Y-%m-%d")
        result[dt] = round(float(cl), 3)
    print(f"[Yahoo] USDJPY {len(result)}건 수신")
    return result

# ── 3. 두 시리즈 병합 ────────────────────────────
def merge(krw_dict, jpy_dict):
    """공통 날짜만 남기고 날짜순 정렬"""
    common = sorted(set(krw_dict) & set(jpy_dict))
    dates  = common
    krw    = [krw_dict[d] for d in common]
    jpy    = [jpy_dict[d] for d in common]
    print(f"[Merge] 공통 날짜 {len(dates)}건 (최신: {dates[-1]})")
    return dates, jpy, krw

# ── 4. index.html JS 변수 업데이트 ───────────────
def update_html(dates, jpy, krw, html_path="index.html"):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    def replace_var(content, var_name, new_list):
        # const varName=[...]; 패턴을 새 값으로 교체
        pattern = rf'(const {var_name}=)\[.*?\]'
        replacement = rf'\g<1>{json.dumps(new_list, ensure_ascii=False)}'
        new_content, n = re.subn(pattern, replacement, content, flags=re.DOTALL)
        if n == 0:
            print(f"  ⚠️  {var_name} 변수를 찾지 못했습니다.")
        else:
            print(f"  ✅  {var_name} 업데이트 완료 ({len(new_list)}건)")
        return new_content

    html = replace_var(html, "dates",   dates)
    html = replace_var(html, "jpyData", jpy)
    html = replace_var(html, "krwData", krw)

    # 마지막 업데이트 시각 주석 추가/갱신
    stamp = f"<!-- last-updated: {TODAY_DASH} -->"
    if "<!-- last-updated:" in html:
        html = re.sub(r'<!-- last-updated:.*?-->', stamp, html)
    else:
        html = html.replace("</head>", f"{stamp}\n</head>", 1)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[HTML] {html_path} 저장 완료")

# ── 5. KPI 배지 업데이트 ─────────────────────────
def update_badges(dates, jpy, krw, html_path="index.html"):
    """헤더 배지의 현재 환율 수치 갱신"""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    latest_jpy = jpy[-1]
    latest_krw = krw[-1]
    latest_date = dates[-1]

    html = re.sub(
        r'USDJPY \d+\.\d+',
        f'USDJPY {latest_jpy:.1f}',
        html
    )
    html = re.sub(
        r'USDKRW \d[\d,]+',
        f'USDKRW {latest_krw:,.0f}',
        html
    )
    # 기준일 업데이트
    html = re.sub(
        r'\d{4}\.\d{2}\.\d{2} 기준',
        f'{latest_date.replace("-",".")} 기준',
        html
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Badge] JPY={latest_jpy:.1f}, KRW={latest_krw:,.0f} ({latest_date})")

# ── MAIN ─────────────────────────────────────────
if __name__ == "__main__":
    print(f"=== 데이터 갱신 시작 ({TODAY_DASH}) ===")
    try:
        krw_dict = fetch_krw()
    except Exception as e:
        print(f"[ECOS 오류] {e} — KRW 데이터 갱신 실패, 종료")
        raise

    try:
        jpy_dict = fetch_jpy()
    except Exception as e:
        print(f"[Yahoo 오류] {e} — JPY 데이터 갱신 실패, 종료")
        raise

    dates, jpy, krw = merge(krw_dict, jpy_dict)
    update_html(dates, jpy, krw)
    update_badges(dates, jpy, krw)
    print("=== 완료 ✅ ===")
