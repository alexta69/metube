import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import music_meta


class SplitArtistsTests(unittest.TestCase):
    def test_splits_database_separators(self):
        self.assertEqual(music_meta.split_artists('A & B feat. C'), ['A', 'B', 'C'])
        self.assertEqual(music_meta.split_artists('X, Y; Z'), ['X', 'Y', 'Z'])
        self.assertEqual(music_meta.split_artists('Solo ft. Guest'), ['Solo', 'Guest'])

    def test_handles_empty(self):
        self.assertEqual(music_meta.split_artists(None), [])
        self.assertEqual(music_meta.split_artists(''), [])


class SplitListTests(unittest.TestCase):
    def test_ampersand_survives_user_lists(self):
        self.assertEqual(music_meta.split_list('Hootie & the Blowfish, R&B'), ['Hootie & the Blowfish', 'R&B'])

    def test_semicolons_and_whitespace(self):
        self.assertEqual(music_meta.split_list(' a ;b, c '), ['a', 'b', 'c'])


class SanitizePartTests(unittest.TestCase):
    def test_strips_filesystem_specials(self):
        self.assertEqual(music_meta.sanitize_part('AC/DC: Live? *<1980>*', 'x'), 'AC DC Live 1980')

    def test_falls_back_when_empty(self):
        self.assertEqual(music_meta.sanitize_part('...', 'Unknown Artist'), 'Unknown Artist')
        self.assertEqual(music_meta.sanitize_part(None, 'Unknown'), 'Unknown')

    def test_caps_length(self):
        self.assertLessEqual(len(music_meta.sanitize_part('x' * 300, 'y')), 80)


class OrganizedRelPathTests(unittest.TestCase):
    def test_artist_album_year_layout(self):
        rel = music_meta.organized_rel_path(['Volbeat'], 'Rewind, Replay, Rebound', '2019-08-02', 'Last Day Under the Sun', '.opus')
        self.assertEqual(rel, os.path.join(
            'Volbeat', 'Rewind, Replay, Rebound(2019)',
            'Volbeat - Rewind, Replay, Rebound(2019) - Last Day Under the Sun.opus'))

    def test_fallbacks(self):
        rel = music_meta.organized_rel_path([], None, None, None, '.mp3')
        self.assertEqual(rel, os.path.join(
            'Unknown Artist', 'Unknown Album', 'Unknown Artist - Unknown Album - Unknown.mp3'))


class BuildTagsTests(unittest.TestCase):
    def test_clears_video_junk_and_sets_fields(self):
        tags = music_meta.build_tags('Song', ['A', 'B'], 'Album', '2024', ['Rock'])
        self.assertEqual(tags['title'], 'Song')
        self.assertEqual(tags['artist'], ['A', 'B'])
        self.assertEqual(tags['albumartist'], 'A')
        self.assertEqual(tags['description'], '')
        self.assertEqual(tags['comment'], '')


class TagAudioFileTests(unittest.TestCase):
    def test_tags_mp3_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'test.mp3')
            # A few silent MPEG-1 Layer III frames (128 kbps, 44.1 kHz) are
            # enough for mutagen to recognize the file as an MP3.
            frame = b'\xff\xfb\x90\x00' + b'\x00' * 413
            with open(path, 'wb') as f:
                f.write(frame * 4)
            music_meta.tag_audio_file(path, music_meta.build_tags('Song', ['Artist'], 'Album', '2024', ['Rock']))
            from mutagen import File
            audio = File(path, easy=True)
            self.assertEqual(audio['title'], ['Song'])
            self.assertEqual(audio['artist'], ['Artist'])
            self.assertEqual(audio['album'], ['Album'])


if __name__ == '__main__':
    unittest.main()
