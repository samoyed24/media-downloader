#!/usr/bin/env python3
"""
aria2 RPC 客户端封装
使用 aria2c 的 JSON-RPC 接口
"""

import requests
import os
import subprocess
import time
import threading


class Aria2Client:
    def __init__(self):
        self.download_path = os.getenv('DOWNLOAD_DIR', '/downloads')
        self.rpc_port = 6800
        self.rpc_secret = ''  # 可以设置密钥
        self.rpc_url = f'http://localhost:{self.rpc_port}/jsonrpc'
        self._ensure_aria2_running()

    def _ensure_aria2_running(self):
        """确保 aria2c 守护进程在运行"""
        # 检查是否已在运行
        try:
            resp = requests.post(self.rpc_url, json={
                'jsonrpc': '2.0',
                'id': '1',
                'method': 'aria2.getVersion',
                'params': [f'token:{self.rpc_secret}'] if self.rpc_secret else []
            }, timeout=2)
            if resp.status_code == 200:
                return
        except:
            pass

        # 启动 aria2c 守护进程
        try:
            os.makedirs(self.download_path, exist_ok=True)
            os.makedirs('/app/data', exist_ok=True)
            session_file = '/app/data/aria2_session.txt'
            if not os.path.exists(session_file):
                open(session_file, 'a').close()

            cmd = [
                'aria2c',
                f'--dir={self.download_path}',
                '--enable-rpc=true',
                f'--rpc-listen-port={self.rpc_port}',
                '--rpc-allow-origin-all=true',
                '--daemon=true',
                '--continue=true',
                '--seed-time=0',
                '--bt-stop-timeout=300',
                '--max-upload-limit=1K',
                '--file-allocation=none',
                '--disk-cache=16M',
                '--min-split-size=1M',
                '--split=16',
                '--max-connection-per-server=16',
                '--bt-max-peers=100',
                '--seed-ratio=0',
                f'--save-session={session_file}',
                '--save-session-interval=60',
                f'--input-file={session_file}',
            ]

            if self.rpc_secret:
                cmd.append(f'--rpc-secret={self.rpc_secret}')

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                print(f"aria2c 启动失败: {result.stderr}")
            time.sleep(2)  # 等待启动
        except Exception as e:
            print(f"启动 aria2c 异常: {e}")

    def _rpc_call(self, method, params=None):
        """调用 aria2 JSON-RPC"""
        params = params or []
        if self.rpc_secret:
            params.insert(0, f'token:{self.rpc_secret}')

        payload = {
            'jsonrpc': '2.0',
            'id': '1',
            'method': method,
            'params': params
        }

        try:
            resp = requests.post(self.rpc_url, json=payload, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            if 'error' in result:
                return None, result['error'].get('message', 'Unknown error')
            return result.get('result'), None
        except Exception as e:
            return None, str(e)

    def add_magnet(self, magnet_url, save_path=None):
        """添加磁力链接到下载队列"""
        if save_path is None:
            save_path = self.download_path

        options = {'dir': save_path}
        result, err = self._rpc_call('aria2.addUri', [[magnet_url], options])
        if err:
            return None, err
        return result, None

    def list_torrents(self):
        """获取所有下载任务列表"""
        # 获取活跃任务
        active_result, _ = self._rpc_call('aria2.tellActive')
        active = active_result or []

        # 获取等待中的任务
        waiting_result, _ = self._rpc_call('aria2.tellWaiting', [0, 1000])
        waiting = waiting_result or []

        # 获取已停止的任务
        stopped_result, _ = self._rpc_call('aria2.tellStopped', [0, 1000])
        stopped = stopped_result or []

        all_torrents = active + waiting + stopped

        torrents = []
        for t in all_torrents:
            # 计算总大小和已下载大小
            total_size = sum(int(f.get('length', 0)) for f in t.get('files', []))
            downloaded = sum(int(f.get('completedLength', 0)) for f in t.get('files', []))
            progress = (downloaded / total_size * 100) if total_size > 0 else 0

            # 获取文件名
            name = t.get('bittorrent', {}).get('info', {}).get('name')
            if not name and t.get('files'):
                name = t['files'][0].get('path', '').split('/')[-1]

            # 映射状态
            status = t.get('status', 'unknown')
            if status == 'active':
                state = 'downloading'
            elif status == 'waiting':
                state = 'waiting'
            elif status == 'paused':
                state = 'paused'
            elif status == 'complete':
                state = 'completed'
            elif status == 'error':
                state = 'error'
            else:
                state = status

            torrents.append({
                'hash': t.get('infoHash') or t.get('gid'),
                'name': name or 'Unknown',
                'size': total_size,
                'downloaded': downloaded,
                'progress': progress,
                'dlspeed': int(t.get('downloadSpeed', 0)),
                'upspeed': int(t.get('uploadSpeed', 0)),
                'eta': 0,
                'state': state,
                'gid': t.get('gid'),
            })

        return torrents, None

    def pause_torrent(self, gid):
        """暂停下载任务"""
        result, err = self._rpc_call('aria2.pause', [gid])
        if err:
            return False, err
        return True, None

    def resume_torrent(self, gid):
        """恢复下载任务"""
        result, err = self._rpc_call('aria2.unpause', [gid])
        if err:
            return False, err
        return True, None

    def delete_torrent(self, gid, delete_files=False):
        """删除下载任务"""
        # 先尝试移除活跃任务
        result, err = self._rpc_call('aria2.remove', [gid])
        if err:
            # 如果失败，尝试移除已停止的任务
            result, err = self._rpc_call('aria2.removeDownloadResult', [gid])
            if err:
                return False, err

        if delete_files:
            # 删除文件（简化处理）
            pass

        return True, None
