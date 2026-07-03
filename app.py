#!/usr/bin/env python3
"""
影视磁力链接搜索工具 - Web 版本
基于 mukaku_scraper.py 的 Flask Web 界面
"""

from flask import Flask, render_template, request, flash, Response, jsonify
import requests
import re
import time
import threading
from utils.mukaku_scraper import MukakuScraper
from utils.qbittorrent_client import QBittorrentClient
from utils.database import init_db, add_download_record, get_all_records, update_record_hash, update_record_status, get_active_magnet_urls, get_paginated_records, update_media_type, mark_jellyfin_synced
from utils.jellyfin_mover import move_to_jellyfin, detect_media_type
from utils.jellyfin_setup import init_jellyfin
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'mukaku-web-tool-2024'  # 用于 flash 消息

# 创建全局 scraper 实例，减少延迟以提高响应速度
scraper = MukakuScraper(delay=3, max_retries=3)
qb_client = QBittorrentClient()

# 初始化数据库
init_db()

# 在后台线程中初始化 Jellyfin（不阻塞 Flask 启动）
def _init_jellyfin_bg():
    try:
        init_jellyfin()
    except Exception as e:
        print(f"Jellyfin 初始化异常: {e}")

threading.Thread(target=_init_jellyfin_bg, daemon=True).start()


@app.route('/')
def index():
    """首页 - 搜索页面"""
    return render_template('search.html', results=None, query='')


@app.route('/search')
def search():
    """搜索影视"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    if not query:
        flash('请输入搜索关键词', 'warning')
        return render_template('search.html', results=None, query='')

    try:
        all_results = scraper.search(query)
        total = len(all_results)

        # 客户端分页
        start = (page - 1) * per_page
        end = start + per_page
        results = all_results[start:end]

        return render_template(
            'search.html',
            results=results,
            query=query,
            page=page,
            total=total,
            per_page=per_page
        )
    except Exception as e:
        flash(f'搜索失败: {str(e)}', 'danger')
        return render_template('search.html', results=None, query=query)


@app.route('/detail/<int:doub_id>')
def detail(doub_id):
    """获取影视详情和磁力链接"""
    try:
        magnet_data = scraper.get_magnets(doub_id)
        # 获取正在下载的磁力链接，用于禁用已添加的下载按钮
        active_magnets = set(get_active_magnet_urls())
        return render_template('detail.html', magnet_data=magnet_data, active_magnets=active_magnets)
    except Exception as e:
        flash(f'获取详情失败: {str(e)}', 'danger')
        return render_template('search.html', results=None, query='')


@app.route('/image-proxy')
def image_proxy():
    """图片代理，解决防盗链问题"""
    image_url = request.args.get('url', '')
    if not image_url:
        return Response(status=400)

    try:
        # 使用 scraper 的 headers 来获取图片
        headers = {
            'User-Agent': scraper.HEADERS['User-Agent'],
            'Referer': 'https://web5.mukaku.com/',
        }
        resp = requests.get(image_url, headers=headers, timeout=10)
        resp.raise_for_status()

        # 返回图片内容
        return Response(
            resp.content,
            content_type=resp.headers.get('Content-Type', 'image/jpeg'),
            headers={
                'Cache-Control': 'public, max-age=86400',  # 缓存 1 天
            }
        )
    except Exception as e:
        return Response(f'Image load failed: {str(e)}', status=500)


def _merge_with_qbittorrent(records):
    """将数据库记录与 qBittorrent 实时数据合并"""
    qb_torrents, err = qb_client.list_torrents()
    if err:
        qb_torrents = []

    downloads_data = []
    qb_hash_map = {t['hash']: t for t in qb_torrents}

    for record in records:
        download_info = {
            'record_id': record['id'],
            'doub_id': record['doub_id'],
            'title': record['title'],
            'year': record['year'],
            'image': record['image'],
            'episode_name': record['episode_name'],
            'quality': record['quality'],
            'file_size': record['file_size'],
            'magnet_url': record['magnet_url'],
            'added_at': record['added_at'],
            'status': record['status'],
            'completed_at': record['completed_at'],
            'torrent_hash': record['torrent_hash'],
            'media_type': record.get('media_type'),
            'jellyfin_synced': bool(record.get('jellyfin_synced', 0)),
        }

        # 只匹配正在进行中的记录，已删除/已完成的记录不再关联 qBittorrent
        if (record['torrent_hash']
                and record['status'] not in ('deleted', 'completed')
                and record['torrent_hash'] in qb_hash_map):
            qb_data = qb_hash_map[record['torrent_hash']]
            download_info.update({
                'progress': qb_data['progress'],
                'dlspeed': qb_data['dlspeed'],
                'upspeed': qb_data['upspeed'],
                'eta': qb_data['eta'],
                'size': qb_data['size'],
                'downloaded': qb_data['downloaded'],
                'qb_status': qb_data['state'],
                'is_active': True,
            })
            if qb_data['progress'] >= 100 and record['status'] != 'completed':
                update_record_status(record['id'], 'completed', datetime.now())
                download_info['status'] = 'completed'
        else:
            # 不在 qBittorrent 中了（被删除或已完成），或记录本身已是终态
            if record['status'] == 'downloading':
                # 之前在下载中但现在没了，说明被删除了
                update_record_status(record['id'], 'deleted')
                record['status'] = 'deleted'
            download_info.update({
                'progress': 100 if record['status'] == 'completed' else 0,
                'dlspeed': 0,
                'upspeed': 0,
                'eta': 0,
                'size': 0,
                'downloaded': 0,
                'qb_status': record['status'],
                'is_active': False,
            })

        downloads_data.append(download_info)

    return downloads_data


@app.route('/downloads')
def downloads():
    """下载管理页面"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', 'all')
    per_page = 20

    records, total = get_paginated_records(page=page, per_page=per_page, status=status)
    downloads_data = _merge_with_qbittorrent(records)

    return render_template(
        'downloads.html',
        downloads=downloads_data,
        page=page,
        total=total,
        per_page=per_page,
        current_status=status
    )


@app.route('/api/downloads')
def api_downloads():
    """下载数据 JSON API（用于 AJAX 局部刷新，支持分页）"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', 'all')
    per_page = 20

    records, total = get_paginated_records(page=page, per_page=per_page, status=status)
    downloads_data = _merge_with_qbittorrent(records)

    return jsonify({
        'downloads': downloads_data,
        'page': page,
        'total': total,
        'per_page': per_page
    })


@app.route('/api/add-torrent', methods=['POST'])
def add_torrent():
    """添加磁力链接到 qBittorrent 并创建数据库记录"""
    # 接收完整元数据
    magnet_url = request.form.get('magnet_url', '')
    doub_id = request.form.get('doub_id')
    title = request.form.get('title')
    year = request.form.get('year')
    image = request.form.get('image')
    episode_name = request.form.get('episode_name')
    quality = request.form.get('quality')
    file_size = request.form.get('file_size')

    if not magnet_url:
        return jsonify({'success': False, 'message': '无磁力链接'}), 400

    # 添加到 qBittorrent
    ok, err = qb_client.add_magnet(magnet_url)
    if not ok:
        return jsonify({'success': False, 'message': err}), 500

    # 创建数据库记录
    record_id = add_download_record(
        doub_id=int(doub_id) if doub_id else 0,
        title=title or '',
        year=year or '',
        image=image or '',
        episode_name=episode_name or '',
        quality=quality or '',
        magnet_url=magnet_url,
        file_size=file_size or ''
    )

    # 从磁力链接提取 info hash
    hash_match = re.search(r'btih:([a-fA-F0-9]{40})', magnet_url, re.IGNORECASE)
    if not hash_match:
        hash_match = re.search(r'xt=urn:btih:([a-zA-Z0-9]+)', magnet_url)
    magnet_hash = hash_match.group(1).lower() if hash_match else None

    # 等待 torrent 出现在 qBittorrent 列表中，然后匹配 hash
    torrent_hash = None
    for _ in range(5):
        time.sleep(1)
        torrents, _ = qb_client.list_torrents()
        if torrents:
            for torrent in torrents:
                # 直接匹配 hash
                if magnet_hash and torrent['hash'].lower() == magnet_hash:
                    torrent_hash = torrent['hash']
                    break
            if torrent_hash:
                break

    if torrent_hash:
        update_record_hash(record_id, torrent_hash)

    return jsonify({'success': True, 'message': '已添加到下载队列', 'record_id': record_id})


@app.route('/api/pause-torrent', methods=['POST'])
def pause_torrent():
    """暂停下载任务"""
    data = request.get_json()
    torrent_hash = data.get('hash', '')
    if not torrent_hash:
        return jsonify({'success': False, 'message': '无效的 hash'}), 400

    ok, err = qb_client.pause_torrent(torrent_hash)
    if ok:
        return jsonify({'success': True, 'message': '已暂停'})
    return jsonify({'success': False, 'message': err}), 500


@app.route('/api/resume-torrent', methods=['POST'])
def resume_torrent():
    """恢复下载任务"""
    data = request.get_json()
    torrent_hash = data.get('hash', '')
    if not torrent_hash:
        return jsonify({'success': False, 'message': '无效的 hash'}), 400

    ok, err = qb_client.resume_torrent(torrent_hash)
    if ok:
        return jsonify({'success': True, 'message': '已恢复'})
    return jsonify({'success': False, 'message': err}), 500


@app.route('/api/delete-torrent', methods=['POST'])
def delete_torrent():
    """删除下载任务"""
    data = request.get_json()
    torrent_hash = data.get('hash', '')
    delete_files = data.get('delete_files', False)

    if not torrent_hash:
        return jsonify({'success': False, 'message': '无效的 hash'}), 400

    ok, err = qb_client.delete_torrent(torrent_hash, delete_files)
    if ok:
        return jsonify({'success': True, 'message': '已删除'})
    return jsonify({'success': False, 'message': err}), 500


@app.route('/api/push-to-jellyfin', methods=['POST'])
def push_to_jellyfin():
    """推送已完成的下载到 Jellyfin 媒体库"""
    data = request.get_json()
    record_id = data.get('record_id')

    if not record_id:
        return jsonify({'success': False, 'message': '缺少 record_id'}), 400

    # 获取记录
    records = get_all_records()
    record = next((r for r in records if r['id'] == record_id), None)
    if not record:
        return jsonify({'success': False, 'message': '记录不存在'}), 404

    if record['status'] != 'completed':
        return jsonify({'success': False, 'message': '任务未完成，无法推送'}), 400

    if record.get('jellyfin_synced'):
        return jsonify({'success': False, 'message': '已推送到 Jellyfin'}), 400

    # 检测媒体类型并保存
    media_type = detect_media_type(record['episode_name'], record['title'])
    update_media_type(record_id, media_type)

    # 执行移动
    result = move_to_jellyfin(record)
    if result['success']:
        mark_jellyfin_synced(record_id)

    return jsonify(result)


if __name__ == '__main__':
    print("=" * 60)
    print("  影视磁力链接搜索工具 - Web 版")
    print("  访问: http://127.0.0.1:5000")
    print("  qBittorrent: http://127.0.0.1:8080")
    print("  Jellyfin: http://127.0.0.1:8096")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True, use_reloader=False)
