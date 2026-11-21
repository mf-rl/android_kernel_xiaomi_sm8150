#!/system/bin/sh
MODDIR=${0%/*}
# wait for boot to complete
while [ "$(getprop sys.boot_completed)" != "1" ]; do sleep 2; done
sleep 5
# skip if already loaded or kernel doesn't match the build
grep -q '^8188eu ' /proc/modules && exit 0
[ "$(uname -r)" = "4.14.357-gd6709120a8f3" ] || { log -t 8188eu "kernel mismatch: $(uname -r)"; exit 0; }
insmod "$MODDIR/8188eu.ko" && log -t 8188eu "loaded" || log -t 8188eu "insmod failed"
