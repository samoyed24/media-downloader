import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'data' / 'downloads.db'


def init_db():
    """初始化数据库"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS download_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doub_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            year TEXT,
            image TEXT,
            episode_name TEXT NOT NULL,
            quality TEXT NOT NULL,
            magnet_url TEXT NOT NULL,
            file_size TEXT,
            torrent_hash TEXT,
            status TEXT DEFAULT 'downloading',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            last_synced_at TIMESTAMP
        )
    ''')

    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_doub_id ON download_records(doub_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON download_records(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_torrent_hash ON download_records(torrent_hash)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_added_at ON download_records(added_at)')

    # 迁移：添加 Jellyfin 相关字段
    try:
        cursor.execute('ALTER TABLE download_records ADD COLUMN media_type TEXT')
    except sqlite3.OperationalError:
        pass  # 字段已存在
    try:
        cursor.execute('ALTER TABLE download_records ADD COLUMN jellyfin_synced INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # 字段已存在

    conn.commit()
    conn.close()


def add_download_record(doub_id, title, year, image, episode_name, quality, magnet_url, file_size):
    """添加下载记录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO download_records
        (doub_id, title, year, image, episode_name, quality, magnet_url, file_size)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (doub_id, title, year, image, episode_name, quality, magnet_url, file_size))
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_all_records():
    """获取所有下载记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM download_records ORDER BY added_at DESC')
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return records


def get_active_magnet_urls():
    """获取所有正在进行中的下载磁力链接（不包括已删除和已完成的）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT magnet_url FROM download_records WHERE status NOT IN ('completed', 'deleted')")
    urls = [row[0] for row in cursor.fetchall()]
    conn.close()
    return urls


def update_record_hash(record_id, torrent_hash):
    """更新记录的 torrent hash"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE download_records
        SET torrent_hash = ?, last_synced_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (torrent_hash, record_id))
    conn.commit()
    conn.close()


def update_record_status(record_id, status, completed_at=None):
    """更新记录状态"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if completed_at:
        cursor.execute('''
            UPDATE download_records
            SET status = ?, completed_at = ?, last_synced_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, completed_at, record_id))
    else:
        cursor.execute('''
            UPDATE download_records
            SET status = ?, last_synced_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, record_id))
    conn.commit()
    conn.close()


def get_paginated_records(page=1, per_page=20, status=None):
    """分页获取下载记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    offset = (page - 1) * per_page

    if status and status != 'all':
        cursor.execute('SELECT COUNT(*) FROM download_records WHERE status = ?', (status,))
        total = cursor.fetchone()[0]
        cursor.execute(
            'SELECT * FROM download_records WHERE status = ? ORDER BY added_at DESC LIMIT ? OFFSET ?',
            (status, per_page, offset)
        )
    else:
        cursor.execute('SELECT COUNT(*) FROM download_records')
        total = cursor.fetchone()[0]
        cursor.execute(
            'SELECT * FROM download_records ORDER BY added_at DESC LIMIT ? OFFSET ?',
            (per_page, offset)
        )

    records = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return records, total


def update_media_type(record_id, media_type):
    """更新媒体类型"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE download_records
        SET media_type = ?, last_synced_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (media_type, record_id))
    conn.commit()
    conn.close()


def mark_jellyfin_synced(record_id):
    """标记已推送到 Jellyfin"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE download_records
        SET jellyfin_synced = 1, last_synced_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (record_id,))
    conn.commit()
    conn.close()
