import os
import sys
from pathlib import Path

import yaml

# 确保同目录模块可以导入
sys.path.insert(0, str(Path(__file__).parent))

from bitbrowser import open_browser, close_browser, create_window, create_window_dynamic_ip, delete_window
from link_extractor import extract_affiliate_params
from github_updater import read_params, write_params, merge_params


def load_scraper_config() -> dict:
    config_path = Path(__file__).parent / "scraper_config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _open_window(cfg: dict) -> tuple[str, str]:
    """根据配置模式打开或创建 BitBrowser 窗口，返回 (profile_id, cdp_ws_url)。"""
    mode = cfg.get("bitbrowser_mode", "use_existing")

    if mode == "use_existing":
        profile_id = cfg["bitbrowser_profile_id"]
        cdp_ws_url = open_browser(profile_id)
        return profile_id, cdp_ws_url

    if mode == "create_static":
        profile_id = create_window(
            proxy_type=cfg.get("proxy_type", "socks5"),
            host=cfg["proxy_host"],
            port=cfg["proxy_port"],
            proxy_user=cfg.get("proxy_user", ""),
            proxy_password=cfg.get("proxy_password", ""),
        )
        cdp_ws_url = open_browser(profile_id)
        return profile_id, cdp_ws_url

    if mode == "create_dynamic":
        profile_id = create_window_dynamic_ip(
            proxy_type=cfg.get("proxy_type", "socks5"),
            dynamic_ip_url=cfg["dynamic_ip_url"],
            dynamic_ip_channel=cfg.get("dynamic_ip_channel", "common"),
        )
        cdp_ws_url = open_browser(profile_id)
        return profile_id, cdp_ws_url

    raise ValueError(f"未知的 bitbrowser_mode: {mode}")


def main() -> None:
    cfg = load_scraper_config()
    patterns = cfg["affiliate_patterns"]
    repo_name = cfg["github_repo"]
    file_path = cfg["params_file_path"]
    mode = cfg.get("bitbrowser_mode", "use_existing")
    is_temp_window = mode != "use_existing"

    print(f"[1/5] 打开 BitBrowser 窗口（模式: {mode}）")
    profile_id, cdp_ws_url = _open_window(cfg)
    print(f"      profile_id: {profile_id}")
    print(f"      CDP endpoint: {cdp_ws_url}")

    try:
        print("[2/5] 定位并访问目标页面")
        suffixes = extract_affiliate_params(
            cdp_ws_url=cdp_ws_url,
            patterns=patterns,
            fallback_url=cfg["fallback_url"],
            search_engine=cfg.get("search_engine", ""),
            search_query=cfg.get("search_query", ""),
            search_result_domain=cfg.get("search_result_domain", ""),
            target_path=cfg.get("target_path", ""),
        )
        print(f"      共找到 {len(suffixes)} 个联盟参数")

        if not suffixes:
            print("      未找到任何联盟参数，退出。")
            return

        print("[3/5] 读取 GitHub 上的 params.yaml")
        config, sha = read_params(repo_name, file_path)

        print("[4/5] 合并新参数")
        updated_config, added_count = merge_params(config, suffixes)

        if added_count == 0:
            print("      所有参数均已存在，无需更新。")
            return

        print(f"      新增 {added_count} 组，跳过 {len(suffixes) - added_count} 组重复")

        print("[5/5] 提交更新到 GitHub")
        write_params(repo_name, file_path, updated_config, sha, added_count)
        print("      完成！")

    finally:
        print("关闭 BitBrowser 窗口")
        close_browser(profile_id)
        if is_temp_window:
            delete_window(profile_id)


if __name__ == "__main__":
    main()
