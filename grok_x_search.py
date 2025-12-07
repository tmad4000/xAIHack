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


def _build_prompt(location: str, count: int) -> str:
    """Build the standard prompt for X search queries."""
    return (
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


def _parse_csv_response(csv_text: str) -> List[Dict[str, str]]:
    """Parse CSV text into a list of row dictionaries."""
    rows: List[Dict[str, str]] = []
    if csv_text:
        try:
            reader = csv.DictReader(StringIO(csv_text))
            for row in reader:
                clean_row = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
                if any(clean_row.values()):
                    rows.append(clean_row)
        except Exception:
            rows = []
    return rows


def run_grok_search_responses_api(
    location: str,
    *,
    count: int = 10,
    model: str = "grok-4-1-fast",
    timeout: int = 90,
) -> Dict[str, Any]:
    """Execute x_search using the direct Responses API (often faster/more reliable)."""
    import requests

    api_key = get_env("XAI_API_KEY")
    if not api_key:
        raise SystemExit("Set XAI_API_KEY in your environment or .env file.")

    prompt = _build_prompt(location, count)

    payload = {
        "model": model,
        "input": [
            {"role": "user", "content": prompt}
        ],
        "tools": [
            {"type": "x_search"}
        ]
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    response = requests.post(
        "https://api.x.ai/v1/responses",
        headers=headers,
        json=payload,
        timeout=timeout
    )

    if response.status_code != 200:
        raise RuntimeError(f"Responses API error {response.status_code}: {response.text}")

    data = response.json()

    # Extract the text content from the response
    csv_text = ""
    if "output" in data:
        for item in data["output"]:
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        csv_text = content.get("text", "")
                        break

    rows = _parse_csv_response(csv_text)

    return {
        "csv_text": csv_text,
        "rows": rows,
        "response_text": csv_text,
        "usage": data.get("usage"),
        "citations": None,
        "tool_calls": [],
        "model": model,
        "location": location,
        "count": count,
        "api_method": "responses_api",
    }


def run_grok_search_sdk(
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
    """Execute x_search using the xAI SDK (supports more options but may be slower)."""
    api_key = get_env("XAI_API_KEY")
    if not api_key:
        raise SystemExit("Set XAI_API_KEY in your environment or .env file.")

    Client, user, _ = ensure_sdk()

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

    prompt = _build_prompt(location, count)
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
    rows = _parse_csv_response(csv_text)

    return {
        "csv_text": csv_text,
        "rows": rows,
        "response_text": _extract_response_text(final_response),
        "usage": to_jsonable(getattr(final_response, "usage", None)),
        "citations": to_jsonable(getattr(final_response, "citations", None)),
        "tool_calls": tool_calls,
        "model": model,
        "location": location,
        "count": count,
        "api_method": "sdk",
    }


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
    use_responses_api: bool = True,
) -> Dict[str, Any]:
    """Execute an x_search-powered Grok query and return structured results.

    By default, tries the faster Responses API first. Falls back to SDK if it fails
    or if advanced options (handle filtering, date ranges) are specified.
    """
    if allowed_handles and excluded_handles:
        raise ValueError("Specify either allowed_handles or excluded_handles, not both.")

    # Use SDK directly if advanced filtering options are specified
    needs_sdk = allowed_handles or excluded_handles or from_date or to_date

    if use_responses_api and not needs_sdk:
        # Try Responses API first (reportedly faster/more reliable)
        try:
            print("[grok] Trying Responses API...", file=sys.stderr)
            result = run_grok_search_responses_api(
                location,
                count=count,
                model=model,
                timeout=90,
            )
            print("[grok] Responses API succeeded", file=sys.stderr)
            return result
        except Exception as exc:
            print(f"[grok] Responses API failed: {exc}. Falling back to SDK.", file=sys.stderr)

    # Fall back to SDK
    print("[grok] Using SDK...", file=sys.stderr)
    return run_grok_search_sdk(
        location,
        count=count,
        allowed_handles=allowed_handles,
        excluded_handles=excluded_handles,
        from_date=from_date,
        to_date=to_date,
        model=model,
        chunk_callback=chunk_callback,
        tool_callback=tool_callback,
    )


def run_grok_report_insights(
    nodes: List[dict],
    edges: List[dict],
    *,
    context: str = "civic",
    model: str = "grok-4-1-fast",
    max_items: int = 40,
) -> str:
    """Generate high-level insights about the current graph using Grok."""
    if not nodes:
        return "No ideas available yet for Grok to analyze."

    api_key = get_env("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set XAI_API_KEY in your environment or .env file to generate Grok insights.")

    Client, user, _ = ensure_sdk()
    client = Client(api_key=api_key)

    # Prepare concise summaries for Grok
    sorted_nodes = sorted(
        nodes,
        key=lambda n: (n.get("date") or "", n.get("username") or ""),
        reverse=True,
    )
    node_snippets = []
    for node in sorted_nodes[:max_items]:
        node_snippets.append(
            f"- [{node.get('date', '')}] {node.get('username', '')}: {node.get('summary', '')}"
        )

    # Include sample edges with reasons if available
    node_lookup = {n.get("id"): n for n in nodes}
    edge_snippets = []
    for edge in edges[: max_items // 2]:
        source = node_lookup.get(edge.get("source_id"), {})
        target = node_lookup.get(edge.get("target_id"), {})
        edge_snippets.append(
            f"- {source.get('username', 'Unknown')} ↔ {target.get('username', 'Unknown')}: {edge.get('reason', '')}"
        )

    prompt_sections = [
        f"You are an urban planning analyst reviewing {len(nodes)} public suggestions ({context} context).",
        "Here are representative posts:",
        "\n".join(node_snippets) or "- No samples available.",
    ]

    if edge_snippets:
        prompt_sections.extend(
            [
                "\nKey connections that our clustering pipeline identified:",
                "\n".join(edge_snippets),
            ]
        )

    prompt_sections.append(
        "\nYou are Grok, an analyst summarizing civic input for decision makers. "
        "Write a concise markdown section (≤250 words) covering:\n"
        "- Emerging macro themes with cited voices\n"
        "- Conflicting opinions or tensions\n"
        "- Suggested next actions for city leaders"
    )

    prompt = "\n\n".join(prompt_sections)

    chat = client.chat.create(model=model)
    chat.append(user(prompt))

    final_response = None
    for response, _ in chat.stream():
        final_response = response

    return _extract_response_text(final_response)


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
