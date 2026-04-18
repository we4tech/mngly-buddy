import os
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv


def main() -> int:
    load_dotenv(".env.local")

    api_url = os.getenv("API_URL", "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()
    if not api_url:
        print("API URL is not configured. Set API_URL in .env.local.")
        return 1

    model = os.getenv("LLM_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "").strip()
    if not model:
        print("Model is not configured. Set LLM_MODEL in .env.local.")
        return 1

    endpoint = urljoin(api_url.rstrip("/") + "/", "models")

    try:
        response = httpx.get(endpoint, timeout=5.0)
        status = response.status_code
        if status >= 400:
            print(f"API reachable but returned HTTP {status} for {endpoint}")
            return 2

        print(f"API reachable: {endpoint}")
        print(f"Configured model: {model}")
        return 0
    except httpx.HTTPError as exc:
        print(f"Unable to reach API endpoint: {endpoint}")
        print(f"Error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

