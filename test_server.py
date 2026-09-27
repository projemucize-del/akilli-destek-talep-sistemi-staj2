import tempfile
import unittest
from pathlib import Path

from ai_model import MODEL, MultinomialNaiveBayes
from server import TicketStore


class TicketStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = TicketStore(Path(self.temp.name) / "test.db", seed=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_and_stats(self):
        self.assertEqual(self.store.stats()["total"], 6)
        self.assertEqual(sum(self.store.stats()["by_status"].values()), 6)

    def test_create_persists_ai_result_and_history(self):
        item, errors = self.store.create({"title": "Yeni kablosuz ağ sorunu", "category": "Ağ ve İnternet", "priority": "Normal", "description": "Wifi bağlantısı sürekli kopuyor ve tekrar bağlanıyor."})
        self.assertIsNone(errors)
        self.assertEqual(item["status"], "Açık")
        self.assertTrue(item["ai_category"])
        self.assertTrue(item["ai_priority"])
        self.assertEqual(len(item["history"]), 1)

    def test_rejects_invalid_input(self):
        item, errors = self.store.create({"title": "x", "category": "Bilinmiyor", "priority": "Normal", "description": "kısa"})
        self.assertIsNone(item)
        self.assertIn("title", errors)
        self.assertIn("category", errors)
        self.assertIn("description", errors)

    def test_search_filter_and_pagination(self):
        page = self.store.list(search="Yazılım", status="İşlemde", page=1, page_size=2)
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["category"], "Yazılım")

    def test_status_history(self):
        first = self.store.list(page=1, page_size=1)["items"][0]
        updated, errors = self.store.update_status(first["id"], "İşlemde", "Test kapsamında atandı.")
        self.assertIsNone(errors)
        self.assertEqual(updated["status"], "İşlemde")
        self.assertGreaterEqual(len(updated["history"]), 2)

    def test_csv_export_contains_ai_columns(self):
        csv_text = self.store.export_csv()
        self.assertIn("AI Kategori", csv_text)
        self.assertIn("AI Öncelik", csv_text)


class AIModelTests(unittest.TestCase):
    def test_network_category_prediction(self):
        result = MODEL.predict("Kablosuz bağlantı", "Wifi ağına bağlanamıyorum ve internet sürekli kopuyor")
        self.assertEqual(result["category"], "Ağ ve İnternet")

    def test_account_security_high_priority_prediction(self):
        result = MODEL.predict("Hesap güvenliği", "Hesabım ele geçirilmiş olabilir acil giriş engellensin")
        self.assertEqual(result["category"], "Hesap ve Yetki")
        self.assertEqual(result["priority"], "Yüksek")

    def test_short_text_is_rejected(self):
        with self.assertRaises(ValueError):
            MODEL.predict("a", "b")

    def test_metrics_are_reproducible(self):
        metrics = MODEL.metrics()
        self.assertEqual(metrics["evaluation_samples"], 6)
        self.assertGreaterEqual(metrics["category_accuracy"], 0.65)
        self.assertGreaterEqual(metrics["priority_accuracy"], 0.65)

    def test_classifier_handles_unknown_words(self):
        model = MultinomialNaiveBayes().fit([("ağ bağlantı", "A"), ("program hata", "B")])
        label, confidence, _ = model.predict("bilinmeyen ağ")
        self.assertIn(label, {"A", "B"})
        self.assertGreater(confidence, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
