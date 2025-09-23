# yt-dlp 扩展器开发完整指南

本文档基于 tingdao.org 扩展器的成功开发经验，提供了一套完整的 yt-dlp 扩展器开发和 Metube 集成方案。

## 📋 目录

1. [项目概述](#项目概述)
2. [技术架构](#技术架构)
3. [开发流程](#开发流程)
4. [实现细节](#实现细节)
5. [Metube 集成](#metube-集成)
6. [部署方案](#部署方案)
7. [故障排除](#故障排除)
8. [通用模板](#通用模板)

## 🎯 项目概述

### 功能目标
- 为 yt-dlp 添加新网站支持
- 与 Metube Web 界面无缝集成
- 支持单个视频和播放列表下载
- 完整的元数据提取和错误处理

### 成功案例：tingdao.org
- **网站类型**: 中文基督教音频内容网站
- **API 架构**: REST API with POST 请求
- **内容格式**: MP3 音频文件
- **特殊功能**: 主要和备用音频源、播放列表支持

## 🏗️ 技术架构

### 核心组件
```
yt-dlp 扩展器
├── 插件包 (yt_dlp_plugins)
│   └── extractor/
│       └── 自定义扩展器.py
├── 配置文件 (setup.cfg, pyproject.toml)
├── Metube 集成修改
└── 环境配置
```

### 技术栈
- **Python 3.7+**
- **yt-dlp 2025.09.05+**
- **Metube** (aiohttp + Socket.IO)
- **正则表达式** (URL 匹配)
- **JSON API 处理**

## 🚀 开发流程

### 阶段 1: 网站分析和 API 调研

#### 1.1 网站结构分析
```bash
# 使用浏览器开发者工具分析
# 1. URL 模式识别
# 2. 网络请求监控
# 3. API 端点发现
# 4. 数据结构分析
```

#### 1.2 API 接口调研
```python
# 测试 API 调用
import requests

# 发现正确的 API 端点
api_url = "https://example.com/api/endpoint"
data = {'param': 'value'}
response = requests.post(api_url, data=data)
```

#### 1.3 数据结构映射
```json
// 分析 API 响应结构
{
  "status": 1,
  "list": {
    "mediaList": [...],
    "authorMsg": {...}
  }
}
```

### 阶段 2: 插件开发

#### 2.1 项目结构创建
```bash
# 按照 yt-dlp 官方规范创建目录
mkdir -p your-plugin/yt_dlp_plugins/extractor
```

#### 2.2 配置文件设置
**setup.cfg**:
```ini
[metadata]
name = yt-dlp-yoursite-plugin
version = 1.0.0
description = yt-dlp extractor plugin for yoursite.com
author = Your Name
license = Public Domain

[options]
packages = find_namespace:
python_requires = >=3.7
```

**pyproject.toml**:
```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "yt-dlp-yoursite-plugin"
version = "1.0.0"
description = "yt-dlp extractor plugin for yoursite.com"
authors = [{name = "Your Name"}]
license = {text = "Public Domain"}
requires-python = ">=3.7"
```

#### 2.3 扩展器代码实现

**关键实现要点**:

1. **类命名规范**: 必须以 `IE` 结尾
2. **URL 匹配**: 使用正则表达式精确匹配
3. **API 调用**: 正确的请求头和参数
4. **数据提取**: 完整的元数据处理
5. **错误处理**: 优雅的异常处理
6. **格式支持**: 主要和备用源处理

### 阶段 3: Metube 集成

#### 3.1 修改 Metube 配置支持
**app/main.py** 添加插件目录配置:
```python
_DEFAULTS = {
    # ... 其他配置
    'YTDL_PLUGINS_DIR': '',
    # ...
}
```

#### 3.2 修改下载引擎支持插件
**app/ytdl.py** 添加插件加载逻辑:
```python
# 在 YoutubeDL 参数中添加插件目录
if (self.manager and
    hasattr(self.manager, 'config') and
    hasattr(self.manager.config, 'YTDL_PLUGINS_DIR') and
    self.manager.config.YTDL_PLUGINS_DIR):
    import glob
    plugin_dirs = glob.glob(f"{self.manager.config.YTDL_PLUGINS_DIR}/*")
    plugin_dirs = [d for d in plugin_dirs if os.path.isdir(d)]
    if plugin_dirs:
        params['plugin_dirs'] = plugin_dirs
```

### 阶段 4: 测试和验证

#### 4.1 插件安装测试
```bash
# 安装插件包
cd your-plugin
pip install -e .

# 验证插件加载
export PYTHONPATH="/path/to/your-plugin"
yt-dlp --list-extractors | grep yoursite
```

#### 4.2 功能测试
```bash
# 命令行测试
yt-dlp "https://yoursite.com/video/123" --dump-json

# 实际下载测试
yt-dlp "https://yoursite.com/video/123"
```

#### 4.3 Metube 集成测试
```bash
# 启动 Metube 服务器
export PYTHONPATH="/path/to/your-plugin"
pipenv run python3 app/main.py

# 浏览器测试 Web 界面
# http://localhost:8081
```

## 📝 实现细节

### 通用扩展器模板

```python
"""
YourSite.com extractor for yt-dlp

This extractor supports downloading content from yoursite.com

Author: Your Name
License: Public Domain
"""

from datetime import datetime
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError, int_or_none, try_get


class YourSiteIE(InfoExtractor):
    """Extractor for yoursite.com content"""

    IE_NAME = 'yoursite'
    IE_DESC = 'yoursite.com content'

    _VALID_URL = r'https?://(?:www\.)?yoursite\.com/video/(?P<id>\d+)'

    _TESTS = [{
        'url': 'https://www.yoursite.com/video/123',
        'info_dict': {
            'id': '123',
            'title': 'Test Video',
            'ext': 'mp4',
            # 添加更多测试数据
        },
        'params': {
            'skip_download': True,
        }
    }]

    def _real_extract(self, url):
        """Main extraction method"""
        video_id = self._match_id(url)

        # 调用 API 获取视频信息
        video_data = self._download_json(
            'https://api.yoursite.com/video',
            video_id,
            data=f'id={video_id}'.encode(),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (compatible; yt-dlp)',
                'Accept': 'application/json',
            },
            note='Downloading video metadata',
            errnote='Failed to download video metadata'
        )

        # 检查 API 响应
        if video_data.get('status') != 'success':
            raise ExtractorError(
                f'API returned error: {video_data.get("message", "Unknown error")}',
                expected=True
            )

        # 提取视频信息
        video_info = video_data.get('data', {})

        # 构建格式列表
        formats = []

        # 主要视频源
        if video_info.get('video_url'):
            formats.append({
                'url': video_info['video_url'],
                'format_id': 'primary',
                'quality': 1,
            })

        # 备用视频源
        if video_info.get('backup_url'):
            formats.append({
                'url': video_info['backup_url'],
                'format_id': 'backup',
                'quality': 0,
            })

        if not formats:
            raise ExtractorError('No video URLs found', expected=True)

        # 解析时间戳
        timestamp = self._parse_timestamp(video_info.get('upload_time'))

        return {
            'id': video_id,
            'title': video_info.get('title', '').strip(),
            'timestamp': timestamp,
            'uploader': video_info.get('uploader'),
            'formats': formats,
        }

    def _parse_timestamp(self, time_str):
        """解析时间戳"""
        if not time_str:
            return None

        try:
            # 根据实际格式调整
            dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            return int(dt.timestamp())
        except (ValueError, TypeError) as e:
            self.report_warning(f'Failed to parse timestamp "{time_str}": {e}')
            return None
```

### API 调用最佳实践

#### 1. 请求头配置
```python
headers = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://yoursite.com/',
    'Origin': 'https://yoursite.com',
}
```

#### 2. 参数处理
```python
# POST 数据编码
data = f'param1={value1}&param2={value2}'.encode()

# GET 参数
params = {'param1': value1, 'param2': value2}
```

#### 3. 错误处理
```python
# API 状态检查
if api_response.get('status') != 1:
    raise ExtractorError(
        f'API error: {api_response.get("msg", "Unknown error")}',
        expected=True
    )

# 数据验证
if not media_list:
    raise ExtractorError('No media found', expected=True)
```

### 格式处理策略

#### 1. 多源支持
```python
formats = []

# 主要源
if primary_url:
    formats.append({
        'url': primary_url,
        'format_id': 'primary',
        'quality': 1,
        'ext': 'mp4',
    })

# 备用源
if backup_url and backup_url != primary_url:
    formats.append({
        'url': backup_url,
        'format_id': 'backup',
        'quality': 0,
        'ext': 'mp4',
    })
```

#### 2. 音频专用处理
```python
formats.append({
    'url': audio_url,
    'ext': 'mp3',
    'acodec': 'mp3',
    'vcodec': 'none',
    'abr': 128,
    'format_id': 'audio',
})
```

## 🔧 Metube 集成

### 服务器启动配置

#### 环境变量方式
```bash
export PYTHONPATH="/path/to/your-plugin"
pipenv run python3 app/main.py
```

#### Docker 方式
```yaml
# docker-compose.yml
services:
  metube:
    image: alexta69/metube
    environment:
      - YTDL_PLUGINS_DIR=/app/plugins
    volumes:
      - "./downloads:/downloads"
      - "./plugins:/app/plugins"
```

### 修改清单

#### 1. 配置系统修改 (app/main.py)
```python
# 添加插件目录配置项
_DEFAULTS = {
    # ... 现有配置
    'YTDL_PLUGINS_DIR': '',
}
```

#### 2. 下载引擎修改 (app/ytdl.py)
```python
# 在 _download 方法中添加插件支持
if (self.manager and
    hasattr(self.manager, 'config') and
    hasattr(self.manager.config, 'YTDL_PLUGINS_DIR') and
    self.manager.config.YTDL_PLUGINS_DIR):
    # 插件目录处理逻辑
```

#### 3. 信息提取修改 (app/ytdl.py)
```python
# 在 __extract_info 方法中添加插件支持
if (hasattr(self.config, 'YTDL_PLUGINS_DIR') and
    self.config.YTDL_PLUGINS_DIR):
    # 插件目录处理逻辑
```

## 📦 部署方案

### 方案 1: 开发环境部署
```bash
# 1. 创建插件包
mkdir -p your-plugin/yt_dlp_plugins/extractor

# 2. 安装插件
cd your-plugin
pip install -e .

# 3. 设置环境变量
export PYTHONPATH="/path/to/your-plugin"

# 4. 启动 Metube
pipenv run python3 app/main.py
```

### 方案 2: 生产环境部署
```bash
# 1. 构建插件包
python setup.py sdist bdist_wheel

# 2. 安装到系统
pip install dist/yt-dlp-yoursite-plugin-1.0.0.tar.gz

# 3. 配置 Metube
# 设置相应的环境变量或配置文件
```

### 方案 3: Docker 容器化部署
```dockerfile
# Dockerfile 扩展
FROM alexta69/metube

# 复制插件
COPY plugins/ /app/plugins/

# 设置环境变量
ENV PYTHONPATH="/app/plugins"
```

## 🛠️ 故障排除

### 常见问题和解决方案

#### 1. 插件未被识别

**症状**: `Unsupported URL` 或 `Falling back on generic information extractor`

**解决方法**:
```bash
# 检查插件安装
pip list | grep yoursite

# 检查环境变量
echo $PYTHONPATH

# 验证插件目录结构
ls -la your-plugin/yt_dlp_plugins/extractor/

# 测试直接安装
pipenv run python -c "import yt_dlp_plugins.extractor.yoursite"
```

#### 2. API 调用失败

**症状**: `Failed to download metadata` 或 HTTP 错误

**解决方法**:
```python
# 调试 API 调用
import requests
response = requests.post(api_url, data=data, headers=headers)
print(response.status_code, response.text)

# 检查请求头
# 检查参数格式
# 验证网站 API 变化
```

#### 3. 元数据提取错误

**症状**: 标题为空或时间戳解析失败

**解决方法**:
```python
# 调试数据结构
print(json.dumps(api_response, indent=2, ensure_ascii=False))

# 检查字段映射
# 验证数据类型转换
```

#### 4. Metube 集成问题

**症状**: Web 界面下载失败或进程错误

**解决方法**:
```bash
# 检查 Metube 日志
docker logs metube_container

# 验证插件目录映射
# 检查环境变量设置
# 测试进程间通信
```

### 调试技巧

#### 1. 详细日志输出
```bash
# 启用详细模式
yt-dlp --verbose "https://yoursite.com/video/123"

# 启用调试模式
yt-dlp --debug "https://yoursite.com/video/123"
```

#### 2. JSON 输出调试
```bash
# 仅提取元数据
yt-dlp --dump-json "https://yoursite.com/video/123"

# 检查插件加载
yt-dlp --verbose --list-extractors | grep yoursite
```

#### 3. Python 调试
```python
# 直接测试扩展器
from yt_dlp_plugins.extractor.yoursite import YourSiteIE
extractor = YourSiteIE()
result = extractor.extract("https://yoursite.com/video/123")
```

## 📋 开发检查清单

### 开发阶段
- [ ] 网站 API 调研完成
- [ ] URL 正则表达式测试通过
- [ ] 数据结构映射正确
- [ ] 错误处理完善
- [ ] 测试用例编写

### 集成阶段
- [ ] 插件目录结构正确
- [ ] 配置文件格式正确
- [ ] Metube 修改完成
- [ ] 环境变量设置正确

### 测试阶段
- [ ] 命令行测试通过
- [ ] Metube Web 界面测试通过
- [ ] 元数据提取正确
- [ ] 下载功能正常
- [ ] 错误处理验证

### 部署阶段
- [ ] 生产环境配置
- [ ] 性能测试
- [ ] 监控设置
- [ ] 文档更新

## 🔮 最佳实践总结

### 1. 开发原则
- **遵循官方规范**: 严格按照 yt-dlp 插件开发标准
- **完整测试覆盖**: 包含单元测试和集成测试
- **优雅错误处理**: 提供清晰的错误信息
- **性能优化**: 避免不必要的网络请求

### 2. 代码质量
- **清晰命名**: 使用描述性的变量和函数名
- **完整注释**: 解释复杂的业务逻辑
- **模块化设计**: 将功能拆分为可复用的方法
- **安全考虑**: 验证输入数据和 API 响应

### 3. 维护策略
- **版本控制**: 使用语义化版本号
- **变更记录**: 维护详细的 CHANGELOG
- **监控告警**: 设置 API 变化监控
- **用户反馈**: 建立问题反馈渠道

## 📚 参考资源

### 官方文档
- [yt-dlp Plugin Development](https://github.com/yt-dlp/yt-dlp/wiki/Plugin-Development)
- [yt-dlp Sample Plugins](https://github.com/yt-dlp/yt-dlp-sample-plugins)
- [yt-dlp Developer Instructions](https://github.com/yt-dlp/yt-dlp/blob/master/CONTRIBUTING.md#developer-instructions)

### 技术资源
- [Python setuptools 文档](https://setuptools.pypa.io/)
- [正则表达式测试工具](https://regex101.com/)
- [JSON 格式化工具](https://jsonformatter.org/)

### 相关项目
- [Metube 项目](https://github.com/alexta69/metube)
- [yt-dlp 主项目](https://github.com/yt-dlp/yt-dlp)

---

通过本指南，您可以为任何网站开发 yt-dlp 扩展器并与 Metube 完美集成。记住始终遵循官方标准，进行充分测试，并保持代码的可维护性。