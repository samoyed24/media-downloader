#!/usr/bin/env python3
"""
qBittorrent 自动初始化脚本
在 Flask 应用启动时运行，自动设置 WebUI 密码
"""

import os
import requests
import time
import subprocess


QB_HOST = os.getenv('QB_HOST', 'http://localhost:8080')
QB_USERNAME = os.getenv('QB_USERNAME', 'admin')
QB_PASSWORD = os.getenv('QB_PASSWORD', 'adminadmin')


def log(msg):
    """打印日志（强制刷新，确保 Docker 日志可见）"""
    print(f"[qBittorrent 初始化] {msg}", flush=True)


def wait_for_qbittorrent(timeout=120):
    """等待 qBittorrent 服务就绪"""
    log(f"等待 qBittorrent 启动 ({QB_HOST})...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # 尝试访问公开端点（不需要认证的）
            resp = requests.get(f'{QB_HOST}/api/v2/app/version', timeout=5)
            # 200 表示无需认证，403 表示需要认证但服务已就绪
            if resp.status_code in (200, 403):
                log("qBittorrent 服务已就绪")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    log("等待 qBittorrent 超时")
    return False


def test_login(username, password):
    """测试登录凭据是否有效"""
    try:
        resp = requests.post(
            f'{QB_HOST}/api/v2/auth/login',
            data={'username': username, 'password': password},
            timeout=10
        )
        # 200 或 204 都表示成功
        if resp.status_code in (200, 204):
            return True
    except Exception:
        pass
    return False


def get_temp_password_from_logs():
    """从 Docker 日志中提取临时密码"""
    log("尝试从日志读取临时密码...")
    try:
        # 尝试使用 docker logs 命令
        result = subprocess.run(
            ['docker', 'logs', 'qbittorrent', '--tail', '50'],
            capture_output=True,
            text=True,
            timeout=10
        )
        logs = result.stdout + result.stderr

        # 查找临时密码
        # 格式: "The WebUI administrator password was not set. A temporary password is provided for this session: XXXXX"
        import re
        match = re.search(r'temporary password.*?:\s*([A-Za-z0-9]+)', logs, re.IGNORECASE)
        if match:
            temp_password = match.group(1)
            log(f"找到临时密码: {temp_password}")
            return temp_password
    except Exception as e:
        log(f"读取日志失败: {e}")

    return None


def set_password(username, new_password):
    """设置 qBittorrent WebUI 密码"""
    log(f"设置 WebUI 密码 (用户: {username})...")

    # 创建会话
    session = requests.Session()

    try:
        # 先尝试用当前配置的凭据登录
        if not test_login(username, new_password):
            # 如果新密码不行，尝试临时密码
            temp_password = get_temp_password_from_logs()
            if not temp_password or not test_login(username, temp_password):
                log("无法登录 qBittorrent，跳过密码设置")
                return False

            log("使用临时密码登录成功")

        # 登录
        resp = session.post(
            f'{QB_HOST}/api/v2/auth/login',
            data={'username': username, 'password': new_password if test_login(username, new_password) else temp_password},
            timeout=10
        )

        if resp.status_code not in (200, 204):
            log("登录失败")
            return False

        # 设置新密码
        import json
        prefs = json.dumps({
            'web_ui_username': username,
            'web_ui_password': new_password
        })

        resp = session.post(
            f'{QB_HOST}/api/v2/app/setPreferences',
            data={'json': prefs},
            timeout=10
        )

        if resp.status_code == 200:
            log("密码设置成功")
            return True
        else:
            log(f"设置密码失败: HTTP {resp.status_code}")
            return False

    except Exception as e:
        log(f"设置密码异常: {e}")
        return False


def init_qbittorrent():
    """主初始化流程"""
    log("=" * 50)
    log("qBittorrent 自动初始化")
    log("=" * 50)

    # 等待服务就绪
    if not wait_for_qbittorrent(timeout=120):
        log("qBittorrent 初始化失败：服务未就绪")
        return False

    # 测试当前凭据是否有效
    if test_login(QB_USERNAME, QB_PASSWORD):
        log("当前凭据有效，无需初始化")
        log(f"访问: {QB_HOST}")
        log(f"用户名: {QB_USERNAME}")
        log("=" * 50)
        return True

    log("当前凭据无效，尝试自动设置密码...")

    # 尝试设置密码
    if set_password(QB_USERNAME, QB_PASSWORD):
        # 验证新密码
        time.sleep(1)
        if test_login(QB_USERNAME, QB_PASSWORD):
            log("密码设置成功")
            log(f"访问: {QB_HOST}")
            log(f"用户名: {QB_USERNAME}")
            log(f"密码: {QB_PASSWORD}")
            log("=" * 50)
            return True
        else:
            log("密码验证失败")
            return False
    else:
        # 无法自动设置密码，提供手动设置指引
        log("无法自动设置密码")
        log("")
        log("请手动设置 qBittorrent 密码：")
        log("1. 查看临时密码：docker logs qbittorrent --tail 20")
        log(f"2. 访问 {QB_HOST} 并使用临时密码登录")
        log(f"3. 在设置中修改密码为：{QB_PASSWORD}")
        log("=" * 50)
        return False


if __name__ == '__main__':
    init_qbittorrent()
