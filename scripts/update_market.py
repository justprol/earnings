#!/usr/bin/env python3
"""market.json 생성: 미국 주요 지수·섹터 ETF·반도체 지수·국채 금리·유가의 일별 종가와 기간 수익률.

- 가격: Yahoo Finance chart API(일봉 종가, 가격 기준·배당 미포함)
- 국채 금리: 미 재무부 Daily Treasury Par Yield Curve(2·10·30년)
값을 받지 못한 종목은 이전 market.json 값을 유지하고 notes에 사유를 남긴다.
"""
import csv, io, json, os, sys, time, urllib.request, urllib.parse
from datetime import date, datetime, timedelta, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'market.json')
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
      'Accept': 'application/json,text/csv,*/*'}
KST = timezone(timedelta(hours=9))

ITEMS = [
    # id, 그룹, 이름, 심볼, 종류, 단위
    ('SPX',   'index',  'S&P 500',            '^GSPC', 'price', 'pt'),
    ('NDX',   'index',  '나스닥 100',          '^NDX',  'price', 'pt'),
    ('RUT',   'index',  '러셀 2000',           '^RUT',  'price', 'pt'),
    ('DJI',   'index',  '다우존스',            '^DJI',  'price', 'pt'),
    ('SPXEW', 'index',  'S&P 500 동일가중',     '^SPXEW', 'price', 'pt'),
    ('SOX',   'index',  '필라델피아 반도체',     '^SOX',  'price', 'pt'),
    ('SPY',   'sector', 'S&P 500 (기준)', 'SPY',   'price', '$'),
    ('XLK',   'sector', '정보기술',            'XLK',   'price', '$'),
    ('XLC',   'sector', '커뮤니케이션',         'XLC',   'price', '$'),
    ('XLY',   'sector', '경기소비재',           'XLY',   'price', '$'),
    ('XLF',   'sector', '금융',               'XLF',   'price', '$'),
    ('XLV',   'sector', '헬스케어',            'XLV',   'price', '$'),
    ('XLI',   'sector', '산업재',              'XLI',   'price', '$'),
    ('XLE',   'sector', '에너지',              'XLE',   'price', '$'),
    ('XLP',   'sector', '필수소비재',           'XLP',   'price', '$'),
    ('XLU',   'sector', '유틸리티',            'XLU',   'price', '$'),
    ('XLB',   'sector', '소재',               'XLB',   'price', '$'),
    ('XLRE',  'sector', '부동산',              'XLRE',  'price', '$'),
    ('US2Y',  'rate',   '미국 2년물',           '2 Yr',  'yield', '%'),
    ('US10Y', 'rate',   '미국 10년물',          '10 Yr', 'yield', '%'),
    ('US30Y', 'rate',   '미국 30년물',          '30 Yr', 'yield', '%'),
    ('WTI',   'commod', 'WTI 원유',            'CL=F',  'price', '$'),
    ('BRENT', 'commod', '브렌트 원유',          'BZ=F',  'price', '$'),
]


def log(level, msg):
    """GitHub Actions 주석으로 남겨 API로 확인 가능하게 함."""
    print(f'::{level}::{msg}', flush=True)


def get(url, tries=2):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(2 * (i + 1))
    raise last


def drop_unsettled(sym, pts):
    """장중 실행 대비: 미국 동부 기준 오늘 봉이 아직 확정 종가가 아니면 제외."""
    now = datetime.now(timezone.utc)
    now_et = now - timedelta(hours=4 if is_dst_et(now) else 5)
    close = (14, 45) if sym.endswith('=F') else (16, 15)
    if pts and pts[-1][0] == now_et.date().isoformat() and (now_et.hour, now_et.minute) < close:
        return pts[:-1]
    return pts


YF = {}


def yf_all(syms):
    """yfinance로 한 번에 받기(실패 시 빈 dict)."""
    try:
        import yfinance as yf
        df = yf.download(syms, period='2y', interval='1d', auto_adjust=False, progress=False,
                         group_by='ticker', threads=True, timeout=30)
        for sy in syms:
            try:
                ser = df[sy]['Close'].dropna()
                pts = [(ix.date().isoformat(), round(float(v), 4)) for ix, v in ser.items()]
                pts = drop_unsettled(sy, pts)
                if len(pts) >= 30:
                    YF[sy] = pts
            except Exception as e:  # noqa
                log('warning', f'yfinance {sy}: {type(e).__name__} {str(e)[:120]}')
        log('notice', f'yfinance ok {len(YF)}/{len(syms)}')
    except Exception as e:  # noqa
        log('warning', f'yfinance 실패: {type(e).__name__} {str(e)[:160]}')


def yahoo(sym):
    if sym in YF:
        return YF[sym]
    q = urllib.parse.quote(sym)
    err = None
    for host in ('query1', 'query2'):
        try:
            j = json.loads(get(f'https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range=2y&interval=1d&includePrePost=false'))
            res = j['chart']['result'][0]
            off = res['meta'].get('gmtoffset', 0)
            ts = res.get('timestamp') or []
            cl = res['indicators']['quote'][0]['close']
            by = {}
            for t, c in zip(ts, cl):
                if c is None:
                    continue
                d = datetime.fromtimestamp(t + off, tz=timezone.utc).date().isoformat()
                by[d] = round(float(c), 4)
            pts = drop_unsettled(sym, sorted(by.items()))
            if len(pts) < 30:
                raise ValueError(f'too few points {len(pts)}')
            return pts
        except Exception as e:  # noqa
            err = e
            log('warning', f'yahoo {host} {sym}: {type(e).__name__} {str(e)[:120]}')
    raise err


def is_dst_et(now_utc):
    y = now_utc.year
    # 3월 둘째 일요일 07:00 UTC ~ 11월 첫째 일요일 06:00 UTC
    m = date(y, 3, 1); start = m + timedelta(days=(6 - m.weekday()) % 7 + 7)
    n = date(y, 11, 1); end = n + timedelta(days=(6 - n.weekday()) % 7)
    s = datetime(start.year, start.month, start.day, 7, tzinfo=timezone.utc)
    e = datetime(end.year, end.month, end.day, 6, tzinfo=timezone.utc)
    return s <= now_utc < e


def fred(series_id):
    txt = get(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}').decode('utf-8-sig')
    pts = []
    for r in csv.reader(io.StringIO(txt)):
        if len(r) < 2 or not r[0][:1].isdigit() or r[1] in ('', '.'):
            continue
        pts.append((r[0], round(float(r[1]), 3)))
    if len(pts) < 30:
        raise ValueError('fred too few points')
    return pts


def treasury():
    try:
        return treasury_gov()
    except Exception as e:  # noqa
        log('warning', f'treasury.gov 실패: {type(e).__name__} {str(e)[:120]} — FRED로 대체')
    out = {}
    for col, sid in (('2 Yr', 'DGS2'), ('10 Yr', 'DGS10'), ('30 Yr', 'DGS30')):
        pts = fred(sid)
        cut = (date.today() - timedelta(days=800)).isoformat()
        out[col] = [x for x in pts if x[0] >= cut]
    out['_src'] = 'FRED(미 연준 세인트루이스, 재무부 고시 금리 재게시)'
    return out


def treasury_gov():
    y = datetime.now(timezone.utc).year
    rows = {}
    for yy in (y - 2, y - 1, y):
        url = ('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/'
               f'{yy}/all?type=daily_treasury_yield_curve&field_tdr_date_value={yy}&page&_format=csv')
        try:
            txt = get(url).decode('utf-8-sig')
        except Exception as e:  # noqa
            if yy == y:
                raise
            continue
        for r in csv.DictReader(io.StringIO(txt)):
            try:
                d = datetime.strptime(r['Date'].strip(), '%m/%d/%Y').date().isoformat()
            except Exception:  # noqa
                continue
            rows[d] = r
    out = {}
    for col in ('2 Yr', '10 Yr', '30 Yr'):
        pts = []
        for d in sorted(rows):
            v = (rows[d].get(col) or '').strip()
            if v and v.upper() != 'N/A':
                pts.append((d, round(float(v), 3)))
        if len(pts) < 30:
            raise ValueError(f'treasury {col} too few points')
        out[col] = pts
    out['_src'] = '미 재무부 Daily Treasury Par Yield Curve'
    return out


def base_before(pts, cutoff):
    """cutoff(포함) 이전의 마지막 관측치."""
    b = None
    for d, v in pts:
        if d <= cutoff:
            b = (d, v)
        else:
            break
    return b


def minus_months(d, m):
    y, mo = d.year, d.month - m
    while mo <= 0:
        mo += 12; y -= 1
    import calendar
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def changes(pts, kind):
    ld = date.fromisoformat(pts[-1][0]); lv = pts[-1][1]
    cut = {
        '1D': pts[-2][0] if len(pts) > 1 else None,
        '1W': (ld - timedelta(days=7)).isoformat(),
        '1M': minus_months(ld, 1).isoformat(),
        '6M': minus_months(ld, 6).isoformat(),
        'YTD': date(ld.year - 1, 12, 31).isoformat(),
        '1Y': minus_months(ld, 12).isoformat(),
    }
    chg, base = {}, {}
    for k, c in cut.items():
        b = base_before(pts, c) if c else None
        if not b or b[0] == pts[-1][0]:
            chg[k] = None; continue
        base[k] = b[0]
        chg[k] = round((lv - b[1]) * 100, 1) if kind == 'yield' else round((lv / b[1] - 1) * 100, 2)
    return chg, base


def main():
    old = {}
    if os.path.exists(OUT):
        try:
            old = {i['id']: i for i in json.load(open(OUT, encoding='utf-8')).get('items', [])}
        except Exception:  # noqa
            old = {}
    notes, items = [], []
    yf_all([x[3] for x in ITEMS if x[4] == 'price'])
    try:
        tre = treasury()
    except Exception as e:  # noqa
        tre = None
        notes.append(f'미 재무부 금리 자료 수신 실패({type(e).__name__}) — 금리는 이전 값 유지')
    for iid, grp, name, sym, kind, unit in ITEMS:
        try:
            if kind == 'yield':
                if tre is None:
                    raise ValueError('no treasury')
                pts, src = tre[sym], tre['_src']
            else:
                pts, src = yahoo(sym), 'Yahoo Finance 일봉 종가(가격 기준)'
        except Exception as e:  # noqa
            log('warning', f'{iid} 실패: {type(e).__name__} {str(e)[:120]}')
            if iid in old:
                items.append(old[iid]); notes.append(f'{name} 수신 실패({type(e).__name__}) — 이전 값 유지')
            else:
                notes.append(f'{name} 수신 실패({type(e).__name__})')
            continue
        chg, base = changes(pts, kind)
        ld = date.fromisoformat(pts[-1][0])
        start = min(minus_months(ld, 12), date(ld.year - 1, 12, 31)) - timedelta(days=7)
        series = [[d, v] for d, v in pts if d >= start.isoformat()]
        items.append({'id': iid, 'group': grp, 'name': name, 'sym': sym if kind != 'yield' else f'UST {sym}',
                      'kind': kind, 'unit': unit, 'date': pts[-1][0], 'last': pts[-1][1],
                      'chg': chg, 'base': base, 'series': series, 'src': src})
        time.sleep(0.4)
    spx = next((i for i in items if i['id'] == 'SPX'), None)
    data = {'asOf': spx['date'] if spx else max((i['date'] for i in items), default=None),
            'items': items, 'notes': notes,
            'method': '기간 수익률 = 마지막 종가 ÷ 기준일 종가 − 1. 기준일은 1W·1M·6M·1Y는 해당 날짜 이전 마지막 거래일, YTD는 전년 마지막 거래일. 금리는 %p 변화를 bp(0.01%p)로 표시.'}
    prev = None
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT, encoding='utf-8'))
        except Exception:  # noqa
            prev = None
    if prev and {k: v for k, v in prev.items() if k != 'generatedAt'} == data:
        print('no change'); return
    data = {'generatedAt': datetime.now(KST).isoformat(timespec='seconds'), **data}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    log('notice', f"asOf {data['asOf']} items {len(items)} notes {notes}")
    if not items:
        sys.exit(1)


if __name__ == '__main__':
    main()
