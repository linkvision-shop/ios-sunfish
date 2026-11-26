# ios-sunfish: ios-sweet'in Pixel 4a (sunfish, SM7150) uyarlaması

Taban: `ios-sweet-main.zip`. Hiçbir şey derlenmedi (bu ortamda aarch64 derleyici, mkbootimg ve ağ yok),
telefonda denenmedi. Aşağıdaki "doğrulandı" ifadeleri yalnızca **canlı FDT / cmdline / iomem / dtbo
dosyalarından okunan** değerler için geçerli, çalışma davranışı için değil.

## Değişmeden kalanlar (canlı FDT'ye göre sunfish'te sweet ile aynı)
| Sabit | Değer | Kaynak |
|---|---|---|
| RAM (highmem) | `0x100000000` + `0xfcc00000`, yedek `0xb0000000` + `0x4d000000` | iomem: `0xa5030000-0x1fcbfffff` kesintisiz, sabit rezerve bölgeler hep altında |
| GIC | GICD `0x17a00000`, GICR `0x17a60000` | live.fdt |
| UFS | `0x01d84000` | live.fdt, cmdline |
| Timer | 19,2 MHz, INTID 19 | live.fdt (PPI 3 + 16) |
| CPU | 8 çekirdek, MPIDR `0x0`...`0x700` | live.fdt |
| IMEM restart reason / PSHOLD | `0x146aa65c` / `0x0c264000` | live.fdt |
| Framebuffer tabanı | `0x9c000000` (cont_splash_region, `0x1700000`) | live.fdt |
| Dokunmatik I2C bus tabanı | `0xa84000` | live.fdt, iomem |

## Değiştirilenler (ekran 1080x2400 -> 1080x2340)
- `shim/console.h`: `FB_H` 2340
- `tools/mkadt.py`: `FB_H` 2340 (stride 4320 sweet'ten taşındı, DOĞRULANMADI)
- `tools/qemu-sweet.py`: `FB_H` 2340
- `xnu/patches/0058`, `0061`: dokunmatik Y ölçeği ve ortalama 2340'a göre
- `xnu/patches/0010`: erken beyaz bant satırı 2368 -> 2308 (panelin görünen son 32 satırı)
- `shim/build.sh`: `dtb/boot_unpacked/dtb` artık sunfish `boot.img` dtb'si; LZ4 sıkıştırılmış kernelli ikinci imaj (`shim-boot-lz4.img`)
- `sunfish/`: profil, adaylar ve araçlar (`fdt2profile.py`, `dir2fdt.py`, `check_profile.py`)

## Yapılmayanlar / bilinmeyenler
1. **Dokunmatik:** sunfish ST FTS (`0x49`, qupv3_se7), sweet Goodix GT9896 (`0x5d`). Yama 0063 **uygun değil**, yeni FTS sürücüsü gerekir (sunfish Linux kernel kaynağı lazım). Şimdilik dokunmatik çalışmaz.
2. **Stride/format:** 4320 (1080x4, a8r8g8b8) sweet'ten varsayım. İlk boot'ta ekran bozuksa ilk şüpheli bu.
3. **Panel command mode** (`sofef01 sdc`): ekran donabilir, yenileme komutu gerekebilir.
4. **Kernel LZ4 şartı:** stok boot.img kernel'i LZ4 çerçevesi. Bootloader'ın şart koşup koşmadığı bilinmiyor, iki imajı da dene.
5. **`mem_dump_region` (36 MiB):** FDT'de `alloc-ranges` yok. Üst RAM'de yer alıyorsa çakışma olabilir.
6. **Yamalar 0060 (tuşlar), 0062 (RPMh)** sunfish için incelenmedi.
7. `tools/mkadt.py` `research/ipsw-x/d22ap.adt` dosyasını (iPhone X IPSW'den) ister; yoksa /product düğümü eklenmez.
8. Yama dosyalarında yalnızca sayı değiştirdim, satır sayıları aynı. XNU kaynağına karşı `git apply` denemedi (kaynak bu ortamda yok).

## İlk deneme sırası
1. CI'da kernel derle, `shim/build.sh` ile imajları üret. Önce `shim-boot.img` ile `fastboot boot` dene (flash YOK), sonra `shim-boot-lz4.img`.
2. Önce yalnızca shim/tanı imajı: ekranda yazı çıkıyor mu?
3. Her denemede tek şey değiştir, ekran fotoğrafı ve sonucu yaz.
4. `userdata`'ya yazmadan önce `persist`, `boot`, `dtbo`, `vbmeta` yedeğini al.
