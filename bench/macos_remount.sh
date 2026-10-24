#!/bin/bash
# Cold-cache prepare step on macOS: evict the dataset volume from the unified buffer cache.
# DSB_DMG = disk image path, DSB_MNT = mountpoint. Detaching drops all cached pages for the volume;
# `purge` additionally flushes the host-side cache of the image file itself.
LOG="${TMPDIR:-/tmp}/dsb-remount.log"
sync
for i in 1 2 3 4 5 6; do
  mount | grep -q " on $DSB_MNT " || break
  hdiutil detach "$DSB_MNT" -quiet 2>>"$LOG" || hdiutil detach "$DSB_MNT" -force -quiet 2>>"$LOG" || sleep 2
done
sudo purge
for i in 1 2 3 4 5 6; do
  mount | grep -q " on $DSB_MNT " && exit 0
  hdiutil attach "$DSB_DMG" -mountpoint "$DSB_MNT" -nobrowse -noverify -noautofsck -owners on -quiet 2>>"$LOG" && { sudo mdutil -i off "$DSB_MNT" >>"$LOG" 2>&1; exit 0; }
  sleep 2
done
echo "remount failed, see $LOG" >&2; exit 1
