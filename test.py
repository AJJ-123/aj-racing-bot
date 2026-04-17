"""
Test script — run this manually to verify everything works.
Set TEST_MODE=1 in Railway variables, then trigger a manual run.
Uses yesterday's file to test without waiting for tomorrow.
"""

import os, sys, json
from datetime import date, timedelta

# Force test mode
os.environ['TEST_MODE'] = '1'

# Import main bot functions
from main import (
    login, download_file, parse_xlsx, scan_picks,
    save_picks_locally, build_message, send_telegram,
    download_results, parse_results, settle_picks,
    build_results_message, STAKE, log
)

def run_full_test():
    log.info("=" * 50)
    log.info("RUNNING FULL TEST")
    log.info("=" * 50)

    errors = []

    # ── TEST 1: Login ─────────────────────────────────────
    log.info("\n[TEST 1] Login to racing-bet-data.com...")
    try:
        session = login()
        log.info("✅ Login OK")
    except Exception as e:
        log.error(f"❌ Login FAILED: {e}")
        errors.append(f"Login: {e}")
        send_telegram(f"⚠️ AJ Test FAILED — Login error:\n{e}")
        return

    # ── TEST 2: Download pre-race file ────────────────────
    log.info("\n[TEST 2] Download pre-race file...")
    try:
        content = download_file(session)
        log.info(f"✅ Downloaded {len(content):,} bytes")
    except Exception as e:
        log.error(f"❌ Download FAILED: {e}")
        errors.append(f"Download: {e}")
        send_telegram(f"⚠️ AJ Test FAILED — Download error:\n{e}")
        return

    # ── TEST 3: Parse file ────────────────────────────────
    log.info("\n[TEST 3] Parse xlsx...")
    try:
        horses, file_date = parse_xlsx(content)
        log.info(f"✅ Parsed {len(horses)} horses for {file_date}")
        log.info(f"   Sample: {horses[0]['horse']} @ {horses[0]['track']} odds={horses[0]['pred_isp']} flag={horses[0]['flag']}")
    except Exception as e:
        log.error(f"❌ Parse FAILED: {e}")
        errors.append(f"Parse: {e}")
        send_telegram(f"⚠️ AJ Test FAILED — Parse error:\n{e}")
        return

    # ── TEST 4: Scan picks ────────────────────────────────
    log.info("\n[TEST 4] Scan for qualifying picks...")
    try:
        picks = scan_picks(horses)
        ff  = [p for p in picks if p['system'] == 'False Fav']
        sys = [p for p in picks if p['system'] != 'False Fav']
        log.info(f"✅ Found {len(picks)} picks: {len(ff)} FF + {len(sys)} Sys")
        for p in picks[:5]:
            log.info(f"   {p['horse']} @ {p['track']} {p['time']} [{p['system']}] @{p['odds']:.1f} liability=£{p['liability']:.2f}")
    except Exception as e:
        log.error(f"❌ Scan FAILED: {e}")
        errors.append(f"Scan: {e}")
        send_telegram(f"⚠️ AJ Test FAILED — Scan error:\n{e}")
        return

    # ── TEST 5: Save picks ────────────────────────────────
    log.info("\n[TEST 5] Save picks to file...")
    try:
        save_picks_locally(picks, file_date)
        log.info("✅ Picks saved")
    except Exception as e:
        log.error(f"❌ Save FAILED: {e}")
        errors.append(f"Save: {e}")

    # ── TEST 6: Build Telegram message ────────────────────
    log.info("\n[TEST 6] Build Telegram message...")
    try:
        message = build_message(picks, file_date)
        log.info(f"✅ Message built ({len(message)} chars)")
        log.info(f"\n{message}\n")
    except Exception as e:
        log.error(f"❌ Message FAILED: {e}")
        errors.append(f"Message: {e}")
        return

    # ── TEST 7: Send to Telegram ──────────────────────────
    log.info("\n[TEST 7] Send to Telegram...")
    try:
        test_msg = f"🧪 AJ BOT TEST — {file_date}\n\n{message}\n\n✅ Bot is working correctly!"
        send_telegram(test_msg)
        log.info("✅ Telegram sent!")
    except Exception as e:
        log.error(f"❌ Telegram FAILED: {e}")
        errors.append(f"Telegram: {e}")

    # ── TEST 8: Download results ──────────────────────────
    log.info("\n[TEST 8] Download results file...")
    try:
        results_content = download_results(session)
        log.info(f"✅ Results downloaded {len(results_content):,} bytes")
    except Exception as e:
        log.error(f"❌ Results download FAILED: {e}")
        errors.append(f"Results download: {e}")
        results_content = None

    # ── SUMMARY ───────────────────────────────────────────
    log.info("\n" + "=" * 50)
    if errors:
        log.error(f"TEST COMPLETE — {len(errors)} ERRORS:")
        for e in errors:
            log.error(f"  ❌ {e}")
        send_telegram(f"⚠️ AJ Test completed with errors:\n" + "\n".join(f"❌ {e}" for e in errors))
    else:
        log.info("✅ ALL TESTS PASSED")
        send_telegram(f"✅ AJ Bot fully tested — {len(picks)} picks found for {file_date}. Everything working!")

if __name__ == '__main__':
    run_full_test()
