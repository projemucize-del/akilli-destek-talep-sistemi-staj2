# Akıllı Destek Talep Sistemi

Staj 2 kapsamında hazırlanmış, gerçekten çalışan yerel bir yazılım ve web uygulaması test projesidir.

## Uygulanan bileşenler

- Duyarlı HTML/CSS/JavaScript kullanıcı arayüzü
- Python standart kütüphanesiyle REST API
- Kalıcı SQLite veritabanı ve parametreli SQL sorguları
- Talep oluşturma, arama, filtreleme ve sayfalama
- Personel görünümü, durum güncelleme ve işlem geçmişi
- İstatistik paneli ve CSV dışa aktarma
- Türkçe metin için Multinomial Naive Bayes sınıflandırıcısı
- AI ile kategori ve öncelik önerisi, güven oranı ve değerlendirme ölçütleri
- Birim testleri

## Çalıştırma

```bash
cd staj2_destek_ai
python3 server.py
```

Tarayıcıdan `http://127.0.0.1:8765` adresini açın.

## Testler

```bash
python3 -m unittest -v test_server.py
```

## API uç noktaları

- `GET /api/health`
- `GET /api/stats`
- `GET /api/tickets`
- `GET /api/tickets/{id}`
- `POST /api/tickets`
- `PATCH /api/tickets/{id}/status`
- `POST /api/ai/predict`
- `GET /api/ai/metrics`
- `GET /api/export.csv`

## Doğruluk ve sınırlar

Uygulama ve yapay zekâ modülü yerel test ortamında gerçekten çalıştırılmak üzere uygulanmıştır. AI modeli yalnızca kaynak kodda bulunan küçük, sentetik ve anonim Türkçe örnek veri kümesiyle eğitilir. Gösterilen doğruluk oranları aynı sentetik değerlendirme kümesine aittir; üniversitenin gerçek hizmet kalitesini veya gerçek kullanıcı verileri üzerindeki başarıyı kanıtlamaz. AI önerileri otomatik karar değildir ve personel onayı gerektirir.

Uygulama gerçek üniversite sistemine bağlı değildir; üretim kimlik doğrulaması, kurum kullanıcıları ve kişisel veri içermez.
