#!/usr/bin/env python3
"""
Jellyfin 媒体库管理工具
负责将下载完成的文件移动到 Jellyfin 媒体库，并按规范重命名
"""

import re
import os
import shutil
from pathlib import Path

MEDIA_DIR = Path(os.getenv('MEDIA_DIR', '/media'))
DOWNLOAD_DIR = Path(os.getenv('DOWNLOAD_DIR', '/downloads'))
MOVIE_LIBRARY_PATH = os.getenv('MOVIE_LIBRARY_PATH', '/media/movies')
TV_LIBRARY_PATH = os.getenv('TV_LIBRARY_PATH', '/media/tvshows')


def detect_media_type(episode_name: str, title: str = '') -> str:
    """
    根据文件名判断媒体类型
    返回 'movie' 或 'tv'
    """
    text = f'{episode_name} {title}'

    # 剧集标识（中文）
    if re.search(r'第\d+集|全\d+集|第\d+季', text):
        return 'tv'

    # 剧集标识（英文）
    if re.search(r'S\d{1,2}E\d{1,3}|Season\s*\d+', text, re.IGNORECASE):
        return 'tv'

    # 独立季号标识：S01, S02（但排除 S01E01 这种完整格式，已在上面处理）
    if re.search(r'\bS\d{2}\b', text, re.IGNORECASE):
        return 'tv'

    return 'movie'


def extract_season_episode(episode_name: str) -> tuple:
    """
    从文件名提取季号和集号
    返回 (season, episode)，季号默认为 1，集号可能为 None
    """
    # 中文集号：第41集 → 41
    ep_match = re.search(r'第(\d+)集', episode_name)
    # 英文集号：E05 → 5
    if not ep_match:
        ep_match = re.search(r'E(\d{1,3})', episode_name, re.IGNORECASE)
    episode = int(ep_match.group(1)) if ep_match else None

    # 中文季号：第3季 → 3
    season_match = re.search(r'第(\d+)季', episode_name)
    # 英文季号：S01 → 1
    if not season_match:
        season_match = re.search(r'S(\d{1,2})', episode_name, re.IGNORECASE)
    season = int(season_match.group(1)) if season_match else 1

    return season, episode


def move_to_jellyfin(record: dict) -> dict:
    """
    将下载文件移动到 Jellyfin 媒体库
    record: 数据库记录字典，包含 episode_name, title, year 等
    """
    media_type = detect_media_type(record['episode_name'], record['title'])

    # 在 downloads 中定位文件（qBittorrent 以 torrent 名称创建文件夹）
    torrent_dir = DOWNLOAD_DIR / record['episode_name']

    if not torrent_dir.exists():
        # 尝试用 title 模糊匹配
        candidates = [d for d in DOWNLOAD_DIR.iterdir()
                      if d.is_dir() and record['title'] in d.name]
        if candidates:
            torrent_dir = candidates[0]
        else:
            return {'success': False, 'message': f'找不到下载文件: {record["episode_name"]}'}

    if media_type == 'movie':
        return _move_movie(record, torrent_dir)
    else:
        return _move_tv(record, torrent_dir)


def _move_movie(record: dict, source_dir: Path) -> dict:
    """移动电影到 Jellyfin"""
    title = record['title']
    year = record.get('year', '')
    folder_name = f'{title} ({year})' if year else title
    dest_dir = Path(MOVIE_LIBRARY_PATH) / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    video_files = [f for f in source_dir.rglob('*')
                   if f.is_file() and f.suffix.lower() in ('.mkv', '.mp4', '.avi', '.ts', '.iso')]

    if not video_files:
        return {'success': False, 'message': '没有找到视频文件'}

    moved = 0
    for f in video_files:
        dest_file = dest_dir / f'{folder_name}{f.suffix}'
        shutil.move(str(f), str(dest_file))
        moved += 1

    # 清理空目录
    _cleanup_empty_dirs(source_dir)

    return {'success': True, 'message': f'已移动 {moved} 个文件到 {dest_dir}'}


def _move_tv(record: dict, source_dir: Path) -> dict:
    """移动剧集到 Jellyfin"""
    title = record['title']
    year = record.get('year', '')
    folder_name = f'{title} ({year})' if year else title

    season, episode = extract_season_episode(record['episode_name'])
    season_folder = f'Season {season:02d}'
    dest_dir = Path(TV_LIBRARY_PATH) / folder_name / season_folder
    dest_dir.mkdir(parents=True, exist_ok=True)

    video_files = sorted([f for f in source_dir.rglob('*')
                          if f.is_file() and f.suffix.lower() in ('.mkv', '.mp4', '.avi', '.ts', '.iso')])

    if not video_files:
        return {'success': False, 'message': '没有找到视频文件'}

    moved = 0
    if len(video_files) > 1:
        # 整季打包：按文件名排序后编号 E01, E02, ...
        for idx, f in enumerate(video_files, 1):
            dest_file = dest_dir / f'{title} - S{season:02d}E{idx:02d}{f.suffix}'
            shutil.move(str(f), str(dest_file))
            moved += 1
    elif episode is not None:
        # 单集：使用提取的集号
        f = video_files[0]
        dest_file = dest_dir / f'{title} - S{season:02d}E{episode:02d}{f.suffix}'
        shutil.move(str(f), str(dest_file))
        moved += 1
    else:
        # 无法确定集号，保持原文件名
        f = video_files[0]
        dest_file = dest_dir / f.name
        shutil.move(str(f), str(dest_file))
        moved += 1

    # 清理空目录
    _cleanup_empty_dirs(source_dir)

    return {'success': True, 'message': f'已移动 {moved} 个文件到 {dest_dir}'}


def _cleanup_empty_dirs(source_dir: Path):
    """清理移动后留下的空目录"""
    try:
        # 从最深层开始删除空目录
        for dirpath, dirnames, filenames in os.walk(str(source_dir), topdown=False):
            if not filenames and not dirnames:
                Path(dirpath).rmdir()
        # 如果源目录本身也空了，删除它
        if source_dir.exists() and not any(source_dir.iterdir()):
            source_dir.rmdir()
    except Exception:
        pass  # 清理失败不影响主流程


# 需要导入 os 用于 walk
import os
