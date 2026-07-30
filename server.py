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
PERIODS_FILE = os.path.join(ROOT, "data", "periods.json")
SHELF_FILE = os.path.join(ROOT, "data", "gift-shelf-status.json")
EDITS_FILE = os.path.join(ROOT, "data", "period-edits.json")
VALID_SHELF = {"on_sale", "off_sale", "pending"}
SHELF_LABELS = {
    "on_sale": "上架中",
    "off_sale": "已下架",
    "pending": "待上架",
}
_lock = threading.Lock()


def _is_no_cache_path(path: str) -> bool:
    clean_path = urlparse(path).path
    return clean_path in {"/", "/index.html"} or clean_path.endswith((".html", ".css", ".js"))


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


def read_periods() -> dict:
    return _read_json(PERIODS_FILE)


def merge_bundles(base_bundles: list, overlay_bundles: list) -> list:
    if not overlay_bundles:
        return json.loads(json.dumps(base_bundles or [], ensure_ascii=False))
    merged_by_id = {
        bundle.get("id"): json.loads(json.dumps(bundle, ensure_ascii=False))
        for bundle in base_bundles or []
        if isinstance(bundle, dict) and bundle.get("id")
    }
    for overlay_bundle in overlay_bundles:
        if not isinstance(overlay_bundle, dict):
            continue
        bundle_id = overlay_bundle.get("id")
        base_bundle = merged_by_id.get(bundle_id, {})
        merged_by_id[bundle_id] = deep_merge(base_bundle, overlay_bundle)

    ordered_ids = [
        bundle.get("id")
        for bundle in base_bundles or []
        if isinstance(bundle, dict) and bundle.get("id")
    ]
    ordered = [merged_by_id[bundle_id] for bundle_id in ordered_ids if bundle_id in merged_by_id]
    extra = [
        bundle
        for bundle_id, bundle in merged_by_id.items()
        if bundle_id not in set(ordered_ids)
    ]
    return ordered + extra


def deep_merge(target, source):
    if not isinstance(target, dict):
        target = {}
    for key, value in source.items():
        if key == "bundles" and isinstance(value, list) and isinstance(target.get("bundles"), list):
            target["bundles"] = merge_bundles(target.get("bundles"), value)
        elif isinstance(value, list):
            target[key] = value
        elif isinstance(value, dict):
            target[key] = deep_merge(target.get(key) if isinstance(target.get(key), dict) else {}, value)
        else:
            target[key] = value
    return target


def get_period_for_edit(period_id: str, edits: dict):
    periods = read_periods().get("periods", [])
    base_period = next(
        (
            json.loads(json.dumps(period, ensure_ascii=False))
            for period in periods
            if isinstance(period, dict) and str(period.get("id")) == period_id
        ),
        None,
    )
    overlay = edits.get(period_id)
    if base_period and isinstance(overlay, dict):
        return deep_merge(base_period, overlay)
    if base_period:
        return base_period
    if isinstance(overlay, dict):
        return json.loads(json.dumps(overlay, ensure_ascii=False))
    return None


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
        if _is_no_cache_path(self.path):
            self.send_header("Cache-Control", "no-store")
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
        if path == "/api/gift-item":
            self._put_gift_item()
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

    def _put_gift_item(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            period_id = str(payload.get("periodId", "")).strip()
            bundle_id = str(payload.get("bundleId", "")).strip()
            gift = payload.get("gift")
            recommended = bool(payload.get("recommended"))
            shelf_status = str(payload.get("shelfStatus", "on_sale")).strip() or "on_sale"

            if not period_id or not bundle_id or not isinstance(gift, dict):
                self._json_response(400, {"error": "缺少 periodId / bundleId / gift"})
                return
            if shelf_status not in VALID_SHELF:
                self._json_response(400, {"error": "无效的 shelfStatus"})
                return

            gift_name = str(gift.get("name", "")).strip()
            if not gift_name:
                self._json_response(400, {"error": "赠品名称不能为空"})
                return

            selling_points = gift.get("sellingPoints")
            if not isinstance(selling_points, list):
                selling_points = []
            cleaned_gift = {
                "name": gift_name,
                "image": str(gift.get("image", "")).strip(),
                "sellingPoints": [
                    str(point).strip()
                    for point in selling_points
                    if str(point).strip()
                ],
                "isNew": bool(gift.get("isNew")),
            }
            if not cleaned_gift["sellingPoints"]:
                cleaned_gift["sellingPoints"] = ["待补充卖点。"]

            edits = read_edits()
            period = get_period_for_edit(period_id, edits)
            if not period:
                self._json_response(404, {"error": "没有找到对应期次"})
                return

            bundle = next(
                (
                    item
                    for item in period.get("bundles", [])
                    if isinstance(item, dict) and str(item.get("id")) == bundle_id
                ),
                None,
            )
            if not bundle:
                self._json_response(404, {"error": "没有找到对应礼包"})
                return

            gifts = bundle.setdefault("gifts", [])
            if any(str(item.get("name", "")).strip() == gift_name for item in gifts if isinstance(item, dict)):
                self._json_response(409, {"error": "这个礼包里已经有同名赠品"})
                return

            gifts.append(cleaned_gift)
            rec_list = bundle.setdefault("recommended", [])
            if recommended and gift_name not in rec_list:
                rec_list.append(gift_name)

            edits[period_id] = period
            write_edits(edits)

            shelf = read_shelf()
            shelf.setdefault(period_id, {}).setdefault(bundle_id, {})[gift_name] = {
                "shelfStatus": shelf_status,
                "shelfStatusLabel": SHELF_LABELS[shelf_status],
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
            write_shelf(shelf)

            self._json_response(
                200,
                {"ok": True, "period": period, "edits": edits, "overrides": shelf},
                cache=False,
            )
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
    print("  PUT /api/gift-item")
    server.serve_forever()


if __name__ == "__main__":
    main()
