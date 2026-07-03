# 影视磁力链接搜索下载工具

一个集成了影视搜索、BT 下载和 Jellyfin 媒体库管理的 Web 应用。通过 Docker Compose 一键部署，实现从搜索到观影的完整流程。

## 功能特性

- 🔍 **影视搜索** - 搜索影视资源，查看详情和磁力链接
- ⬇️ **BT 下载** - 集成 qBittorrent，管理下载任务
- 🎬 **Jellyfin 集成** - 下载完成后一键推送到 Jellyfin 媒体库
- 🤖 **自动初始化** - Jellyfin 自动完成初始设置并创建媒体库
- 📱 **Web 界面** - 响应式设计，支持移动端访问

## 快速开始

### 1. 克隆项目

```bash
git clone <repository-url>
cd programme-downloader
```

### 2. 启动服务

```bash
docker compose up -d
```

首次启动会自动：
- 初始化 qBittorrent
- 初始化 Jellyfin（创建管理员账号、设置媒体库）
- 创建数据库

### 3. 访问服务

| 服务 | 地址 | 默认账号 | 默认密码 |
|------|------|----------|----------|
| Web 应用 | http://localhost:5001 | - | - |
| qBittorrent | http://localhost:8080 | admin | QyFd3vWvL |
| Jellyfin | http://localhost:8096 | admin | admin123 |

## 使用流程

1. **搜索影视** - 在首页输入影视名称搜索
2. **查看详情** - 点击搜索结果查看可用的磁力链接
3. **添加下载** - 选择合适的资源添加到 qBittorrent
4. **等待下载** - 在下载管理页面查看进度
5. **推送到 Jellyfin** - 下载完成后点击"推送到 Jellyfin"按钮
6. **观看影视** - 在 Jellyfin 中浏览和播放

## 配置说明

通过 `docker-compose.yml` 中的环境变量配置各项参数：

### qBittorrent 配置

```yaml
environment:
  - QB_HOST=http://qbittorrent:8080    # qBittorrent 地址
  - QB_USERNAME=admin                   # 用户名
  - QB_PASSWORD=QyFd3vWvL              # 密码
```

### Jellyfin 配置

```yaml
environment:
  - JELLYFIN_URL=http://jellyfin:8096  # Jellyfin 地址
  - JELLYFIN_USERNAME=admin             # 管理员用户名
  - JELLYFIN_PASSWORD=admin123          # 管理员密码
```

### 路径配置

```yaml
environment:
  - DOWNLOAD_DIR=/downloads             # 下载目录（容器内）
  - MEDIA_DIR=/media                    # 媒体根目录（容器内）
  - MOVIE_LIBRARY_PATH=/media/movies    # 电影库路径
  - TV_LIBRARY_PATH=/media/tvshows      # 电视剧库路径
```

### 卷挂载

```yaml
volumes:
  - ./downloads:/downloads              # 下载文件存储
  - ./data:/app/data                    # 数据库和配置
  - ./media:/media                      # Jellyfin 媒体库
  - ./qbittorrent_config:/config        # qBittorrent 配置
  - ./jellyfin_config:/config           # Jellyfin 配置
```

## 目录结构

```
.
├── app.py                      # Flask 主应用
├── docker-compose.yml          # Docker 编排配置
├── Dockerfile                  # Flask 应用镜像
├── requirements.txt            # Python 依赖
├── utils/
│   ├── database.py            # 数据库操作
│   ├── jellyfin_mover.py      # Jellyfin 文件移动和重命名
│   ├── jellyfin_setup.py      # Jellyfin 自动初始化
│   ├── mukaku_scraper.py      # 影视资源爬虫
│   └── qbittorrent_client.py  # qBittorrent API 客户端
└── templates/
    ├── base.html              # 基础模板
    ├── search.html            # 搜索页面
    ├── detail.html            # 详情页面
    ├── downloads.html         # 下载管理页面
    └── macros.html            # 分页宏定义
```

## 媒体文件组织

下载完成后推送到 Jellyfin 的文件会自动按以下结构组织：

**电影：**
```
media/movies/
└── 电影名称 (年份)/
    └── 电影名称 (年份).mkv
```

**电视剧：**
```
media/tvshows/
└── 剧集名称 (年份)/
    └── Season 01/
        ├── 剧集名称 - S01E01.mkv
        ├── 剧集名称 - S01E02.mkv
        └── ...
```

系统会自动识别：
- 中文格式：`第X集`、`全X集`、`第X季`
- 英文格式：`S01E01`、`Season 1`

## 常见问题

### 如何修改默认密码？

修改 `docker-compose.yml` 中对应的环境变量，然后重启：

```bash
docker compose down
docker compose up -d
```

**注意：** Jellyfin 密码修改后需要重置配置：

```bash
rm -rf ./jellyfin_config ./data/jellyfin_api_key
docker compose up -d
```

### 下载完成后如何推送到 Jellyfin？

在下载管理页面，找到已完成的任务，点击"推送到 Jellyfin"按钮。系统会：
1. 检测媒体类型（电影/电视剧）
2. 移动文件到对应的媒体库目录
3. 按 Jellyfin 规范重命名文件
4. 标记为已推送

### 如何重置 Jellyfin？

```bash
docker compose stop jellyfin
rm -rf ./jellyfin_config ./data/jellyfin_api_key
docker compose up -d jellyfin
```

### 如何查看日志？

```bash
# 查看所有服务日志
docker compose logs -f

# 查看特定服务日志
docker logs -f mukaku-web      # Flask 应用
docker logs -f qbittorrent     # qBittorrent
docker logs -f jellyfin        # Jellyfin
```

## 技术栈

- **后端** - Flask (Python 3.12)
- **数据库** - SQLite
- **下载** - qBittorrent (Web API)
- **媒体服务器** - Jellyfin
- **部署** - Docker Compose

## 开发

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export QB_HOST=http://localhost:8080
export QB_USERNAME=admin
export QB_PASSWORD=your_password
export JELLYFIN_URL=http://localhost:8096
export JELLYFIN_USERNAME=admin
export JELLYFIN_PASSWORD=admin123

# 启动应用
python app.py
```

### 构建镜像

```bash
docker compose build
```

## 许可证

MIT License
