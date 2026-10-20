"""Exercise the actual INT4 sampling wrapper with unavailable hardware."""
from pathlib import Path
import subprocess
import tempfile
import sys

r = Path(__file__).resolve().parents[2]
p = r/'src/rtsmart/rtsmart/kernel/bsp/maix3/drivers/interdrv/pmu'
source = (Path(sys.argv[1]) if len(sys.argv)>1 else p/'drv_pmu.c').read_text()
sample = source[source.index('static void pmu_int4_sample_work'):source.index('static void pmu_int4_timer_cb')]
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "pmu_int4_monitor.h"
#define RT_NULL NULL
#define RT_EOK 0
#define PMU_IO_CFG_4 4
#define PMU_IO_CFG_IO_SEL_MASK 3U
#define PMU_IO_CFG_GPIO_SEL 1U
#define PMU_IO_CFG_IE 4U
#define PMU_IO_CFG_OE 8U
#define PMU_SHUTDOWN_INT4 2U
#define rt_kprintf(...) ((void)0)
typedef int rt_base_t;
struct pmu_dev {
    struct { uint32_t generation; bool registered, shutdown_started; } notify;
    struct pmu_int4_monitor int4_monitor;
};
static bool gpio_available;
static unsigned gpio_reads, mux_reads, requests, now;
static uint32_t mux = PMU_IO_CFG_GPIO_SEL | PMU_IO_CFG_IE;
static int input;
void *rt_device_find(const char *name) {
    assert(!strcmp(name,"gpio")); return gpio_available ? (void*)1 : NULL;
}
static int rt_hw_interrupt_disable(void) { return 0; }
static void rt_hw_interrupt_enable(int level) { (void)level; }
static uint32_t rt_tick_get(void) { return now; }
static uint32_t rt_tick_from_millisecond(int ms) { return ms; }
static uint32_t pmu_readl(struct pmu_dev *p, unsigned reg) {
    assert(gpio_available && p->notify.registered && !p->notify.shutdown_started);
    assert(reg==PMU_IO_CFG_4); mux_reads++; return mux;
}
static unsigned kd_pin_get_dr(unsigned pin) {
    assert(gpio_available && pin==68); gpio_reads++; return input;
}
static int pmu_notify_send_shutdown_request(struct pmu_dev *p,unsigned reason,unsigned gen) {
    assert(reason==PMU_SHUTDOWN_INT4 && gen==p->notify.generation);
    requests++; return 0;
}
'''+sample+r'''
int main(void) {
    struct pmu_dev p={0};
    /* PREV init/timer before GPIO device init: must not touch MMIO. */
    for(now=0;now<500;now+=20) pmu_int4_sample_work(&p);
    assert(!mux_reads && !gpio_reads && !requests);
    /* A listener cannot bypass an unavailable GPIO driver. */
    p.notify.registered=true;
    for(now=500;now<1000;now+=20) pmu_int4_sample_work(&p);
    assert(!mux_reads && !gpio_reads && !requests);
    gpio_available=true; p.notify.registered=false;
    pmu_int4_sample_work(&p);
    assert(!mux_reads && !gpio_reads);
    p.notify.registered=true;
    for(now=1000;now<1500;now+=20) pmu_int4_sample_work(&p);
    assert(gpio_reads && !requests); /* Initial low must keep power. */
    input=1;
    for(now=1500;now<=1600;now+=20) pmu_int4_sample_work(&p);
    assert(p.int4_monitor.armed && !requests);
    input=0;
    for(now=1620;now<=1720;now+=20) pmu_int4_sample_work(&p);
    assert(requests==1);
    input=1;
    for(now=1740;now<2000;now+=20) pmu_int4_sample_work(&p);
    assert(requests==1 && p.int4_monitor.pending);
    unsigned before=gpio_reads;
    p.notify.shutdown_started=true; pmu_int4_sample_work(&p);
    assert(gpio_reads==before);
    p.notify.shutdown_started=false; mux=PMU_IO_CFG_GPIO_SEL | PMU_IO_CFG_IE | PMU_IO_CFG_OE;
    pmu_int4_sample_work(&p); assert(gpio_reads==before);
    assert(!p.int4_monitor.armed && !p.int4_monitor.pending);
    puts("INT4 startup wrapper tests passed");
}
'''
with tempfile.TemporaryDirectory(prefix='pmu-startup-') as d:
    c = Path(d)/'test.c'
    c.write_text(harness)
    exe = Path(d)/'test'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(p),str(c),'-o',str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
