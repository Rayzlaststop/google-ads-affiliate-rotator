import os
import sys
import subprocess
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import yaml
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

# 确保 scraper 模块可以导入
sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-prod")

CONFIG_PATH = Path(__file__).parent.parent / "config" / "params.yaml"
SCRAPER_CONFIG_PATH = Path(__file__).parent.parent / "scraper" / "scraper_config.yaml"
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "")

# 采集任务状态（内存中，重启清空）
scraper_state = {
    "running": False,
    "last_run": None,       # ISO 时间字符串
    "last_status": None,    # "success" / "error"
    "last_log": "",
}
scraper_lock = threading.Lock()


# ── 工具函数 ──────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def load_scraper_config() -> dict:
    with open(SCRAPER_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_scraper_config(cfg: dict) -> None:
    with open(SCRAPER_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)


def get_current_index(params: list, start_time_str: str) -> int:
    if not params:
        return -1
    start_time = datetime.fromisoformat(start_time_str).replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    hours_elapsed = int((now - start_time).total_seconds() // 3600)
    return hours_elapsed % len(params)


def get_next_switch_seconds(params: list, start_time_str: str) -> int:
    if not params:
        return 0
    start_time = datetime.fromisoformat(start_time_str).replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    elapsed = (now - start_time).total_seconds()
    seconds_into_hour = elapsed % 3600
    return int(3600 - seconds_into_hour)


def get_github_last_commit() -> dict:
    try:
        from github import Github
        token = os.environ.get("GITHUB_TOKEN", "")
        cfg = load_scraper_config()
        repo_name = cfg.get("github_repo", "")
        if not token or not repo_name:
            return {}
        g = Github(token)
        repo = g.get_repo(repo_name)
        commit = repo.get_commits(path="config/params.yaml")[0]
        return {
            "sha": commit.sha[:7],
            "message": commit.commit.message.strip(),
            "date": commit.commit.author.date.isoformat(),
            "author": commit.commit.author.name,
        }
    except Exception as e:
        return {"error": str(e)}


def require_password(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if WEB_PASSWORD and not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


# ── 认证 ─────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if not WEB_PASSWORD:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        if request.form.get("password") == WEB_PASSWORD:
            session["authenticated"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "密码错误"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard"))


# ── 页面路由 ──────────────────────────────────────────────

@app.route("/")
@require_password
def dashboard():
    config = load_config()
    params = config.get("params", [])
    start_time = config.get("start_time", "2025-01-01T00:00:00")
    current_index = get_current_index(params, start_time)
    next_switch = get_next_switch_seconds(params, start_time)
    return render_template("dashboard.html",
        params=params,
        current_index=current_index,
        next_switch=next_switch,
        campaign_ids=config.get("campaign_ids", []),
        scraper_state=scraper_state,
        password_enabled=bool(WEB_PASSWORD),
    )


@app.route("/params")
@require_password
def params_page():
    config = load_config()
    params = config.get("params", [])
    start_time = config.get("start_time", "2025-01-01T00:00:00")
    current_index = get_current_index(params, start_time)
    return render_template("params.html",
        params=params,
        current_index=current_index,
        password_enabled=bool(WEB_PASSWORD),
    )


@app.route("/scraper")
@require_password
def scraper_page():
    cfg = load_scraper_config()
    return render_template("scraper.html",
        cfg=cfg,
        scraper_state=scraper_state,
        password_enabled=bool(WEB_PASSWORD),
    )


# ── 参数池 API ────────────────────────────────────────────

@app.route("/params/add", methods=["POST"])
@require_password
def add_param():
    value = request.form.get("param", "").strip()
    if value:
        config = load_config()
        config.setdefault("params", []).append(value)
        save_config(config)
    return redirect(url_for("params_page"))


@app.route("/params/delete/<int:idx>", methods=["POST"])
@require_password
def delete_param(idx: int):
    config = load_config()
    params = config.get("params", [])
    if 0 <= idx < len(params):
        params.pop(idx)
        config["params"] = params
        save_config(config)
    return redirect(url_for("params_page"))


@app.route("/params/reorder", methods=["POST"])
@require_password
def reorder_params():
    config = load_config()
    order = request.json.get("order", [])
    params = config.get("params", [])
    try:
        config["params"] = [params[i] for i in order]
        save_config(config)
    except (IndexError, TypeError):
        abort(400)
    return {"ok": True}


# ── 采集任务 API ──────────────────────────────────────────

def _run_scraper_bg():
    scraper_path = Path(__file__).parent.parent / "scraper" / "scraper.py"
    env = os.environ.copy()
    try:
        result = subprocess.run(
            [sys.executable, str(scraper_path)],
            capture_output=True, text=True, timeout=300, env=env,
        )
        log = result.stdout + result.stderr
        status = "success" if result.returncode == 0 else "error"
    except subprocess.TimeoutExpired:
        log = "采集超时（超过 5 分钟）"
        status = "error"
    except Exception as e:
        log = str(e)
        status = "error"

    with scraper_lock:
        scraper_state["running"] = False
        scraper_state["last_run"] = datetime.now(tz=timezone.utc).isoformat()
        scraper_state["last_status"] = status
        scraper_state["last_log"] = log


@app.route("/scraper/run", methods=["POST"])
@require_password
def scraper_run():
    with scraper_lock:
        if scraper_state["running"]:
            return jsonify({"ok": False, "msg": "采集任务正在运行中"}), 409
        scraper_state["running"] = True
        scraper_state["last_log"] = ""
    threading.Thread(target=_run_scraper_bg, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/scraper/status")
@require_password
def scraper_status():
    return jsonify(scraper_state)


@app.route("/scraper/config", methods=["POST"])
@require_password
def scraper_config_save():
    cfg = load_scraper_config()
    for key in ["bitbrowser_mode", "bitbrowser_profile_id", "search_engine",
                "search_query", "search_result_domain", "fallback_url",
                "target_path", "github_repo", "proxy_host", "proxy_port",
                "proxy_user", "dynamic_ip_url", "dynamic_ip_channel"]:
        val = request.form.get(key)
        if val is not None:
            cfg[key] = int(val) if key == "proxy_port" and val.isdigit() else val
    save_scraper_config(cfg)
    return redirect(url_for("scraper_page"))


# ── 状态 API ──────────────────────────────────────────────

@app.route("/api/rotation-status")
@require_password
def rotation_status():
    config = load_config()
    params = config.get("params", [])
    start_time = config.get("start_time", "2025-01-01T00:00:00")
    current_index = get_current_index(params, start_time)
    next_switch = get_next_switch_seconds(params, start_time)
    return jsonify({
        "total": len(params),
        "current_index": current_index,
        "current_param": params[current_index] if params else None,
        "next_switch_seconds": next_switch,
    })


@app.route("/api/github-status")
@require_password
def github_status():
    return jsonify(get_github_last_commit())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)
