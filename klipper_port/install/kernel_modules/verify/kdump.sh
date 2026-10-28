#!/bin/sh
# Read-only: dump some kernel functions' code from /dev/kmem (stock side, busybox)
OUT=/mnt/sd/home/klipper/printer_data/logs/x_kfuncs
mkdir -p $OUT
sort /proc/kallsyms > $OUT/kallsyms.sorted
for f in usb_ifnum_to_if usb_alloc_urb usb_init_urb usb_submit_urb usb_kill_urb usb_get_intf usb_put_intf \
         usb_driver_claim_interface usb_driver_release_interface usb_control_msg usb_alloc_coherent \
         tty_port_init tty_port_tty_get tty_port_tty_set tty_flip_buffer_push tty_insert_flip_string_fixed_flag \
         tty_wakeup tty_port_close_start tty_port_close_end tty_port_hangup tty_port_block_til_ready \
         alloc_tty_driver tty_register_driver tty_hangup tty_get_baud_rate; do
    line=$(grep -n " [Tt] $f\$" $OUT/kallsyms.sorted | head -1)
    [ -n "$line" ] || { echo "no $f"; continue; }
    n=${line%%:*}
    a=$(sed -n "${n}p" $OUT/kallsyms.sorted | cut -d' ' -f1)
    b=$(sed -n "$((n+1))p" $OUT/kallsyms.sorted | cut -d' ' -f1)
    len=$(( 0x$b - 0x$a ))
    [ $len -gt 0 ] && [ $len -lt 8192 ] || { echo "odd size $f $len"; continue; }
    dd if=/dev/kmem of=$OUT/$f.bin bs=1 skip=$((0x$a)) count=$len 2>/dev/null
    echo "$f $a $len $(wc -c < $OUT/$f.bin)"
done
chmod -R 644 $OUT/*; chmod 755 $OUT
