"""
AJ Racing Bot — Railway Scheduled Service
Runs daily at 8:30am BST. Logs in, downloads file, finds picks, sends Telegram.
"""

import os, sys, io, logging, requests, openpyxl
from datetime import date, datetime, timedelta
from collections import defaultdict
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

# ── CONFIG — Railway Environment Variables ────────────────
RBD_EMAIL    = os.environ['RBD_EMAIL']
RBD_PASSWORD = os.environ['RBD_PASSWORD']
TG_TOKEN     = os.environ['TG_TOKEN']
TG_CHAT_ID   = os.environ['TG_CHAT_ID']
STAKE        = float(os.environ.get('STAKE', '3.0'))

BASE_URL     = 'https://www.racing-bet-data.com'
SIGNIN_URL   = f'{BASE_URL}/signin/'
TODAY_URL    = f'{BASE_URL}/today/'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9',
}

# ── AJ SYSTEM RULES ───────────────────────────────────────
FF_TRACKS = {
    'WOLVERHAMPTON':   {'min': 3, 'max': 8,   'bsp': 3},
    'SOUTHWELL':       {'min': 4, 'max': 8,   'bsp': 4},
    'LINGFIELD':       {'min': 5, 'max': 999, 'bsp': 5},
    'NEWCASTLE':       {'min': 3, 'max': 8,   'bsp': 3},
    'DUNDALK':         {'min': 3, 'max': 8,   'bsp': 3},
    'CHELMSFORD CITY': {'min': 5, 'max': 999, 'bsp': 5},
    'REDCAR':          {'min': 5, 'max': 999, 'bsp': 5},
}

LAY_SYSTEMS = [
    {'id': 1,  'name': 'Lay Sys 1',  'track': 'CHEPSTOW',        'flag': 'BACK',  'min': 5, 'max': 8},
    {'id': 2,  'name': 'Lay Sys 2',  'track': 'MUSSELBURGH',     'flag': 'ALL',   'min': 5, 'max': 8},
    {'id': 3,  'name': 'Lay Sys 3',  'track': 'HEXHAM',          'flag': 'ALL',   'min': 5, 'max': 8},
    {'id': 4,  'name': 'Lay Sys 4',  'track': 'DONCASTER',       'flag': 'PEAK',  'min': 3, 'max': 8},
    {'id': 5,  'name': 'Lay Sys 5',  'track': 'CATTERICK',       'flag': 'WATCH', 'min': 4, 'max': 6},
    {'id': 6,  'name': 'Lay Sys 6',  'track': 'HAYDOCK',         'flag': 'PEAK',  'min': 4, 'max': 8},
    {'id': 7,  'name': 'Lay Sys 7',  'track': 'AYR',             'flag': 'BACK',  'min': 3, 'max': 5},
    {'id': 8,  'name': 'Lay Sys 8',  'track': 'LEICESTER',       'flag': 'BACK',  'min': 4, 'max': 6},
    {'id': 9,  'name': 'Lay Sys 9',  'track': 'DUNDALK',         'flag': 'BACK',  'min': 5, 'max': 8},
    {'id': 10, 'name': 'Lay Sys 10', 'track': 'LINGFIELD',       'flag': 'PEAK',  'min': 5, 'max': 8},
    {'id': 11, 'name': 'Lay Sys 11', 'track': 'CHELMSFORD CITY', 'flag': 'WATCH', 'min': 5, 'max': 8},
    {'id': 12, 'name': 'Lay Sys 12', 'track': 'WOLVERHAMPTON',   'flag': 'PEAK',  'min': 5, 'max': 8},
    {'id': 13, 'name': 'Lay Sys 13', 'track': 'NEWMARKET',       'flag': 'PEAK',  'min': 4, 'max': 6},
    {'id': 14, 'name': 'Lay Sys 14', 'track': 'BANGOR-ON-DEE',   'flag': 'WATCH', 'min': 5, 'max': 8},
    {'id': 15, 'name': 'Lay Sys 15', 'track': 'MUSSELBURGH',     'flag': 'WATCH', 'min': 4, 'max': 8},
    {'id': 16, 'name': 'Lay Sys 16', 'track': 'NEWBURY',         'flag': 'WATCH', 'min': 2, 'max': 4},
]

COL_DATE=0; COL_TRACK=2; COL_TIME=7; COL_HORSE=9
COL_PRED_ISP=16; COL_LTO_IPL=38; COL_LTO_POS=64; COL_OR_DIFF=49

# ── ASP.NET HELPERS ───────────────────────────────────────
def get_aspnet_fields(soup):
    """Extract all hidden ASP.NET fields from a page"""
    fields = {}
    for inp in soup.find_all('input', {'type': 'hidden'}):
        name = inp.get('name', '')
        val  = inp.get('value', '')
        if name:
            fields[name] = val
    return fields

# ── STEP 1: LOGIN ─────────────────────────────────────────
def login():
    session = requests.Session()
    session.headers.update(HEADERS)

    log.info("GET signin page...")
    r = session.get(SIGNIN_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')

    # Grab all hidden ASP.NET fields (__VIEWSTATE etc)
    payload = get_aspnet_fields(soup)
    log.info(f"Hidden fields found: {list(payload.keys())}")

    # Add credentials — exact field names from F12
    payload['ctl00$ContentPlaceHolder2$unameTextBox'] = RBD_EMAIL
    payload['ctl00$ContentPlaceHolder2$pwordTextBox'] = RBD_PASSWORD
    payload['ctl00$ContentPlaceHolder2$submitButton'] = 'Submit'

    log.info(f"POST signin for {RBD_EMAIL}...")
    r = session.post(SIGNIN_URL, data=payload, timeout=30,
                     allow_redirects=True,
                     headers={**HEADERS,
                              'Content-Type': 'application/x-www-form-urlencoded',
                              'Referer': SIGNIN_URL,
                              'Origin': BASE_URL})
    r.raise_for_status()

    # Check we're no longer on the signin page
    if '/signin' in r.url or '/login' in r.url:
        soup2 = BeautifulSoup(r.text, 'html.parser')
        err = (soup2.find(class_='validation-summary-errors') or
               soup2.find(class_='error') or
               soup2.find(class_='alert-danger'))
        msg = err.get_text(strip=True) if err else f"Still on signin page: {r.url}"
        raise Exception(f"Login failed: {msg}")

    log.info(f"Logged in. URL: {r.url}")
    return session

# ── STEP 2: DOWNLOAD FILE ─────────────────────────────────
def download_file(session):
    log.info("GET today's page...")
    r = session.get(TODAY_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')

    # Grab all ASP.NET hidden fields from the page
    payload = get_aspnet_fields(soup)
    log.info(f"Today page hidden fields: {list(payload.keys())}")

    # The Download button — from F12: ctl00$ContentPlaceHolder1$dlButton1=Download
    payload['__EVENTTARGET']   = ''
    payload['__EVENTARGUMENT'] = ''
    payload['ctl00$ContentPlaceHolder1$dlButton1'] = 'Download'

    # Check scroll position fields exist
    payload.setdefault('__SCROLLPOSITIONX', '0')
    payload.setdefault('__SCROLLPOSITIONY', '300')

    log.info("POST download request...")
    r = session.post(TODAY_URL, data=payload, timeout=60,
                     headers={**HEADERS,
                              'Content-Type': 'application/x-www-form-urlencoded',
                              'Referer': TODAY_URL,
                              'Origin': BASE_URL})
    r.raise_for_status()

    content_type = r.headers.get('content-type', '').lower()
    log.info(f"Response: {len(r.content):,} bytes | type: {content_type}")

    # Should be xlsx
    if len(r.content) < 5000:
        # Might have returned HTML — try to find a direct link instead
        soup2 = BeautifulSoup(r.text, 'html.parser')
        for a in soup2.find_all('a', href=True):
            href = a['href']
            if '.xlsx' in href or '.xls' in href:
                url = href if href.startswith('http') else BASE_URL + href
                log.info(f"Found direct xlsx link: {url}")
                r2 = session.get(url, timeout=60)
                r2.raise_for_status()
                return r2.content
        raise Exception(f"Download response too small ({len(r.content)} bytes). "
                        f"Content-type: {content_type}")

    log.info(f"Downloaded {len(r.content):,} bytes OK")
    return r.content

# ── STEP 3: PARSE XLSX ────────────────────────────────────
def excel_serial_to_str(v):
    if isinstance(v, (int, float)) and v > 40000:
        return (date(1899, 12, 30) + timedelta(days=int(v))).strftime('%Y-%m-%d')
    return ''

def excel_time_to_str(v):
    if isinstance(v, (int, float)):
        total = round(v * 24 * 60)
        h, m = divmod(total, 60)
        return f"{h:02d}:{m:02d}"
    if isinstance(v, str) and ':' in v:
        return v[:5]
    return '--:--'

def safe_float(v, default=0):
    try: return float(v) if v not in (None, '') else default
    except: return default

def calc_flag(lto_ipl, lto_pos, or_diff):
    score = 0
    if lto_ipl < 2:    score += 25
    elif lto_ipl < 3:  score += 20
    elif lto_ipl < 5:  score += 10
    elif lto_ipl > 50: score -= 10
    if lto_pos == 1:   score += 18
    elif lto_pos <= 3: score += 15
    elif lto_pos <= 6: score += 5
    else:              score -= 5
    if 0 <= or_diff <= 10: score += 15
    elif or_diff > 10:     score += 8
    elif -5 <= or_diff < 0: score += 3
    else:              score -= 10
    lay = (20 if lto_ipl > 50 else 0) + (15 if or_diff < -5 else 0) + (10 if lto_pos > 8 else 0)
    if lay >= 35:    return 'LAY'
    if score >= 65:  return 'PEAK'
    if score >= 40:  return 'BACK'
    if score >= 20:  return 'WATCH'
    return 'SKIP'

def parse_xlsx(content):
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    sn = 'Combined' if 'Combined' in wb.sheetnames else wb.sheetnames[0]
    ws = wb[sn]
    all_rows = list(ws.iter_rows(values_only=True))
    log.info(f"Sheet '{sn}': {len(all_rows)} rows x {len(all_rows[0]) if all_rows else 0} cols")

    # Find header row
    header_idx = 0
    for i, row in enumerate(all_rows[:10]):
        if row and str(row[9] or '').strip().lower() == 'horse':
            header_idx = i
            log.info(f"Header row {i}: cols={len(row)}")
            break

    data = all_rows[header_idx + 1:]

    # Latest date = today's races
    max_ds = max(
        (r[COL_DATE] for r in data
         if r and len(r) > COL_DATE and isinstance(r[COL_DATE], (int, float))),
        default=0
    )
    if not max_ds:
        raise Exception("No date found in file")

    file_date = excel_serial_to_str(max_ds)
    log.info(f"Race date: {file_date}")

    horses = []
    for r in data:
        if not r or len(r) <= COL_HORSE: continue
        ds = r[COL_DATE] if len(r) > COL_DATE else None
        if not isinstance(ds, (int, float)) or abs(ds - max_ds) > 0.5: continue
        horse = str(r[COL_HORSE] or '').strip()
        if not horse: continue

        pred_isp = safe_float(r[COL_PRED_ISP] if len(r) > COL_PRED_ISP else None)
        lto_ipl  = safe_float(r[COL_LTO_IPL]  if len(r) > COL_LTO_IPL  else None, 99)
        lto_pos  = safe_float(r[COL_LTO_POS]  if len(r) > COL_LTO_POS  else None, 99)
        or_diff  = safe_float(r[COL_OR_DIFF]   if len(r) > COL_OR_DIFF  else None, 0)
        if lto_ipl == 0: lto_ipl = 99
        if lto_pos == 0: lto_pos = 99

        horses.append({
            'horse':    horse,
            'track':    str(r[COL_TRACK] or '').strip().upper() if len(r) > COL_TRACK else '',
            'time':     excel_time_to_str(r[COL_TIME] if len(r) > COL_TIME else None),
            'pred_isp': pred_isp,
            'lto_ipl':  lto_ipl,
            'lto_pos':  lto_pos,
            'flag':     calc_flag(lto_ipl, lto_pos, or_diff),
        })

    log.info(f"Parsed {len(horses)} horses")
    if horses:
        s = horses[0]
        log.info(f"Sample: {s['horse']} @ {s['track']} {s['time']} odds={s['pred_isp']} flag={s['flag']}")
    return horses, file_date

# ── STEP 4: SCAN FOR PICKS ────────────────────────────────
def in_season_redcar():
    return 4 <= date.today().month <= 10

def scan_picks(horses):
    picks  = []
    added  = set()

    # FALSE FAV — lowest pred_isp per race at FF tracks
    races = defaultdict(list)
    for h in horses:
        if h['pred_isp'] > 0 and h['track']:
            races[f"{h['track']}|{h['time']}"].append(h)

    for race_runners in races.values():
        race_runners.sort(key=lambda x: x['pred_isp'])
        fav   = race_runners[0]
        track = fav['track']
        odds  = fav['pred_isp']
        rule  = FF_TRACKS.get(track)
        if not rule: continue
        if track == 'REDCAR' and not in_season_redcar(): continue
        if odds < rule['min'] or odds > rule['max']: continue
        key = f"{fav['horse']}|FF"
        if key in added: continue
        added.add(key)
        picks.append({'horse': fav['horse'], 'track': track, 'time': fav['time'],
                      'system': 'False Fav', 'odds': odds,
                      'liability': round((odds - 1) * STAKE, 2)})

    # LAY SYSTEMS 1-16
    for h in horses:
        if h['pred_isp'] <= 0 or not h['track']: continue
        for sys in LAY_SYSTEMS:
            if sys['track'] != h['track']: continue
            if sys['flag'] != 'ALL' and h['flag'] != sys['flag']: continue
            if h['pred_isp'] < sys['min'] or h['pred_isp'] > sys['max']: continue
            key = f"{h['horse']}|{sys['name']}"
            if key in added: continue
            added.add(key)
            picks.append({'horse': h['horse'], 'track': h['track'], 'time': h['time'],
                          'system': sys['name'], 'odds': h['pred_isp'],
                          'liability': round((h['pred_isp'] - 1) * STAKE, 2)})

    picks.sort(key=lambda x: x['time'])
    log.info(f"Picks: {len([p for p in picks if p['system']=='False Fav'])} FF + "
             f"{len([p for p in picks if p['system']!='False Fav'])} Sys = {len(picks)} total")
    return picks

def save_picks_locally(picks, file_date):
    """Save today's picks to file so evening bot can settle them"""
    import json
    picks_dir = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '/tmp/aj_data')
    os.makedirs(picks_dir, exist_ok=True)
    path = os.path.join(picks_dir, f'picks_{file_date}.json')
    with open(path, 'w') as f:
        json.dump(picks, f, indent=2)
    log.info(f"Picks saved to {path}")

def load_picks_locally(date_str):
    """Load picks saved by morning bot"""
    import json
    picks_dir = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '/tmp/aj_data')
    path = os.path.join(picks_dir, f'picks_{date_str}.json')
    if not os.path.exists(path):
        log.warning(f"No picks file found at {path}")
        return []
    with open(path, 'r') as f:
        picks = json.load(f)
    log.info(f"Loaded {len(picks)} picks from {path}")
    return picks

# ── STEP 5: TELEGRAM ─────────────────────────────────────
def build_message(picks, file_date):
    today_str = datetime.now().strftime('%A %d %B %Y')
    if not picks:
        return f"🏇 AJ RACING — {today_str}\n\nNo qualifying picks today."

    ff  = [p for p in picks if p['system'] == 'False Fav']
    sys = [p for p in picks if p['system'] != 'False Fav']
    tot = round(sum(p['liability'] for p in picks), 2)

    lines = [f"🏇 AJ RACING PICKS — {today_str}",
             f"Stake: £{STAKE:.2f}/pt", "—" * 30, ""]

    if ff:
        lines.append(f"🔴 FALSE FAV LAYS ({len(ff)})")
        for i, p in enumerate(ff, 1):
            lines.append(f"  {i}. {p['horse']}")
            lines.append(f"     {p['track']} · {p['time']} · @{p['odds']:.1f} · Liability £{p['liability']:.2f}")
        lines.append("")

    if sys:
        lines.append(f"🔴 LAY SYSTEMS ({len(sys)})")
        for i, p in enumerate(sys, 1):
            lines.append(f"  {i}. {p['horse']} [{p['system']}]")
            lines.append(f"     {p['track']} · {p['time']} · @{p['odds']:.1f} · Liability £{p['liability']:.2f}")
        lines.append("")

    lines += ["—" * 30,
              f"📊 {len(ff)} FF + {len(sys)} Sys = {len(picks)} total",
              f"Total Liability: £{tot:.2f}",
              "⚠️ Pred Odds — verify BSP at race time"]
    return "\n".join(lines)

def send_telegram(text):
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      json={'chat_id': TG_CHAT_ID, 'text': text}, timeout=30)
    r.raise_for_status()
    if not r.json().get('ok'):
        raise Exception(f"Telegram error: {r.json()}")
    log.info("Telegram sent OK")

# ── MAIN ─────────────────────────────────────────────────
def main():
    log.info("=" * 50)
    log.info(f"AJ Racing Bot — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 50)
    try:
        session         = login()
        content         = download_file(session)
        horses, fdate   = parse_xlsx(content)
        picks           = scan_picks(horses)
        save_picks_locally(picks, fdate)   # save for evening bot
        message         = build_message(picks, fdate)
        log.info(f"\n{message}\n")
        send_telegram(message)
        log.info("Done.")
        return 0
    except Exception as e:
        log.error(f"FAILED: {e}", exc_info=True)
        try:
            send_telegram(f"⚠️ AJ Bot ERROR {datetime.now().strftime('%H:%M')}:\n{str(e)[:300]}")
        except: pass
        return 1

if __name__ == '__main__':
    sys.exit(main())


# ═══════════════════════════════════════════════════════════
# RESULTS BOT — runs at 10:45pm, downloads results,
# settles AJ picks, sends P&L summary to Telegram
# ═══════════════════════════════════════════════════════════

RESULTS_URL = f'{BASE_URL}/results/'

# Results file column indices (from app's RCOL mapping)
RCOL_DATE   = 0
RCOL_PLACE  = 1
RCOL_BSP    = 16
RCOL_HORSE  = 11
RCOL_TRACK  = 7
RCOL_TIME   = 5

def download_results(session):
    log.info("GET results page...")
    r = session.get(RESULTS_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')

    payload = get_aspnet_fields(soup)
    payload['__EVENTTARGET']   = ''
    payload['__EVENTARGUMENT'] = ''
    payload['__SCROLLPOSITIONX'] = '0'
    payload['__SCROLLPOSITIONY'] = '100'
    payload['ctl00$ContentPlaceHolder1$dlButton1'] = 'Download'

    log.info("POST results download...")
    r = session.post(RESULTS_URL, data=payload, timeout=60,
                     headers={**HEADERS,
                              'Content-Type': 'application/x-www-form-urlencoded',
                              'Referer': RESULTS_URL,
                              'Origin': BASE_URL})
    r.raise_for_status()
    log.info(f"Results: {len(r.content):,} bytes")
    if len(r.content) < 1000:
        raise Exception(f"Results file too small: {len(r.content)} bytes")
    return r.content

def parse_results(content):
    """Parse results xlsx — returns dict of horse_name_clean -> {finPos, bsp}"""
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    sn = wb.sheetnames[0]
    ws = wb[sn]
    all_rows = list(ws.iter_rows(values_only=True))

    # Find header row
    header_idx = 0
    for i, row in enumerate(all_rows[:10]):
        if row and any(str(v or '').strip().lower() == 'horse' for v in row):
            header_idx = i
            break

    results = {}
    for row in all_rows[header_idx + 1:]:
        if not row: continue
        horse = str(row[RCOL_HORSE] or '').strip() if len(row) > RCOL_HORSE else ''
        if not horse: continue
        place = row[RCOL_PLACE] if len(row) > RCOL_PLACE else None
        bsp   = safe_float(row[RCOL_BSP] if len(row) > RCOL_BSP else None)
        try:
            fin_pos = int(float(str(place))) if place not in (None, '', 'PU','UR','F','BD','SU') else 99
        except:
            fin_pos = 99
        key = horse.lower().replace(' ', '').replace("'", '')
        results[key] = {'finPos': fin_pos, 'bsp': bsp, 'horse': horse}

    log.info(f"Results parsed: {len(results)} horses")
    return results

def load_aj_picks_from_api(today_str):
    """Load today's picks — saved by morning bot"""
    return load_picks_locally(today_str)

def save_aj_picks_to_api(picks):
    """Save settled picks locally"""
    import json
    picks_dir = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '/tmp/aj_data')
    today_str = date.today().strftime('%Y-%m-%d')
    path = os.path.join(picks_dir, f'picks_{today_str}.json')
    with open(path, 'w') as f:
        json.dump(picks, f, indent=2)
    log.info(f"Settled picks saved to {path}")

def settle_picks(picks, results):
    """Match picks against results and calculate P&L"""
    settled = []
    for pick in picks:
        key = pick['horse'].lower().replace(' ', '').replace("'", '')
        result = results.get(key)
        if not result:
            # Try partial match
            for rkey, rval in results.items():
                if key in rkey or rkey in key:
                    result = rval
                    break
        if not result:
            pick['status']  = 'pending'
            pick['settled'] = False
            settled.append(pick)
            continue

        fin_pos   = result['finPos']
        pred_odds = float(pick.get('odds', 2))
        stake     = float(pick.get('stake', STAKE))

        if pick.get('betType') == 'lay':
            won = fin_pos != 1
            pick['status'] = 'won' if won else 'lost'
            pick['pnl']    = round(stake * 0.98, 2) if won else round(-(pred_odds - 1) * stake, 2)
        else:
            won = fin_pos == 1
            pick['status'] = 'won' if won else 'lost'
            pick['pnl']    = round((pred_odds - 1) * stake * 0.98, 2) if won else -stake

        pick['finPos']   = fin_pos
        pick['bsp']      = result['bsp']
        pick['settled']  = True
        settled.append(pick)

    return settled

def build_results_message(settled, today_str):
    """Build Telegram message with today's P&L summary"""
    today_str_nice = datetime.now().strftime('%A %d %B %Y')
    done   = [p for p in settled if p.get('settled')]
    pend   = [p for p in settled if not p.get('settled')]
    wins   = [p for p in done if p.get('status') == 'won']
    losses = [p for p in done if p.get('status') == 'lost']
    total_pnl = round(sum(p.get('pnl', 0) for p in done), 2)

    lines = [
        f"📊 AJ RESULTS — {today_str_nice}",
        f"Stake: £{STAKE:.2f}/pt",
        "—" * 30,
        ""
    ]

    if done:
        lines.append(f"✅ Won: {len(wins)}  ❌ Lost: {len(losses)}  ⏳ Pending: {len(pend)}")
        lines.append(f"Strike Rate: {round(len(wins)/len(done)*100)}%" if done else "")
        pnl_col = "+" if total_pnl >= 0 else ""
        lines.append(f"Today P&L: {pnl_col}£{total_pnl:.2f}")
        lines.append("")

        # Show each result
        for p in sorted(done, key=lambda x: x.get('time', '')):
            icon   = "✅" if p.get('status') == 'won' else "❌"
            pnl    = p.get('pnl', 0)
            pnl_s  = f"+£{pnl:.2f}" if pnl >= 0 else f"-£{abs(pnl):.2f}"
            lines.append(f"{icon} {p['horse']} ({p.get('strategy','?')})")
            lines.append(f"   {p.get('track','')} · @{p.get('odds',0):.1f} · Fin: {p.get('finPos','?')} · {pnl_s}")

    if pend:
        lines.append("")
        lines.append(f"⏳ {len(pend)} still pending:")
        for p in pend:
            lines.append(f"  - {p['horse']} ({p.get('track','')} {p.get('time','')})")

    lines += ["", "—" * 30]
    if total_pnl >= 0:
        lines.append(f"💰 Day profit: +£{total_pnl:.2f}")
    else:
        lines.append(f"📉 Day loss: -£{abs(total_pnl):.2f}")

    return "\n".join(lines)

def run_results_bot():
    """Main function for the evening results job"""
    log.info("=" * 50)
    log.info(f"AJ Results Bot — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 50)

    today_str = date.today().strftime('%Y-%m-%d')

    try:
        # 1. Login
        session = login()

        # 2. Download results
        content = download_results(session)

        # 3. Parse results
        results = parse_results(content)

        # 4. Load today's AJ picks from cloud
        picks = load_aj_picks_from_api(today_str)
        if not picks:
            send_telegram(f"📊 AJ Results {today_str}\n\nNo pending picks found for today.")
            return 0

        # 5. Settle picks
        settled = settle_picks(picks, results)

        # 6. Save back to cloud
        save_aj_picks_to_api(settled)

        # 7. Build and send message
        message = build_results_message(settled, today_str)
        log.info(f"\n{message}\n")
        send_telegram(message)

        log.info("Results bot done.")
        return 0

    except Exception as e:
        log.error(f"Results bot FAILED: {e}", exc_info=True)
        try:
            send_telegram(f"⚠️ AJ Results Bot ERROR {datetime.now().strftime('%H:%M')}:\n{str(e)[:300]}")
        except: pass
        return 1


# ── ENTRY POINT ──────────────────────────────────────────
# RESULTS_MODE=1  → run evening results bot
# TEST_MODE=1     → run full test (sends Telegram on completion)  
# (default)       → run morning picks bot
if __name__ == '__main__':
    mode = os.environ.get('RESULTS_MODE'), os.environ.get('TEST_MODE')
    if mode[0] == '1':
        sys.exit(run_results_bot())
    elif mode[1] == '1':
        # Run test inline
        log.info("=" * 50)
        log.info(f"AJ Bot TEST RUN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.info("=" * 50)
        try:
            session = login()
            log.info("✅ Login OK")
            content = download_file(session)
            log.info(f"✅ Download OK — {len(content):,} bytes")
            horses, fdate = parse_xlsx(content)
            log.info(f"✅ Parse OK — {len(horses)} horses for {fdate}")
            picks = scan_picks(horses)
            ff_count  = len([p for p in picks if p['system']=='False Fav'])
            sys_count = len([p for p in picks if p['system']!='False Fav'])
            log.info(f"✅ Scan OK — {ff_count} FF + {sys_count} Sys = {len(picks)} total picks")
            for p in picks:
                log.info(f"   PICK: {p['horse']} @ {p['track']} {p['time']} [{p['system']}] @{p['odds']:.1f} liability=£{p['liability']:.2f}")
            save_picks_locally(picks, fdate)
            log.info("✅ Picks saved")
            message = build_message(picks, fdate)
            send_telegram("🧪 AJ BOT TEST RUN\n\n" + message + "\n\n✅ All systems working!")
            log.info("✅ Telegram sent — check your phone!")

            # Also test results download
            log.info("\nTesting results download...")
            results_content = download_results(session)
            log.info(f"✅ Results download OK — {len(results_content):,} bytes")
            results = parse_results(results_content)
            log.info(f"✅ Results parsed — {len(results)} horses")
            send_telegram(f"✅ Results download also working — {len(results)} results found")
            sys.exit(0)
        except Exception as e:
            log.error(f"❌ TEST FAILED: {e}", exc_info=True)
            try: send_telegram(f"❌ AJ Bot TEST FAILED:\n{str(e)[:300]}")
            except: pass
            sys.exit(1)
    else:
        sys.exit(main())
