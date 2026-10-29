# 글로벌 시장 브리핑(시장·뉴스·실적)

- `index.html`: 화면. 같은 폴더의 `market.json`·`news.json`·`data.json`을 읽어 표시
- `market.json`: GitHub Actions(`.github/workflows/market.yml`, `scripts/update_market.py`)가 화~토 06:20·07:50 KST 갱신. 지수·섹터 ETF·원유는 Yahoo Finance 일봉 종가, 국채 금리는 미 재무부 고시(실패 시 FRED)
- `news.json`: 예약 작업(화~토 06:43 KST)이 전날 뉴스와 장 마감 메모(`marketMemo`)를 추가
- `data.json`: 예약 작업(매일 07:30·24:00 KST)이 실적 요약·발표 일정을 갱신

글 단위 주소: `#market`, `#news/<기사ID>`, `#earnings/<종목_기간>`, `#calendar`
