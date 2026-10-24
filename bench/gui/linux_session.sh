#!/bin/bash
# Start a headless desktop session for the Linux GUI track and print its environment (KEY=VALUE lines,
# suitable for >> $GITHUB_ENV): Xvfb, a private D-Bus session bus and the AT-SPI accessibility bus.
# Qt 5 connects to the AT-SPI bus synchronously when the AT_SPI_BUS root-window property is set; we leave
# org.a11y.Status.IsEnabled false so Qt does not also take its asynchronous path, which races with app
# registration (the app then never shows up in the accessibility tree).
set -e
DPY=${DSB_DISPLAY:-:99}
Xvfb "$DPY" -screen 0 1280x1024x24 -nolisten tcp -noreset >/dev/null 2>&1 &
export DISPLAY=$DPY
for i in $(seq 100); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done
eval "$(dbus-launch --sh-syntax)"
/usr/libexec/at-spi-bus-launcher --launch-immediately >/dev/null 2>&1 &
for i in $(seq 100); do
  ADDR=$(dbus-send --session --print-reply=literal --dest=org.a11y.Bus /org/a11y/bus org.a11y.Bus.GetAddress 2>/dev/null | sed 's/^ *//') && [ -n "$ADDR" ] && break; sleep 0.1
done
[ -n "$ADDR" ] || { echo "AT-SPI bus did not start" >&2; exit 1; }
xprop -root -f AT_SPI_BUS 8s -set AT_SPI_BUS "$ADDR"
echo "DISPLAY=$DISPLAY"
echo "DBUS_SESSION_BUS_ADDRESS=$DBUS_SESSION_BUS_ADDRESS"
echo "XDG_CURRENT_DESKTOP=dsb"
