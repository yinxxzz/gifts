#!/usr/bin/env python3
"""静态文件 + 全员共享编辑 API（文案/期次状态 + 上架状态）"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
SHELF_FILE = os.path.join(ROOT, "data", "gift-shelf-status.json")
EDITS_FILE = os.path.join(ROOT, "data", "period-edits.json")
VALID_SHELF = {"on_sale", "off_sale", "pending"}
SHELF_LABELS = {
    "on_sale": "上架中",
    "off_sale": "已下架",
    "pending": "待上架",
}
_lock = threading.Lock()


def _read_json(path: str) -> dict:
    with _lock:
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _lock:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)


def read_shelf() -> dict:
    return _read_json(SHELF_FILE)


def write_shelf(data: dict) -> None:
    _write_json(SHELF_FILE, data)


def read_edits() -> dict:
    return _read_json(EDITS_FILE)


def write_edits(data: dict) -> None:
    _write_json(EDITS_FILE, data)


class GiftStrategyHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, format, *args):
        if str(args[0]).startswith(("GET /api/", "PUT /api/")):
            super().log_message(format, *args)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/gift-shelf-status":
            self._json_response(200, read_shelf(), cache=False)
            return
        if path == "/api/period-edits":
            self._json_response(200, {"edits": read_edits()}, cache=False)
            return
        super().do_GET()

    def do_PUT(self):
        path = urlparse(self.path).path
        if path == "/api/gift-shelf-status":
            self._put_shelf_status()
            return
        if path == "/api/period-edits":
            self._put_period_edits()
            return
        self.send_error(404)

    def _put_shelf_status(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            period_id = str(payload.get("periodId", "")).strip()
            bundle_id = str(payload.get("bundleId", "")).strip()
            gift_name = str(payload.get("giftName", "")).strip()
            shelf_status = str(payload.get("shelfStatus", "")).strip()

            if not period_id or not bundle_id or not gift_name:
                self._json_response(400, {"error": "缺少 periodId / bundleId / giftName"})
                return
            if shelf_status not in VALID_SHELF:
                self._json_response(400, {"error": "无效的 shelfStatus"})
                return

            data = read_shelf()
            data.setdefault(period_id, {}).setdefault(bundle_id, {})[gift_name] = {
                "shelfStatus": shelf_status,
                "shelfStatusLabel": SHELF_LABELS[shelf_status],
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
            write_shelf(data)
            self._json_response(200, {"ok": True, "overrides": data}, cache=False)
        except json.JSONDecodeError:
            self._json_response(400, {"error": "JSON 格式错误"})
        except OSError as e:
            self._json_response(500, {"error": f"写入失败: {e}"})

    def _put_period_edits(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            data = read_edits()

            if isinstance(payload.get("edits"), dict):
                data = payload["edits"]
            else:
                period_id = str(payload.get("periodId", "")).strip()
                period = payload.get("period")
                if not period_id or not isinstance(period, dict):
                    self._json_response(400, {"error": "缺少 periodId / period，或 edits 对象"})
                    return
                data[period_id] = period

            write_edits(data)
            self._json_response(200, {"ok": True, "edits": data}, cache=False)
        except json.JSONDecodeError:
            self._json_response(400, {"error": "JSON 格式错误"})
        except OSError as e:
            self._json_response(500, {"error": f"写入失败: {e}"})

    def _json_response(self, code: int, payload: dict, cache: bool = True):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if not cache:
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), GiftStrategyHandler)
    print(f"Gift strategy server on :{port}")
    print("  GET/PUT /api/period-edits")
    print("  GET/PUT /api/gift-shelf-status")
    server.serve_forever()


if __name__ == "__main__":
    main()
