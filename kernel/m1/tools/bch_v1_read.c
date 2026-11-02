/*
 * bch_v1 (88PA6170) page reads, matched to the vendor 3.2 driver
 * (2026-11-01; docs/kernel/nand_bch_plan.md, "Read path rework").
 *
 * Like the vendor's mv61x0_nand_do_cmd()/mv61x0_nand_irq(), a page is read
 * once, with BCH on (2048 data + 32 spare), from a stopped controller, and
 * UNCERR counts only when it comes with the data (RDDREQ):
 *  - nothing flagged: the page as read;
 *  - CORERR: corrected. NDSR ERRCNT read after CMDD is the number of bits
 *    corrected (it equalled the count from a raw re-read on 5535 of 5543
 *    pages; the rest were flips in the ECC bytes, which only ERRCNT sees).
 *    At RDDREQ it still reads 0, and idle it reads 16: only use it here;
 *  - UNCERR only after the data, with data and spare all 0xff: an erased
 *    page (every programmed page has "programz" in its spare);
 *  - UNCERR before RDDREQ (rare): the controller gives no data for that
 *    command; read the page again;
 *  - UNCERR otherwise: read it raw to tell an erased page from a failure,
 *    and try again; after BCH_V1_READ_TRIES it is counted as failed.
 * Validated against the stock dumps: md5s of mtd0/mtd3/mtd5, 6000 random
 * reads with pauses, the UBI headers of mtd6, a read-only UBIFS mount of
 * the stock root. Never read NDDB from a debug tool: it takes a word out
 * of the FIFO and shifts every later read by 4 bytes.
 * stats (0644, write zeros to reset): clean corrected erased retried
 * failed timeouts early_unc early_cor rdd_unc end_unc
 */
enum { ST_CLEAN, ST_COR, ST_ERASED, ST_RETRY, ST_FAILED, ST_TIMEOUT,
       ST_EARLY_UNC, ST_EARLY_COR, ST_RDD_UNC, ST_END_UNC, ST_N };
static uint bch_v1_st[ST_N];
static int bch_v1_st_n = ST_N;
module_param_array_named(stats, bch_v1_st, uint, &bch_v1_st_n, 0644);
MODULE_PARM_DESC(stats, "88PA6170 reads: clean corrected erased retried failed timeouts early_unc early_cor rdd_unc end_unc");
static u32 bch_v1_end_ndsr;

#define F_EARLY_UNC	BIT(0)
#define F_EARLY_COR	BIT(1)
#define F_RDD_UNC	BIT(2)
#define F_RDD_COR	BIT(3)
#define F_END_UNC	BIT(4)
#define F_END_COR	BIT(5)
#define F_ANY		0x3f

/*
 * Start every bch_v1 command from a stopped controller, as the vendor's
 * mv61x0_nand_do_cmd() does: clear NDSR and force ND_RUN off. A read can
 * leave a word in the FIFO with ND_RUN still set; mainline then waits for
 * ND_RUN (100 ms "Timeout on NAND controller run mode") or, after an idle
 * gap, the next read starts with the stale 4 bytes and all its data is
 * shifted ("ramz" / 0xff before "UBI#", 2026-11-01). Only ever written
 * here, before the controller is started.
 */
static void bch_v1_stop(struct marvell_nfc *nfc)
{
	writel_relaxed(0xFFFFFFFF, nfc->regs + NDSR);
	writel_relaxed(readl_relaxed(nfc->regs + NDCR) & ~NDCR_ND_RUN,
		       nfc->regs + NDCR);
}

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
	bch_v1_stop(nfc);
	marvell_nfc_enable_hw_ecc(chip);
	ret = marvell_nfc_prepare_cmd(chip);
	if (ret)
		goto out;
	marvell_nfc_send_cmd(chip, &nfc_op);
	end = ktime_add_us(ktime_get(), POLL_TIMEOUT);
	for (;;) {
		ndsr = readl_relaxed(nfc->regs + NDSR);
		if (ndsr & NDSR_RDDREQ)
			break;
		if ((ndsr & NDSR_CORERR) && !(*flags & F_EARLY_COR)) {
			*flags |= F_EARLY_COR;
			bch_v1_st[ST_EARLY_COR]++;
		}
		if (ndsr & NDSR_UNCERR) {
			/* no data follows for this command: read it again */
			*flags |= F_EARLY_UNC;
			bch_v1_st[ST_EARLY_UNC]++;
			ret = -EBADMSG;
			goto out;
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
	bch_v1_end_ndsr = ndsr;
	if (ndsr & NDSR_UNCERR)
		*flags |= F_END_UNC;
	if (ndsr & NDSR_CORERR)
		*flags |= F_END_COR;
	if (ndsr & (NDSR_UNCERR | NDSR_CORERR))
		writel_relaxed(ndsr & (NDSR_UNCERR | NDSR_CORERR),
			       nfc->regs + NDSR);
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

static void bch_v1_take(struct nand_chip *chip, u8 *buf, const u8 *ecc_buf,
			bool oob_rest_ff)
{
	const struct marvell_hw_ecc_layout *lt = to_marvell_nand(chip)->layout;

	memcpy(buf, ecc_buf, lt->data_bytes);
	memcpy(chip->oob_poi, ecc_buf + lt->data_bytes, lt->spare_bytes);
	if (oob_rest_ff)
		memset(chip->oob_poi + lt->spare_bytes, 0xff,
		       nand_to_mtd(chip)->oobsize - lt->spare_bytes);
}

static int marvell_nfc_bch_v1_read_page(struct nand_chip *chip, u8 *buf,
					int oob_required, int page)
{
	struct marvell_nand_chip *marvell_nand = to_marvell_nand(chip);
	struct marvell_nfc *nfc = to_marvell_nfc(chip->controller);
	const struct marvell_hw_ecc_layout *lt = marvell_nand->layout;
	struct mtd_info *mtd = nand_to_mtd(chip);
	unsigned int flags = 0, flips;
	bool have_raw = false;
	u8 *ecc_buf;
	int ret = 0, r, bf, try;

	marvell_nfc_select_target(chip, chip->cur_cs);
	ecc_buf = kmalloc(lt->data_bytes + lt->spare_bytes, GFP_KERNEL);
	if (!ecc_buf)
		return -ENOMEM;

	for (try = 0; try < BCH_V1_READ_TRIES; try++) {
		if (try)
			bch_v1_st[ST_RETRY]++;
		ret = marvell_nfc_bch_v1_ecc_read(chip, ecc_buf, page, &flags);
		if (ret == -ETIMEDOUT)
			continue;
		if (!ret && !(flags & F_ANY)) {
			/* nothing flagged: the page as read */
			bch_v1_take(chip, buf, ecc_buf, true);
			bch_v1_st[ST_CLEAN]++;
			goto done;
		}
		/* UNCERR only after the data, all 0xff: an erased page */
		if (ret == -EBADMSG &&
		    (flags & (F_EARLY_UNC | F_RDD_UNC | F_END_UNC)) == F_END_UNC) {
			bf = nand_check_erased_ecc_chunk(ecc_buf, lt->data_bytes,
							 NULL, 0,
							 ecc_buf + lt->data_bytes,
							 lt->spare_bytes,
							 chip->ecc.strength);
			if (bf >= 0) {
				bch_v1_take(chip, buf, ecc_buf, true);
				bch_v1_st[ST_ERASED]++;
				mtd->ecc_stats.corrected += bf;
				ret = bf;
				goto done;
			}
		}
		if (!ret) {
			/* corrected: ERRCNT after CMDD is the bit count */
			flips = max_t(unsigned int, 1, NDSR_ERRCNT(bch_v1_end_ndsr));
			mtd->ecc_stats.corrected += flips;
			bch_v1_take(chip, buf, ecc_buf, true);
			bch_v1_st[ST_COR]++;
			ret = flips;
			goto done;
		}
		/* UNCERR before the data: no data came, just read again */
		if (flags & F_EARLY_UNC)
			continue;
		/* UNCERR: the raw copy tells an erased page from a failed one */
		marvell_nfc_disable_hw_ecc(chip);
		r = marvell_nfc_hw_ecc_hmg_do_read_page(chip, buf, chip->oob_poi,
							true, page);
		if (r) {
			ret = r;
			continue;
		}
		have_raw = true;
		bf = nand_check_erased_ecc_chunk(buf, lt->data_bytes,
						 chip->oob_poi + lt->spare_bytes,
						 lt->ecc_bytes, chip->oob_poi,
						 lt->spare_bytes, chip->ecc.strength);
		if (bf >= 0) {
			bch_v1_st[ST_ERASED]++;
			mtd->ecc_stats.corrected += bf;
			ret = bf;
			goto done;
		}
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
	if (try && try < BCH_V1_READ_TRIES)
		bch_v1_reread_ok++;
	kfree(ecc_buf);
	return ret;
}

