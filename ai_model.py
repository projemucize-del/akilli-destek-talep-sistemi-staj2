"""Türkçe destek talepleri için küçük, açıklanabilir bir Naive Bayes modeli.

Model yalnızca anonim ve sentetik eğitim örnekleriyle çalışır. Kurum verisi içermez.
"""

from collections import Counter, defaultdict
from math import exp, log
import re


TOKEN_RE = re.compile(r"[a-zçğıöşü0-9]+", re.IGNORECASE)


CATEGORY_TRAINING = [
    ("kablosuz ağa bağlanamıyorum wifi bağlantısı sürekli kopuyor", "Ağ ve İnternet"),
    ("internet çok yavaş dns adresine erişilemiyor", "Ağ ve İnternet"),
    ("ethernet kablosu takılı fakat ağ bağlantısı yok", "Ağ ve İnternet"),
    ("vpn bağlantısı kurulamadı uzak erişim çalışmıyor", "Ağ ve İnternet"),
    ("program açılırken hata veriyor ve kapanıyor", "Yazılım"),
    ("uygulama güncellemesinden sonra form kaydedilmiyor", "Yazılım"),
    ("ofis programı lisans uyarısı gösteriyor", "Yazılım"),
    ("csv raporu dışa aktarma işlemi tamamlanmıyor", "Yazılım"),
    ("üniversite web sayfasındaki bağlantı açılmıyor", "Web Sayfası"),
    ("duyuru sayfasında görsel bozuk görünüyor", "Web Sayfası"),
    ("mobil ekranda menü sayfanın dışına taşıyor", "Web Sayfası"),
    ("web formunda zorunlu alan uyarısı çıkmıyor", "Web Sayfası"),
    ("parolamı unuttum hesaba giriş yapamıyorum", "Hesap ve Yetki"),
    ("kullanıcı hesabım kilitlendi yetki talep ediyorum", "Hesap ve Yetki"),
    ("eposta hesabına erişim iznim bulunmuyor", "Hesap ve Yetki"),
    ("personel panelinde yetkisiz erişim uyarısı alıyorum", "Hesap ve Yetki"),
    ("bilgisayar açılmıyor güç ışığı yanmıyor", "Donanım"),
    ("klavye bazı tuşları algılamıyor", "Donanım"),
    ("yazıcı kağıdı çekmiyor ve ses çıkarıyor", "Donanım"),
    ("monitörde görüntü yok ekran karanlık", "Donanım"),
    ("genel teknik destek ve bilgi talebi", "Diğer"),
    ("hangi birime başvurmam gerektiğini öğrenmek istiyorum", "Diğer"),
]


PRIORITY_TRAINING = [
    ("tüm kullanıcılar sisteme giremiyor hizmet tamamen durdu acil", "Yüksek"),
    ("güvenlik ihlali şüphesi var hesap ele geçirilmiş olabilir", "Yüksek"),
    ("sınav sistemi çalışmıyor işlem yapılamıyor", "Yüksek"),
    ("sunucu bağlantısı kesildi bütün birim etkilendi", "Yüksek"),
    ("uygulamada hata alıyorum fakat alternatif yöntem var", "Normal"),
    ("tek kullanıcı bağlantı sorunu yaşıyor", "Normal"),
    ("form bazen kaydedilmiyor kontrol edilmesi gerekiyor", "Normal"),
    ("hesap yetkisinin güncellenmesini talep ediyorum", "Normal"),
    ("arayüz renginin değiştirilmesi önerisi", "Düşük"),
    ("rapor başlığında küçük yazım hatası var", "Düşük"),
    ("ileride kullanılmak üzere yeni özellik önerisi", "Düşük"),
    ("menü simgesinin konumu iyileştirilebilir", "Düşük"),
]


EVALUATION_CASES = [
    ("wifi ağına bağlanamıyorum bağlantı kopuyor", "Ağ ve İnternet", "Normal"),
    ("hesabım ele geçirilmiş olabilir acil giriş engellensin", "Hesap ve Yetki", "Yüksek"),
    ("uygulama raporu kaydetmiyor", "Yazılım", "Normal"),
    ("duyuru sayfasında küçük yazım hatası", "Web Sayfası", "Düşük"),
    ("bilgisayar hiç açılmıyor güç gelmiyor", "Donanım", "Normal"),
    ("tüm personelde internet kesildi hizmet durdu", "Ağ ve İnternet", "Yüksek"),
]


def tokenize(text):
    return TOKEN_RE.findall(str(text).lower())


class MultinomialNaiveBayes:
    def __init__(self):
        self.labels = []
        self.doc_counts = Counter()
        self.word_counts = defaultdict(Counter)
        self.total_words = Counter()
        self.vocabulary = set()
        self.total_docs = 0

    def fit(self, rows):
        for text, label in rows:
            tokens = tokenize(text)
            self.doc_counts[label] += 1
            self.word_counts[label].update(tokens)
            self.total_words[label] += len(tokens)
            self.vocabulary.update(tokens)
            self.total_docs += 1
        self.labels = sorted(self.doc_counts)
        return self

    def predict(self, text):
        tokens = tokenize(text)
        vocabulary_size = max(1, len(self.vocabulary))
        scores = {}
        for label in self.labels:
            score = log(self.doc_counts[label] / self.total_docs)
            denominator = self.total_words[label] + vocabulary_size
            for token in tokens:
                score += log((self.word_counts[label][token] + 1) / denominator)
            scores[label] = score
        best = max(scores, key=scores.get)
        peak = max(scores.values())
        probabilities = {key: exp(value - peak) for key, value in scores.items()}
        total = sum(probabilities.values())
        confidence = probabilities[best] / total if total else 0.0
        return best, round(confidence, 4), scores


class SupportRequestAI:
    name = "Multinomial Naive Bayes"
    data_notice = "Sentetik ve anonim örnek veri"

    def __init__(self):
        self.category_model = MultinomialNaiveBayes().fit(CATEGORY_TRAINING)
        self.priority_model = MultinomialNaiveBayes().fit(PRIORITY_TRAINING)

    def predict(self, title, description):
        text = f"{title} {description}".strip()
        if len(text) < 10:
            raise ValueError("Analiz için en az 10 karakterlik açıklama gereklidir.")
        category, category_confidence, _ = self.category_model.predict(text)
        priority, priority_confidence, _ = self.priority_model.predict(text)
        return {
            "category": category,
            "priority": priority,
            "category_confidence": category_confidence,
            "priority_confidence": priority_confidence,
            "model": self.name,
            "warning": "Sonuç bir öneridir; personel onayı olmadan otomatik karar verilmez.",
        }

    def metrics(self):
        category_correct = 0
        priority_correct = 0
        details = []
        for text, expected_category, expected_priority in EVALUATION_CASES:
            result = self.predict("", text)
            category_correct += result["category"] == expected_category
            priority_correct += result["priority"] == expected_priority
            details.append({
                "text": text,
                "expected_category": expected_category,
                "predicted_category": result["category"],
                "expected_priority": expected_priority,
                "predicted_priority": result["priority"],
            })
        total = len(EVALUATION_CASES)
        return {
            "model": self.name,
            "training_samples": len(CATEGORY_TRAINING) + len(PRIORITY_TRAINING),
            "evaluation_samples": total,
            "category_accuracy": round(category_correct / total, 4),
            "priority_accuracy": round(priority_correct / total, 4),
            "data_notice": self.data_notice,
            "details": details,
        }


MODEL = SupportRequestAI()
