#!/usr/bin/env python3
"""
Jellyfin 自动初始化和媒体库配置脚本
在 Flask 应用启动时运行，自动完成 Jellyfin 初始设置
"""

import time
import sys
import requests
import os

JELLYFIN_URL = os.getenv('JELLYFIN_URL', 'http://jellyfin:8096')
JELLYFIN_USERNAME = os.getenv('JELLYFIN_USERNAME', 'admin')
JELLYFIN_PASSWORD = os.getenv('JELLYFIN_PASSWORD', 'admin123')
MOVIE_LIBRARY_PATH = os.getenv('MOVIE_LIBRARY_PATH', '/media/movies')
TV_LIBRARY_PATH = os.getenv('TV_LIBRARY_PATH', '/media/tvshows')

# 强制 unbuffered 输出，确保 Docker 日志可见
_print = print
def log(msg):
    _print(msg, flush=True)

CLIENT_HEADER = 'MediaBrowser Client="Jellyfin Setup", Device="Script", DeviceId="init", Version="1.0"'

AUTH_PROVIDER = 'Jellyfin.Server.Implementations.Users.DefaultAuthenticationProvider'
PASSWORD_RESET_PROVIDER = 'Jellyfin.Server.Implementations.Users.DefaultPasswordResetProvider'


def wait_for_jellyfin_basic(timeout=120):
    """等待 Jellyfin 基本服务就绪"""
    log(f"等待 Jellyfin 启动 ({JELLYFIN_URL})...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            resp = requests.get(f'{JELLYFIN_URL}/System/Info/Public', timeout=5)
            if resp.status_code == 200:
                log("Jellyfin 服务已就绪")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    log("等待 Jellyfin 超时")
    return False


def wait_for_startup_api(timeout=60):
    """等待启动向导 API 可用（返回 JSON）"""
    log("等待启动向导 API...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            resp = requests.get(f'{JELLYFIN_URL}/Startup/Configuration', timeout=5)
            if resp.status_code == 200 and resp.headers.get('Content-Type', '').startswith('application/json'):
                log("启动向导 API 已就绪")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    log("等待启动向导 API 超时")
    return False


def is_jellyfin_initialized():
    """检查 Jellyfin 是否已完成初始化"""
    try:
        resp = requests.get(f'{JELLYFIN_URL}/System/Info/Public', timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('StartupWizardCompleted', False)
        return False
    except Exception:
        return False


def authenticate(username, password):
    """通过用户名密码获取 API Key"""
    try:
        resp = requests.post(
            f'{JELLYFIN_URL}/Users/AuthenticateByName',
            json={'Username': username, 'Pw': password},
            headers={'X-Emby-Authorization': CLIENT_HEADER},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get('AccessToken'), resp.json().get('User', {}).get('Id')
    except Exception as e:
        log(f"认证失败 ({username}): {e}")
    return None, None


def complete_initial_setup():
    """完成 Jellyfin 初始设置"""
    log("开始 Jellyfin 初始设置...")

    # 1. 设置服务器配置
    config_data = {
        "ServerName": "Media Server",
        "UICulture": "zh-CN",
        "MetadataCountryCode": "CN",
        "PreferredSubtitleLanguage": "chi",
        "EnableRemoteAccess": False
    }
    try:
        resp = requests.post(
            f'{JELLYFIN_URL}/Startup/Configuration',
            json=config_data,
            timeout=10
        )
        log(f"设置服务器配置: {resp.status_code}")
    except Exception as e:
        log(f"设置服务器配置失败: {e}")
        return False

    # 2. 通过 /Startup/User 创建初始管理员用户
    #    这是 Jellyfin 启动向导专用的端点，不需要认证
    #    注意：设置配置后端点可能暂时不可用，需要先检查并确保就绪
    try:
        # 先检查端点是否可用（GET 请求会"唤醒"端点）
        for attempt in range(5):
            check_resp = requests.get(f'{JELLYFIN_URL}/Startup/User', timeout=10)
            if check_resp.status_code == 200:
                log(f"启动向导用户端点就绪")
                break
            log(f"等待用户端点就绪... (尝试 {attempt + 1}/5)")
            time.sleep(2)
        else:
            log("用户端点始终不可用")
            return False

        time.sleep(1)  # 再等待一下确保稳定

        resp = requests.post(
            f'{JELLYFIN_URL}/Startup/User',
            json={
                'Name': JELLYFIN_USERNAME,
                'Password': JELLYFIN_PASSWORD
            },
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        log(f"创建管理员用户 '{JELLYFIN_USERNAME}': {resp.status_code}")
        if resp.status_code not in (200, 204):
            log(f"创建用户失败: {resp.text[:200]}")
            return False
    except Exception as e:
        log(f"创建用户失败: {e}")
        return False

    # 3. 用新创建的用户登录，获取 API Key
    time.sleep(1)
    api_key, user_id = authenticate(JELLYFIN_USERNAME, JELLYFIN_PASSWORD)
    if not api_key:
        log("新用户认证失败")
        return False
    log(f"认证成功，API Key: {api_key[:20]}...")

    # 4. 设置管理员策略（确保有完整权限）
    try:
        resp = requests.post(
            f'{JELLYFIN_URL}/Users/{user_id}/Policy',
            json={
                'IsAdministrator': True,
                'EnableAllFolders': True,
                'EnableAllDevices': True,
                'EnableAllChannels': True,
                'AuthenticationProviderId': AUTH_PROVIDER,
                'PasswordResetProviderId': PASSWORD_RESET_PROVIDER
            },
            headers={
                'X-Emby-Token': api_key,
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        log(f"设置管理员权限: {resp.status_code}")
    except Exception as e:
        log(f"设置管理员权限失败 (非致命): {e}")

    # 5. 完成启动向导
    try:
        resp = requests.post(
            f'{JELLYFIN_URL}/Startup/Complete',
            timeout=10
        )
        log(f"完成启动向导: {resp.status_code}")
    except Exception as e:
        log(f"完成启动向导失败: {e}")

    # 6. 保存 API Key
    save_api_key(api_key)
    return True


def save_api_key(api_key):
    """保存 API Key 到文件"""
    try:
        os.makedirs('/app/data', exist_ok=True)
        with open('/app/data/jellyfin_api_key', 'w') as f:
            f.write(api_key)
        log("API Key 已保存")
    except Exception as e:
        log(f"保存 API Key 失败: {e}")


def load_api_key():
    """从文件加载 API Key"""
    try:
        with open('/app/data/jellyfin_api_key', 'r') as f:
            return f.read().strip()
    except Exception:
        return None


def get_auth_headers():
    """获取认证头"""
    api_key = load_api_key()
    if not api_key:
        api_key, _ = authenticate(JELLYFIN_USERNAME, JELLYFIN_PASSWORD)
        if api_key:
            save_api_key(api_key)

    if api_key:
        return {
            'X-Emby-Token': api_key,
            'Content-Type': 'application/json'
        }
    return {}


def create_media_library(name, path, collection_type):
    """创建媒体库"""
    headers = get_auth_headers()
    if not headers:
        log("无法获取认证，跳过创建媒体库")
        return False

    library_body = {
        "PathInfos": [{"Path": path}],
        "RefreshMode": "Default",
        "EnableRealtimeMonitor": True
    }

    try:
        # name 和 collectionType 必须作为查询参数传递
        resp = requests.post(
            f'{JELLYFIN_URL}/Library/VirtualFolders',
            params={'name': name, 'collectionType': collection_type},
            json=library_body,
            headers=headers,
            timeout=30
        )
        log(f"创建媒体库 '{name}' ({collection_type}): {resp.status_code}")
        return resp.status_code in (200, 204)
    except Exception as e:
        log(f"创建媒体库失败: {e}")
        return False


def setup_media_libraries():
    """设置媒体库"""
    log("设置媒体库...")

    headers = get_auth_headers()
    if not headers:
        log("无法获取认证，跳过创建媒体库")
        return

    # 获取现有媒体库
    existing_names = set()
    try:
        resp = requests.get(
            f'{JELLYFIN_URL}/Library/VirtualFolders',
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            existing = resp.json()
            existing_names = {lib.get('Name') for lib in existing}
            log(f"现有媒体库: {list(existing_names)}")
    except Exception:
        pass

    # 创建电影库（如果不存在）
    if '电影' not in existing_names:
        create_media_library(
            name='电影',
            path=MOVIE_LIBRARY_PATH,
            collection_type='movies'
        )
    else:
        log("电影库已存在，跳过")

    # 创建剧集库（如果不存在）
    if '电视剧' not in existing_names:
        create_media_library(
            name='电视剧',
            path=TV_LIBRARY_PATH,
            collection_type='tvshows'
        )
    else:
        log("电视剧库已存在，跳过")


def init_jellyfin():
    """主初始化流程"""
    log("=" * 50)
    log("Jellyfin 自动初始化")
    log("=" * 50)

    # 先等待基本服务就绪
    if not wait_for_jellyfin_basic(timeout=120):
        log("Jellyfin 初始化失败：服务未就绪")
        return False

    # 检查是否已初始化（在等待启动 API 之前检查）
    initialized = is_jellyfin_initialized()
    log(f"Jellyfin 向导状态: {'已完成' if initialized else '未完成'}")

    if initialized:
        log("Jellyfin 已初始化，跳过初始设置")
        # 即使已初始化，也确保 API Key 存在
        if not load_api_key():
            api_key, _ = authenticate(JELLYFIN_USERNAME, JELLYFIN_PASSWORD)
            if api_key:
                save_api_key(api_key)
    else:
        # 等待启动向导 API 可用
        if not wait_for_startup_api(timeout=60):
            log("启动向导 API 未就绪")
            return False

        if not complete_initial_setup():
            log("Jellyfin 初始设置失败")
            return False

    # 等待服务完全就绪
    time.sleep(3)
    setup_media_libraries()

    log("Jellyfin 初始化完成")
    log(f"访问: {JELLYFIN_URL}")
    log(f"用户名: {JELLYFIN_USERNAME}")
    log(f"密码: {JELLYFIN_PASSWORD}")
    log("=" * 50)
    return True


if __name__ == '__main__':
    init_jellyfin()
