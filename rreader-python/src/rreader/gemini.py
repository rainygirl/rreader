# -*- coding:utf-8 -*-

import os
import requests
import sys
import html2text
import google.genai as genai
from google.genai import Client

import json
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

    try:
        client = Client(api_key=api_key)

        prompt_titles_json = json.dumps({"titles": titles_to_translate}, ensure_ascii=False)

        prompt = f"Translate the 'titles' in the following JSON to Korean and return the result as a JSON object where each original title from the input is a key and its Korean translation is the value. For example, for input {{'titles': ['Hello', 'World']}}, the output should be {{'Hello': '안녕하세요', 'World': '세상'}}. Respond with ONLY the JSON object.\\n\\nInput:\\n{prompt_titles_json}"

        response = client.models.generate_content(
            model='models/gemini-2.5-flash-lite',
            contents=prompt
        )

        cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()
        translated_data = json.loads(cleaned_response)

        if "titles" in translated_data and isinstance(translated_data["titles"], dict):
            translated_dict = translated_data["titles"]
        else:
            translated_dict = translated_data

        for original, translated in translated_dict.items():
            cache[original] = translated
            result[original] = translated

        return result
    except Exception as e:
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
