import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from intelligence_engine import run_intelligence_report, send_to_telegram
except ImportError:
    from src.intelligence_engine import run_intelligence_report, send_to_telegram

BOT_TOKEN = os.environ.get("BOT_TOKEN_G") or os.environ.get("TECHBOTTOKEN")
CHAT_ID = os.environ.get("CHAT_ID_G", "-1003590230315")

SCHEDULE_CONFIG = {
    "morning": {
        "hour": 8,
        "minute": 0,
        "name": "晨报",
        "categories": ["tech", "finance", "world"],
        "message_template": (
            "**OpenNews Matrix 晨报**\n"
            "| {date} | {categories} |\n\n"
            "{reports}\n\n"
            "_祝您今日工作顺利_"
        )
    },
    "evening": {
        "hour": 20,
        "minute": 0,
        "name": "晚报",
        "categories": ["tech", "oracle", "finance"],
        "message_template": (
            "**OpenNews Matrix 晚报**\n"
            "| {date} | {categories} |\n\n"
            "{reports}\n\n"
            "_明日见_"
        )
    }
}

async def generate_digest_report(categories: list[str]) -> str:
    reports = []
    
    for cat in categories:
        try:
            result = await run_intelligence_report(category=cat, chat_id=CHAT_ID)
            if result.get("count", 0) > 0:
                reports.append(result["report"])
            else:
                reports.append("*[%s: 暂无重大情报]*" % cat.upper())
        except Exception as e:
            print("[Digest] Error generating %s report: %s" % (cat, e))
            reports.append("*[%s: 生成失败]*" % cat.upper())
    
    return "\n\n---\n\n".join(reports)


async def send_scheduled_digest(schedule_type: str):
    config = SCHEDULE_CONFIG.get(schedule_type)
    if not config:
        print("[Schedule] Unknown type: %s" % schedule_type)
        return
    
    now = datetime.now(timezone(timedelta(hours=8)))
    
    print("[Schedule] Generating %s at %s..." % (config["name"], now.strftime("%H:%M:%S")))
    
    try:
        report_content = await generate_digest_report(config["categories"])
        
        date_str = now.strftime("%Y-%m-%d")
        cats_str = ", ".join(config["categories"]).upper()
        
        message = config["message_template"].format(
            date=date_str,
            categories=cats_str,
            reports=report_content
        )
        
        success = await send_to_telegram(message, chat_id=CHAT_ID, bot_token=BOT_TOKEN)
        
        if success:
            print("[Schedule] %s sent successfully!" % config["name"])
        else:
            print("[Schedule] Failed to send %s" % config["name"])
            
    except Exception as e:
        print("[Schedule] Error in %s: %s" % (config["name"], e))


async def scheduler_loop():
    print("[Scheduler] Starting scheduler loop...")
    print("[Scheduler] Morning digest: 08:00")
    print("[Scheduler] Evening digest: 20:00")
    
    last_sent = {"morning": None, "evening": None}
    
    while True:
        now = datetime.now(timezone(timedelta(hours=8)))
        current_time = now.strftime("%H:%M")
        
        for schedule_type, config in SCHEDULE_CONFIG.items():
            target_time = "%02d:%02d" % (config["hour"], config["minute"])
            
            if current_time == target_time:
                last_date = last_sent.get(schedule_type)
                today = now.strftime("%Y-%m-%d")
                
                if last_date != today:
                    await send_scheduled_digest(schedule_type)
                    last_sent[schedule_type] = today
        
        await asyncio.sleep(30)


async def run_once(schedule_type: str = "morning"):
    await send_scheduled_digest(schedule_type)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenNews Matrix Scheduler")
    parser.add_argument("--mode", choices=["loop", "once"], default="loop",
                        help="Run mode: loop (continuous) or once (single)")
    parser.add_argument("--type", choices=["morning", "evening"], default="morning",
                        help="Schedule type for --mode once")
    args = parser.parse_args()
    
    if not BOT_TOKEN:
        print("[ERROR] BOT_TOKEN_G not set")
        sys.exit(1)
    
    if args.mode == "loop":
        asyncio.run(scheduler_loop())
    else:
        asyncio.run(run_once(args.type))
