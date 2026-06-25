"""Browser-backed HTML fetching for scraper providers."""

from __future__ import annotations

from pathlib import Path

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
"""

CHROMIUM_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
]


async def fetch_scrape_html(
    url: str,
    *,
    timeout: float = 30.0,
    locale: str = "fr-MA",
    wait_for_selector: str = "a[href]",
) -> tuple[str, str]:
    """Fetch a page with Playwright (real browser rendering)."""
    return await fetch_rendered_html(
        url,
        timeout=timeout,
        locale=locale,
        wait_for_selector=wait_for_selector,
    )


async def fetch_rendered_html(
    url: str,
    *,
    timeout: float = 30.0,
    locale: str = "fr-MA",
    wait_for_selector: str = "a[href]",
) -> tuple[str, str]:
    """Fetch a page after browser rendering and return ``(html, final_url)``."""

    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright

    navigation_timeout_ms = max(int(timeout * 1000), 5_000)
    async with async_playwright() as playwright:
        browser = await _launch_browser(playwright)
        try:
            context = await browser.new_context(
                user_agent=BROWSER_USER_AGENT,
                locale=locale,
                viewport={"width": 1366, "height": 900},
                extra_http_headers={
                    "Accept-Language": f"{locale},fr;q=0.9,en;q=0.8",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            page = await context.new_page()
            await page.add_init_script(STEALTH_INIT_SCRIPT)
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=navigation_timeout_ms,
            )
            try:
                await page.wait_for_load_state("networkidle", timeout=min(10_000, navigation_timeout_ms))
            except PlaywrightTimeoutError:
                pass
            if wait_for_selector:
                try:
                    await page.wait_for_selector(wait_for_selector, timeout=min(10_000, navigation_timeout_ms))
                except PlaywrightTimeoutError:
                    pass
            return await page.content(), page.url
        finally:
            await browser.close()


async def _launch_browser(playwright):
    launch_kwargs = {
        "headless": True,
        "args": CHROMIUM_LAUNCH_ARGS,
        "ignore_default_args": ["--enable-automation"],
    }
    try:
        return await playwright.chromium.launch(**launch_kwargs)
    except Exception as first_error:
        for executable_path in _local_browser_paths():
            try:
                return await playwright.chromium.launch(
                    **launch_kwargs,
                    executable_path=str(executable_path),
                )
            except Exception:
                continue
        raise first_error


def _local_browser_paths() -> list[Path]:
    return [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
