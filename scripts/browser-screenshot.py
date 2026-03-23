#!/usr/bin/env python3
"""Take a screenshot of a URL or the current Chrome tab via CDP."""
import sys
import subprocess
import json

def screenshot_url(url: str, output: str = "/tmp/screenshot.png"):
    """Use playwright to screenshot a URL via CDP connection to Chrome."""
    script = f"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        # Find existing page with this URL, or open new one
        contexts = browser.contexts
        page = None
        for ctx in contexts:
            for pg in ctx.pages:
                if "{url}" in pg.url:
                    page = pg
                    break
            if page:
                break

        if not page:
            # Open the URL in a new tab
            context = contexts[0] if contexts else await browser.new_context()
            page = await context.new_page()
            await page.goto("{url}", wait_until="networkidle")

        await page.screenshot(path="{output}", full_page=True)
        print(f"Screenshot saved to {output}")
        # Don't close — it's the user's browser

asyncio.run(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stdout, end="")


def screenshot_active_tab(output: str = "/tmp/screenshot.png"):
    """Screenshot whatever tab is currently active."""
    script = f"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        contexts = browser.contexts
        if not contexts or not contexts[0].pages:
            print("No pages found")
            return
        # Last page is usually the active one
        page = contexts[0].pages[-1]
        await page.screenshot(path="{output}", full_page=True)
        print(f"Screenshot of '{{page.title()}}' saved to {output}")

asyncio.run(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stdout, end="")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
        output = sys.argv[2] if len(sys.argv) > 2 else "/tmp/screenshot.png"
        screenshot_url(url, output)
    else:
        screenshot_active_tab()
