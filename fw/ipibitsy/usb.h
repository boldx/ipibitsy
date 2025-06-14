#ifndef IPIBITSY_USB_H
#define IPIBITSY_USB_H

void usb_init(uint8_t *rx_buff, uint16_t rx_buff_siz);
void usb_poll(void);
uint16_t usb_received_len(void);
uint16_t usb_send_packet(uint8_t *buff, uint16_t len);

#endif /* IPIBITSY_USB_H */
