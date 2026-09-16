# -*- coding:utf-8 -*-

import os
import requests
import sys
import html2text
import google.genai as genai
from google.genai import Client

import json

_TRANSLATE_MODEL = "models/gemini-3.1-flash-lite"
_CHUNK_SIZE = 80  # a single unchunked request for a large category (900+ titles)
# took 160s+ and silently lost ~10% of titles -- big batches are slow, easy to
# truncate/time out, and any single malformed response poisons the whole
# batch. Chunking (same size rreader-web uses) keeps each request fast.


def _is_korean(s):
    """True if s contains at least one Hangul syllable (a real translation should)."""
    return isinstance(s, str) and any("가" <= c <= "힣" for c in s)


def _translate_chunk(titles, api_key):
    """
    Translate one chunk of titles. Returns {original_title: translated}, only
    for titles that actually got a Korean-looking translation back.

    Matched by an explicit idx sent with each title, not by re-parsing the
    title text Gemini echoes back as a JSON key -- some sources (e.g. Le
    Monde) use non-breaking spaces around punctuation that Gemini normalizes
    away when echoing a title, which silently breaks a text-based match even
    though the translation itself was correct.
    """
    try:
        client = Client(api_key=api_key)
        indexed = [{"idx": i, "title": t} for i, t in enumerate(titles)]
        prompt = (
            "Translate the 'title' in each object of the following JSON array to Korean. "
            "Each title may be in English, French, Japanese, or other languages -- translate all of them to Korean. "
            'Return a JSON array of the same length, each item as {"idx": <idx from input>, "ko": "<Korean translation>"}. '
            "Keep idx exactly as given; do not skip, merge, split, or reorder entries. "
            "Respond with ONLY the JSON array, no markdown.\n\n" + json.dumps(indexed, ensure_ascii=False)
        )
        response = client.models.generate_content(model=_TRANSLATE_MODEL, contents=prompt)
        cleaned = response.text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        arr = json.loads(cleaned)
        result = {}
        for item in arr:
            try:
                idx = int(item.get("idx"))
                ko = str(item.get("ko", "")).strip()
            except (TypeError, ValueError, AttributeError):
                continue
            if 0 <= idx < len(titles) and _is_korean(ko):
                result[titles[idx]] = ko
        return result
    except Exception as e:
        sys.stderr.write(f"[rreader] Gemini translation error: {e}\n")
        return {}


def translate_titles_batch(titles, api_key, cache):
    """
    Translates a batch of titles to Korean using Gemini, with caching.
    Returns a dictionary of {original_title: translated_title}.
    """
    if not api_key:
        return {}

    result = {}
    titles_to_translate = []

    for t in titles:
        if t in cache:
            result[t] = cache[t]
        else:
            titles_to_translate.append(t)

    if not titles_to_translate:
        return result

    chunks = [
        titles_to_translate[i : i + _CHUNK_SIZE]
        for i in range(0, len(titles_to_translate), _CHUNK_SIZE)
    ]
    for chunk in chunks:
        pending = chunk
        for attempt in range(3):
            good = _translate_chunk(pending, api_key)
            for original, translated in good.items():
                cache[original] = translated
                result[original] = translated
            pending = [t for t in pending if t not in good]
            if not pending:
                break

    return result

def summarize_with_gemini(url, api_key):
    """
    Fetches content from a URL, summarizes and translates it to Korean using Gemini.

    Args:
        url (str): The URL to fetch and summarize.
        api_key (str): The Gemini API key.

    Returns:
        str: The summarized and translated content, or an error message.
    """
    try:
        if not api_key:
            return "Error: Gemini API key is not provided."

        client = Client(api_key=api_key)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.body_width = 0
        page_text = h.handle(response.text)

        prompt = f"다음 글의 주요 내용만 한국어 bullet point 목록으로 정리해. 부연 설명, 재요약, 결론 문단 없이 목록만 출력해.\\n\\n{page_text}"

        try:
            # Generate content
            response = client.models.generate_content(
                model='models/gemini-2.5-flash-lite',
                contents=prompt
            )
            return response.text
        except Exception as e:
            if "429 RESOURCE_EXHAUSTED" in str(e):
                token_limits_output = get_model_token_limits(api_key)
                return f"An error occurred: {e}.\\n{token_limits_output}"
            elif "404 models/gemini-pro is not found" in str(e):
                # We are using gemini-2.5-flash-lite now, so this error should be less frequent
                return f"An error occurred: {e}. Please ensure the correct model name is used and it supports 'generateContent'."
            else:
                return f"An error occurred: {e}"

    except requests.exceptions.HTTPError as e:
        return ("fetch_error", e.response.status_code if e.response is not None else 0)
    except requests.exceptions.RequestException:
        return ("fetch_error", 0)
    except Exception as e:
        return f"An unexpected error occurred: {e}"

if __name__ == '__main__':
    # For testing purposes
    test_url = "https://www.zdnet.com/article/the-best-linux-laptops/"
    summary = summarize_with_gemini(test_url)
    print(summary)
