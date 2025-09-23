# yt-dlp-tingdao-plugin

yt-dlp 扩展器插件，用于下载 tingdao.org 网站的音频内容。

## 安装

使用 pip 安装：

```bash
pip install -e .
```

或者从本地目录安装：

```bash
python -m pip install -e /path/to/tingdao-plugin
```

## 支持的 URL 格式

```
https://www.tingdao.org/dist/#/Media?device=mobile&id=11869
https://www.tingdao.org/dist/#/Media?id=11868
```

## 功能特性

- ✅ 支持单个音频下载
- ✅ 支持完整播放列表下载（共8集）
- ✅ 备用音频源机制确保下载可靠性
- ✅ 完整元数据支持（标题、时间戳、作者等）
- ✅ 与 Metube 完全兼容
- ✅ 健壮的错误处理

## 使用方法

```bash
yt-dlp "https://www.tingdao.org/dist/#/Media?device=mobile&id=11869"
```

## 验证安装

```bash
yt-dlp --list-extractors | grep -i tingdao
```