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

# These 57 IDs were extracted from the previously verified full image version.
# The reference quiz groups are numbered like 2.01, 3.02, 6.03 and the item
# position in each group is the question number, so the reference source can be
# mapped to our bank deterministically without guessing from question wording.
EXPECTED_IMAGE_IDS = {
    "2-1-1","2-1-2","2-1-3","2-1-4","2-1-5","2-1-6","2-1-8","2-1-10","2-1-11","2-1-16","2-1-17","2-1-33","2-1-34","2-1-35","2-1-45",
    "2-2-2","2-2-3","2-2-4","2-2-5","2-2-9","2-2-11","2-2-12","2-2-16","2-2-17","2-2-18","2-2-19","2-2-21","2-2-22","2-2-23","2-2-24","2-2-26","2-2-27",
    "3-1-27","3-1-28","3-1-39","3-2-5","3-2-10","3-2-45","3-2-46",
    "4-1-20","4-1-28",
    "6-1-5","6-1-6","6-1-7","6-1-8","6-2-19","6-2-20","6-2-23","6-3-6","6-3-13","6-3-19","6-3-20","6-3-21","6-3-22","6-3-23","6-3-30",
    "7-1-20",
}


def normalize_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    value = unicodedata.normalize("NFKC", value).lower()
    return "".join(ch for ch in value if ch.isalnum())


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
    decoder = json.JSONDecoder()
    questions, _ = decoder.raw_decode(site_html[match.end():])
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
                    "id": f"{chapter}-{section}-{item_number}",
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
    site_by_id = {str(q.get("id")): q for q in site_questions if q.get("id")}

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

    reference_ids = {item["id"] for item in reference}
    if reference_ids != EXPECTED_IMAGE_IDS:
        missing = sorted(EXPECTED_IMAGE_IDS - reference_ids)
        extra = sorted(reference_ids - EXPECTED_IMAGE_IDS)
        raise RuntimeError(f"Reference image ID set changed; missing={missing}, extra={extra}")

    missing_site_ids = sorted(EXPECTED_IMAGE_IDS - set(site_by_id))
    if missing_site_ids:
        raise RuntimeError(f"Stable site is missing expected image-question IDs: {missing_site_ids}")

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
    for item in reference:
        site = site_by_id[item["id"]]
        media = {
            "question": ref_to_path.get(item["direct"]) if item["direct"] else None,
            "options": [ref_to_path.get(x) if x else None for x in item["options"]],
        }
        while media["options"] and media["options"][-1] is None:
            media["options"].pop()
        key = normalize_text(site.get("question", ""))
        if not key:
            raise RuntimeError(f"Stable-site question has no usable text: {item['id']}")
        by_id[item["id"]] = media
        by_key[key] = media

    if len(by_id) != EXPECTED_IMAGE_QUESTIONS or len(by_key) != EXPECTED_IMAGE_QUESTIONS:
        raise RuntimeError(f"Final image map size mismatch: byId={len(by_id)}, byKey={len(by_key)}")

    stats = {
        "siteQuestions": len(site_questions),
        "imageQuestions": len(by_id),
        "directQuestions": direct_count,
        "optionQuestions": option_count,
        "uniqueImages": len(all_refs),
        "imageBytes": total_bytes,
        "idMatches": len(by_id),
        "expectedIdSetVerified": True,
    }
    bundle = {"byId": by_id, "byKey": by_key, "stats": stats}
    js = "window.__MOTORBOAT_IMAGE_MAP__=" + json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (out_dir / "image-map.js").write_text(js, encoding="utf-8")
    (out_dir / "image-build-stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
