"""Browser-backed HTML fetching for scraper providers."""

from __future__ import annotations

from pathlib import Path


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def fetch_rendered_html(
    url: str,
    *,
    timeout: float = 15.0,
    locale: str = "fr-MA",
    wait_for_selector: str = "a[href]",
) -> tuple[str, str]:
    """Fetch a page after browser rendering and return ``(html, final_url)``."""

    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await _launch_browser(playwright)
        try:
            page = await browser.new_page(
                user_agent=BROWSER_USER_AGENT,
                locale=locale,
                viewport={"width": 1366, "height": 900},
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            try:
                await page.wait_for_load_state("networkidle", timeout=7000)
            except PlaywrightTimeoutError:
                pass
            if wait_for_selector:
                try:
                    await page.wait_for_selector(wait_for_selector, timeout=7000)
                except PlaywrightTimeoutError:
                    pass
            return await page.content(), page.url
        finally:
            await browser.close()


async def _launch_browser(playwright):
    try:
        return await playwright.chromium.launch(headless=True)
    except Exception as first_error:
        for executable_path in _local_browser_paths():
            try:
                return await playwright.chromium.launch(
                    headless=True,
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
