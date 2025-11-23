import json
import os
import re
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


BASE_URL = os.getenv("STC_BACKEND_URL", "https://stc-tender-platform.onrender.com").rstrip("/")


def http_get(path: str):
    url = BASE_URL + path
    try:
        with urlopen(url) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except (URLError, HTTPError) as e:
        print(f"GET {url} failed: {e}")
        raise


def http_post(path: str, payload: dict):
    url = BASE_URL + path
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except (URLError, HTTPError) as e:
        print(f"POST {url} failed: {e}")
        raise


def extract_count_ar(answer: str):
    if not answer:
        return None
    m = re.search(r"وجدت\s+(\d+)", answer)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)", answer)
    return int(m.group(1)) if m else None


def extract_count_en(answer: str):
    if not answer:
        return None
    m = re.search(r"I found\s+(\d+)", answer)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)", answer)
    return int(m.group(1)) if m else None


def test_global_count() -> bool:
    """Check that global count question matches /api/tenders/stats/summary total."""
    stats = http_get("/api/tenders/stats/summary")
    expected = stats.get("total_tenders")
    print(f"[GLOBAL] Expected total_tenders = {expected}")

    chat = http_post(
        "/api/chat/ask",
        {
            "question": "كم عدد المناقصات الموجودة حالياً في النظام؟",
            "lang": "ar",
        },
    )

    got_ar = extract_count_ar(chat.get("answer_ar"))
    got_en = extract_count_en(chat.get("answer_en"))
    got = got_ar if got_ar is not None else got_en

    print(f"[GLOBAL] Agent answered (ar): {chat.get('answer_ar')[:150]}...")
    print(f"[GLOBAL] Parsed count = {got}")

    if got != expected:
        print(f"[GLOBAL] ❌ MISMATCH: expected {expected}, got {got}")
        return False

    print("[GLOBAL] ✅ PASS")
    return True


def test_ministry_top_count() -> bool:
    """Pick the top ministry from stats and verify count matches agent answer."""
    stats = http_get("/api/tenders/stats/summary")
    top_ministries = stats.get("top_ministries") or []
    if not top_ministries:
        print("[MINISTRY] ⚠️ No ministries found in stats, skipping test")
        return True

    top = top_ministries[0]
    ministry_name = top.get("name")
    expected = top.get("count")
    print(f"[MINISTRY] Testing ministry: {ministry_name} (expected count = {expected})")

    question = f"كم عدد المناقصات من {ministry_name}؟"
    chat = http_post(
        "/api/chat/ask",
        {
            "question": question,
            "lang": "ar",
        },
    )

    got_ar = extract_count_ar(chat.get("answer_ar"))
    got_en = extract_count_en(chat.get("answer_en"))
    got = got_ar if got_ar is not None else got_en

    print(f"[MINISTRY] Agent answered (ar): {chat.get('answer_ar')[:150]}...")
    print(f"[MINISTRY] Parsed count = {got}")

    if got != expected:
        print(f"[MINISTRY] ❌ MISMATCH: expected {expected}, got {got}")
        return False

    print("[MINISTRY] ✅ PASS")
    return True


def main():
    print(f"Using backend base URL: {BASE_URL}")
    all_ok = True

    if not test_global_count():
        all_ok = False

    if not test_ministry_top_count():
        all_ok = False

    if not all_ok:
        print("\nOverall result: ❌ SOME TESTS FAILED")
        sys.exit(1)

    print("\nOverall result: ✅ ALL TESTS PASSED")


if __name__ == "__main__":
    main()
