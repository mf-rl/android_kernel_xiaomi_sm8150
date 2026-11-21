# TP-Link TL-WN722N v2/v3 (RTL8188EUS) on POCO X3 Pro (vayu) + NetHunter

Everything needed to get the adapter (USB ID `2357:010c`) listed by `lsusb` in
the Kali chroot, working with `airmon-ng`/`wifite` in monitor mode (with
injection), with its LED working, and loading automatically at boot.

Tested on: kernel `4.14.357-gd6709120a8f3` (this tree, `nethunter_defconfig`),
Kali rolling arm64 NetHunter chroot at `/data/local/nhsystem/kali-arm64`,
Magisk root.

## Summary of the four problems and their fixes

| # | Symptom | Cause | Fix | Where |
|---|---------|-------|-----|-------|
| 1 | `lsusb` empty in the Kali chroot (root shell outside shows the device) | The chroot's `libudev1`/`usbutils` (systemd 262) cannot enumerate devices on a 4.14 kernel; sysfs and `/dev/bus/usb` are fine | `lsusb` wrapper that reads sysfs directly, names from a rebuilt `hwdb.bin` | `kali/` (userspace) |
| 2 | Adapter has no driver (`Driver=[none]`), no `wlan2` | Kernel has no driver for the 8188EUS: `rtl8xxxu`/`rtlwifi` do not claim `2357:010c` on 4.14 | Build a driver for it | this kernel tree |
| 3 | Staging `r8188eu` loads but `iwconfig wlan2 mode monitor` fails ("Operation not permitted") | Staging driver is wext-only, no monitor mode/injection | Use aircrack-ng `rtl8188eus` (`8188eu.ko`) instead of staging `r8188eu` | this kernel tree |
| 4 | Adapter LED never lights on the phone | LED support is compiled out upstream: `/* #define CONFIG_RTW_LED */` in `include/autoconf.h` | Enable `CONFIG_RTW_LED` when fetching the driver | `build.sh` |
| 5 | Driver gone after reboot | Android does not auto-load modules | Magisk `service.sh` that `insmod`s it at boot | `magisk/` |

## Kernel-side changes (what is in this branch)

1. `build.sh` clones `aircrack-ng/rtl8188eus` (branch `v5.3.9`) into
   `drivers/staging/rtl8188eus`, pinned to commit
   `af3bf004458f76b7aec33e9ba552cd382ed1f5c3`, then enables `CONFIG_RTW_LED`
   with `sed` (the build aborts if the patch did not apply). It follows the
   existing pattern used for `rtw88` and the CAN drivers.
2. `drivers/staging/Kconfig` / `drivers/staging/Makefile` hook the new
   directory (`CONFIG_RTL8188EU`). As with `rtw88`, the directory is not
   committed, so run `build.sh` (or clone it yourself) before `make *config`.
3. `arch/arm64/configs/nethunter_defconfig`:
   `# CONFIG_R8188EU is not set` (staging driver off - both drivers match the
   same USB ID, so only one must be present) and `CONFIG_RTL8188EU=m`.
   `CONFIG_88EU_AP_MODE` is removed because it only belongs to the staging
   driver.

The result is `8188eu.ko` inside the `NetHunter-Modules-*.zip` produced by the
build. Its `vermagic` matches the kernel automatically because it is built with
it (and there is no `MODVERSIONS`/`MODULE_SIG`).

## Userspace setup (after flashing the kernel + modules)

### A. Load the driver at boot (Magisk)

The NetHunter modules zip installs modules to `/system/lib/modules/` but does
not load them. Copy `magisk/8188eu-loader/` to
`/data/adb/modules/8188eu-loader/`, add the built `8188eu.ko` next to
`service.sh`, and make them executable/readable:

```sh
su -c '
D=/data/adb/modules/8188eu-loader
mkdir -p $D
cp magisk/8188eu-loader/{module.prop,service.sh} $D/
cp 8188eu.ko $D/
chmod 755 $D/service.sh; chmod 644 $D/8188eu.ko $D/module.prop
'
```

`service.sh` waits for `sys.boot_completed`, skips if already loaded, refuses
to run on a different kernel release (edit the hard-coded release string in the
script when you move to a new kernel build), and logs to `logcat -s 8188eu`.
Manual load: `su -c insmod /data/adb/modules/8188eu-loader/8188eu.ko`.

### B. `lsusb` in the Kali chroot

Inside the chroot, as root:

```sh
install -m755 kali/lsusb /usr/local/bin/lsusb          # wrapper (ahead of /usr/bin in PATH)
install -m644 kali/hwdb_build.py /usr/local/sbin/hwdb_build.py
python3 /usr/local/sbin/hwdb_build.py                  # writes /etc/udev/hwdb.bin
lsusb
```

* `hwdb_build.py` is a minimal compiler for systemd's `hwdb.bin` format
  (`systemd-hwdb update` does not work inside the chroot). Re-run it after
  `apt upgrade` of `udev`/`hwdb` data if you want fresh vendor names.
* If the hwdb lookup fails, the wrapper falls back to the `manufacturer` and
  `product` strings from sysfs.
* Limitations: when run with arguments, the wrapper tries the real `lsusb`
  first. `lsusb -t` works with the real tool (prints harmless
  `rx_lanes`/`tx_lanes` errors on this kernel); `-s`/`-d` filters are not
  implemented by the fallback.

### C. Use it

```sh
iw dev                         # wlan2 appears (phy1), driver 8188eu
airmon-ng                      # lists wlan2
ip link set wlan2 down; iw dev wlan2 set type monitor; ip link set wlan2 up
iw dev wlan2 set channel 6
aireplay-ng --test wlan2       # injection test
wifite -i wlan2
```

The LED lights when the interface is up and blinks with traffic.

## Notes / gotchas

* Android's `/system/bin` is first in `PATH` inside a bare `chroot`; export
  `PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`
  (NetHunter's own launcher does this).
* Building the module separately against a running kernel needs the full
  source (the `kheaders` archive has no Kbuild files), `clang`, `lld`,
  `llvm`, `bc`, `flex`, `bison`, `libssl-dev`, `libelf-dev`, then
  `make ARCH=arm64 CC=clang LD=ld.lld ... modules_prepare` and `make M=...`.
  The `rtw88`/CAN submodule directories must exist (stub `Kconfig` files are
  enough) for `make olddefconfig` to succeed.
* Only one of `r8188eu` (staging) and `8188eu` should be present; unload with
  `rmmod` before loading the other.
* Passive scanning/monitor use only on networks you are authorised to test.
