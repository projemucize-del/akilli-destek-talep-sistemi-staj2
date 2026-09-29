# Protez El Sensör Verilerinin İzlenmesi ve Test Kayıt Sistemi

Protez el için EMG, FSR, motor akımı, parmak konumu ve batarya değerlerini izleyen yerel web uygulaması prototipidir.

## Özellikler

- Python REST API ve SQLite veritabanı
- Test oturumu başlatma ve tamamlama
- Örnek üretici veya manuel test girdilerini kaynak etiketi ve zaman damgasıyla kaydetme
- Oturum bazlı EMG ve FSR değişim grafiği
- Ortalama EMG/FSR, en yüksek kuvvet ve akım, güvenli okuma oranı
- Pearson EMG–FSR korelasyonu ve anlaşılır ilişki etiketi
- Kuvvet, motor akımı, batarya ve EMG eşik uyarıları
- Arama, durum filtresi ve CSV dışa aktarma
- Masaüstü ve mobil uyumlu arayüz
- Mevcut SQLite dosyaları için otomatik şema geçişi
- 19 otomatik test

## Çalıştırma

```bash
python3 server.py
```

Tarayıcıdan `http://127.0.0.1:8765` adresini açın.

## Testler

```bash
python3 -m unittest -v test_server.py
```

## API

- `GET /api/health`
- `GET /api/stats`
- `GET /api/sessions`
- `GET /api/sessions/{id}`
- `POST /api/sessions`
- `POST /api/sessions/{id}/readings`
- `POST /api/sessions/{id}/sample`
- `PATCH /api/sessions/{id}/complete`
- `GET /api/export.csv`

## Veri kaynağı ve sınır

Mevcut sürüm gerçek protez el donanımına bağlı değildir. Arayüz, veri akışı, kayıt yapısı ve uyarılar yerel olarak üretilen örnek sensör verileriyle doğrulanır. Gerçek sensör bağlantısı yapıldığında örnek veri üreticisi yerine mikrodenetleyiciden gelen seri veya ağ verisi kullanılabilir.

Manuel girişler de gerçek sensör ölçümü sayılmaz ve her kayıtta `Manuel Test Girdisi` olarak işaretlenir. Arayüzdeki “güvenli okuma” ifadesi yalnızca prototip yazılım eşiklerini belirtir; klinik güvenlik veya cihaz uygunluğu kanıtı değildir.
