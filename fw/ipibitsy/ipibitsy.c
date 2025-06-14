#include <libopencm3/stm32/rcc.h>
#include <libopencm3/stm32/gpio.h>
#include <stdint.h>
#include "usb.h"

#define PACKET_SIZ 64
static uint8_t rx_buff[PACKET_SIZ];
// usbd_ep_write_packet hangs when called with len == wMaxPacketSize
static uint8_t tx_buff[PACKET_SIZ - 1];

struct bus_state {
    uint16_t pba;
    uint16_t pbb;
    uint16_t pbc;
};

static void read_state(struct bus_state *state) {
    state->pbc = gpio_port_read(GPIOC);
    state->pbb = gpio_port_read(GPIOB);
    state->pba = gpio_port_read(GPIOA);
}

static uint8_t get_ctrl_flags(struct bus_state *state) {
    uint16_t ctrl_state = ((state->pbb & 0x7000) >> 12) | ((state->pbc & 0xE000) >> 10);
    return ctrl_state & 0x3F;
}

static void reset_buff(uint8_t *buff) {
    buff[3] = 0;  // clear state change counter
}

static void push_state(struct bus_state *state, uint8_t *buff, uint8_t buff_siz) {
    // | C1 | CA | opcode | n msg | msg 0 | ... | msg n - 1 |
    // |  1 |  1 |   1    |   1   | 3*2=6 | ... |   3*2=6   |
    uint8_t off = 4 + 3 * 2 * buff[3];
    uint8_t end = off + 3 * 2 - 1;
    if (end < buff_siz) {
        tx_buff[0] = 0xC1;
        tx_buff[1] = 0xCA;
        tx_buff[2] = 1;
        buff[3]++;
        buff = &buff[off];
        buff[0] = state->pba & 0xFF;
        buff[1] = state->pba >> 8;
        buff[2] = state->pbb & 0xFF;
        buff[3] = state->pbb >> 8;
        buff[4] = state->pbc & 0xFF;
        buff[5] = state->pbc >> 8;
    }
}

static uint8_t decode_state(uint8_t *buff, struct bus_state *state) {
    // | C1 | CA | opcode | pba | pbb |
    // |  1 |  1 |   1    |  2  |  2  |
    if (buff[0] == 0xC1 && buff[1] == 0xCA && buff[2] == 1) {
        state->pba = buff[3] | (buff[4] << 8);
        state->pbb = buff[5] | (buff[6] << 8);
        return 0;
    }
    return 1;
}

static uint8_t decode_opcode(uint8_t *buff, uint8_t *opcode) {
    if (buff[0] == 0xC1 && buff[1] == 0xCA) {
        *opcode = buff[2];
        return 0;
    }
    return 1;
}

static void write_state(struct bus_state *state) {
    state->pbb |= (1 << 15); // CTRL.OE should be always high
    
    if (state->pba & (1 << 15)) {
        gpio_mode_setup(GPIOA, GPIO_MODE_OUTPUT, GPIO_PUPD_NONE, 0x01FF);
    } else {
        gpio_mode_setup(GPIOA, GPIO_MODE_INPUT, GPIO_PUPD_NONE, 0x01FF);
    }
    
    if (state->pbb & (1 << 9)) {
        gpio_mode_setup(GPIOB, GPIO_MODE_OUTPUT, GPIO_PUPD_NONE, 0x01FF);
    } else {
        gpio_mode_setup(GPIOB, GPIO_MODE_INPUT, GPIO_PUPD_NONE, 0x01FF);
    }

    gpio_port_write(GPIOA, state->pba);
    gpio_port_write(GPIOB, state->pbb);
}

int main(void)
{  
    rcc_clock_setup_pll(&rcc_hse_25mhz_3v3[RCC_CLOCK_3V3_84MHZ]);
    
    rcc_periph_clock_enable(RCC_GPIOA);
    rcc_periph_clock_enable(RCC_GPIOB);
    rcc_periph_clock_enable(RCC_GPIOC);
    
    // A15 / A.DIR
    gpio_mode_setup(GPIOA, GPIO_MODE_OUTPUT, GPIO_PUPD_NONE, 0x8000);
    // B9, B12-15 / B.DIR, CTRL.OE, CTRL.SEL_OUT, CTRL.MST_POUT, CTRL.SYNC_OUT
    gpio_mode_setup(GPIOB, GPIO_MODE_OUTPUT, GPIO_PUPD_NONE, 0xF200);  
    // Enable drivers for output CTRL signals  
    gpio_set(GPIOB, GPIO15);

    uint16_t rx_len = 0;
    uint8_t opcode = 0;
    struct bus_state bus_state;
    uint8_t current_ctrl_flags, prev_ctrl_flags = 0xFF;

    usb_init(rx_buff, sizeof(rx_buff));
    
    while (1) {
        usb_poll();

        rx_len = usb_received_len();
        if (rx_len && decode_opcode(rx_buff, &opcode) == 0) {
            if (opcode == 1 && decode_state(rx_buff, &bus_state) == 0) {
                write_state(&bus_state);
            } else if (opcode == 2) {
                prev_ctrl_flags = 0xFF;  // force update
            }
        }
        
        read_state(&bus_state);
        current_ctrl_flags = get_ctrl_flags(&bus_state);
        if (current_ctrl_flags != prev_ctrl_flags) {
            push_state(&bus_state, tx_buff, sizeof(tx_buff));
            prev_ctrl_flags = current_ctrl_flags;
        }
        
        if (rx_len) {
            usb_send_packet(tx_buff, sizeof(tx_buff));
            reset_buff(tx_buff);
        }
        
    }

    return 0;
}
