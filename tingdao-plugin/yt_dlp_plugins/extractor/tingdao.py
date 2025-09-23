"""
Tingdao.org extractor for yt-dlp

This extractor supports downloading audio content from tingdao.org,
a Chinese Christian audio content website.

Author: Claude Code Assistant
License: Public Domain
"""

from datetime import datetime
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError, int_or_none, try_get


class TingdaoIE(InfoExtractor):
    """Extractor for tingdao.org audio content"""

    IE_NAME = 'tingdao'
    IE_DESC = 'tingdao.org audio content'

    _VALID_URL = r'https?://(?:www\.)?tingdao\.org/dist/#/Media\?.*?id=(?P<id>\d+)'

    _TESTS = [{
        'url': 'https://www.tingdao.org/dist/#/Media?device=mobile&id=11869',
        'info_dict': {
            'id': '11869',
            'title': '2018年10月 柏训师生会：神永远的旨意-基督与教会 01 于宏洁',
            'ext': 'mp3',
            'timestamp': 1585395926,
            'upload_date': '20200328',
            'uploader': '于宏洁',
            'uploader_id': '1190',
            'playlist': '2018年10月 柏训师生会：神永远的旨意-基督与教会（于宏洁）',
            'playlist_id': '1190',
            'playlist_index': 1,
            'playlist_title': '2018年10月 柏训师生会：神永远的旨意-基督与教会（于宏洁）',
            'duration': float,
        },
        'playlist_count': 8,
        'params': {
            'skip_download': True,
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
    }]

    def _real_extract(self, url):
        """Main extraction method"""
        media_id = self._match_id(url)

        # Call the exhibitions API with correct parameters
        exhibitions_data = self._download_json(
            'https://www.tingdao.org/Record/exhibitions',
            media_id,
            data=f'ypid={media_id}&userid='.encode(),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
            },
            note='Downloading playlist metadata',
            errnote='Failed to download playlist metadata'
        )

        # Check API response status
        if exhibitions_data.get('status') != 1:
            raise ExtractorError(
                f'API returned error status: {exhibitions_data.get("msg", "Unknown error")}',
                expected=True
            )

        # Extract data from correct JSON structure
        list_data = exhibitions_data.get('list', {})
        media_list = list_data.get('mediaList', [])
        author_info = list_data.get('authorMsg', {})

        if not media_list:
            raise ExtractorError('No media found in playlist', expected=True)

        # Build playlist entries
        current_entry = None
        playlist_entries = []

        for index, item in enumerate(media_list):
            entry_id = item.get('id')
            if not entry_id:
                continue

            # Build formats list with primary and backup sources
            formats = []

            # Primary audio source
            video_url = item.get('video_url')
            if video_url:
                formats.append({
                    'url': video_url,
                    'ext': 'mp3',
                    'quality': 1,
                    'format_id': 'primary',
                    'acodec': 'mp3',
                    'vcodec': 'none',
                    'abr': 128,  # Assume reasonable bitrate
                })

            # Backup audio source (if different from primary)
            videos_url = item.get('videos_url')
            if videos_url and videos_url != video_url:
                formats.append({
                    'url': videos_url,
                    'ext': 'mp3',
                    'quality': 0,
                    'format_id': 'backup',
                    'acodec': 'mp3',
                    'vcodec': 'none',
                    'abr': 128,
                })

            if not formats:
                self.report_warning(f'No audio URLs found for item {entry_id}')
                continue

            # Parse timestamp
            timestamp = self._parse_timestamp(item.get('add_time'))

            # Build entry info
            entry = {
                'id': entry_id,
                'title': item.get('title', '').strip(),
                'timestamp': timestamp,
                'uploader': author_info.get('author'),
                'uploader_id': author_info.get('id'),
                'playlist': author_info.get('title'),
                'playlist_id': author_info.get('id'),
                'playlist_index': index + 1,
                'playlist_title': author_info.get('title'),
                'ext': 'mp3',
            }

            # Add formats or single URL
            if len(formats) > 1:
                entry['formats'] = formats
            else:
                entry.update(formats[0])
                # Remove format-specific fields that shouldn't be in main entry
                for key in ['quality', 'format_id', 'acodec', 'vcodec', 'abr']:
                    entry.pop(key, None)

            playlist_entries.append(entry)

            # Track current requested media
            if entry_id == media_id:
                current_entry = entry

        # Return current entry if found, otherwise return playlist
        if current_entry:
            return current_entry

        # Return full playlist
        return {
            '_type': 'playlist',
            'id': author_info.get('id'),
            'title': author_info.get('title'),
            'description': author_info.get('jj'),
            'uploader': author_info.get('author'),
            'entries': playlist_entries,
        }

    def _parse_timestamp(self, time_str):
        """Parse timestamp from 'YYYY-MM-DD HH:MM:SS' format"""
        if not time_str:
            return None

        try:
            dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            return int(dt.timestamp())
        except (ValueError, TypeError) as e:
            self.report_warning(f'Failed to parse timestamp "{time_str}": {e}')
            return None