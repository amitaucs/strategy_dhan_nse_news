"""CLI entry point for the NSE corporate announcements poller and text extractor."""

import argparse
from datetime import datetime
import sys
import time
from typing import Optional
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
from news_based_strategy.intelligence.analyzer import FilingAnalyzer
from news_based_strategy.storage.repository import StrategyStorage


def get_five_word_brief(announcement: Announcement) -> str:
    """Return a concise 5-word brief of the announcement."""
    raw_text = (announcement.desc or announcement.details or "").strip()
    words = raw_text.split()
    if not words:
        return "Routine compliance filing"
    return " ".join(words[:5])


def print_announcement(
    announcement: Announcement,
    analyzer: Optional[FilingAnalyzer] = None,
    storage: Optional[StrategyStorage] = None,
    debug: bool = False,
    max_age_seconds: int = 180,
    enable_ai: bool = True,
) -> None:
    """Pretty-print an individual announcement to the console with extracted text and AI sentiment reasoning."""
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
    print("   ↳ Status: 🟢 PASSED ALL FILTERS ➔ Sent to AI Reasoning Engine")

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

    # AI Reasoning via Gemini
    if enable_ai and analyzer:
        print("   ⏳ Evaluating catalyst impact via Google Gemini...", flush=True)
        audit = analyzer.audit(
            symbol=announcement.symbol,
            headline=announcement.desc,
            details=announcement.clean_content,
        )
        if audit:
            sentiment_upper = audit.sentiment.upper()
            if sentiment_upper in ("BULLISH", "BUY"):
                sent_badge = "BULLISH 🟢"
            elif sentiment_upper in ("BEARISH", "SELL"):
                sent_badge = "BEARISH 🔴"
            else:
                sent_badge = "NEUTRAL ⚪"

            is_conviction = (
                audit.material_impact
                and audit.confidence >= settings.confidence_threshold
                and sentiment_upper in ("BULLISH", "BUY", "BEARISH", "SELL")
            )
            conviction_badge = (
                "🟢 HIGH CONVICTION (Trade Trigger in Phase 3)"
                if is_conviction
                else "⚪ STANDARD (Below conviction threshold)"
            )

            print(f"\n   ┌─ 🧠 AI Sentiment & Catalyst Verdict ({analyzer.model_name}) ─────")
            print(f"   │ • Sentiment: {sent_badge} (Confidence: {audit.confidence}% | Threshold: >= {settings.confidence_threshold}%)")
            print(f"   │ • Catalyst Category: {audit.catalyst_type}")
            print(f"   │ • Material Price Impact: {audit.material_impact} (Expected rapid price movement >= 1.5%)")
            print(f"   │ • Conviction Gate: {conviction_badge}")
            print(f"   │ • AI Rationale: \"{audit.summary}\"")
            print("   │ • Broker Execution: ⏸️ Strictly Paused (Phase 2 Reasoning Mode)")
            print("   └───────────────────────────────────────────────────────────────")

            if storage:
                storage.save_audit(announcement.seq_id, announcement.symbol, audit)
        else:
            print("   ⚠️  [AI Reasoning Error]: Unable to obtain structured verdict from Gemini.")

    if debug and announcement.raw_data:
        print("\n   🔍 [DEBUG Raw Item from NSE]:")
        for k, v in announcement.raw_data.items():
            print(f"      • {k}: {v}")


def get_simulated_nse_payload() -> list[dict]:
    """Generate realistic live market announcements for simulation."""
    now_ts = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
    t_int = int(time.time())
    return [
        # 1. Non-F&O stock (fails F&O gate)
        {
            "seq_id": f"SIM_NONFNO_{t_int}",
            "symbol": "SBC",
            "desc": "Receipt of Domestic Order",
            "attmntText": "SBC Exports has received an order worth INR 5 Crore.",
            "an_dt": now_ts,
        },
        # 2. F&O stock with routine noise (fails Noise gate)
        {
            "seq_id": f"SIM_NOISE_{t_int}",
            "symbol": "TATASTEEL",
            "desc": "Closure of Trading Window",
            "attmntText": "Intimation of trading window closure for designated persons pursuant to SEBI regulations.",
            "an_dt": now_ts,
        },
        # 3. Eligible F&O stock with BULLISH catalyst (passes all gates -> triggers Gemini 3.7 Flash)
        {
            "seq_id": f"SIM_BULLISH_{t_int}",
            "symbol": "BEL",
            "desc": "Bharat Electronics secures major export defense contract worth INR 3,850 Crore",
            "attmntText": "Bharat Electronics Limited (BEL) has signed an export contract with the Ministry of Defence of a friendly nation for the supply of state-of-the-art radar and electronic warfare systems. The contract value is INR 3,850 Crore and execution will take place over 24 months.",
            "an_dt": now_ts,
        },
        # 4. Eligible F&O stock with BEARISH catalyst (passes all gates -> triggers Gemini 3.7 Flash)
        {
            "seq_id": f"SIM_BEARISH_{t_int}",
            "symbol": "BANKINDIA",
            "desc": "RBI imposes severe monetary penalty and business restrictions",
            "attmntText": "The Reserve Bank of India (RBI) has issued a regulatory order imposing a penalty of INR 120 Crore and halting new digital credit card issuance due to material deficiencies in IT and risk governance framework.",
            "an_dt": now_ts,
        },
    ]


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
    enable_ai: bool = True,
    simulate: bool = False,
) -> int:
    """Poll announcements, filter F&O stocks & noise, extract PDF text, and analyze sentiment with Gemini."""
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

    analyzer = (
        FilingAnalyzer(api_key=settings.gemini_api_key, model_name=settings.gemini_model)
        if enable_ai
        else None
    )

    ai_desc = (
        f"Active (Google Gemini: {settings.gemini_model} | Conviction Threshold: >= {settings.confidence_threshold}%)"
        if enable_ai
        else "Disabled (--no-ai)"
    )

    order_style = (
        f"Bracket Super Order (TP: +{settings.target_profit_pct}% | SL: -{settings.stop_loss_pct}% | Trail: {settings.trailing_jump_points} pts | Slippage: {settings.slippage_buffer_pct}%)"
        if settings.super_order_enabled
        else "Standard Order"
    )

    mode_str = "Simulated Feed (--simulate)" if simulate else ("Single Shot (--once)" if once else f"Continuous (every {interval_seconds}s)")

    print("=" * 70)
    print("⚡ Real-Time NSE Corporate Announcements Poller (Console Mode)")
    print(f"   Mode: {mode_str}")
    print(f"   Universe: {universe_desc}")
    print(f"   Persistence: {db_desc}")
    print(f"   Order Style: {order_style}")
    print(f"   AI Intelligence: {ai_desc}")
    print(f"   Noise Rejection: {'Active (Trading window, share certs, etc. suppressed)' if filter_noise else 'Disabled'}")
    print(f"   Max News Age: {max_age_seconds}s (Stale news circuit breaker)" if max_age_seconds > 0 else "   Max News Age: Disabled")
    print(f"   PDF Extractor: {pypdf_status}")
    print("   Broker Execution: Strictly Paused (Phase 2: Sentiment & Catalyst Reasoning)")
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

    if simulate:
        import json
        monitor._do_get = lambda url: (200, json.dumps(get_simulated_nse_payload()))

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
                    print_announcement(
                        item,
                        analyzer=analyzer,
                        storage=storage,
                        debug=debug,
                        max_age_seconds=max_age_seconds,
                        enable_ai=enable_ai,
                    )
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
        "--no-ai",
        action="store_true",
        help="Disable Gemini AI sentiment reasoning (run in pure Phase 1 monitoring mode)",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Simulate realistic live corporate filings to test the full pipeline end-to-end",
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
        once=args.once or args.simulate,
        symbol=args.symbol,
        fno_only=not args.all_stocks,
        filter_noise=not args.include_noise,
        extract_pdf=not args.no_pdf,
        skip_initial=args.skip_initial,
        debug=args.debug,
        max_age_seconds=args.max_age_seconds,
        enable_ai=not args.no_ai,
        simulate=args.simulate,
    )


if __name__ == "__main__":
    sys.exit(main())
