import json
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

app = FastAPI()

# Path configuration
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

@app.get("/")
async def read_root():
    return FileResponse(WEB_DIR / "index.html")

@app.get("/api/latest-report")
async def get_latest_report():
    report_file = DATA_DIR / "latest_report.json"
    if report_file.exists():
        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    else:
        return JSONResponse(content={"insight": "暂无最新情报，请等待下次更新。"}, status_code=404)

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Wisteria Intelligence Dashboard...")
    print("🌍 Open in Browser: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
