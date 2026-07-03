#!/usr/bin/env python3
"""
qBittorrent API 客户端封装
用于与 qBittorrent Web API 交互
"""

import qbittorrentapi
import os


class QBittorrentClient:
    def __init__(self):
        self.host = os.getenv('QB_HOST', 'http://localhost:8080')
        self.username = os.getenv('QB_USERNAME', 'admin')
        self.password = os.getenv('QB_PASSWORD', 'adminadmin')
        self.download_path = os.getenv('DOWNLOAD_DIR', '/downloads')
        self.client = None

    def connect(self):
        """连接到 qBittorrent"""
        try:
            self.client = qbittorrentapi.Client(
                host=self.host,
                username=self.username,
                password=self.password,
            )
            # 测试连接是否成功
            self.client.app_version()
            return True, None
        except Exception as e:
            return False, str(e)

    def add_magnet(self, magnet_url, save_path=None):
        """添加磁力链接到下载队列"""
        if save_path is None:
            save_path = self.download_path
        ok, err = self.connect()
        if not ok:
            return False, err
        try:
            self.client.torrents_add(urls=magnet_url, save_path=save_path)
            return True, None
        except Exception as e:
            return False, str(e)

    def list_torrents(self):
        """获取所有下载任务列表"""
        ok, err = self.connect()
        if not ok:
            return None, err
        try:
            torrents = self.client.torrents_info()
            return [{
                'hash': t.hash,
                'name': t.name,
                'size': t.size,
                'downloaded': int(t.size * t.progress),
                'progress': t.progress * 100,
                'dlspeed': t.dlspeed,
                'upspeed': t.upspeed,
                'eta': t.eta,
                'state': t.state,
                'added_on': t.added_on,
            } for t in torrents], None
        except Exception as e:
            return None, str(e)

    def pause_torrent(self, torrent_hash):
        """暂停下载任务"""
        ok, err = self.connect()
        if not ok:
            return False, err
        try:
            self.client.torrents_pause(torrent_hashes=torrent_hash)
            return True, None
        except Exception as e:
            return False, str(e)

    def resume_torrent(self, torrent_hash):
        """恢复下载任务"""
        ok, err = self.connect()
        if not ok:
            return False, err
        try:
            self.client.torrents_resume(torrent_hashes=torrent_hash)
            return True, None
        except Exception as e:
            return False, str(e)

    def delete_torrent(self, torrent_hash, delete_files=False):
        """删除下载任务"""
        ok, err = self.connect()
        if not ok:
            return False, err
        try:
            self.client.torrents_delete(
                torrent_hashes=torrent_hash,
                delete_files=delete_files
            )
            return True, None
        except Exception as e:
            return False, str(e)
