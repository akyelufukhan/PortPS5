# Türkçe başlangıç

Bu depo, [ymatrix1/PortPS5](https://github.com/ymatrix1/PortPS5) projesinin
geliştirme fork'udur. Orijinal proje ve AnyPS5 atıfları ile GPL-2.0-only lisansı
korunur. Proje deneysel aşamadadır; hedef oyun listesi çalışır oyun garantisi
değildir. [Uyumluluk durumu](COMPATIBILITY.md).

## Ortam kontrolü

Windows x64 üzerinde Python 3.11 veya üstüyle:

```powershell
python tools/doctor.py
python tools/doctor.py --json
```

Komut eksik araçları ve önerilen düzeltmeleri gösterir; bilgisayara yazılım
kurmaz. MinGW-w64 GCC 15.2.0, CMake 3.25+, Ninja ve alt modüller gereklidir.
Başarılı kontrol, ekran kartını veya oyun uyumluluğunu doğrulamaz.

## Derleme

```powershell
git submodule update --init --recursive
cmake --preset release
cmake --build --preset release
```

## Oyunu hazırlama

Kendi oyununuzun önceden şifresi çözülmüş kopyasını kullanın. Proje oyunların
şifresini çözmez. Dump ve kurulum klasörlerini deponun dışında tutun.

```powershell
python tools/regress.py prepare --dump "D:\dumps\TITLE_ID" --install "D:\PortPS5\TITLE_ID" --relinker "build\release\core\relinker\relinker.exe" --libs "build\release\core\libs\libs"
```

Intel işlemcide bu komuta `--to-intel` ekleyin. `--config "D:\defaults"`
ile kendi varsayılan ayarlarınızı seçebilirsiniz; klasörde `global.toml`
bulunmalıdır. Mevcut ayarlar korunur, yalnızca eksik dosyalar eklenir.
Kütüphaneler ve oluşturulan çalıştırılabilir dosya yeniden hazırlanır.
`app0` bağlantısı dump klasörünü yazmaya karşı korumaz; yedeğini saklayın.

```powershell
Set-Location "D:\PortPS5\TITLE_ID"
.\game.exe
```

Bu fork'un ilk katkısı hazırlama ve tanılama araçlarıdır. Yeni oyun
uyumluluğu veya FPS sonucu iddiası yoktur. Telemetri bağlantıları henüz
tamamlanmadığı için `regress.py run` tam koşu doğrulamasına hazır değildir.
Detaylar: [kullanıcı kılavuzu](USER_GUIDE.md), [fork notları](FORK_NOTES.md).
