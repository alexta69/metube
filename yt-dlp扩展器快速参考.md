# yt-dlp 扩展器快速参考

基于 tingdao.org 成功案例的快速开发指南

## 🚀 快速开始

### 1. 创建插件结构
```bash
mkdir -p your-plugin/yt_dlp_plugins/extractor
cd your-plugin
```

### 2. 配置文件
**setup.cfg**:
```ini
[metadata]
name = yt-dlp-yoursite-plugin
version = 1.0.0

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
requires-python = ">=3.7"
```

### 3. 扩展器模板
```python
# yt_dlp_plugins/extractor/yoursite.py
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError

class YourSiteIE(InfoExtractor):
    IE_NAME = 'yoursite'
    _VALID_URL = r'https?://(?:www\.)?yoursite\.com/video/(?P<id>\d+)'

    def _real_extract(self, url):
        video_id = self._match_id(url)

        # API 调用
        data = self._download_json(
            'https://api.yoursite.com/video',
            video_id,
            data=f'id={video_id}'.encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        return {
            'id': video_id,
            'title': data.get('title'),
            'url': data.get('video_url'),
        }
```

## 📦 Metube 集成

### 修改 app/main.py
```python
_DEFAULTS = {
    # ... 现有配置
    'YTDL_PLUGINS_DIR': '',
}
```

### 修改 app/ytdl.py
```python
# 在 YoutubeDL 参数中添加
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

## 🧪 测试和部署

### 安装测试
```bash
# 安装插件
pip install -e .

# 测试加载
export PYTHONPATH="/path/to/your-plugin"
yt-dlp --list-extractors | grep yoursite
```

### 功能测试
```bash
# 提取信息
yt-dlp --dump-json "https://yoursite.com/video/123"

# 实际下载
yt-dlp "https://yoursite.com/video/123"
```

### Metube 测试
```bash
# 启动服务器
export PYTHONPATH="/path/to/your-plugin"
pipenv run python3 app/main.py

# 访问 http://localhost:8081 测试
```

## 🔧 常见问题

### 插件未识别
```bash
# 检查环境变量
echo $PYTHONPATH

# 验证插件导入
python -c "import yt_dlp_plugins.extractor.yoursite"
```

### API 调用失败
```python
# 调试 API
import requests
response = requests.post(api_url, data=data, headers=headers)
print(response.status_code, response.text)
```

### Metube 集成问题
```bash
# 检查日志
docker logs metube_container

# 验证插件目录
ls -la /path/to/plugins/
```

## 📋 检查清单

- [ ] URL 正则表达式正确
- [ ] API 调用成功
- [ ] 元数据提取正确
- [ ] 错误处理完善
- [ ] 插件目录结构正确
- [ ] Metube 修改完成
- [ ] 环境变量设置
- [ ] 命令行测试通过
- [ ] Web 界面测试通过

## 🎯 关键成功因素

1. **严格遵循 yt-dlp 官方规范**
2. **正确设置 PYTHONPATH 环境变量**
3. **完整的 API 调研和测试**
4. **优雅的错误处理机制**
5. **充分的集成测试验证**

---

基于 tingdao.org 案例的经验总结，遵循此指南可快速开发任何网站的 yt-dlp 扩展器。