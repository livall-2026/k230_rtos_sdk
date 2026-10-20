"""Compile and exercise the actual PMU notification functions and level filter.

Run with python3 tests/pmu/test_pmu_host.py from the SDK root. No board access.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
p = root / 'src/rtsmart/rtsmart/kernel/bsp/maix3/drivers/interdrv/pmu'
priv = (p/'pmu_priv.h').read_text()
user = (p/'pmu_userdev.c').read_text()
notify = user[user.index('static void pmu_notify_reset_locked'):user.index('static rt_err_t pmu_copy_from_user')]

def struct(name):
    return re.search(r'struct '+name+r' \{.*?\n\};', priv, re.S)[0]

key = (p/'pmu_pwrkey.c').read_text()
release = key[key.index('void pmu_pwrkey_handle_release_work'):key.index('void pmu_pwrkey_irq')]

harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "pmu_int4_monitor.h"
#define RT_USING_LWP 1
#define RT_NULL NULL
#define RT_EOK 0
#define RT_ERROR 1
#define RT_EINVAL 2
#define RT_EBUSY 3
#define RT_ENOSYS 4
#define PMU_NOTIFY_DEFAULT_SIGNO 10
#define PMU_SHUTDOWN_KEY 1U
#define PMU_SHUTDOWN_INT4 2U
typedef int rt_int32_t;
typedef int rt_err_t;
typedef int rt_base_t;
typedef void *rt_timer_t;
struct rt_device {int unused;};
static int shutdowns, signal_calls, signal_result;
static int current_pid = 42;
static int rt_hw_interrupt_disable(void) {return 0;}
static void rt_hw_interrupt_enable(int level) {(void)level;}
static int pmu_current_pid(void) {return current_pid;}
static void pmu_do_shutdown(const char *reason) {(void)reason; shutdowns++;}
static int lwp_kill(int pid, int signo) {
    assert(pid==42 && signo==10); signal_calls++; return signal_result;
}
#define rt_kprintf(...) ((void)0)
void pmu_notify_try_shutdown(struct pmu_dev *pmu);
'''
# Define structs before the prototype to avoid function-scope tag declarations.
harness = harness.replace('void pmu_notify_try_shutdown(struct pmu_dev *pmu);', '')
for name in ('pmu_notify_cfg', 'pmu_shutdown_request', 'pmu_notify_state', 'pmu_pwrkey_state'):
    harness += struct(name)+'\n'
harness += '''struct pmu_dev {
    struct pmu_notify_state notify;
    struct pmu_pwrkey_state pwrkey;
    struct pmu_int4_monitor int4_monitor;
};
void pmu_notify_try_shutdown(struct pmu_dev *pmu);
static struct pmu_dev *current_dev;
static struct pmu_dev *pmu_get_dev(void) { return current_dev; }
struct dfs_fd { int unused; };
'''
harness += notify + release
harness += user[user.index('static int pmu_userdev_close'):user.index('static int pmu_userdev_ioctl')]
harness += r'''
static struct pmu_dev fresh(bool polling) {
    struct pmu_dev dev = {0};
    struct pmu_notify_cfg cfg = {42, 0};
    assert(pmu_notify_register(&dev, &cfg, polling, (void *)1)==0);
    return dev;
}
int main(void) {
    struct pmu_int4_monitor s = {0};
    /* Cold boot low never arms, including after application registration. */
    for (unsigned t=0;t<1000;t+=20)
        assert(!pmu_int4_monitor_sample(&s,true,0,t,100));
    assert(!s.armed);
    /* High and low glitches do not arm or request. */
    assert(!pmu_int4_monitor_sample(&s,true,1,1000,100));
    assert(!pmu_int4_monitor_sample(&s,true,0,1080,100));
    assert(!s.armed);
    for (unsigned t=1100;t<=1200;t+=20)
        assert(!pmu_int4_monitor_sample(&s,true,1,t,100));
    assert(s.armed);
    assert(!pmu_int4_monitor_sample(&s,true,0,1220,100));
    assert(!pmu_int4_monitor_sample(&s,true,1,1300,100));
    assert(!pmu_int4_monitor_sample(&s,true,0,1320,100));
    for (unsigned t=1340;t<1420;t+=20)
        assert(!pmu_int4_monitor_sample(&s,true,0,t,100));
    assert(pmu_int4_monitor_sample(&s,true,0,1420,100));
    for (unsigned t=1440;t<2000;t+=20)
        assert(!pmu_int4_monitor_sample(&s,true,t%40==0,t,100));
    assert(s.pending);
    assert(!pmu_int4_monitor_sample(&s,false,1,2020,100));
    assert(!s.armed && !s.pending);
    /* Unsigned tick rollover and invalid readings restart qualification. */
    assert(!pmu_int4_monitor_sample(&s,true,1,UINT32_MAX-50,100));
    assert(!pmu_int4_monitor_sample(&s,true,1,50,100));
    assert(s.armed);
    assert(!pmu_int4_monitor_sample(&s,true,-1,70,100));
    assert(!s.armed);

    struct pmu_dev d = fresh(true);
    struct pmu_notify_cfg cfg = {42, 0};
    struct pmu_shutdown_request req;
    assert(pmu_notify_confirm_shutdown(&d)<0 && shutdowns==0);
    assert(pmu_notify_register(&d,&cfg,true,(void*)2)<0);
    assert(d.notify.owner==(void*)1);
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_INT4,d.notify.generation)==0);
    assert(signal_calls==0 && shutdowns==0);
    assert(pmu_notify_read_request(&d,&req)==0 && req.pending);
    assert(pmu_notify_read_request(&d,&req)==0 && !req.pending);
    /* Duplicate and concurrent key request share one acknowledgement. */
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_KEY,0)==0);
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_INT4,0)==0);
    assert(!d.notify.shutdown_request_pending && shutdowns==0);
    current_pid=7;
    assert(pmu_notify_confirm_shutdown(&d)<0);
    current_pid=42;
    assert(pmu_notify_confirm_shutdown(&d)==0 && shutdowns==1);
    assert(pmu_notify_confirm_shutdown(&d)<0 && shutdowns==1);
    pmu_notify_try_shutdown(&d); assert(shutdowns==1);

    d = fresh(true);
    unsigned generation=d.notify.generation;
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_INT4,generation)==0);
    d.pwrkey.long_press_seen=d.pwrkey.release_seen=true;
    pmu_notify_unregister_pid(&d,42);
    assert(shutdowns==1 && !d.notify.registered && !d.pwrkey.release_seen);
    assert(pmu_notify_register(&d,&cfg,true,(void*)1)==0);
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_INT4,generation)<0);
    assert(!d.notify.reasons && !d.int4_monitor.armed);
    pmu_notify_unregister_pid(&d,42);
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_INT4,0)<0);
    assert(shutdowns==1);

    /* A failed second constructor must not unregister the original listener. */
    current_dev=&d;
    struct dfs_fd first={0}, second={0};
    assert(pmu_notify_register(&d,&cfg,true,&first)==0);
    assert(pmu_notify_register(&d,&cfg,true,&second)<0);
    pmu_userdev_close(&second);
    assert(d.notify.registered && d.notify.owner==&first);
    pmu_userdev_close(&first);
    assert(!d.notify.registered && shutdowns==1);

    /* Key confirmation still waits for release. INT4 can share that cleanup. */
    d=fresh(true);
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_KEY,0)==0);
    assert(pmu_notify_confirm_shutdown(&d)==0 && shutdowns==1);
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_INT4,0)==0);
    assert(shutdowns==2);
    d=fresh(true); d.pwrkey.long_press_seen=true;
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_KEY,0)==0);
    assert(pmu_notify_confirm_shutdown(&d)==0 && shutdowns==2);
    d.pwrkey.release_seen=true;
    pmu_pwrkey_handle_release_work(&d);
    assert(shutdowns==3);

    /* Existing signal registration is retained; failed INT4 delivery holds power. */
    d=fresh(false); signal_result=-1;
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_INT4,0)<0);
    assert(signal_calls==1 && !d.notify.registered && shutdowns==3);
    d=fresh(false); signal_result=0;
    assert(pmu_notify_send_shutdown_request(&d,PMU_SHUTDOWN_KEY,0)==0);
    assert(signal_calls==2 && shutdowns==3);
    puts("PMU host tests: sampled levels, rollover, notification, ownership, acknowledgement and key coexistence passed");
}
'''

with tempfile.TemporaryDirectory(prefix='vg1-pmu-host-') as work:
    source = Path(work)/'test.c'
    binary = Path(work)/'test'
    source.write_text(harness)
    subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',
                    '-Wno-unused-variable','-I'+str(p),str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
