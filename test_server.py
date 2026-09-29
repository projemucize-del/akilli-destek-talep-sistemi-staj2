import tempfile
import unittest
import sqlite3
from pathlib import Path

from sensor_rules import evaluate_reading, normalize_reading
from server import SensorStore


VALID_READING = {"emg": 55, "force": 62, "current": 1.2, "position": 90, "battery": 88}


class SensorStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SensorStore(Path(self.temp.name) / "test.db", seed=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_session_and_readings(self):
        stats = self.store.stats()
        self.assertEqual(stats["sessions"], 1)
        self.assertEqual(stats["readings"], 18)

    def test_create_session(self):
        item, errors = self.store.create_session({"name": "FSR kavrama testi", "notes": "Masaüstü deneme"})
        self.assertIsNone(errors)
        self.assertEqual(item["source"], "Örnek Veri")
        self.assertEqual(item["status"], "Kayıt")

    def test_short_name_is_rejected(self):
        item, errors = self.store.create_session({"name": "x"})
        self.assertIsNone(item)
        self.assertIn("name", errors)

    def test_add_reading_is_persisted(self):
        item, errors = self.store.add_reading(1, VALID_READING)
        self.assertIsNone(errors)
        self.assertEqual(item["alert_level"], "Normal")
        self.assertEqual(item["reading_origin"], "Manuel Test Girdisi")
        self.assertEqual(self.store.stats()["readings"], 19)

    def test_generated_sample_has_explicit_origin(self):
        item, errors = self.store.add_sample(1)
        self.assertIsNone(errors)
        self.assertEqual(item["reading_origin"], "Örnek Üretici")

    def test_invalid_reading_is_rejected(self):
        item, errors = self.store.add_reading(1, {**VALID_READING, "current": 8})
        self.assertIsNone(item)
        self.assertIn("current", errors)

    def test_threshold_warning(self):
        result = evaluate_reading({**VALID_READING, "force": 84})
        self.assertEqual(result["level"], "Uyarı")
        self.assertIn("kuvveti", result["message"])

    def test_critical_current(self):
        result = evaluate_reading({**VALID_READING, "current": 3.8})
        self.assertEqual(result["level"], "Kritik")

    def test_sample_generator_stays_in_range(self):
        for index in range(80):
            _clean, errors = normalize_reading(self.store.sample_values(index))
            self.assertFalse(errors)

    def test_search_and_status_filter(self):
        page = self.store.list_sessions(search="kavrama", status="Kayıt")
        self.assertEqual(page["total"], 1)

    def test_invalid_pagination_falls_back_to_defaults(self):
        page = self.store.list_sessions(page="yanlış", page_size="yanlış")
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["page_size"], 8)

    def test_complete_blocks_new_readings(self):
        session, errors = self.store.complete_session(1)
        self.assertIsNone(errors)
        self.assertEqual(session["status"], "Tamamlandı")
        item, errors = self.store.add_reading(1, VALID_READING)
        self.assertIsNone(item)
        self.assertIn("session", errors)

    def test_csv_contains_sensor_columns(self):
        csv_text = self.store.export_csv()
        self.assertIn("EMG (%)", csv_text)
        self.assertIn("Motor Akımı (A)", csv_text)
        self.assertIn("Okuma Kaynağı", csv_text)

    def test_session_analytics_include_requested_metrics(self):
        session = self.store.get_session(1)
        analytics = session["analytics"]
        self.assertEqual(analytics["count"], 18)
        self.assertIsInstance(analytics["averages"]["emg"], float)
        self.assertGreater(analytics["maximums"]["force"], 0)
        self.assertGreaterEqual(analytics["safe_ratio"], 0)
        self.assertLessEqual(analytics["safe_ratio"], 100)
        self.assertIsNotNone(analytics["emg_force_correlation"])

    def test_pearson_correlation_and_label(self):
        value = self.store.pearson_correlation([1, 2, 3], [2, 4, 6])
        self.assertEqual(value, 1.0)
        self.assertEqual(self.store.correlation_label(value), "Güçlü pozitif")

    def test_correlation_handles_constant_or_insufficient_data(self):
        self.assertIsNone(self.store.pearson_correlation([1], [2]))
        self.assertIsNone(self.store.pearson_correlation([1, 1], [2, 3]))

    def test_empty_session_analytics_are_explicit(self):
        session, errors = self.store.create_session({"name": "Boş test oturumu"})
        self.assertIsNone(errors)
        self.assertEqual(session["analytics"]["count"], 0)
        self.assertEqual(session["analytics"]["correlation_label"], "Yetersiz veri")

    def test_non_object_payload_is_rejected(self):
        item, errors = self.store.create_session([])
        self.assertIsNone(item)
        self.assertIn("request", errors)
        item, errors = self.store.add_reading(1, [])
        self.assertIsNone(item)
        self.assertIn("request", errors)

    def test_existing_database_gets_origin_column_migration(self):
        old_path = Path(self.temp.name) / "old.db"
        with sqlite3.connect(old_path) as con:
            con.executescript("""
                CREATE TABLE sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'Örnek Veri',
                    status TEXT NOT NULL DEFAULT 'Kayıt',
                    notes TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    ended_at TEXT
                );
                CREATE TABLE readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    emg REAL NOT NULL,
                    force REAL NOT NULL,
                    current REAL NOT NULL,
                    position REAL NOT NULL,
                    battery REAL NOT NULL,
                    alert_level TEXT NOT NULL,
                    alert_message TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
            """)
        migrated = SensorStore(old_path, seed=False)
        with migrated.connect() as con:
            columns = {row["name"] for row in con.execute("PRAGMA table_info(readings)")}
        self.assertIn("reading_origin", columns)


if __name__ == "__main__":
    unittest.main(verbosity=2)
