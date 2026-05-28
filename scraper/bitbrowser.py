import requests

BITBROWSER_BASE = "http://127.0.0.1:54345"


def create_window(
    name: str = "scraper",
    core_version: str = "118",
    proxy_method: int = 2,
    proxy_type: str = "socks5",
    host: str = "",
    port: int = 0,
    proxy_user: str = "",
    proxy_password: str = "",
) -> str:
    """创建新窗口（静态代理），返回窗口 ID。"""
    payload = {
        "name": name,
        "browserFingerPrint": {
            "coreVersion": core_version,
            "ostype": "PC",
            "os": "Win32",
            "osVersion": "11,10",
        },
        "proxyMethod": proxy_method,
        "proxyType": proxy_type,
        "host": host,
        "port": port,
        "proxyUserName": proxy_user,
        "proxyPassword": proxy_password,
    }
    resp = requests.post(f"{BITBROWSER_BASE}/browser/update", json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"BitBrowser create_window failed: {data}")
    return data["data"]["id"]


def create_window_dynamic_ip(
    name: str = "scraper",
    core_version: str = "118",
    dynamic_ip_url: str = "",
    ip_check_service: str = "ip123in",
    dynamic_ip_channel: str = "common",
    proxy_type: str = "socks5",
) -> str:
    """创建新窗口（动态 IP 提取链接），返回窗口 ID。"""
    payload = {
        "name": name,
        "browserFingerPrint": {
            "coreVersion": core_version,
            "ostype": "PC",
            "os": "Win32",
            "osVersion": "11,10",
        },
        "ipCheckService": ip_check_service,
        "proxyMethod": 3,
        "proxyType": proxy_type,
        "dynamicIpUrl": dynamic_ip_url,
        "dynamicIpChannel": dynamic_ip_channel,
        "isDynamicIpChangeIp": True,
    }
    resp = requests.post(f"{BITBROWSER_BASE}/browser/update", json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"BitBrowser create_window_dynamic_ip failed: {data}")
    return data["data"]["id"]


def open_browser(profile_id: str) -> str:
    """打开已有窗口，返回 CDP WebSocket 地址供 Playwright 连接。"""
    resp = requests.post(
        f"{BITBROWSER_BASE}/browser/open",
        json={"id": profile_id},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"BitBrowser open failed: {data}")
    return data["data"]["ws"]["selenium"]


def close_browser(profile_id: str) -> None:
    """关闭窗口，失败不抛出异常。"""
    try:
        requests.post(
            f"{BITBROWSER_BASE}/browser/close",
            json={"id": profile_id},
            timeout=10,
        )
    except Exception:
        pass


def delete_window(profile_id: str) -> None:
    """删除窗口（用于临时创建的窗口清理）。"""
    try:
        requests.post(
            f"{BITBROWSER_BASE}/browser/delete",
            json={"ids": [profile_id]},
            timeout=10,
        )
    except Exception:
        pass
