from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


def extract_suffix(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.query:
        return parsed.query
    return None


def is_affiliate_link(url: str, patterns: list[str]) -> bool:
    return any(p in url for p in patterns)


def find_target_via_search(page, search_engine: str, query: str, domain: str, target_path: str) -> str | None:
    """通过搜索引擎查找目标页面 URL，返回找到的 URL 或 None。"""
    print(f"  搜索引擎: {search_engine}")
    print(f"  搜索词: {query}")

    # 导航到搜索引擎
    page.goto(search_engine, wait_until="domcontentloaded", timeout=15000)

    # 找到搜索框并输入
    search_box = (
        page.locator("input[name='q']").first          # Google
        or page.locator("input[name='q']").first       # Bing 也用 q
    )
    search_box.fill(query)
    search_box.press("Enter")
    page.wait_for_load_state("networkidle", timeout=15000)

    # 在搜索结果中找匹配目标域名的链接
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
    for href in hrefs:
        parsed = urlparse(href)
        if domain in parsed.netloc:
            # 如果指定了 target_path，拼接上去
            if target_path:
                return f"{parsed.scheme}://{parsed.netloc}{target_path}"
            return href

    return None


def extract_affiliate_params(
    cdp_ws_url: str,
    patterns: list[str],
    fallback_url: str,
    search_engine: str = "",
    search_query: str = "",
    search_result_domain: str = "",
    target_path: str = "",
) -> list[str]:
    found: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_ws_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()

        # Step 1: 确定目标 URL（先搜索，失败则用 fallback）
        target_url = fallback_url
        if search_engine and search_query and search_result_domain:
            print(f"  尝试通过搜索引擎定位目标页面...")
            try:
                found_url = find_target_via_search(
                    page, search_engine, search_query, search_result_domain, target_path
                )
                if found_url:
                    print(f"  搜索成功，目标: {found_url}")
                    target_url = found_url
                else:
                    print(f"  搜索结果未找到目标域名，使用 fallback: {fallback_url}")
            except Exception as e:
                print(f"  搜索失败（{e}），使用 fallback: {fallback_url}")

        # Step 2: 访问目标页面，拦截含联盟参数的响应 URL
        redirect_urls: list[str] = []

        def on_response(response):
            if is_affiliate_link(response.url, patterns):
                redirect_urls.append(response.url)

        page.on("response", on_response)
        print(f"  访问目标页面: {target_url}")
        page.goto(target_url, wait_until="networkidle", timeout=30000)

        # Step 3: 直接提取页面中含联盟参数的 href
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
        for href in hrefs:
            if is_affiliate_link(href, patterns):
                suffix = extract_suffix(href)
                if suffix:
                    found.append(suffix)

        # Step 4: 点击不含联盟参数的链接，捕获重定向后的联盟 URL
        clickable = [h for h in hrefs if not is_affiliate_link(h, patterns) and h.startswith("http")]
        for href in clickable[:20]:
            try:
                redirect_urls.clear()
                new_page = context.new_page()
                new_page.on("response", on_response)
                new_page.goto(href, wait_until="commit", timeout=10000)
                new_page.close()
                for url in redirect_urls:
                    suffix = extract_suffix(url)
                    if suffix:
                        found.append(suffix)
            except Exception:
                continue

        page.close()

    # 去重，保持顺序
    seen: set[str] = set()
    unique: list[str] = []
    for s in found:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique
