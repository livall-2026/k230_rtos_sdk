"""Run actual MS OS vendor-request handling in both descriptor modes."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
usb = root / 'src/rtsmart/rtsmart/kernel/bsp/maix3/components'
core = (usb / 'CherryUSB/core/usbd_core.c').read_text()
handler = core[core.index('static int usbd_vendor_request_handler'):core.index('/**\n * @brief handle setup request')]
adb = (usb / 'canmv_usb/usbd_adb.c').read_text()
descriptors = adb[adb.index('__ALIGN_BEGIN const uint8_t WCID_StringDescriptor_MSOS'):adb.index('#ifndef CONFIG_USBDEV_SHELL_RX_BUFSIZE')]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#define __ALIGN_BEGIN
#define __ALIGN_END
#define USB_DESCRIPTOR_TYPE_STRING 3
#define WINUSB_REQUEST_GET_DESCRIPTOR_SET 7
#define WCID_VENDOR_CODE 0x17
#define USB_LOG_INFO(...) ((void)0)
#define USB_LOG_ERR(...) ((void)0)
#define usb_memcpy memcpy
struct usb_setup_packet { uint8_t bRequest; uint16_t wIndex, wValue; };
struct usb_msosv1_descriptor {
    const uint8_t *string; uint8_t vendor_code; const uint8_t *compat_id;
    const uint8_t **comp_id_property;
};
struct usb_msosv2_descriptor {
    uint8_t vendor_code; const uint8_t *compat_id; unsigned compat_id_len;
};
struct web_descriptor { uint8_t vendor_code; const uint8_t *string; unsigned string_len; };
struct descriptors {
    const struct usb_msosv1_descriptor *msosv1_descriptor;
    const struct usb_msosv2_descriptor *msosv2_descriptor;
    const struct web_descriptor *webusb_url_descriptor;
};
struct usbd_interface {
    int (*vendor_handler)(uint8_t, struct usb_setup_packet *, uint8_t **, uint32_t *);
};
static struct {
    unsigned intf_offset;
    const struct usb_msosv1_descriptor *msosv1_desc;
    const struct usb_msosv2_descriptor *msosv2_desc;
    const struct descriptors *descriptors;
    struct usbd_interface *intf[8];
} g_usbd_core[1];
''' + descriptors + handler + r'''
int main(void) {
    uint8_t buffer[256], *data = buffer;
    uint32_t length;
    struct descriptors desc = {.msosv1_descriptor = &msosv1_desc};
    g_usbd_core[0].intf_offset = ADB_INTF_NUM + 1;
    g_usbd_core[0].msosv1_desc = &msosv1_desc;
    g_usbd_core[0].descriptors = &desc;
    struct usb_setup_packet setup = {WCID_VENDOR_CODE, 4, 0};
    assert(usbd_vendor_request_handler(0, &setup, &data, &length) == 0);
    assert(length == 40 && buffer[16] == ADB_INTF_NUM);
    setup.wIndex = 5; setup.wValue = ADB_INTF_NUM;
    assert(usbd_vendor_request_handler(0, &setup, &data, &length) == 0);
    assert(length == 142 && !memcmp(buffer, WINUSB_IF0_WCIDProperties, length));
#if ADB_INTF_NUM > 0
    for (unsigned i = 0; i < ADB_INTF_NUM; ++i) {
        setup.wValue = i;
        assert(usbd_vendor_request_handler(0, &setup, &data, &length) < 0);
    }
#endif
    setup.wValue = ADB_INTF_NUM + 1;
    assert(usbd_vendor_request_handler(0, &setup, &data, &length) < 0);
    setup.wValue = 65535;
    assert(usbd_vendor_request_handler(0, &setup, &data, &length) < 0);
    puts("MS OS properties interface selection and invalid-request tests passed");
}
'''
with tempfile.TemporaryDirectory(prefix='k230-msos-') as work:
    c = Path(work) / 'test.c'
    c.write_text(harness)
    for interface in [0, 2, 3, 5]:
        for advanced in [False, True]:
            exe = Path(work) / ('test-%s-%s' % (interface, advanced))
            cmd = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                   '-DADB_INTF_NUM=' + str(interface)]
            if advanced:
                cmd.append('-DCONFIG_USBDEV_ADVANCE_DESC')
            subprocess.run(cmd + [str(c), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
