# Offline reverse engineering of the vendor kernel

These scripts read the vendor kernel image only from a NAND dump on the PC.
Nothing touches the printer. The results are in `docs/kernel/` and are used
in `docs/no_gpl_plan.md`.

```
python -I tools/kernel_re/extract_image.py ../nand_images/mtd0.bin OUT/Image
python -I tools/kernel_re/kallsyms.py OUT/Image OUT/System.map
python -I tools/kernel_re/hwtables.py OUT/Image OUT/System.map > OUT/hwtables.txt
KRE_PYLIB=<pip --target dir with capstone> \
  python -I tools/kernel_re/kdis.py OUT/Image OUT/System.map timer_set_next_event
```

| Script | What it does |
|---|---|
| `extract_image.py` | Finds the uImage at mtd0+0x40000 and inflates the gzip'd kernel into the raw `Image`, which is linked at 0xc0008000. It also writes the embedded initramfs cpio. |
| `kallsyms.py` | Rebuilds `System.map` (38,440 symbols) from the kallsyms tables in the image. In 3.2 each table starts on a 16-byte boundary. |
| `hwtables.py` | Dumps the static I/O map (`gogin_io_desc`, virtual to physical), every platform `struct resource` (MMIO + IRQ), and the ATAGS machine record. |
| `kdis.py` | Disassembles functions by name. Literal-pool values are resolved to symbols or strings. Needs capstone (`pip install --target DIR capstone`, then set `KRE_PYLIB=DIR`, because `python -I` ignores PYTHONPATH). |

Inputs checked on 2026-10-28:
- `mtd0.bin` md5 `298b7390ccb500998661949c02ea68f8`
- the resulting `Image` md5 `a416b1bc28233d42080512ce76cc3ab9` (10,410,868 bytes)
