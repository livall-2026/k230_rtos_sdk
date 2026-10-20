"""Validate the actual compiled USB descriptor and upstream serial builder."""
from pathlib import Path
import struct
import subprocess
import tempfile

r=Path('/home/by/230')
out=r/'output/k230d_canmv_bpi_zero_defconfig'
obj=out/'rtsmart/kernel/components/canmv_usb/usbd_desc.o'
elf=obj.read_bytes()
assert elf[:6] == b'\x7fELF\x02\x01'
off=struct.unpack_from('<Q',elf,40)[0]
size,count,names=struct.unpack_from('<HHH',elf,58)
sections=[struct.unpack_from('<IIQQQQIIQQ',elf,off+i*size) for i in range(count)]
s=sections[names]
strings=elf[s[4]:s[4]+s[5]]
data=None
for s in sections:
    name=strings[s[0]:].split(b'\0',1)[0]
    if name==b'.rodata.canmv_usb_descriptor':
        data=elf[s[4]:s[4]+s[5]]
assert data is not None
assert data[0:2]==bytes([18,1])
assert struct.unpack_from('<HH',data,8)==(0x1209,0xABD1)
assert data[18:20]==bytes([9,2])
total=struct.unpack_from('<H',data,20)[0]
end=18+total
pos=18
interfaces=[]
eps=[]
while pos<end:
    n,kind=data[pos:pos+2]
    assert n>=2 and pos+n<=end
    d=data[pos:pos+n]
    if kind==4: interfaces.append((d[2],d[5],d[6],d[7]))
    if kind==5: eps.append(d[2])
    pos+=n
assert pos==end
assert len(interfaces)==data[22]==4
assert [i[1:] for i in interfaces]==[(2,2,1),(10,0,0),(6,1,1),(255,66,1)],interfaces
assert len(set(eps))==len(eps) and all(1<=e%128<=6 for e in eps),eps
print('Compiled USB interfaces:',interfaces,'endpoints:',[hex(e) for e in eps])

src=(r/'src/rtsmart/rtsmart/kernel/bsp/maix3/components/canmv_usb/usbd_desc.c').read_text()
defines=src[src.index('#define CANMV_USB_UID_SIZE'):src.index('bool g_usb_device_connected')]
finder=src[src.index('static const uint8_t* find_string_descriptor'):src.index('static bool read_chip_uid')]
prepare=src[src.index('static void prepare_usb_descriptor'):src.index('void board_usb_device_event_handler')]
harness='''#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#define RT_NULL NULL
#define USB_DESCRIPTOR_TYPE_STRING 3
#define USB_STRING_SERIAL_INDEX 3
#define rt_memcpy memcpy
#define rt_kprintf(...) ((void)0)
'''+defines+'static const uint8_t canmv_usb_descriptor[]={'+','.join(str(b) for b in data)+'''};
static uint8_t g_canmv_usb_descriptor[sizeof(canmv_usb_descriptor)+CANMV_USB_SERIAL_DESCRIPTOR_SIZE];
static bool uid_ok;
static bool read_chip_uid(uint8_t uid[CANMV_USB_UID_SIZE]) {
    memset(uid,0xAB,CANMV_USB_UID_SIZE); return uid_ok;
}
'''+finder+prepare+'''
int main(void) {
    uid_ok=false; prepare_usb_descriptor();
    assert(g_canmv_usb_descriptor[16]==0);
    assert(!memcmp(g_canmv_usb_descriptor+18,canmv_usb_descriptor+18,sizeof(canmv_usb_descriptor)-18));
    uid_ok=true; prepare_usb_descriptor();
    assert(g_canmv_usb_descriptor[16]==3);
    const uint8_t *serial=find_string_descriptor(g_canmv_usb_descriptor,sizeof(g_canmv_usb_descriptor),3);
    assert(serial && serial[0]==130 && serial[2]=='A' && serial[4]=='B');
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='pmu-usb-') as d:
    c=Path(d)/'usb.c'; c.write_text(harness)
    exe=Path(d)/'usb'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(c),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print('Compiled USB descriptor and actual UID serial-builder tests passed')
