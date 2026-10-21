// Sindoh DP200 / Marvell 88PA6170 "Gemstone" UPC hardware definitions.
//
// Everything here was recovered from the stock firmware (upc.ko, the
// fm/io UPC microcode and the main printer program). See
// docs/hardware_notes.md for the evidence behind each value. Items
// marked UNVERIFIED have not been observed on real hardware yet.
//
// Addresses are as seen by the UPC cores. SoC peripherals (UART, stepper
// engines, dec_*) are at their physical addresses, which is also what
// Linux sees through /dev/mem.

#ifndef __UPC_HW_H
#define __UPC_HW_H

// ---------------------------------------------------------------------
// Memory map (UPC view)
// ---------------------------------------------------------------------
#define UPC_ITCM_BASE       0x00000000u
#define UPC_ITCM_SIZE       0x00004000u   // 16 KiB, limit enforced by upc.ko
#define UPC_DTCM_BASE       0x04000000u
#define UPC_DTCM_SIZE       0x00040000u   // 256 KiB, shared by both cores
#define XENA_BASE           0x08000000u   // UPC-local register block

// ---------------------------------------------------------------------
// XENA registers (offsets from upc.ko DWARF: struct XENA_REGS_s)
// ---------------------------------------------------------------------
#define XENA_PHASE(n)       (XENA_BASE + 0x094 + 4 * (n))
#define XENA_MAILBOX0       (XENA_BASE + 0x128)
#define XENA_MAILBOX1       (XENA_BASE + 0x12c)
#define XENA_GPSTATUS       (XENA_BASE + 0x150) // bit0/bit1 raise Linux IRQs
#define XENA_CPUSOFTRESET   (XENA_BASE + 0x154)
#define XENA_PHASEREF       (XENA_BASE + 0x158)
#define XENA_PERFMON0_TIMER (XENA_BASE + 0x204)
#define XENA_PERFMON1_TIMER (XENA_BASE + 0x264)
#define XENA_ENCPOS         (XENA_BASE + 0x1084)
#define XENA_STATUS         (XENA_BASE + 0x1124)
#define XENA_PSEUDOENCODER  (XENA_BASE + 0x1128)
#define XENA_MAILBOX(n)     (XENA_BASE + 0x1130 + 4 * ((n) - 2)) // n = 2..5
#define XENA_TIMER(n)       (XENA_BASE + 0x1140 + 4 * (n))      // n = 0..3
#define XENA_XIIC(n)        (XENA_BASE + 0x1268 + 4 * (n))      // input cfg
#define XENA_XIRW           (XENA_BASE + 0x1650)
#define XENA_XIRD           (XENA_BASE + 0x1658) // input pins 0..31
#define XENA_XIRD1          (XENA_BASE + 0x165c) // input pins 32..63
#define XENA_IRQEN_FM       (XENA_BASE + 0x1800)
#define XENA_FIQEN_FM       (XENA_BASE + 0x1820)
#define XENA_INTPOST_FM     (XENA_BASE + 0x1840)
#define XENA_INTCLR_FM      (XENA_BASE + 0x1860)
#define XENA_IRQEN_IO       (XENA_BASE + 0x1880)
#define XENA_FIQEN_IO       (XENA_BASE + 0x18a0)
#define XENA_INTPOST_IO     (XENA_BASE + 0x18c0)
#define XENA_INTCLR_IO      (XENA_BASE + 0x18e0)

// Stock interrupt bits (we run with interrupts disabled, listed for reference)
#define XENA_INT_TIMER0     (1u << 0)   // IO core periodic tick
#define XENA_INT_IO_CMD     (1u << 5)   // IO core command from Linux
#define XENA_INT_FM_ESTOP   (1u << 4)   // FM FIQ: emergency stop
#define XENA_INT_FM_AUX     (1u << 6)
#define XENA_INT_FM_CMD     (1u << 9)   // FM command (Linux wrote mailbox 5)

// ---------------------------------------------------------------------
// Debug UART (16550-style, shared with the Linux console ttyS0!)
// ---------------------------------------------------------------------
#define UART_THR            0xf8060000u
#define UART_LSR            0xf8060014u
#define UART_LSR_THRE       0x20u
#define UART_LSR_TEMT       0x40u

// ---------------------------------------------------------------------
// "Gogin" hardware stepper pulse engines, 200 MHz timebase
// engine 0 = X, 1 = Y, 2 = Z, 3 = E, 4 = C (cartridge, unused on DP200?)
// ---------------------------------------------------------------------
#define SMOT_COUNT          5
#define SMOT_BASE(n)        (0xf8150000u + 0x1000u * (n))
#define SMOT_ABORT          0x04  // write 0x100 to stop a running move
#define SMOT_CFG            0x0c  // bit0 = 1: A4982 driver disabled
#define SMOT_CTRL           0x44  // stock value 0x33224, bit4 = direction
#define SMOT_ENABLE         0x50  // stock writes 1 before each move
#define SMOT_RAMP_LEN       0x54
#define SMOT_PERIOD         0x58  // ticks per output edge (half step period)
#define SMOT_CMD            0x5c  // (edges << 16) | mode; edges = 2 * steps
#define SMOT_START          0x60  // write 1
#define SMOT_STATUS         0x64
#define SMOT_DONE           0x88  // bit8 = move finished
#define SMOT_CLEAR          0x8c  // write 0x100 to clear done
#define SMOT_CTRL_STOCK     0x33224u
#define SMOT_CTRL_DIR       0x10u
#define SMOT_MODE_CONST     0x1u
#define SMOT_MODE_RAMP      0x2u
#define SMOT_DONE_BIT       0x100u
#define SMOT_CLOCK_HZ       200000000u

// ---------------------------------------------------------------------
// dec_pwm: register block N at PWM_BASE + 0x100*N (N = 1..32),
// global enable bit (N-1) in PWM_GLOBAL_EN.
// Stock users: 1-4 fans (period 100), 5 nozzle heater (period 1000),
// 6 clutch, 8 solenoid, 0x18 bed heater (period 1000),
// 0x1b/0x1d/0x1e/0x1f motor current REF X/Y/Z/E (period 200).
// ---------------------------------------------------------------------
#define PWM_BASE            0xf9304000u
#define PWM_GLOBAL_EN       PWM_BASE
#define PWM_BLOCK(n)        (PWM_BASE + 0x100u * (n))
#define PWM_CTRL            0x00  // bit0 run, bit2 static level when not running
#define PWM_HIGH            0x08  // ticks high
#define PWM_LOW             0x0c  // ticks low
#define PWM_STATUS          0x20  // bit31 + [15:0] current position
#define PWM_CTRL_RUN        0x1u
#define PWM_CTRL_LEVEL      0x4u
#define PWM_FIRST_BLOCK     1
#define PWM_NUM_BLOCKS      32

// ---------------------------------------------------------------------
// dec_adc: 10-entry sample FIFO, mux select in the 0x200.. words.
// Stock: select 0 = nozzle thermistor, 1 = bed thermistor.
// Samples are 10 bit; stock code scales to 11 bit (x 2048/1023), drops
// min and max and averages the remaining 8.
// ---------------------------------------------------------------------
#define ADC_BASE            0xf930a000u
#define ADC_CTRL            (ADC_BASE + 0x000)
#define ADC_CFG1            (ADC_BASE + 0x004)
#define ADC_CFG2            (ADC_BASE + 0x008)
#define ADC_FIFO(n)         (ADC_BASE + 0x180 + 4 * (n)) // n = 0..9
#define ADC_MUX(n)          (ADC_BASE + 0x200 + 4 * (n)) // n = 0..8
#define ADC_MUX_LAST        (ADC_BASE + 0x224)
#define ADC_SEQ             (ADC_BASE + 0x2bc)
#define ADC_FIFO_LEN        10
#define ADC_RAW_MAX         1023
#define ADC_CTRL_RUN        0x7770c006u   // io_2870(7,7,7,0,3,0,0,1,1)
#define ADC_CFG1_VAL        0x00244d01u   // io_28fc(0,0x24,0x4d,1)
#define ADC_MUX_WORD(sel)   (0x00010100u | (sel))

#define DEC_SENSOR_BASE     0xf9301000u   // 2 encoder channels
#define DEC_CONFIG_BASE     0xf9300000u

#endif // upc_hw.h
