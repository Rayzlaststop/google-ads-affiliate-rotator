import os
import base64
import yaml
from github import Github, GithubException


def _get_client() -> Github:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN 环境变量未设置")
    return Github(token)


def read_params(repo_name: str, file_path: str) -> tuple[dict, str]:
    """返回 (config_dict, file_sha)"""
    g = _get_client()
    repo = g.get_repo(repo_name)
    content_file = repo.get_contents(file_path)
    raw = base64.b64decode(content_file.content).decode("utf-8")
    return yaml.safe_load(raw), content_file.sha


def write_params(repo_name: str, file_path: str, config: dict, sha: str, new_count: int) -> None:
    g = _get_client()
    repo = g.get_repo(repo_name)
    new_content = yaml.dump(config, allow_unicode=True, default_flow_style=False)
    repo.update_file(
        path=file_path,
        message=f"scraper: add {new_count} new affiliate param(s)",
        content=new_content,
        sha=sha,
    )


def merge_params(config: dict, new_suffixes: list[str]) -> tuple[dict, int]:
    """将新参数追加到 config，返回 (updated_config, added_count)"""
    existing = set(config.get("params") or [])
    to_add = [s for s in new_suffixes if s not in existing]
    if to_add:
        config.setdefault("params", []).extend(to_add)
    return config, len(to_add)
