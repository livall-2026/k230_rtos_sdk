"""Inspect the actual compiled descriptor and class registration relocations."""
from pathlib import Path
import struct,sys,subprocess
r=Path(__file__).resolve().parents[2]
obj=r/'output/k230d_canmv_bpi_zero_defconfig/rtsmart/kernel/components/canmv_usb/usbd_desc.o'
elf=obj.read_bytes()
assert elf[:6]==b'\x7fELF\x02\x01'
off=struct.unpack_from('<Q',elf,40)[0]
size,count,names=struct.unpack_from('<HHH',elf,58)
sections=[struct.unpack_from('<IIQQQQIIQQ',elf,off+i*size) for i in range(count)]
s=sections[names];strings=elf[s[4]:s[4]+s[5]]
data=None
for s in sections:
    if strings[s[0]:].split(b'\0',1)[0]==b'.rodata.canmv_usb_descriptor':data=elf[s[4]:s[4]+s[5]]
assert data is not None and data[:2]==bytes([18,1])
assert struct.unpack_from('<HH',data,8)==(0x1209,0xABD1)
total=struct.unpack_from('<H',data,20)[0];pos=18;end=18+total
interfaces=[];eps=[]
while pos<end:
    n,kind=data[pos:pos+2];assert n>=2 and pos+n<=end
    d=data[pos:pos+n]
    if kind==4:interfaces.append((d[2],d[5],d[6],d[7]))
    if kind==5:eps.append(d[2])
    pos+=n
assert pos==end
expected=[(2,2,1),(10,0,0),(6,1,1)]
missing='--expect-missing-adb' in sys.argv
if not missing: expected.append((255,66,1))
assert [i[1:] for i in interfaces]==expected,interfaces
assert len(set(eps))==len(eps) and all(1<=e%128<=6 for e in eps),eps
# A high-speed composite also advertises a valid full-speed configuration.
# Bulk endpoints must use 64-byte packets there instead of the 512-byte HS size.
cursor=end
other_speed=False
while cursor<len(data) and data[cursor]:
    length,kind=data[cursor:cursor+2]
    assert length>=2 and cursor+length<=len(data)
    if kind==7:
        other_end=cursor+struct.unpack_from('<H',data,cursor+2)[0]
        position=cursor+length
        other_interfaces=[]
        other_eps=[]
        while position<other_end:
            size,descriptor_kind=data[position:position+2]
            assert size>=2 and position+size<=other_end
            descriptor=data[position:position+size]
            if descriptor_kind==4:
                other_interfaces.append(tuple(descriptor[5:8]))
            if descriptor_kind==5:
                other_eps.append(descriptor[2])
                if descriptor[3]&3==2:
                    assert struct.unpack_from('<H',descriptor,4)[0]==64
            position+=size
        assert position==other_end and other_interfaces==expected
        assert other_eps==eps
        other_speed=True
        cursor=other_end
    else:
        cursor+=length
assert other_speed, 'Missing full-speed descriptor for high-speed composite'
relocations=subprocess.check_output(['readelf','-rW',str(obj)],text=True)
for name in ['canmv_usb_device_cdc_init','canmv_usb_device_mtp_init']:
    assert name in relocations,name
assert ('canmv_usb_device_adb_init' in relocations)==(not missing)
print('Compiled USB interfaces:',interfaces,'endpoints:',[hex(e) for e in eps])
print('Verified missing ADB in exact pre-sync configuration' if missing else 'CDC/MTP/ADB descriptor and actual class-init references passed')
print('Full-speed composite descriptor and bulk endpoint sizes passed')
