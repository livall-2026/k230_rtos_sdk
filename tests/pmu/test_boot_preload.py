"""Exercise the actual SPL layout helpers with the built application size."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'src/uboot/uboot/board/kendryte/common/k230_boot.c').read_text()
helpers = source[source.index('unsigned long k230_get_rttapp_load_addr'):source.index('static ulong k230_get_encrypted_image_buffer_size')]
validate = source[source.index('static int k230_validate_image_layout'):source.index('static int k230_boot_decomp_to_load_addr')]
image = root / 'output/k230d_canmv_bpi_zero_defconfig/canmv/micropython'
size = image.stat().st_size
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef unsigned long ulong;
static unsigned long long g_dram_base;
static ulong g_dram_size;
typedef struct { ulong load; int comp; } image_header_t;
#define IH_COMP_GZIP 1
static ulong image_get_load(image_header_t *h) { return h->load; }
static int image_get_comp(image_header_t *h) { return h->comp; }
static const char *image_get_name(image_header_t *h) { (void)h; return "rtapp"; }
''' + helpers + validate + r'''
int main(void) {
    ulong end;
    g_dram_base = 0;
    g_dram_size = 128UL * 1024 * 1024;
    image_header_t h = {k230_get_rttapp_load_addr(), IH_COMP_GZIP};
    ulong actual_size = ACTUAL_SIZE;
    assert(h.load == 0x5555000UL);
    assert(actual_size > 0 && actual_size <= g_dram_size - h.load);
    assert(k230_validate_image_layout(&h, 64UL << 20, 18UL << 20, actual_size) == 0);
    /* Preserve the upstream rejection of the original unstripped ELF. */
    assert(k230_validate_image_layout(&h, 64UL << 20, 18UL << 20, 46216800) < 0);
    assert(k230_validate_image_layout(&h, h.load, 4096, actual_size) < 0);
    assert(!k230_calc_range_end(~0UL, 1, &end));

    puts("Upstream SPL layout accepts release ELF and rejects oversize and source overlap");
}
'''
with tempfile.TemporaryDirectory(prefix='k230-preload-') as work:
    c = Path(work) / 'test.c'
    exe = Path(work) / 'test'
    c.write_text(harness)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-DACTUAL_SIZE=' + str(size), str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
