#!/usr/bin/env python3
"""Use xAI's Grok X Search tool to retrieve recent posts for a location or set of handles."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from io import StringIO
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

_ENV_CACHE: Optional[Dict[str, str]] = None


def _load_env_file() -> None:
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return
    _ENV_CACHE = {}
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        _ENV_CACHE[key.strip()] = value.strip().strip('\'"')


def get_env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value:
        return value
    _load_env_file()
    return _ENV_CACHE.get(name) if _ENV_CACHE else None


def ensure_sdk():
    try:
        from xai_sdk import Client  # type: ignore
        from xai_sdk.chat import user  # type: ignore
        from xai_sdk.tools import x_search  # type: ignore
    except ImportError as exc:  # pragma: no cover - guard for missing dep
        raise SystemExit(
            "xai-sdk is required for Grok search. Install with: pip install 'xai-sdk>=1.3.1'"
        ) from exc
    return Client, user, x_search


def parse_handles(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    parts = [handle.strip().lstrip("@") for handle in value.split(",") if handle.strip()]
    return parts or None


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 dates if provided; ignore invalid values."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        print(f"Warning: ignoring invalid date '{date_str}'. Expected YYYY-MM-DD.", file=sys.stderr)
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Leverage Grok's x_search tool to summarize tweets for a location."
    )
    parser.add_argument(
        "--location",
        default="San Francisco",
        help="Location or topic to ask Grok to focus on.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of posts to request in the prompt (default: %(default)s).",
    )
    parser.add_argument(
        "--allowed-handles",
        help="Comma-separated list of handles to restrict search to (omit @).",
    )
    parser.add_argument(
        "--excluded-handles",
        help="Comma-separated list of handles to exclude.",
    )
    parser.add_argument(
        "--from-date",
        help="Only consider posts on/after this ISO date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--to-date",
        help="Only consider posts on/before this ISO date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--model",
        default="grok-4-1-fast",
        help="Grok model name (default: %(default)s).",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Path to save the JSON metadata (response text, citations, usage).",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        help="Path to save the raw CSV text emitted by Grok.",
    )
    return parser.parse_args()


def _extract_response_text(response: Any) -> str:
    """Extract plain text from the SDK response object."""
    if response is None:
        return ""
    if getattr(response, "output_text", None):
        return response.output_text
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    text_blocks = []
    for block in content or []:
        text = getattr(block, "text", "")
        if text:
            text_blocks.append(text)
    return "".join(text_blocks)


def to_jsonable(value: Any) -> Any:
    """Best-effort conversion of SDK objects (e.g., repeated containers) to JSON."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if hasattr(value, "to_dict"):
        return to_jsonable(value.to_dict())
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [to_jsonable(v) for v in value]
    return str(value)


def run_grok_search(
    location: str,
    *,
    count: int = 10,
    allowed_handles: Optional[List[str]] = None,
    excluded_handles: Optional[List[str]] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    model: str = "grok-4-1-fast",
    chunk_callback: Optional[Callable[[str], None]] = None,
    tool_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Execute an x_search-powered Grok query and return structured results."""
    if allowed_handles and excluded_handles:
        raise ValueError("Specify either allowed_handles or excluded_handles, not both.")

    api_key = get_env("XAI_API_KEY")
    if not api_key:
        raise SystemExit("Set XAI_API_KEY in your environment or .env file.")

    Client, user, x_search = ensure_sdk()

    tool_kwargs: Dict[str, Any] = {}
    if allowed_handles:
        tool_kwargs["allowed_x_handles"] = allowed_handles
    if excluded_handles:
        tool_kwargs["excluded_x_handles"] = excluded_handles
    if from_date:
        tool_kwargs["from_date"] = from_date
    if to_date:
        tool_kwargs["to_date"] = to_date

    tool = x_search(**tool_kwargs)
    client = Client(api_key=api_key)
    chat = client.chat.create(model=model, tools=[tool])

    prompt = (
        f"Use the X search tool to find {count} recent posts mentioning {location}. "
        "Return ONLY CSV text with the exact header:\n"
        "Date,Username,Summary/Quote,Link\n"
        "For each row:\n"
        "- Date: ISO (YYYY-MM-DD) of the tweet\n"
        "- Username: the @handle\n"
        "- Summary/Quote: 1-2 sentences capturing the proposal/problem details, matching the specificity found in curated civic planning datasets (e.g., mention numbers, locations, specific improvements, concrete requests)\n"
        "- Link: canonical https://x.com/... status URL\n"
        "Write rich summaries similar in detail to analytical civic planning notes (see geodatanyc.csv). "
        "No numbering, no extra commentary-just the header and rows."
    )
    chat.append(user(prompt))

    csv_buffer: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    final_response: Any = None

    for response, chunk in chat.stream():
        if chunk.tool_calls:
            for tool_call in chunk.tool_calls:
                entry = {
                    "name": getattr(getattr(tool_call, "function", None), "name", "unknown"),
                    "arguments": getattr(getattr(tool_call, "function", None), "arguments", {}),
                }
                tool_calls.append(entry)
                if tool_callback:
                    tool_callback(entry)

        if chunk.content:
            csv_buffer.append(chunk.content)
            if chunk_callback:
                chunk_callback(chunk.content)

        final_response = response

    csv_text = "".join(csv_buffer).strip()
    rows: List[Dict[str, str]] = []

    if csv_text:
        try:
            reader = csv.DictReader(StringIO(csv_text))
            for row in reader:
                clean_row = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
                if any(clean_row.values()):
                    rows.append(clean_row)
        except Exception:
            # If parsing fails, still return the raw CSV text
            rows = []

    result = {
        "csv_text": csv_text,
        "rows": rows,
        "response_text": _extract_response_text(final_response),
        "usage": to_jsonable(getattr(final_response, "usage", None)),
        "citations": to_jsonable(getattr(final_response, "citations", None)),
        "tool_calls": tool_calls,
        "model": model,
        "location": location,
        "count": count,
    }

    return result


def main() -> None:
    args = parse_args()
    allowed = parse_handles(args.allowed_handles)
    excluded = parse_handles(args.excluded_handles)
    from_date = parse_date(args.from_date)
    to_date = parse_date(args.to_date)

    def chunk_logger(text: str) -> None:
        print(text, end="", flush=True)

    def tool_logger(entry: Dict[str, Any]) -> None:
        print(f"[tool] {entry['name']}: {json.dumps(entry['arguments'])}")

    print("Querying Grok with x_search...")
    result = run_grok_search(
        args.location,
        count=args.count,
        allowed_handles=allowed,
        excluded_handles=excluded,
        from_date=from_date,
        to_date=to_date,
        model=args.model,
        chunk_callback=chunk_logger,
        tool_callback=tool_logger,
    )
    print()

    if args.csv_out:
        csv_text = result["csv_text"]
        if csv_text:
            args.csv_out.write_text(csv_text + ("\n" if not csv_text.endswith("\n") else ""), encoding="utf-8")
            print(f"Saved CSV to {args.csv_out}")

    if args.json_out:
        payload = {
            "response": result["response_text"],
            "citations": result["citations"],
            "usage": result["usage"],
            "tool_calls": result["tool_calls"],
            "location": result["location"],
            "count": result["count"],
            "model": result["model"],
        }
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote Grok response to {args.json_out}")


if __name__ == "__main__":
    main()
