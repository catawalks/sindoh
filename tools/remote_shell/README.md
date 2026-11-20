# Remote shell on a stock Sindoh printer (dev tool)

`unmistakable_remote_shell.sh` gives SSH access to a printer that runs
Sindoh's own firmware, from a USB stick, without changing the flash. Made
for the owner's 1X (2026-11-20); the packer can target the other models'
USB folders, but only the 1X has been checked to have dropbear (2015.71).

What it does on the printer:
- starts the stock `/usr/sbin/dropbear` on **port 2222**, key login only
  (`-s`), with a fresh ECDSA host key in `/tmp/remote_shell`;
- covers `/root` with a RAM copy (bind mount) that holds the public key in
  `.ssh/authorized_keys`; the real `/root` is not changed;
- writes `remote_shell_<time>.txt` to the top of the stick: the firmware,
  the addresses, the port and the host key fingerprint;
- shows nothing on the screen and leaves the stock programs alone.
A reboot removes all of it.

Build (the key pair stays outside the repositories; the packed `.she`
holds only the public key):

    ssh-keygen -t ecdsa -b 256 -N "" -f sindoh_1x_ecdsa
    python -I pack.py --survey ../../../sindoh_model_survey \
        --pubkey sindoh_1x_ecdsa.pub --out STICK_DIR --model 1x

Use: the printer must be on the network first (Wi-Fi from its own screen,
or Ethernet). Put only `_update_rodin_1x/unmistakable_remote_shell.she` in
that folder (the stock updater runs every `unmistakable*` file there),
plug the stick in while idle, wait 30 s, pull it, read the address from
the `.txt`, then:

    ssh -i sindoh_1x_ecdsa -p 2222 root@ADDRESS

Never run the stock `/snapshot_version.sh` there (it writes the U-Boot
environment); read it with `cat`.
