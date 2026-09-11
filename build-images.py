#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import difflib
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


def reference_question_text(question: dict) -> str:
    data = question.get("D") or {}
    plain = data.get("d")
    if isinstance(plain, list) and plain:
        return " ".join(str(x) for x in plain if x is not None).strip()
    return re.sub(r"<[^>]+>", " ", data.get("a") or data.get("h") or "").strip()


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
    for group in (((payload.get("d") or {}).get("sl") or {}).get("g") or []):
        for question in group.get("S", []) if isinstance(group, dict) else []:
            if not isinstance(question, dict) or not question.get("D"):
                continue
            direct, options = image_refs(question)
            if direct or any(options):
                result.append({
                    "text": reference_question_text(question),
                    "direct": direct,
                    "options": options,
                })
    return result


def match_questions(reference: list[dict], site_questions: list[dict]) -> list[tuple[dict, dict, str]]:
    by_key: dict[str, list[dict]] = {}
    site_keys: list[tuple[str, dict]] = []
    for question in site_questions:
        key = normalize_text(question.get("question", ""))
        if not key:
            continue
        by_key.setdefault(key, []).append(question)
        site_keys.append((key, question))

    matched: list[tuple[dict, dict, str]] = []
    used_ids: set[str] = set()
    for ref in reference:
        ref_key = normalize_text(ref["text"])
        exact = [q for q in by_key.get(ref_key, []) if q.get("id") not in used_ids]
        if len(exact) == 1:
            site = exact[0]
            method = "exact"
        else:
            scored = []
            for key, candidate in site_keys:
                if candidate.get("id") in used_ids:
                    continue
                ratio = difflib.SequenceMatcher(None, ref_key, key).ratio()
                scored.append((ratio, candidate, key))
            scored.sort(key=lambda x: x[0], reverse=True)
            if not scored:
                raise RuntimeError(f"No site candidate for image question: {ref['text']}")
            best = scored[0]
            second = scored[1][0] if len(scored) > 1 else 0.0
            if best[0] < 0.94 or best[0] - second < 0.015:
                raise RuntimeError(
                    f"Unsafe fuzzy match ({best[0]:.3f}/{second:.3f}) for: {ref['text']} -> {best[1].get('question')}"
                )
            site = best[1]
            method = f"fuzzy:{best[0]:.3f}"
        used_ids.add(str(site.get("id")))
        matched.append((ref, site, method))
    return matched


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

    matched = match_questions(reference, site_questions)
    if len(matched) != EXPECTED_IMAGE_QUESTIONS:
        raise RuntimeError(f"Matched {len(matched)} image questions, expected {EXPECTED_IMAGE_QUESTIONS}")

    resources = ((payload.get("rs") or {}).get("i") or {})
    all_refs: set[str] = set()
    for ref, _, _ in matched:
        if ref["direct"]:
            all_refs.add(ref["direct"])
        all_refs.update(x for x in ref["options"] if x)
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
    exact_count = 0
    fuzzy_count = 0
    for ref, site, method in matched:
        if method == "exact":
            exact_count += 1
        else:
            fuzzy_count += 1
        media = {
            "question": ref_to_path.get(ref["direct"]) if ref["direct"] else None,
            "options": [ref_to_path.get(x) if x else None for x in ref["options"]],
        }
        while media["options"] and media["options"][-1] is None:
            media["options"].pop()
        qid = str(site.get("id") or "")
        key = normalize_text(site.get("question", ""))
        if not qid or not key:
            raise RuntimeError("Matched site question is missing id/text")
        by_id[qid] = media
        by_key[key] = media

    stats = {
        "siteQuestions": len(site_questions),
        "imageQuestions": len(matched),
        "directQuestions": direct_count,
        "optionQuestions": option_count,
        "uniqueImages": len(all_refs),
        "imageBytes": total_bytes,
        "exactMatches": exact_count,
        "fuzzyMatches": fuzzy_count,
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
