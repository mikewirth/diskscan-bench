#!/bin/bash
# Cold-cache prepare step on macOS: evict the dataset volume from the unified buffer cache.
# DSB_DMG = disk image path, DSB_MNT = mountpoint. Detaching drops all cached pages for the volume.
set -e
sync
hdiutil detach "$DSB_MNT" -force -quiet || diskutil unmount force "$DSB_MNT" >/dev/null
sudo purge
hdiutil attach "$DSB_DMG" -mountpoint "$DSB_MNT" -nobrowse -noverify -noautofsck -owners on -quiet
