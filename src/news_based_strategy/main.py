"""CLI entry point for the NSE corporate announcements poller and text extractor."""

import argparse
from datetime import datetime
import sys
import time
from news_based_strategy.config import settings
from news_based_strategy.core.models import Announcement
from news_based_strategy.ingestion.extractor import is_pypdf_available
from news_based_strategy.ingestion.filter import NoiseFilter
from news_based_strategy.ingestion.monitor import NSEFilingMonitor
from news_based_strategy.ingestion.universe import (
    get_fno_symbols,
    get_security_id_map,
    resolve_security_id,
    sync_dhan_fno_symbols,
)
from news_based_strategy.storage.repository import StrategyStorage


def get_five_word_brief(announcement: Announcement) -> str:
    """Return a concise 5-word brief of the announcement."""
    raw_text = (announcement.desc or announcement.details or "").strip()
    words = raw_text.split()
    if not words:
        return "Routine compliance filing"
    return " ".join(words[:5])


def print_announcement(announcement: Announcement, debug: bool = False, max_age_seconds: int = 180) -> None:
    """Pretty-print an individual announcement to the console with extracted text and LLM payload."""
    if NoiseFilter.is_noise(announcement.desc, announcement.details):
        reason = NoiseFilter.explain_noise(announcement.desc, announcement.details) or "Routine Compliance Noise"
        brief = get_five_word_brief(announcement)
        fno_badge = " [F&O]" if announcement.is_fno else ""
        print(f"\n  ↳ [{announcement.symbol}{fno_badge}] 🔇 Filtered out & rejected ({reason}) — {brief}")
        return


    ts = datetime.now().strftime("%H:%M:%S")
    fno_badge = " [F&O]" if announcement.is_fno else ""
    sec_id = resolve_security_id(announcement.symbol)
    sec_badge = f" [Dhan ID: {sec_id}]" if sec_id else ""
    header = f"[{ts}] [{announcement.symbol}{fno_badge}{sec_badge}]"
    print(f"\n{header} 📢 {announcement.desc}")
    print("   ↳ Status: 🟢 PASSED ALL FILTERS ➔ Prepared for AI Catalyst Evaluation (LLM Execution Paused in Phase 1)")


    if announcement.details:
        print(f"   ↳ Filed Details: {announcement.details}")
    if announcement.attachment_url:
        print(f"   ↳ Attachment Link: {announcement.attachment_url}")
    else:
        print("   ↳ Attachment Link: [None filed by company on exchange]")
    if announcement.an_dt:
        badge = announcement.freshness_badge(max_age_seconds=max_age_seconds)
        badge_str = f" {badge}" if badge else ""
        print(f"   ↳ Exchange Time: {announcement.an_dt}{badge_str}")


    # Check and warn if pypdf is missing
    if not is_pypdf_available():
        print("   ⚠️  [PDF extraction disabled: 'pypdf' not installed. Run: pip install pypdf]")
    elif announcement.extracted_text:
        preview = announcement.extracted_text[:300].replace("\n", " ").strip()
        print(f"   ↳ Extracted PDF Text ({len(announcement.extracted_text)} chars): \"{preview}...\"")
    elif announcement.extraction_error:
        print(f"   ↳ PDF Extraction: [{announcement.extraction_error}]")

    # Print the exact prompt content that is prepared to be sent to Gemini
    print("\n   ┌─ 🤖 Prepared LLM Payload (Content to be evaluated by AI) ──────")
    for line in announcement.llm_payload.split("\n"):
        print(f"   │ {line}")
    print("   └───────────────────────────────────────────────────────────────")

    if debug and announcement.raw_data:
        print("\n   🔍 [DEBUG Raw Item from NSE]:")
        for k, v in announcement.raw_data.items():
            print(f"      • {k}: {v}")


def run_poller(
    interval_seconds: int = 60,
    once: bool = False,
    symbol: str | None = None,
    fno_only: bool = True,
    filter_noise: bool = True,
    extract_pdf: bool = True,
    skip_initial: bool = False,
    debug: bool = False,
    max_age_seconds: int = 180,
) -> int:
    """Poll announcements, filter F&O stocks & noise, extract PDF text, and print to console."""
    if fno_only:
        try:
            sync_dhan_fno_symbols()
        except Exception:
            pass

    fno_count = len(get_fno_symbols())
    sec_count = len(get_security_id_map())
    universe_desc = f"DhanHQ Active F&O Universe ({fno_count} tickers | {sec_count} mapped SecIDs)" if fno_only else f"All NSE Stocks ({sec_count} mapped SecIDs)"
    pypdf_status = "Available (Bounded: Max 2 MB, 2 pages, 3.0s timeout)" if is_pypdf_available() else "Not Installed (Install with 'pip install pypdf')"
    storage = StrategyStorage()
    db_desc = storage.get_status_description()

    order_style = (
        f"Bracket Super Order (TP: +{settings.target_profit_pct}% | SL: -{settings.stop_loss_pct}% | Trail: {settings.trailing_jump_points} pts | Slippage: {settings.slippage_buffer_pct}%)"
        if settings.super_order_enabled
        else "Standard Order"
    )

    print("=" * 70)
    print("⚡ Real-Time NSE Corporate Announcements Poller (Console Mode)")
    print(f"   Mode: {'Single Shot (--once)' if once else f'Continuous (every {interval_seconds}s)'}")
    print(f"   Universe: {universe_desc}")
    print(f"   Persistence: {db_desc}")
    print(f"   Order Style: {order_style}")
    print(f"   Noise Rejection: {'Active (Trading window, share certs, etc. suppressed)' if filter_noise else 'Disabled'}")
    print(f"   Max News Age: {max_age_seconds}s (Stale news circuit breaker)" if max_age_seconds > 0 else "   Max News Age: Disabled")
    print(f"   PDF Extractor: {pypdf_status}")
    print("   AI / Broker Execution: Strictly Disabled (Phase 1: Ingestion & Filter Verification)")
    if symbol:
        print(f"   Symbol Filter: {symbol.upper()}")
    print("   Press Ctrl+C to stop.")
    print("=" * 70)

    monitor = NSEFilingMonitor(
        base_url=settings.nse_base_url,
        api_url=settings.nse_api_url,
        headers=settings.headers,
        storage=storage,
    )

    def on_filtered(item: Announcement, reason: str) -> None:
        brief = get_five_word_brief(item)
        fno_tag = " [F&O]" if item.is_fno else ""
        print(f"\n  ↳ [{item.symbol}{fno_tag}] 🔇 Filtered out ({reason}) — {brief}", flush=True)

    cycle = 1
    try:
        while True:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{now_str}] Cycle #{cycle}: Polling NSE announcements...", end=" ", flush=True)

            new_items = monitor.get_new_announcements(
                symbol_filter=symbol,
                fno_only=fno_only,
                filter_noise=filter_noise,
                extract_pdf=extract_pdf,
                initial_mark_all_seen=(cycle == 1 and skip_initial),
                on_filtered=on_filtered,
            )

            if new_items:
                print(f"found {len(new_items)} tradeable catalyst filing(s):")
                for item in new_items:
                    print_announcement(item, debug=debug, max_age_seconds=max_age_seconds)
            else:
                print("found 0 tradeable catalyst filing(s).")


            if once:
                print("\n✅ Single poll complete (--once). Exiting.")
                break

            cycle += 1
            print(f"⏳ Sleeping for {interval_seconds} seconds...")
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        print("\n\n🛑 Poller stopped by user (Ctrl+C). Goodbye!")
        return 0
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}", file=sys.stderr)
        return 1

    return 0


def main() -> int:
    """Parse CLI arguments and start the poller."""
    parser = argparse.ArgumentParser(
        description="Poll, filter, and extract real-time NSE corporate announcements for F&O stocks."
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=settings.poll_interval_seconds,
        help=f"Polling interval in seconds (default: {settings.poll_interval_seconds})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Poll once and immediately exit",
    )
    parser.add_argument(
        "-s",
        "--symbol",
        type=str,
        default=None,
        help="Filter announcements by stock symbol (e.g. INFY, TATAMOTORS, BEL)",
    )
    parser.add_argument(
        "--all-stocks",
        action="store_true",
        help="Include all NSE stocks (disables F&O universe restriction)",
    )
    parser.add_argument(
        "--include-noise",
        action="store_true",
        help="Include routine compliance noise (trading window closures, share certificates)",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Disable downloading and extracting text from PDF attachments",
    )
    parser.add_argument(
        "--skip-initial",
        action="store_true",
        help="Skip printing historical filings on the first poll, only print new arrivals",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print raw JSON fields returned by NSE for debugging schema variations",
    )
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=180,
        help="Max age in seconds before news is deemed stale (default: 180s, 0 disables)",
    )

    args = parser.parse_args()
    return run_poller(
        interval_seconds=args.interval,
        once=args.once,
        symbol=args.symbol,
        fno_only=not args.all_stocks,
        filter_noise=not args.include_noise,
        extract_pdf=not args.no_pdf,
        skip_initial=args.skip_initial,
        debug=args.debug,
        max_age_seconds=args.max_age_seconds,
    )



if __name__ == "__main__":
    sys.exit(main())
