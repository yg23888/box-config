#!/usr/bin/env python3
"""Merge public TVBox config sources into a split, validated config set.

Output:
  core.json      data-only sites (type 0/1) + parses + lives + flags + ads
  ext.json       code sites (type 3, HTTPS only) - opt-in, hash-pinned
  manifest.json  sha256 + counts + per-source status + JS hashes

Safety rules:
  - core: absolute http(s) API only, no jar/spider, no type 3
  - ext:  absolute https only, no jar/spider
  - never write output if validation fails
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

SOURCES = [
    ("老刘备", "https://raw.liucn.cc/box/m.json"),
    ("小马", "https://szyyds.cn/tv/x.json"),
    ("小盒子4K", "http://xhztv.top/4k.json"),
    ("创享影视", "https://ys.cxkjg.cn/api/provide/tvbox"),
    ("cluntop/tvbox", "https://raw.githubusercontent.com/cluntop/tvbox/main/box.json"),
    ("Lightconer/tvbox-source", "https://raw.githubusercontent.com/Lightconer/tvbox-source/main/tvbox.json"),
    ("larry-biu/tvbox-config", "https://raw.githubusercontent.com/larry-biu/tvbox-config/main/tvbox.json"),
    ("jiusanzhou/tvbox", "https://raw.githubusercontent.com/jiusanzhou/tvbox/main/tvbox.json"),
]

UA = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 TVBoxConfigBot/1.0"
CST = timezone(timedelta(hours=8))
MIN_CORE_SITES = 45
MIN_SOURCES_OK = 4


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_comments(text: str) -> str:
    out, i, n, instr, esc = [], 0, len(text), False, False
    while i < n:
        c = text[i]
        if instr:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
            i += 1
            continue
        if c == '"':
            instr = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n:
            if text[i + 1] == "/":
                j = text.find("\n", i)
                i = n if j < 0 else j
                continue
            if text[i + 1] == "*":
                j = text.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
        out.append(c)
        i += 1
    return "".join(out)


def strip_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def parse_config(raw: bytes):
    text = raw.decode("utf-8-sig", errors="replace").replace("\ufeff", "")
    variants = [text, strip_comments(text)]
    variants += [strip_trailing_commas(v) for v in list(variants)]
    for v in variants:
        try:
            data = json.loads(v, strict=False)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        seg = text[a:b + 1]
        for v in (seg, strip_trailing_commas(strip_comments(seg))):
            try:
                data = json.loads(v, strict=False)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    raise ValueError("not a JSON object")


def is_abs(api: str) -> bool:
    return api.startswith(("http://", "https://"))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def merge(previous_core_count: int):
    core_sites, ext_sites = [], []
    seen_keys, seen_api = set(), set()
    parses, seen_parse = [], set()
    lives, seen_live = [], set()
    flags, seen_flags = [], set()
    ads, seen_ads = [], set()
    status = []

    for name, url in SOURCES:
        entry = {"name": name, "url": url, "ok": False, "sites": 0, "parses": 0, "lives": 0, "error": ""}
        try:
            data = parse_config(fetch(url))
            entry["ok"] = True
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            log(f"[skip] {name}: {entry['error']}")
            status.append(entry)
            continue

        for s in data.get("sites") or []:
            if not isinstance(s, dict):
                continue
            api = str(s.get("api") or "")
            if not is_abs(api):
                continue
            key = str(s.get("key") or s.get("name") or "").strip()
            if not key:
                continue
            typ = s.get("type")
            if typ == 3:
                if not api.startswith("https://"):
                    continue
                bucket = ext_sites
            elif typ in (0, 1):
                bucket = core_sites
            else:
                continue
            k = key.lower()
            if k in seen_keys or api in seen_api:
                continue
            seen_keys.add(k)
            seen_api.add(api)
            s.pop("jar", None)
            s.pop("spider", None)
            bucket.append(s)
            entry["sites"] += 1

        for p in data.get("parses") or []:
            if not isinstance(p, dict):
                continue
            url_p = str(p.get("url") or "")
            if not is_abs(url_p) or url_p in seen_parse:
                continue
            seen_parse.add(url_p)
            parses.append(p)
            entry["parses"] += 1

        for l in data.get("lives") or []:
            if not isinstance(l, dict):
                continue
            name_l, url_l = str(l.get("name") or ""), str(l.get("url") or "")
            if not name_l or not url_l or (name_l.lower(), url_l.lower()) in seen_live:
                continue
            seen_live.add((name_l.lower(), url_l.lower()))
            lives.append(l)
            entry["lives"] += 1

        for f in data.get("flags") or []:
            if isinstance(f, str) and f not in seen_flags:
                seen_flags.add(f)
                flags.append(f)
        for a in data.get("ads") or []:
            if isinstance(a, str) and a not in seen_ads:
                seen_ads.add(a)
                ads.append(a)

        status.append(entry)
        log(f"[ok]   {name}: +{entry['sites']} sites, +{entry['parses']} parses, +{entry['lives']} lives")

    core = {
        "sites": core_sites,
        "parses": parses,
        "lives": lives,
        "flags": flags,
        "ads": ads,
        "spider": "",
        "wallpaper": "",
    }
    ext = {"sites": ext_sites, "parses": [], "lives": [], "flags": [], "ads": [], "spider": ""}
    return core, ext, status


def validate(core, ext, status, previous_core_count):
    errors = []
    ok_sources = sum(1 for s in status if s["ok"])
    if ok_sources < MIN_SOURCES_OK:
        errors.append(f"only {ok_sources} sources reachable (min {MIN_SOURCES_OK})")
    if len(core["sites"]) < MIN_CORE_SITES:
        errors.append(f"core sites {len(core['sites'])} < {MIN_CORE_SITES}")
    if previous_core_count and len(core["sites"]) < previous_core_count * 0.8:
        errors.append(f"core sites dropped {previous_core_count} -> {len(core['sites'])} (>20% loss)")
    if len(ext["sites"]) > 40:
        errors.append(f"ext sites {len(ext['sites'])} > 40")
    if any(not str(s.get("api", "")).startswith(("http://", "https://")) for s in core["sites"]):
        errors.append("core contains non-absolute api")
    if any(s.get("type") == 3 for s in core["sites"]):
        errors.append("core contains type 3 site")
    if any(not str(s.get("api", "")).startswith("https://") for s in ext["sites"]):
        errors.append("ext contains non-https site")
    return errors


def js_hashes(ext):
    result = {}
    for s in ext["sites"]:
        url = str(s.get("api") or "")
        if not url.endswith(".js") and ".js?" not in url:
            continue
        try:
            data = fetch(url, timeout=20)
            result[url] = hashlib.sha256(data).hexdigest()
        except Exception as exc:  # noqa: BLE001
            result[url] = None
            log(f"[warn] js hash failed {url}: {type(exc).__name__}")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--no-js-hash", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    prev_count = 0
    prev_path = os.path.join(args.out, "core.json")
    if os.path.isfile(prev_path):
        try:
            prev_count = len(json.load(open(prev_path, encoding="utf-8")).get("sites") or [])
        except Exception:
            prev_count = 0

    core, ext, status = merge(prev_count)
    errors = validate(core, ext, status, prev_count)
    if errors:
        for e in errors:
            log(f"[FAIL] {e}")
        log("validation failed; output not written")
        return 1

    core_path = os.path.join(args.out, "core.json")
    ext_path = os.path.join(args.out, "ext.json")
    man_path = os.path.join(args.out, "manifest.json")

    with open(core_path, "w", encoding="utf-8") as f:
        json.dump(core, f, ensure_ascii=False, separators=(",", ":"))
    with open(ext_path, "w", encoding="utf-8") as f:
        json.dump(ext, f, ensure_ascii=False, indent=1)

    hashes = {}
    if not args.no_js_hash:
        hashes = js_hashes(ext)

    now = datetime.now(CST)
    manifest = {
        "schema": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "core": {
            "file": "core.json",
            "sha256": sha256_file(core_path),
            "sites": len(core["sites"]),
            "parses": len(core["parses"]),
            "lives": len(core["lives"]),
            "flags": len(core["flags"]),
            "ads": len(core["ads"]),
        },
        "ext": {
            "file": "ext.json",
            "sha256": sha256_file(ext_path),
            "sites": len(ext["sites"]),
            "enabled_by_default": False,
        },
        "sources": status,
        "js_hashes": hashes,
    }
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    log(
        "OK core=%d ext=%d parses=%d lives=%d flags=%d ads=%d"
        % (len(core["sites"]), len(ext["sites"]), len(core["parses"]),
           len(core["lives"]), len(core["flags"]), len(core["ads"]))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
