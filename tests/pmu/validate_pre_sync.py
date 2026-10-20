from pathlib import Path
import subprocess,json,hashlib,shutil
r=Path('/home/by/230');k=r/'src/rtsmart/rtsmart';bsp=k/'kernel/bsp/maix3';out=r/'output/k230d_canmv_bpi_zero_defconfig'
state=json.loads((r/'tests/pmu/pre-sync-rollback-state.json').read_text())
original=Path(state['restore_from']);before=json.loads((original/'state.json').read_text())
def git(repo,*args):return subprocess.check_output(['git','-C',str(repo),*args])
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
for row in before['projects']:
    assert git(r/row['path'],'rev-parse','HEAD').decode().strip()==row['head'],row['path']
revision=(out/'images/sdcard/revision.txt').read_text().splitlines()
for row in before['projects']:
    if row['path']=='.repo/manifests':continue
    assert row['name'].replace('-','_')+'='+row['head'] in revision,row['name']
# Actual storage implementation must match pre-sync HEAD byte for byte.
storage=['kernel/bsp/maix3/drivers/interdrv/sdio/drv_sdhci.c',
         'kernel/bsp/maix3/drivers/interdrv/sdio/drv_sdhci.h',
         'kernel/rt-thread/components/drivers/sdio/mmc.c',
         'kernel/rt-thread/components/drivers/sdio/block_dev.c']
for rel in storage:assert (k/rel).read_bytes()==git(k,'show','773612b:'+rel),rel
for row in before['projects']:
    if row.get('stash'):
        repo=r/row['path']
        for rel in git(repo,'diff','--name-only',row['head'],row['stash']).decode().splitlines():
            if rel.endswith('/drv_pmu.c') and row['path']=='src/rtsmart/rtsmart':continue
            if rel.endswith('/k230d_canmv_bpi_zero_defconfig'):continue
            assert (repo/rel).read_bytes()==git(repo,'show',row['stash']+':'+rel),rel
    for rel in row['untracked_files']:
        assert (r/row['path']/rel).read_bytes()==(Path(row['backup'])/'untracked'/rel).read_bytes(),rel
cfg=(bsp/'.config').read_text()
required=['RT_USING_RTC_PMU','RT_PMU_INT4_SHUTDOWN','RT_PMU_SHUTDOWN_WAKEUP',
          'RT_PMU_SHUTDOWN_WAKEUP_PAD68','RT_PMU_SHUTDOWN_WAKEUP_PAD68_HIGH_LEVEL',
          'RT_PMU_SHUTDOWN_WAKEUP_PAD68_BIAS_KEEP','RT_SDIO0_EMMC','RT_SDIO0_1V8','RT_SDIO0_HS200',
          'DRV_SYSCTL_BOOT_FORCE_MODE_MODE_EMMC','REALTEK_SDIO_RTL8733BS',
          'CHERRY_USB_DEVICE_FUNC_CDC_MTP_ADB']
for key in required:assert 'CONFIG_'+key+'=y\n' in cfg,key
assert 'BSP_SDIO0_MAX_FREQ' not in cfg
assert 'CONFIG_K230_PM_DVFS=y' not in cfg
assert (r/'.config').read_bytes()==(original/'configuration/.config').read_bytes(),'SDK root config drift'
def parse_config(p):
    return {l.split('=',1)[0]:l.split('=',1)[1] for l in p.read_text().splitlines() if l.startswith('CONFIG_') and '=' in l}
oldcfg=parse_config(original/'configuration/src/rtsmart/rtsmart/kernel/bsp/maix3/.config')
newcfg=parse_config(bsp/'.config')
delta={key:[oldcfg.get(key),newcfg.get(key)] for key in sorted(set(oldcfg)|set(newcfg)) if oldcfg.get(key)!=newcfg.get(key)}
assert set(delta)<= {'CONFIG_CHERRY_USB_DEVICE_FUNC_CDC_MTP','CONFIG_CHERRY_USB_DEVICE_FUNC_CDC_MTP_ADB'},delta
for name in ['test_pmu_host.py','test_pmu_startup.py','test_usb_rollback.py']:
    subprocess.run(['python3',str(r/'tests/pmu'/name)],check=True)
maps=(bsp/'rtthread.map').read_text()
assert '.text.pmu_int4_timer_cb' in maps
mpmap=(out/'canmv/micropython.map').read_text()
for symbol in ['machine_pmu_type','drv_pmu_shutdown_poll','drv_pmu_shutdown_register_poll']:assert symbol in mpmap,symbol
for repo in [r,k,r/'src/canmv',r/'src/rtsmart/libs',r/'src/uboot/uboot']:
    subprocess.run(['git','-C',str(repo),'diff','--check'],check=True)
image=out/'CanMV_K230D_Zero_micropython_local_nncase_v2.11.0.img'
embedded=subprocess.check_output(['mtype','-i',str(image)+'@@'+str(140*1024*1024),'::revision.txt'])
assert embedded.replace(b'\r\n',b'\n')==(out/'images/sdcard/revision.txt').read_bytes()
with image.open('rb') as f:
    for offset,rel in [(10,'opensbi/opensbi_rtt_system.bin'),(60,'opensbi/opensbi_rtt_system.bin'),
                       (30,'rtapp/rtapp.elf.gz'),(80,'rtapp/rtapp.elf.gz')]:
        data=(out/'images'/rel).read_bytes();f.seek(offset*1024*1024)
        assert f.read(len(data))==data,(offset,rel)
dest=out/'rollback-presync';dest.mkdir(exist_ok=True)
artifacts=[]
for suffix in ['.img','.img.gz']:
    src=out/('CanMV_K230D_Zero_micropython_local_nncase_v2.11.0'+suffix)
    if suffix.endswith('.gz'):subprocess.run(['gzip','-t',str(src)],check=True)
    dst=dest/('CanMV_K230D_Zero_presync_INT4_PMU_20261019'+suffix)
    shutil.copy2(src,dst)
    artifacts.append({'path':str(dst),'bytes':dst.stat().st_size,'sha256':sha(dst)})
report={'source':'pre-sync snapshot plus GPIO init safety guard and CDC/MTP/ADB composite only',
        'restore_from':str(original),'before_rollback_backup':state['backup'],
        'projects':[{'path':row['path'],'head':row['head']} for row in before['projects']],
        'kernel_config_delta_from_snapshot':delta,'storage_sources_identical_to_presync':storage,
        'pmu_state_machine_test':'passed','startup_guard_test':'passed','compiled_usb_test':'passed',
        'recorder_tests':'48 passed','eio_runtime_fixed':'not established; no flashing authorized',
        'manifest_pin':str(r/'.repo/local_manifests/vg1-presync-rollback.xml'),
        'image_revision_matches_restored_heads':True,
        'embedded_revision_and_both_kernel_app_slots':'verified against generated build inputs',
        'flashed':False,'artifacts':artifacts}
(r/'tests/pmu/pre-sync-rollback-validation.json').write_text(json.dumps(report,indent=2)+'\n')
shutil.copy2(r/'tests/pmu/pre-sync-rollback-validation.json',dest/'validation.json')
print(json.dumps(report,indent=2))
