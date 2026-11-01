/*
 * bch_v1 (88PA6170) page reads, reworked after the vendor 3.2 driver
 * (2026-11-01; docs/kernel/nand_bch_plan.md, "Read path rework").
 *
 * The vendor's mv61x0_nand_irq() treats UNCERR as a failure only when it
 * comes with RDDREQ (data ready); status bits that show up earlier are
 * acknowledged (written back to NDSR) and the command goes on. Ours polled
 * without acknowledging them, and the engine then stalled: "UNCERR without
 * RDDREQ" and silent 100 ms timeouts, on pages that need correction.
 *
 * Switches (diagnosis builds; the defaults are what is measured best):
 *   read_mode  0: raw read first, then BCH (the original bring-up order)
 *              1: BCH first, like the vendor; a raw read only when the
 *                 engine flagged something (to count the corrected bits,
 *                 or to tell an erased page from an uncorrectable one)
 *   ack_early  acknowledge UNCERR/CORERR that arrive before RDDREQ
 * stats: clean, corrected, erased, retried, failed, timeouts, early_unc,
 *        early_cor, rdd_unc, end_unc
 */
static uint bch_v1_mode;
module_param_named(read_mode, bch_v1_mode, uint, 0644);
MODULE_PARM_DESC(read_mode, "88PA6170: 0 raw then BCH, 1 BCH first");
static bool bch_v1_ack;
module_param_named(ack_early, bch_v1_ack, bool, 0644);
MODULE_PARM_DESC(ack_early, "88PA6170: acknowledge UNCERR/CORERR before RDDREQ");
/*
 * Stock 3.2's controller state, idle, differs from ours (devmem, 2026-11-01):
 * NDECCCTRL 0xf21 (BCH_EN, threshold 16, 30 in bits 7-14) and NDCR bits 14
 * (64 pages per block) and 23 (SEQ_DIS) set. Switches to test them:
 *   eccctrl   NDECCCTRL value for BCH reads (0: mainline's BCH_EN only)
 *   ndcr_set  NDCR bits 14/23 for page reads (0x4000, 0x800000; default 0)
 * (The vendor writes NDECCCTRL 0x21 per command; 0xf00 reads back as status.)
 */
static uint bch_v1_eccctrl;
module_param_named(eccctrl, bch_v1_eccctrl, uint, 0644);
static uint bch_v1_ndcr_set;
module_param_named(ndcr_set, bch_v1_ndcr_set, uint, 0644);
/*
 * drain: after a BCH read, the controller can still offer data (NDSR
 * RDDREQ set, 2026-11-01), and the next command's data then started with
 * those stale bytes ("ramz", the tail of the previous page's "programz").
 *   0: leave it (old behaviour)   1: count and drain it (up to 128 bytes)
 * stats extra_reads / extra_bytes count what was found.
 */
static uint bch_v1_drain;
module_param_named(drain, bch_v1_drain, uint, 0644);
enum { ST_CLEAN, ST_COR, ST_ERASED, ST_RETRY, ST_FAILED, ST_TIMEOUT,
       ST_EARLY_UNC, ST_EARLY_COR, ST_RDD_UNC, ST_END_UNC, ST_EXTRA_READS,
       ST_EXTRA_BYTES, ST_N };
static uint bch_v1_st[ST_N];
static int bch_v1_st_n = ST_N;
module_param_array_named(stats, bch_v1_st, uint, &bch_v1_st_n, 0644);
MODULE_PARM_DESC(stats, "88PA6170 reads: clean corrected erased retried failed timeouts early_unc early_cor rdd_unc end_unc extra_reads extra_bytes");

/* data still offered after a read: count it, and drain it if asked */
static void bch_v1_leftover(struct marvell_nfc *nfc)
{
	u32 ndsr = readl_relaxed(nfc->regs + NDSR);
	unsigned int n = 0;
	u8 tmp[FIFO_DEPTH];

	if (!(ndsr & NDSR_RDDREQ))
		return;
	bch_v1_st[ST_EXTRA_READS]++;
	if (!bch_v1_drain)
		return;
	while ((readl_relaxed(nfc->regs + NDSR) & NDSR_RDDREQ) && n < 128) {
		writel_relaxed(NDSR_RDDREQ, nfc->regs + NDSR);
		ioread32_rep(nfc->regs + NDDB, tmp, FIFO_REP(FIFO_DEPTH));
		n += FIFO_DEPTH;
	}
	bch_v1_st[ST_EXTRA_BYTES] += n;
}

#define F_EARLY_UNC	BIT(0)
#define F_EARLY_COR	BIT(1)
#define F_RDD_UNC	BIT(2)
#define F_RDD_COR	BIT(3)
#define F_END_UNC	BIT(4)
#define F_END_COR	BIT(5)
#define F_ANY		0x3f

/* One BCH read of data + spare (2080 bytes, as the vendor reads them) */
static int marvell_nfc_bch_v1_ecc_read(struct nand_chip *chip, u8 *ecc_buf,
				       int page, unsigned int *flags)
{
	struct marvell_nand_chip *marvell_nand = to_marvell_nand(chip);
	struct marvell_nfc *nfc = to_marvell_nfc(chip->controller);
	const struct marvell_hw_ecc_layout *lt = marvell_nand->layout;
	struct marvell_nfc_op nfc_op = {
		.ndcb[0] = NDCB0_CMD_TYPE(TYPE_READ) |
			   NDCB0_ADDR_CYC(marvell_nand->addr_cyc) |
			   NDCB0_DBC |
			   NDCB0_CMD1(NAND_CMD_READ0) |
			   NDCB0_CMD2(NAND_CMD_READSTART),
		.ndcb[1] = NDCB1_ADDRS_PAGE(page),
		.ndcb[2] = NDCB2_ADDR5_PAGE(page),
	};
	ktime_t end;
	u32 ndsr;
	int ret;

	*flags = 0;
	marvell_nfc_enable_hw_ecc(chip);
	if (bch_v1_eccctrl)
		writel_relaxed(bch_v1_eccctrl, nfc->regs + NDECCCTRL);
	ret = marvell_nfc_prepare_cmd(chip);
	if (ret)
		goto out;
	marvell_nfc_send_cmd(chip, &nfc_op);
	end = ktime_add_us(ktime_get(), POLL_TIMEOUT);
	for (;;) {
		ndsr = readl_relaxed(nfc->regs + NDSR);
		if (ndsr & NDSR_RDDREQ)
			break;
		if ((ndsr & NDSR_UNCERR) && !(*flags & F_EARLY_UNC)) {
			*flags |= F_EARLY_UNC;
			bch_v1_st[ST_EARLY_UNC]++;
		}
		if ((ndsr & NDSR_CORERR) && !(*flags & F_EARLY_COR)) {
			*flags |= F_EARLY_COR;
			bch_v1_st[ST_EARLY_COR]++;
		}
		if (ndsr & (NDSR_UNCERR | NDSR_CORERR)) {
			if (!bch_v1_ack && (ndsr & NDSR_UNCERR)) {
				ret = -EBADMSG;
				goto out;
			}
			if (bch_v1_ack)
				writel_relaxed(ndsr & (NDSR_UNCERR | NDSR_CORERR),
					       nfc->regs + NDSR);
		}
		if (ktime_after(ktime_get(), end)) {
			bch_v1_st[ST_TIMEOUT]++;
			ret = -ETIMEDOUT;
			goto out;
		}
		cpu_relax();
	}
	bch_v1_last_ndsr = ndsr;
	if (ndsr & NDSR_UNCERR)
		*flags |= F_RDD_UNC;
	if (ndsr & NDSR_CORERR)
		*flags |= F_RDD_COR;
	writel_relaxed(NDSR_RDDREQ, nfc->regs + NDSR);
	marvell_nfc_xfer_data_in_pio(nfc, ecc_buf, lt->data_bytes);
	marvell_nfc_xfer_data_in_pio(nfc, ecc_buf + lt->data_bytes,
				     lt->spare_bytes);
	ret = marvell_nfc_wait_cmdd(chip);
	if (ret) {
		bch_v1_st[ST_TIMEOUT]++;
		ret = -ETIMEDOUT;
		goto out;
	}
	ndsr = readl_relaxed(nfc->regs + NDSR);
	if (ndsr & NDSR_UNCERR)
		*flags |= F_END_UNC;
	if (ndsr & NDSR_CORERR)
		*flags |= F_END_COR;
	if (ndsr & (NDSR_UNCERR | NDSR_CORERR))
		writel_relaxed(ndsr & (NDSR_UNCERR | NDSR_CORERR),
			       nfc->regs + NDSR);
	bch_v1_leftover(nfc);
	if (*flags & F_RDD_UNC)
		bch_v1_st[ST_RDD_UNC]++;
	if (*flags & F_END_UNC)
		bch_v1_st[ST_END_UNC]++;
	if (*flags & (F_RDD_UNC | F_END_UNC))
		ret = -EBADMSG;

out:
	if (ret) {
		/* End this job so that the next command starts clean */
		writel_relaxed(readl(nfc->regs + NDSR), nfc->regs + NDSR);
		writel_relaxed(readl(nfc->regs + NDCR) & ~NDCR_ND_RUN,
			       nfc->regs + NDCR);
	}
	marvell_nfc_disable_hw_ecc(chip);
	return ret;
}

/*
 * Corrected bits per ECC step, from the raw read and the BCH read. 30 ECC
 * bytes = 4 steps of 60 bits (t = 4, m = 15), each over 512 data + 8 spare
 * bytes. Returns the largest step count; *total gets the page total.
 */
static unsigned int bch_v1_flips(const struct marvell_hw_ecc_layout *lt,
				 const u8 *raw, const u8 *raw_spare,
				 const u8 *ecc_buf, unsigned int *total)
{
	unsigned int step, i, n, max = 0;
	unsigned int dstep = lt->data_bytes / 4, sstep = lt->spare_bytes / 4;

	*total = 0;
	for (step = 0; step < 4; step++) {
		n = 0;
		for (i = step * dstep; i < (step + 1) * dstep; i++)
			n += hweight8(raw[i] ^ ecc_buf[i]);
		for (i = step * sstep; i < (step + 1) * sstep; i++)
			n += hweight8(raw_spare[i] ^ ecc_buf[lt->data_bytes + i]);
		*total += n;
		max = max(max, n);
	}
	return max;
}

static int marvell_nfc_bch_v1_read_page(struct nand_chip *chip, u8 *buf,
					int oob_required, int page)
{
	struct marvell_nand_chip *marvell_nand = to_marvell_nand(chip);
	struct marvell_nfc *nfc = to_marvell_nfc(chip->controller);
	const struct marvell_hw_ecc_layout *lt = marvell_nand->layout;
	struct mtd_info *mtd = nand_to_mtd(chip);
	unsigned int flags = 0, flips = 0, total;
	bool have_raw = false;
	u8 *ecc_buf;
	int ret = 0, r, bf, try = 0;

	marvell_nfc_select_target(chip, chip->cur_cs);
	/*
	 * test switch: NDCR bits 14/23 as ndcr_set has them. Only written when
	 * set: an unconditional NDCR rewrite here broke raw-then-BCH reads
	 * (stale FIFO bytes at the start of the data, 2026-11-01).
	 */
	if (bch_v1_ndcr_set)
		writel_relaxed((readl_relaxed(nfc->regs + NDCR) &
				~(BCH_V1_NDCR_PG_PER_BLK | BCH_V1_NDCR_SEQ_DIS)) |
			       (bch_v1_ndcr_set & (BCH_V1_NDCR_PG_PER_BLK |
						   BCH_V1_NDCR_SEQ_DIS)),
			       nfc->regs + NDCR);
	ecc_buf = kmalloc(lt->data_bytes + lt->spare_bytes, GFP_KERNEL);
	if (!ecc_buf)
		return -ENOMEM;

	if (bch_v1_mode == 0) {
		/* raw first: erased pages never go through the BCH engine */
		marvell_nfc_disable_hw_ecc(chip);
		ret = marvell_nfc_hw_ecc_hmg_do_read_page(chip, buf,
							  chip->oob_poi,
							  true, page);
		if (ret)
			goto done;
		have_raw = true;
		bf = nand_check_erased_ecc_chunk(buf, lt->data_bytes,
						 chip->oob_poi + lt->spare_bytes,
						 lt->ecc_bytes, chip->oob_poi,
						 lt->spare_bytes,
						 chip->ecc.strength);
		if (bf >= 0) {
			bch_v1_st[ST_ERASED]++;
			mtd->ecc_stats.corrected += bf;
			ret = bf;
			goto done;
		}
	}

	for (try = 0; try < BCH_V1_READ_TRIES; try++) {
		if (try)
			bch_v1_st[ST_RETRY]++;
		ret = marvell_nfc_bch_v1_ecc_read(chip, ecc_buf, page, &flags);
		if (ret == -ETIMEDOUT)
			continue;
		if (!ret && !(flags & F_ANY) && !have_raw) {
			/* BCH first, nothing flagged: no raw read needed */
			memcpy(buf, ecc_buf, lt->data_bytes);
			memcpy(chip->oob_poi, ecc_buf + lt->data_bytes,
			       lt->spare_bytes);
			memset(chip->oob_poi + lt->spare_bytes, 0xff,
			       mtd->oobsize - lt->spare_bytes);
			bch_v1_st[ST_CLEAN]++;
			goto done;
		}
		if (!have_raw || bch_v1_mode == 1) {
			/* the raw copy: corrected bits, or erased vs failed */
			marvell_nfc_disable_hw_ecc(chip);
			r = marvell_nfc_hw_ecc_hmg_do_read_page(chip, buf,
								chip->oob_poi,
								true, page);
			if (r) {
				ret = r;
				continue;
			}
			have_raw = true;
		}
		if (ret == -EBADMSG) {
			bf = nand_check_erased_ecc_chunk(buf, lt->data_bytes,
							 chip->oob_poi + lt->spare_bytes,
							 lt->ecc_bytes,
							 chip->oob_poi,
							 lt->spare_bytes,
							 chip->ecc.strength);
			if (bf >= 0) {
				bch_v1_st[ST_ERASED]++;
				mtd->ecc_stats.corrected += bf;
				ret = bf;
				goto done;
			}
			continue;
		}
		/* corrected: more than t bits in a step can't be a correction */
		flips = bch_v1_flips(lt, buf, chip->oob_poi, ecc_buf, &total);
		if (flips > chip->ecc.strength) {
			ret = -EBADMSG;
			continue;
		}
		mtd->ecc_stats.corrected += total;
		memcpy(buf, ecc_buf, lt->data_bytes);
		memcpy(chip->oob_poi, ecc_buf + lt->data_bytes,
		       lt->spare_bytes);
		bch_v1_st[total ? ST_COR : ST_CLEAN]++;
		ret = flips;
		goto done;
	}

	/* Uncorrectable, or no data: the raw copy, counted as failed */
	if (!have_raw) {
		marvell_nfc_disable_hw_ecc(chip);
		marvell_nfc_hw_ecc_hmg_do_read_page(chip, buf, chip->oob_poi,
						    true, page);
	}
	dev_warn_ratelimited(nfc->dev,
			     "page %d: BCH read failed (%d) %d times, raw data, NDSR 0x%08x\n",
			     page, ret, BCH_V1_READ_TRIES, bch_v1_last_ndsr);
	bch_v1_st[ST_FAILED]++;
	mtd->ecc_stats.failed++;
	ret = 0;
done:
	if (try)
		bch_v1_reread_ok += ret >= 0 && try < BCH_V1_READ_TRIES;
	kfree(ecc_buf);
	return ret;
}

