#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import html
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

SOURCE_URL = "https://www.motorboatdrivertest.com/business/exam/index.html"
EXPECTED_DIRECT = 40
EXPECTED_OPTION = 17
EXPECTED_IMAGE_QUESTIONS = 57
EXPECTED_UNIQUE_FILES = 104

# Verified image-question locations from the previously approved full version.
# Format: chapter-section-questionNumber.
EXPECTED_IMAGE_LOCATORS = {
    "2-1-1","2-1-2","2-1-3","2-1-4","2-1-5","2-1-6","2-1-8","2-1-10","2-1-11","2-1-16","2-1-17","2-1-33","2-1-34","2-1-35","2-1-45",
    "2-2-2","2-2-3","2-2-4","2-2-5","2-2-9","2-2-11","2-2-12","2-2-16","2-2-17","2-2-18","2-2-19","2-2-21","2-2-22","2-2-23","2-2-24","2-2-26","2-2-27",
    "3-1-27","3-1-28","3-1-39","3-2-5","3-2-10","3-2-45","3-2-46",
    "4-1-20","4-1-28",
    "6-1-5","6-1-6","6-1-7","6-1-8","6-2-19","6-2-20","6-2-23","6-3-6","6-3-13","6-3-19","6-3-20","6-3-21","6-3-22","6-3-23","6-3-30",
    "7-1-20",
}

CN_NUM = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}


def normalize_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    value = unicodedata.normalize("NFKC", value).lower()
    return "".join(ch for ch in value if ch.isalnum())


def chapter_number(value: str) -> int | None:
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    m = re.match(r"^([一二三四五六七八九十]+)[、.．]", value)
    if not m:
        return None
    token = m.group(1)
    if token in CN_NUM:
        return CN_NUM[token]
    if token.startswith("十") and len(token) == 2 and token[1] in CN_NUM:
        return 10 + CN_NUM[token[1]]
    if token.endswith("十") and len(token) == 2 and token[0] in CN_NUM:
        return CN_NUM[token[0]] * 10
    return None


def site_locator(question: dict) -> str | None:
    chapter = chapter_number(question.get("chapter", ""))
    section_match = re.match(r"^\s*(\d+)", unicodedata.normalize("NFKC", str(question.get("section") or "")))
    try:
        number = int(question.get("num"))
    except (TypeError, ValueError):
        return None
    if chapter is None or not section_match:
        return None
    return f"{chapter}-{int(section_match.group(1))}-{number}"


def fetch_bytes(url: str, retries: int = 4) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 MotorboatQuizBuilder/1.0"})
            with urlopen(req, timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}: {url}")
                return response.read()
        except Exception as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to download {url}: {last}")


def extract_reference_payload(source_html: str) -> dict:
    candidates = re.findall(r"[A-Za-z0-9+/=]{1000000,}", source_html)
    if not candidates:
        raise RuntimeError("Reference quiz payload was not found")
    encoded = max(candidates, key=len)
    raw = base64.b64decode(encoded + "=" * ((4 - len(encoded) % 4) % 4), validate=False)
    payload = json.loads(raw)
    if not isinstance(payload, dict) or "d" not in payload or "rs" not in payload:
        raise RuntimeError("Reference quiz payload has an unexpected structure")
    return payload


def extract_site_questions(site_html: str) -> list[dict]:
    match = re.search(r"(?:const|let|var)\s+QUESTION_BANK\s*=\s*", site_html)
    if not match:
        raise RuntimeError("QUESTION_BANK was not found in stable site HTML")
    questions, _ = json.JSONDecoder().raw_decode(site_html[match.end():])
    if not isinstance(questions, list) or len(questions) < 700:
        raise RuntimeError(f"Unexpected QUESTION_BANK size: {len(questions) if isinstance(questions, list) else 'not-list'}")
    return questions


def image_refs(question: dict) -> tuple[str | None, list[str | None]]:
    direct = (((question.get("at") or {}).get("i") or {}).get("i"))
    options: list[str | None] = []
    for choice in ((question.get("C") or {}).get("chs") or []):
        options.append(((choice.get("ia") or {}).get("i")))
    if not any(options):
        options = []
    return direct, options


def collect_reference_image_questions(payload: dict) -> list[dict]:
    result = []
    groups = (((payload.get("d") or {}).get("sl") or {}).get("g") or [])
    for group in groups:
        if not isinstance(group, dict):
            continue
        title = unicodedata.normalize("NFKC", str(group.get("T") or ""))
        number = re.match(r"^\s*(\d+)\.(\d+)", title)
        if not number:
            continue
        chapter = int(number.group(1))
        section = int(number.group(2))
        for item_number, question in enumerate(group.get("S") or [], start=1):
            if not isinstance(question, dict) or not question.get("D"):
                continue
            direct, options = image_refs(question)
            if direct or any(options):
                result.append({
                    "locator": f"{chapter}-{section}-{item_number}",
                    "direct": direct,
                    "options": options,
                })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True, help="Current stable site HTML")
    parser.add_argument("--out", required=True, help="Pages output directory")
    args = parser.parse_args()

    site_path = Path(args.site)
    out_dir = Path(args.out)
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    site_html = site_path.read_text(encoding="utf-8")
    site_questions = extract_site_questions(site_html)
    site_by_locator: dict[str, dict] = {}
    duplicate_locators: set[str] = set()
    for question in site_questions:
        locator = site_locator(question)
        if not locator:
            continue
        if locator in site_by_locator:
            duplicate_locators.add(locator)
        else:
            site_by_locator[locator] = question
    if duplicate_locators:
        raise RuntimeError(f"Duplicate stable-site question locators: {sorted(duplicate_locators)[:20]}")

    source_html = fetch_bytes(SOURCE_URL).decode("utf-8", errors="ignore")
    payload = extract_reference_payload(source_html)
    reference = collect_reference_image_questions(payload)

    direct_count = sum(1 for item in reference if item["direct"])
    option_count = sum(1 for item in reference if any(item["options"]))
    both_count = sum(1 for item in reference if item["direct"] and any(item["options"]))
    if (direct_count, option_count, both_count, len(reference)) != (
        EXPECTED_DIRECT,
        EXPECTED_OPTION,
        0,
        EXPECTED_IMAGE_QUESTIONS,
    ):
        raise RuntimeError(
            f"Reference image-question counts changed: direct={direct_count}, option={option_count}, both={both_count}, total={len(reference)}"
        )

    reference_locators = {item["locator"] for item in reference}
    if reference_locators != EXPECTED_IMAGE_LOCATORS:
        missing = sorted(EXPECTED_IMAGE_LOCATORS - reference_locators)
        extra = sorted(reference_locators - EXPECTED_IMAGE_LOCATORS)
        raise RuntimeError(f"Reference image locator set changed; missing={missing}, extra={extra}")

    missing_site = sorted(EXPECTED_IMAGE_LOCATORS - set(site_by_locator))
    if missing_site:
        raise RuntimeError(f"Stable site is missing expected image-question locations: {missing_site}")

    resources = ((payload.get("rs") or {}).get("i") or {})
    all_refs: set[str] = set()
    for item in reference:
        if item["direct"]:
            all_refs.add(item["direct"])
        all_refs.update(x for x in item["options"] if x)
    if len(all_refs) != EXPECTED_UNIQUE_FILES:
        raise RuntimeError(f"Unique image count changed: {len(all_refs)} != {EXPECTED_UNIQUE_FILES}")

    ref_to_path: dict[str, str] = {}
    jobs: list[tuple[str, str, Path]] = []
    for storage_ref in sorted(all_refs):
        record = resources.get(storage_ref)
        if not isinstance(record, dict) or not record.get("s"):
            raise RuntimeError(f"Missing resource record: {storage_ref}")
        rel = str(record["s"]).replace("\\", "/")
        filename = Path(rel).name
        if not re.fullmatch(r"[A-Za-z0-9._-]+", filename):
            raise RuntimeError(f"Unsafe image filename: {filename}")
        remote_url = urljoin(SOURCE_URL, rel)
        target = images_dir / filename
        ref_to_path[storage_ref] = f"images/{filename}"
        jobs.append((storage_ref, remote_url, target))

    def download(job: tuple[str, str, Path]) -> tuple[str, int]:
        storage_ref, remote_url, target = job
        data = fetch_bytes(remote_url)
        if len(data) < 100 or not data.startswith(b"\xff\xd8\xff"):
            raise RuntimeError(f"Invalid JPEG for {storage_ref}: {len(data)} bytes")
        target.write_bytes(data)
        return storage_ref, len(data)

    total_bytes = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for _, size in pool.map(download, jobs):
            total_bytes += size

    by_id: dict[str, dict] = {}
    by_key: dict[str, dict] = {}
    by_locator: dict[str, dict] = {}
    for item in reference:
        site = site_by_locator[item["locator"]]
        media = {
            "question": ref_to_path.get(item["direct"]) if item["direct"] else None,
            "options": [ref_to_path.get(x) if x else None for x in item["options"]],
        }
        while media["options"] and media["options"][-1] is None:
            media["options"].pop()

        actual_id = str(site.get("id") or "")
        key = normalize_text(site.get("question", ""))
        if not actual_id or not key:
            raise RuntimeError(f"Stable-site question has no usable id/text at {item['locator']}")
        by_id[actual_id] = media
        by_key[key] = media
        by_locator[item["locator"]] = media

    if len(by_locator) != EXPECTED_IMAGE_QUESTIONS or len(by_key) != EXPECTED_IMAGE_QUESTIONS:
        raise RuntimeError(
            f"Final image map size mismatch: byId={len(by_id)}, byKey={len(by_key)}, byLocator={len(by_locator)}"
        )

    stats = {
        "siteQuestions": len(site_questions),
        "imageQuestions": len(by_locator),
        "directQuestions": direct_count,
        "optionQuestions": option_count,
        "uniqueImages": len(all_refs),
        "imageBytes": total_bytes,
        "locatorMatches": len(by_locator),
        "expectedLocatorSetVerified": True,
    }
    bundle = {"byId": by_id, "byKey": by_key, "byLocator": by_locator, "stats": stats}
    js = "window.__MOTORBOAT_IMAGE_MAP__=" + json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (out_dir / "image-map.js").write_text(js, encoding="utf-8")
    (out_dir / "image-build-stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
