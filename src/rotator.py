import os
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path

# 支持本地调试时从 google-ads.yaml 加载凭证
if Path("credentials/google-ads.yaml").exists():
    os.environ.setdefault("GOOGLE_ADS_CONFIGURATION_FILE_PATH", "credentials/google-ads.yaml")

from ads_client import load_client, update_campaign_suffix


def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "params.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_current_param(params: list, start_time_str: str) -> tuple[str, int]:
    start_time = datetime.fromisoformat(start_time_str).replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    hours_elapsed = int((now - start_time).total_seconds() // 3600)
    index = hours_elapsed % len(params)
    return params[index], index


def main() -> None:
    config = load_config()
    params = config["params"]
    campaign_ids = config["campaign_ids"]
    customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "")

    if not customer_id:
        print("ERROR: GOOGLE_ADS_LOGIN_CUSTOMER_ID is not set", file=sys.stderr)
        sys.exit(1)

    current_param, index = get_current_param(params, config["start_time"])
    print(f"[{datetime.now(tz=timezone.utc).isoformat()}] Using param group {index + 1}/{len(params)}:")
    print(f"  {current_param}")

    client = load_client()

    for campaign_id in campaign_ids:
        update_campaign_suffix(client, customer_id, campaign_id, current_param)

    print("Done.")


if __name__ == "__main__":
    main()
