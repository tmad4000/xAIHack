#!/usr/bin/env python3
"""Use xAI's Grok X Search tool to retrieve recent posts for a location or set of handles."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

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
    if not date_str:
        return None
    return datetime.fromisoformat(date_str)


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


def main() -> None:
    args = parse_args()
    api_key = get_env("XAI_API_KEY")
    if not api_key:
        raise SystemExit("Set XAI_API_KEY in your environment or .env file.")

    Client, user, x_search = ensure_sdk()

    tool_kwargs = {}
    allowed = parse_handles(args.allowed_handles)
    excluded = parse_handles(args.excluded_handles)
    if allowed:
        tool_kwargs["allowed_x_handles"] = allowed
    if excluded:
        tool_kwargs["excluded_x_handles"] = excluded
    from_date = parse_date(args.from_date)
    to_date = parse_date(args.to_date)
    if from_date:
        tool_kwargs["from_date"] = from_date
    if to_date:
        tool_kwargs["to_date"] = to_date

    tool = x_search(**tool_kwargs)
    client = Client(api_key=api_key)
    chat = client.chat.create(model=args.model, tools=[tool])

    prompt = (
        f"Use the X search tool to find {args.count} recent posts mentioning {args.location}. "
        "Return ONLY CSV text with the exact header:\n"
        "Date,Username,Summary/Quote,Link\n"
        "For each row:\n"
        "- Date: ISO (YYYY-MM-DD) of the tweet\n"
        "- Username: the @handle\n"
        "- Summary/Quote: 1-2 sentences capturing the proposal/problem details, matching the specificity found in curated civic planning datasets (e.g., mention numbers, locations, specific improvements, concrete requests)\n"
        "- Link: canonical https://x.com/... status URL\n"
        "Write rich summaries similar in detail to analytical civic planning notes (see geodatanyc.csv). "
        "No numbering, no extra commentary—just the header and rows."
    )
    chat.append(user(prompt))

    final_response = None
    csv_buffer = []
    print("Querying Grok with x_search...")
    for response, chunk in chat.stream():
        if chunk.tool_calls:
            for tool_call in chunk.tool_calls:
                name = getattr(tool_call.function, "name", "unknown")
                arguments = getattr(tool_call.function, "arguments", {})
                print(f"[tool] {name}: {json.dumps(arguments)}")
        if chunk.content:
            print(chunk.content, end="", flush=True)
            csv_buffer.append(chunk.content)
        final_response = response
    print()

    if args.csv_out:
        csv_text = "".join(csv_buffer).strip()
        if csv_text:
            args.csv_out.write_text(csv_text + ("\n" if not csv_text.endswith("\n") else ""), encoding="utf-8")
            print(f"Saved CSV to {args.csv_out}")

    if args.json_out and final_response:
        content = ""
        if getattr(final_response, "output_text", None):
            content = final_response.output_text
        elif getattr(final_response, "content", None):
            # content may be a string or list depending on SDK version
            if isinstance(final_response.content, str):
                content = final_response.content
            else:
                content = "".join(getattr(block, "text", "") for block in final_response.content)
        payload = {
            "response": content,
            "citations": to_jsonable(getattr(final_response, "citations", None)),
            "usage": to_jsonable(getattr(final_response, "usage", None)),
        }
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote Grok response to {args.json_out}")


if __name__ == "__main__":
    main()
