"""Tests for nightly yt-dlp update scheduling helpers."""

from __future__ import annotations

import unittest
from datetime import datetime

from main import seconds_until_next_daily_time


class NightlyUpdateTests(unittest.TestCase):
    def test_seconds_until_later_today(self):
        now = datetime(2026, 6, 4, 10, 0, 0)
        delay = seconds_until_next_daily_time("15:30", now)
        self.assertEqual(delay, 5 * 3600 + 30 * 60)

    def test_seconds_until_wraps_to_next_day(self):
        now = datetime(2026, 6, 4, 18, 0, 0)
        delay = seconds_until_next_daily_time("04:00", now)
        self.assertEqual(delay, 10 * 3600)

    def test_seconds_until_same_minute_is_next_day(self):
        now = datetime(2026, 6, 4, 4, 0, 30)
        delay = seconds_until_next_daily_time("04:00", now)
        self.assertAlmostEqual(delay, 24 * 3600 - 30, delta=1)


if __name__ == "__main__":
    unittest.main()
