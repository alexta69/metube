#!/usr/bin/env python3
"""
Tingdao.org extractor for yt-dlp
Final version with all technical corrections applied
"""

from datetime import datetime
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError


class TingdaoIE(InfoExtractor):
    IE_NAME = 'tingdao'
    _VALID_URL = r'https?://(?:www\.)?tingdao\.org/dist/#/Media\?.*?id=(?P<id>\d+)'

    _TESTS = [{
        'url': 'https://www.tingdao.org/dist/#/Media?device=mobile&id=11869',
        'info_dict': {
            'id': '11869',
            'title': '2018年10月 柏训师生会：神永远的旨意-基督与教会 01 于宏洁',
            'ext': 'mp3',
            'timestamp': 1585395926,  # 修正：正确的时间戳
            'upload_date': '20200328',
            'uploader': '于宏洁',
            'playlist': '2018年10月 柏训师生会：神永远的旨意-基督与教会（于宏洁）',
            'playlist_id': '1190',
            'playlist_index': 1,
        },
        'playlist_count': 8,
        'playlist_title': '2018年10月 柏训师生会：神永远的旨意-基督与教会（于宏洁）',
        'params': {
            'skip_download': True,  # 适合CI环境
        }
    }, {
        'url': 'https://www.tingdao.org/dist/#/Media?device=mobile&id=11868',
        'info_dict': {
            'id': '11868',
            'title': '2018年10月 柏训师生会：神永远的旨意-基督与教会 02 于宏洁',
            'ext': 'mp3',
            'playlist_index': 2,
            'uploader': '于宏洁',
        },
        'playlist_count': 8,
        'params': {
            'skip_download': True,
        }
    }, {
        # 仅URL匹配测试
        'url': 'https://www.tingdao.org/dist/#/Media?device=mobile&id=11934',
        'only_matching': True,
    }]

    def _real_extract(self, url):
        media_id = self._match_id(url)

        # 修正：使用正确的API参数 ypid 而非 id
        exhibitions_data = self._download_json(
            'https://www.tingdao.org/Record/exhibitions',
            media_id,
            data=f'ypid={media_id}&userid='.encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            note='Downloading playlist metadata'
        )

        if exhibitions_data.get('status') != 1:
            raise ExtractorError('Failed to get playlist data', expected=True)

        # 修正：正确的JSON结构解析 list.mediaList
        media_list = exhibitions_data['list']['mediaList']
        author_info = exhibitions_data['list']['authorMsg']

        if not media_list:
            raise ExtractorError('No media found in playlist', expected=True)

        # 构建播放列表条目
        current_entry = None
        playlist_entries = []

        for index, item in enumerate(media_list):
            # 修正：正确的formats处理，避免None值
            formats = []

            # 主要音频源
            formats.append({
                'url': item['video_url'],
                'ext': 'mp3',
                'quality': 1,
                'format_id': 'primary',
                'acodec': 'mp3',
                'vcodec': 'none',
            })

            # 备用音频源（如果不同）
            if item['videos_url'] and item['videos_url'] != item['video_url']:
                formats.append({
                    'url': item['videos_url'],
                    'ext': 'mp3',
                    'quality': 0,
                    'format_id': 'backup',
                    'acodec': 'mp3',
                    'vcodec': 'none',
                })

            entry = {
                'id': item['id'],
                'title': item['title'],
                'timestamp': self._parse_timestamp(item['add_time']),  # 修正：正确时间戳解析
                'uploader': author_info.get('author'),
                'uploader_id': author_info.get('id'),
                'playlist': author_info['title'],
                'playlist_id': author_info['id'],
                'playlist_index': index + 1,
                'playlist_title': author_info['title'],
                'ext': 'mp3',
            }

            # 修正：只在有多个格式时才设置formats字段，避免None值
            if len(formats) > 1:
                entry['formats'] = formats
            else:
                entry['url'] = formats[0]['url']

            playlist_entries.append(entry)

            # 找到当前请求的音频
            if item['id'] == media_id:
                current_entry = entry

        # 如果找到特定音频，返回该音频（包含播放列表上下文）
        if current_entry:
            return current_entry

        # 否则返回整个播放列表
        return {
            '_type': 'playlist',
            'id': author_info['id'],
            'title': author_info['title'],
            'description': author_info.get('jj'),
            'uploader': author_info.get('author'),
            'entries': playlist_entries,
        }

    def _parse_timestamp(self, time_str):
        """修正：正确的时间戳解析，转换为秒级整数"""
        try:
            dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            return int(dt.timestamp())
        except (ValueError, TypeError):
            return None


# 本地测试代码
if __name__ == '__main__':
    # 模拟测试环境
    import sys
    import json
    from unittest.mock import MagicMock, patch

    # 创建模拟的InfoExtractor基类
    class MockInfoExtractor:
        def _match_id(self, url):
            import re
            match = re.search(r'id=(\d+)', url)
            return match.group(1) if match else None

        def _download_json(self, url, video_id, data=None, headers=None, note=None):
            # 模拟API响应
            if 'exhibitions' in url:
                return {
                    "status": 1,
                    "list": {
                        "mediaList": [{
                            "id": "11869",
                            "title": "2018年10月 柏训师生会：神永远的旨意-基督与教会 01 于宏洁",
                            "video_url": "http://example.com/audio1.mp3",
                            "videos_url": "http://example.com/audio1_backup.mp3",
                            "add_time": "2020-03-28 19:45:26",
                            "img_url": "",
                            "mp4_url": ""
                        }],
                        "authorMsg": {
                            "id": "1190",
                            "title": "2018年10月 柏训师生会：神永远的旨意-基督与教会（于宏洁）",
                            "author": "于宏洁",
                            "jj": "2018年10月 柏训师生会：神永远的旨意-基督与教会（于宏洁）"
                        }
                    }
                }
            return {}

    # 继承模拟基类进行测试
    class TestTingdaoIE(MockInfoExtractor, TingdaoIE):
        pass

    # 运行测试
    ie = TestTingdaoIE()
    test_url = 'https://www.tingdao.org/dist/#/Media?device=mobile&id=11869'

    try:
        result = ie._real_extract(test_url)
        print("✅ 提取成功!")
        print(f"ID: {result.get('id')}")
        print(f"标题: {result.get('title')}")
        print(f"时间戳: {result.get('timestamp')}")
        print(f"播放列表: {result.get('playlist')}")
        print(f"格式数量: {len(result.get('formats', [result.get('url')] if result.get('url') else []))}")

    except Exception as e:
        print(f"❌ 提取失败: {e}")
        import traceback
        traceback.print_exc()