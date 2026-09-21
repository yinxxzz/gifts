#!/usr/bin/env python3
"""静态文件 + 全员共享编辑 API（文案/期次状态 + 上架状态）"""

from __future__ import annotations

import json
import io
import os
import re
import shutil
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
PERIODS_FILE = os.path.join(ROOT, "data", "periods.json")
SHELF_FILE = os.path.join(ROOT, "data", "gift-shelf-status.json")
EDITS_FILE = os.path.join(ROOT, "data", "period-edits.json")
VALID_SHELF = {"on_sale", "off_sale", "pending"}
MAX_PACKAGE_BYTES = 120 * 1024 * 1024
MAX_PACKAGE_FILES = 1200
MAX_PACKAGE_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
ALLOWED_ASSET_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PERIOD_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
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


def _safe_zip_parts(name: str) -> list[str]:
    normalized = str(name or "").replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError(f"压缩包包含不安全路径: {name}")
    return parts


def _normalize_period_payload(payload) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("periods"), list):
        periods = payload["periods"]
    elif isinstance(payload, dict) and payload.get("id"):
        periods = [payload]
    elif isinstance(payload, list):
        periods = payload
    else:
        raise ValueError("periods.json 必须包含 periods 数组，或直接提供一个期次对象")

    cleaned = []
    seen = set()
    for raw_period in periods:
        if not isinstance(raw_period, dict):
            raise ValueError("期次内容必须是对象")
        period = json.loads(json.dumps(raw_period, ensure_ascii=False))
        period_id = str(period.get("id", "")).strip()
        title = str(period.get("title", "")).strip()
        bundles = period.get("bundles")
        if not PERIOD_ID_RE.fullmatch(period_id):
            raise ValueError(f"期次 ID 不合法: {period_id or '空'}")
        if period_id in seen:
            raise ValueError(f"期次 ID 重复: {period_id}")
        if not title:
            raise ValueError(f"期次 {period_id} 缺少标题")
        if not isinstance(bundles, list) or not bundles:
            raise ValueError(f"期次 {period_id} 至少需要一个礼包")

        for bundle in bundles:
            if not isinstance(bundle, dict) or not str(bundle.get("id", "")).strip():
                raise ValueError(f"期次 {period_id} 存在缺少 ID 的礼包")
            gifts = bundle.get("gifts", [])
            if not isinstance(gifts, list):
                raise ValueError(f"期次 {period_id} 的赠品列表格式错误")
            for gift in gifts:
                if not isinstance(gift, dict) or not str(gift.get("name", "")).strip():
                    raise ValueError(f"期次 {period_id} 存在缺少名称的赠品")
                image = str(gift.get("image", "")).strip()
                if image:
                    image_parts = _safe_zip_parts(image)
                    if image_parts[0] != "assets":
                        raise ValueError(f"赠品图片路径必须以 assets/ 开头: {image}")

        seen.add(period_id)
        cleaned.append(period)
    return cleaned


def parse_content_package(package_bytes: bytes) -> tuple[list[dict], list[tuple[zipfile.ZipInfo, str]]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(package_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("无法读取 ZIP，请确认上传的是完整压缩包") from exc

    with archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        if not files:
            raise ValueError("压缩包是空的")
        if len(files) > MAX_PACKAGE_FILES:
            raise ValueError(f"压缩包文件过多，最多支持 {MAX_PACKAGE_FILES} 个文件")
        total_size = sum(item.file_size for item in files)
        if total_size > MAX_PACKAGE_UNCOMPRESSED_BYTES:
            raise ValueError("压缩包解压后过大，请分批上传")
        if any(item.flag_bits & 0x1 for item in files):
            raise ValueError("暂不支持带密码的压缩包")

        manifest_candidates = []
        assets = []
        for item in files:
            parts = _safe_zip_parts(item.filename)
            basename = parts[-1].lower()
            if basename in {"period.json", "periods.json"}:
                manifest_candidates.append((len(parts), item))

            asset_index = next((i for i, part in enumerate(parts) if part == "assets"), -1)
            if asset_index < 0:
                continue
            relative_parts = parts[asset_index:]
            extension = os.path.splitext(relative_parts[-1])[1].lower()
            if extension not in ALLOWED_ASSET_EXTENSIONS:
                continue
            assets.append((item, "/".join(relative_parts)))

        if not manifest_candidates:
            raise ValueError("压缩包里没有找到 periods.json 或 period.json")
        manifest_candidates.sort(key=lambda pair: pair[0])
        manifest_info = manifest_candidates[0][1]
        try:
            manifest = json.loads(archive.read(manifest_info).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("periods.json 不是有效的 UTF-8 JSON") from exc

        periods = _normalize_period_payload(manifest)
        return periods, assets


def install_content_package(package_bytes: bytes) -> dict:
    periods, assets = parse_content_package(package_bytes)
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        with tempfile.TemporaryDirectory(prefix="gift-package-", dir=ROOT) as staging:
            staged_assets = []
            for item, relative_path in assets:
                staged_path = os.path.join(staging, *relative_path.split("/"))
                os.makedirs(os.path.dirname(staged_path), exist_ok=True)
                with archive.open(item) as source, open(staged_path, "wb") as target:
                    shutil.copyfileobj(source, target)
                staged_assets.append((staged_path, os.path.join(ROOT, *relative_path.split("/"))))

            for staged_path, target_path in staged_assets:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                os.replace(staged_path, target_path)

    edits = read_edits()
    for period in periods:
        edits[period["id"]] = period
    write_edits(edits)

    return {
        "ok": True,
        "periods": [
            {
                "id": period["id"],
                "title": period["title"],
                "bundleCount": len(period.get("bundles", [])),
                "giftCount": sum(len(bundle.get("gifts", [])) for bundle in period.get("bundles", [])),
            }
            for period in periods
        ],
        "assetsCount": len(assets),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


class GiftStrategyHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, format, *args):
        if str(args[0]).startswith(("GET /api/", "PUT /api/", "POST /api/")):
            super().log_message(format, *args)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Filename")
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

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/content-package":
            self._post_content_package()
            return
        self.send_error(404)

    def _post_content_package(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self._json_response(400, {"error": "请选择要上传的 ZIP 图文包"})
            return
        if length > MAX_PACKAGE_BYTES:
            self._json_response(413, {"error": "图文包过大，压缩后不能超过 120MB"})
            return
        try:
            result = install_content_package(self.rfile.read(length))
            result["edits"] = read_edits()
            self._json_response(200, result, cache=False)
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)}, cache=False)
        except OSError as exc:
            self._json_response(500, {"error": f"保存图文包失败: {exc}"}, cache=False)

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
    print("  POST /api/content-package")
    server.serve_forever()


if __name__ == "__main__":
    main()
