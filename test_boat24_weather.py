"""Regression checks for official venue weather parser. Run: python -m unittest test_boat24_weather.py"""
import datetime as dt
import unittest
from boat24_integrity import JST
from boat24_water import parse_venue_weather

class WeatherParserTest(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,11,8,9,44,tzinfo=JST)

    def row(self,weather="晴",wind="南西",time="0940"):
        return "\t".join([time,weather,"2",wind,"3","19","17"])

    def test_japanese_weather_is_parsed(self):
        for label,code in [("晴",1),("曇",2),("雨",3),("雪",4)]:
            with self.subTest(label=label):
                row=parse_venue_weather(self.row(label),23,self.now)
                self.assertEqual(row["numeric"]["天候"],str(float(code)))
                self.assertEqual(row["numeric"]["風速(m)"],"3.0")
                self.assertEqual(row["numeric"]["風向"],"6.0")

    def test_numeric_weather_remains_compatible(self):
        row=parse_venue_weather(self.row("1"),23,self.now)
        self.assertEqual(row["numeric"]["天候"],"1.0")

    def test_unknown_weather_rejected(self):
        with self.assertRaises(ValueError):
            parse_venue_weather(self.row("不明"),23,self.now)

    def test_old_observation_rejected(self):
        with self.assertRaises(ValueError):
            parse_venue_weather(self.row(time="0700"),23,self.now)

if __name__=="__main__":
    unittest.main()
