#!/usr/bin/env python3
"""Pack unmistakable_remote_shell.sh with a public key for one model's stick.

    python -I pack.py --survey DIR --pubkey KEY.pub --out OUT [--model 1x]

DIR is a checkout of catawalks/sindoh-model-survey (for she_crypto.py and
its model table). Writes OUT/<model folder>/unmistakable_remote_shell.she,
checked by decrypting it again. The public key goes into the packed copy
only; the repository holds no key.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import bz2
import io
import os
import sys
import tarfile

SCRIPT = "unmistakable_remote_shell.sh"
FOLDERS = {"dp200": "_update_rodin", "3dwox1": "_update_rodin_up",
           "2x": "_update_rodin_prime", "1x": "_update_rodin_1x", "7x": "_update_rodin_h"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--survey", required=True)
    ap.add_argument("--pubkey", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="1x", choices=sorted(FOLDERS))
    a = ap.parse_args()

    sys.path.insert(0, os.path.abspath(a.survey))
    import she_crypto  # noqa: E402
    import pack as survey_pack  # noqa: E402

    folder = FOLDERS[a.model]
    cipher, key = next((c, k) for _, f, c, k in survey_pack.MODELS if f == folder)
    pub = open(a.pubkey, encoding="ascii").read().strip()
    if "\n" in pub or "'" in pub or not pub.startswith(("ecdsa-", "ssh-rsa ")):
        sys.exit("expected one ecdsa or rsa public key line")
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), SCRIPT)
    script = open(src, "rb").read().replace(b"\r\n", b"\n")
    if script.count(b"@PUBKEY@") != 1:
        sys.exit("placeholder missing")
    script = script.replace(b"@PUBKEY@", pub.encode())
    blob = survey_pack.tar_bz2(SCRIPT, script)
    she = (she_crypto.des3_encrypt(key, blob) if cipher == "des3"
           else she_crypto.aes_encrypt(key, blob))
    with tarfile.open(fileobj=io.BytesIO(bz2.decompress(she_crypto.decrypt(cipher, key, she)))) as t:
        if t.getnames() != [SCRIPT] or t.extractfile(SCRIPT).read() != script:
            sys.exit("self-check failed")
    d = os.path.join(a.out, folder)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, SCRIPT + "e"), "wb") as f:
        f.write(she)
    print(f"{folder}/{SCRIPT}e {len(she)} bytes, verified")


if __name__ == "__main__":
    main()
