#!/usr/bin/env python3
"""
Connect to the user's running Chrome via CDP (Chrome DevTools Protocol).

Provides subcommands to inspect, screenshot, and read content from
the user's actual browser — not a headless instance.

Prerequisites:
  - Chrome running with --remote-debugging-port (use chrome-debug.sh or 'enable' subcommand)
  - playwright installed (pip install playwright && playwright install chromium)

Usage:
  web-control.py status              — check if CDP is available
  web-control.py screenshot [INDEX]  — screenshot a tab (default: active)
  web-control.py screenshot --url URL — screenshot tab matching URL
  web-control.py content [INDEX]     — get text content of a tab
  web-control.py content --url URL   — get text content matching URL
  web-control.py enable [PORT]       — enable CDP on Chrome (restart if needed)
"""
import argparse
import json
import subprocess
import sys
import urllib.request
import urllib.error
import os
import textwrap

DEFAULT_PORT = 9222
CDP_BASE = "http://localhost:{port}"


def cdp_url(port: int) -> str:
    return CDP_BASE.format(port=port)


def cdp_get(path: str, port: int) -> dict | list | None:
    """Make a GET request to a CDP HTTP endpoint."""
    try:
        url = f"{cdp_url(port)}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def cmd_status(args):
    """Check if Chrome CDP is available."""
    version = cdp_get("/json/version", args.port)
    if version is None:
        print(f"CDP not available on port {args.port}")
        print(f"\nTo enable: {sys.argv[0]} enable")
        return 1

    print(f"CDP active on port {args.port}")
    print(f"  Browser: {version.get('Browser', '?')}")
    print(f"  Protocol: {version.get('Protocol-Version', '?')}")
    print(f"  V8: {version.get('V8-Version', '?')}")
    ws = version.get("webSocketDebuggerUrl", "")
    if ws:
        print(f"  WebSocket: {ws}")
    return 0



def _find_tab_index(tabs: list, url: str | None, index: int | None) -> int | None:
    """Resolve a tab by URL substring or index."""
    pages = [t for t in tabs if t.get("type") == "page"]
    if not pages:
        return None

    if url:
        for i, tab in enumerate(pages):
            if url.lower() in tab.get("url", "").lower():
                return i
        for i, tab in enumerate(pages):
            if url.lower() in tab.get("title", "").lower():
                return i
        return None

    if index is not None:
        return index if 0 <= index < len(pages) else None

    # Default: first tab (most recently active)
    return 0


def _run_playwright(script: str) -> tuple[int, str, str]:
    """Run a playwright script in a subprocess."""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def cmd_screenshot(args):
    """Take a screenshot of a tab via CDP."""
    tabs = cdp_get("/json", args.port)
    if tabs is None:
        print(f"CDP not available on port {args.port}")
        return 1

    pages = [t for t in tabs if t.get("type") == "page"]
    tab_idx = _find_tab_index(tabs, args.url, args.index)
    if tab_idx is None:
        target = args.url or f"index {args.index}"
        print(f"Tab not found: {target}")
        print("Available tabs:")
        for i, t in enumerate(pages):
            print(f"  [{i}] {t.get('title', '?')} — {t.get('url', '?')}")
        return 1

    tab = pages[tab_idx]
    output = args.output or "/tmp/web-control-screenshot.png"
    full_page = "--full-page" not in sys.argv or args.full_page

    script = textwrap.dedent(f"""\
        import asyncio
        from playwright.async_api import async_playwright

        async def main():
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp("http://localhost:{args.port}")
                contexts = browser.contexts
                if not contexts:
                    print("No browser contexts found")
                    return

                # Find the target page by URL
                target_url = {repr(tab.get('url', ''))}
                page = None
                for ctx in contexts:
                    for pg in ctx.pages:
                        if pg.url == target_url:
                            page = pg
                            break
                    if page:
                        break

                if not page:
                    # Fallback: use page at index
                    all_pages = []
                    for ctx in contexts:
                        all_pages.extend(ctx.pages)
                    idx = {tab_idx}
                    if idx < len(all_pages):
                        page = all_pages[idx]
                    else:
                        page = contexts[0].pages[0] if contexts[0].pages else None

                if not page:
                    print("Could not find target page")
                    return

                await page.screenshot(
                    path="{output}",
                    full_page={full_page},
                )
                title = await page.title()
                print(f"Screenshot: {{title}}")
                print(f"URL: {{page.url}}")
                print(f"Saved: {output}")

        asyncio.run(main())
    """)

    rc, stdout, stderr = _run_playwright(script)
    if rc != 0:
        print(f"Screenshot failed: {stderr.strip()}", file=sys.stderr)
        return 1
    print(stdout, end="")
    return 0


def cmd_content(args):
    """Get text content of a tab via CDP."""
    tabs = cdp_get("/json", args.port)
    if tabs is None:
        print(f"CDP not available on port {args.port}")
        return 1

    pages = [t for t in tabs if t.get("type") == "page"]
    tab_idx = _find_tab_index(tabs, args.url, args.index)
    if tab_idx is None:
        target = args.url or f"index {args.index}"
        print(f"Tab not found: {target}")
        return 1

    tab = pages[tab_idx]

    script = textwrap.dedent(f"""\
        import asyncio
        from playwright.async_api import async_playwright

        async def main():
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp("http://localhost:{args.port}")
                contexts = browser.contexts

                target_url = {repr(tab.get('url', ''))}
                page = None
                for ctx in contexts:
                    for pg in ctx.pages:
                        if pg.url == target_url:
                            page = pg
                            break
                    if page:
                        break

                if not page:
                    all_pages = []
                    for ctx in contexts:
                        all_pages.extend(ctx.pages)
                    idx = {tab_idx}
                    if idx < len(all_pages):
                        page = all_pages[idx]

                if not page:
                    print("Could not find target page")
                    return

                title = await page.title()
                url = page.url

                # Get readable text content
                text = await page.evaluate('''() => {{
                    // Remove script and style elements
                    const clone = document.body.cloneNode(true);
                    clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                    return clone.innerText;
                }}''')

                print(f"# {{title}}")
                print(f"URL: {{url}}")
                print(f"---")
                print(text)

        asyncio.run(main())
    """)

    rc, stdout, stderr = _run_playwright(script)
    if rc != 0:
        print(f"Content extraction failed: {stderr.strip()}", file=sys.stderr)
        return 1
    print(stdout, end="")
    return 0


def cmd_enable(args):
    """Enable CDP on Chrome by running chrome-debug.sh."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    debug_script = os.path.join(script_dir, "chrome-debug.sh")

    if not os.path.exists(debug_script):
        print(f"chrome-debug.sh not found at {debug_script}")
        return 1

    result = subprocess.run(
        ["bash", debug_script, str(args.port)],
        capture_output=False,
    )
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Connect to Chrome via CDP to inspect your browser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"CDP port (default: {DEFAULT_PORT})",
    )

    subs = parser.add_subparsers(dest="command", help="Available commands")

    # status
    subs.add_parser("status", help="Check if CDP is available")

    # screenshot
    p_ss = subs.add_parser("screenshot", help="Screenshot a tab")
    p_ss.add_argument("index", type=int, nargs="?", default=None, help="Tab index")
    p_ss.add_argument("--url", help="Match tab by URL substring")
    p_ss.add_argument("--output", "-o", help="Output path (default: /tmp/web-control-screenshot.png)")
    p_ss.add_argument("--full-page", action="store_true", default=True, help="Capture full page (default)")
    p_ss.add_argument("--viewport-only", action="store_true", help="Capture viewport only")

    # content
    p_ct = subs.add_parser("content", help="Get text content of a tab")
    p_ct.add_argument("index", type=int, nargs="?", default=None, help="Tab index")
    p_ct.add_argument("--url", help="Match tab by URL substring")

    # enable
    p_en = subs.add_parser("enable", help="Enable CDP on Chrome")

    parsed = parser.parse_args()

    if parsed.command == "screenshot" and parsed.viewport_only:
        parsed.full_page = False

    handlers = {
        "status": cmd_status,
        "screenshot": cmd_screenshot,
        "content": cmd_content,
        "enable": cmd_enable,
    }

    if not parsed.command:
        parser.print_help()
        return 1

    return handlers[parsed.command](parsed)


if __name__ == "__main__":
    sys.exit(main() or 0)
