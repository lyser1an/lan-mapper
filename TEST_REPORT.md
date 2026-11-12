# Public sürüm doğrulama raporu

Tarih: 12 Kasım 2026

- Python 3.14.8 ve Tk 9.0 üzerinde çalıştırıldı. Harici paket kurulmadı.
- `python -m unittest discover -s tests -v`: **17/17 başarılı**.
- `python -m compileall -q app.py network.py smoke_local.py tests`: başarılı.
- Gerçek yerel fiziksel Ethernet bağlantısında `python smoke_local.py --confirm-local` çalıştırıldı: **2 hedef, 2 ICMP yanıtı, 2 MAC, 0 uyarı**. Yalnızca gateway ve bu bilgisayar kontrol edildi.
- Masaüstü arayüzünde iki hedeflik keşif ayrıca başlatıldı; onay ekranı, işlem boyunca kilitlenen keşif kontrolleri, ilerleme, cihaz tablosu, subnet hesaplayıcı ve mantıksal harita gözle doğrulandı.
- Otomatik testler; subnet hesabı, /31 ve /32, yanlış girişler, hedef sınırı, yerel subnet dışına çıkmanın reddi, genel IPv4 arayüzünün reddi, geniş subnet sınırı, düşük hız zorunluluğu, arayüz değişikliği, VPN/uzak gateway rotasının reddi, iptal, yanıtsız hedefin belirsiz tutulması, komşu kayıtlarının filtrelenmesi, cihaz adlarının saklanması ve CSV kodlaması/formül kaçışını kapsar.
- Son kontrolde gerçek ağdaki iki hedef testi yeniden çalıştırıldı: **2 hedef, 2 ICMP yanıtı, 2 MAC, 0 uyarı**. 64 hedef üst sınırı ve en az 1 saniye ICMP başlangıç aralığı korundu; zamanlama ayrıca ağ isteği göndermeyen sahte saat testiyle doğrulandı.
- `/8`, `/16`, `/20`, `/24`, `/25`, `/30`, `/31` ve `/32` örnekleri; network/broadcast, maske ve adres sayılarıyla doğrulandı.
- Gerçek Tkinter uygulaması sentetik veriyle çalıştırıldı: ad değiştirme, JSON'a yazıp yeniden okuma, CSV aktarımı/yeniden okuma ve belirsiz hedeflerin haritaya cihaz olarak eklenmemesi kontrolleri başarılı.
- Uygulamanın beş temel özelliği kontrol edildi: ağ keşfi, mantıksal harita, cihaz adlandırma, subnet hesabı ve CSV aktarımı. Yeni özellik veya üretim kodunda refactor yapılmadı.
- README görselleri gerçek uygulamanın yalnızca anonim örnek penceresinden alındı: dokümantasyon IPv4 adresleri, kurgusal MAC adresleri, `.example` hostname'leri ve genel cihaz adları kullanıldı. SSID veya başka kişisel bilgi gösterilmedi.
- Gerçek IP/MAC envanteri, log veya gerçek ağ ekran görüntüsü yayımlanacak dosyalara eklenmedi. Sentetik yerel QA verileri ve yardımcı test dosyası `data/` altında Git dışında tutuldu.
- `.gitignore`: yerel `data/`, `exports/`, CSV, log, paket yakalamaları, ortam dosyaları, ham ekran görüntüleri ve Python önbellekleri dışlanır. Yayın için yalnızca açıkça seçilen kaynak, test, belge ve anonim görseller hazırlanır.

Bu doğrulama tüm subnet'in veya tüm cihaz türlerinin bulunduğunu kanıtlamaz. Gerçek Wi-Fi, /23'ten geniş ağ, ağın keşif sırasında değişmesi ve paket engelleyen cihazlar canlı ortamda ayrıca denenmedi; ilgili sınır mantığı otomatik testlerle kontrol edildi. Hostname için mevcut Windows DNS önbelleği kullanıldığından bazı cihazlarda boş değer beklenir. Windows'un varsayılan diyalog düğmeleri sistem dilini izler.

Yalnızca `lan-mapper` klasöründe çalışıldı. Diğer projelerin dosyalarına dokunulmadı. Bu rapor ilk public kaynak sürümü için hazırlanmıştır; web deploy yapılmamıştır.
