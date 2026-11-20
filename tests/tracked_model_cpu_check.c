#include <assert.h>
#include <stdarg.h>
#include <stdlib.h>
#include <stdio.h>
#include "host.h"
#include "platform/platform.h"
void plat_mutex_lock(PlatMutex *m) { (void)m; }
void plat_mutex_unlock(PlatMutex *m) { (void)m; }
void rt_fatal(const char *fmt, ...) { abort(); }
void rt_log(const char *fmt, ...) { (void)fmt; }
#include "tracked_model_cpu_impl.h"

static void put64(void *a, uint64_t v) { memcpy(a, &v, 8); }
int main(void) {
    uint8_t owner[0x200] = {0}, resource[128] = "FMDL", producer[80] = {0};
    uint8_t shape[0x70] = {0}, parts[0x90] = {0}, palettes[0x90] = {0}, storage[1024];
    uint8_t *wrapper = owner + 0xd8;
    pool_t pool = {.mem = storage, .size = sizeof storage};
    buf_t buffers[4] = {
        {MAGIC('B','U','F',0), &pool, 0, 48}, {MAGIC('B','U','F',0), &pool, 64, 48},
        {MAGIC('B','U','F',0), &pool, 256, 256}, {MAGIC('B','U','F',0), &pool, 512, 256}
    };
    put64(wrapper, (uintptr_t)resource);
    wrapper[0x18] = 2; wrapper[0x1c] = 1;
    put64(wrapper + 0x20, (uintptr_t)producer);
    put64(wrapper + 0x28, (uintptr_t)shape);
    producer[0xa] = 2;
    put64(producer + 0x38, (uintptr_t)palettes);
    put64(shape + 0x20, (uintptr_t)parts); shape[0xf] = 2;
    for (int slot = 0; slot < 2; slot++) {
        uint8_t *palette = palettes + slot * 0x48, *part = parts + slot * 0x48;
        put64(palette + 8, (uintptr_t)(palette + 0x10));
        put64(part + 8, (uintptr_t)(part + 0x10));
        memcpy(palette + 0x10, &buffers[slot], sizeof(buf_t));
        memcpy(part + 0x10, &buffers[slot + 2], sizeof(buf_t));
    }
    TrackedModelSample first, second;
    uint64_t w = (uintptr_t)wrapper;
    assert(!model_capture((uintptr_t)owner, 0, &first));
    model_life_begin(w);
    assert(model_capture((uintptr_t)owner, 0, &first));
    assert(first.palette[1] == (uintptr_t)(storage + 64) && first.part[1] == (uintptr_t)(storage + 512));
    assert(first.palette_size == 48 && first.part_size == 256);
    model_refresh(w);
    uint8_t work[0x20] = {0};
    put64(work + 8, (uintptr_t)owner);
    assert(tracked_model_work_sample((uintptr_t)work).identity == first.identity);
    work[0x18] = 1;
    assert(!tracked_model_work_sample((uintptr_t)work).identity);
    work[0x18] = 0;
    uint64_t address = (uintptr_t)(storage + 512);
    TrackedModelSample recorded = tracked_model_resolve(address, 256);
    assert(recorded.identity == first.identity);
    assert(!tracked_model_resolve(address, 257).identity);
    address = (uintptr_t)(storage + 256);
    buffers[2].off = 768;
    memcpy(parts + 0x10, &buffers[2], sizeof(buf_t));
    model_refresh(w);
    assert(!tracked_model_resolve(address, 256).identity);
    address = (uintptr_t)(storage + 768);
    assert(tracked_model_resolve(address, 256).identity == first.identity);
    buffers[2].off = 512;
    memcpy(parts + 0x10, &buffers[2], sizeof(buf_t));
    model_refresh(w);
    address = (uintptr_t)(storage + 512);
    assert(tracked_model_resolve(address, 256).identity == first.identity);
    buffers[2].off = 256;
    memcpy(parts + 0x10, &buffers[2], sizeof(buf_t));
    model_refresh(w);
    uint8_t other_owner[sizeof owner];
    memcpy(other_owner, owner, sizeof owner);
    uint64_t other_wrapper = (uintptr_t)(other_owner + 0xd8);
    model_life_begin(other_wrapper);
    model_refresh(other_wrapper);
    assert(!tracked_model_resolve(address, 256).identity);
    model_life_end(other_wrapper);
    assert(tracked_model_resolve(address, 256).identity == first.identity);
    assert(!model_capture((uintptr_t)owner, 1, &second));
    model_life_end(w);
    assert(!tracked_model_work_sample((uintptr_t)work).identity);
    assert(!tracked_model_resolve(address, 256).identity);
    assert(recorded.identity == first.identity);
    assert(!model_capture((uintptr_t)owner, 0, &second));
    model_life_begin(w);
    assert(model_capture((uintptr_t)owner, 0, &second));
    assert(second.identity != first.identity);
    model_refresh(w);
    assert(tracked_model_resolve(address, 256).identity == second.identity);
    shape[0xf] = 1;
    assert(model_capture((uintptr_t)owner, 0, &second));
    assert(second.part[1] == 0);
    producer[0xa] = 1;
    assert(model_capture((uintptr_t)owner, 0, &second));
    shape[0xf] = 2;
    assert(!model_capture((uintptr_t)owner, 0, &second));
    shape[0xf] = 1;
    buffers[0].off = -1;
    memcpy(palettes + 0x10, &buffers[0], sizeof(buf_t));
    assert(!model_capture((uintptr_t)owner, 0, &second));
    put64(palettes + 8, 0xffff00ff);
    assert(!model_capture((uintptr_t)owner, 0, &second));
    model_life_end(w);
    TrackedModelSample sample = {.identity = 1, .part = {16, 32}, .palette = {64, 128},
                                 .part_size = 256, .palette_size = 48};
    assert(tracked_model_palette_matches(&sample, 16, 256, 64, 48, 48));
    assert(tracked_model_palette_matches(&sample, 32, 256, 128, 48, 48));
    assert(!tracked_model_palette_matches(&sample, 16, 256, 128, 48, 48));
    assert(!tracked_model_palette_matches(&sample, 32, 255, 128, 48, 48));
    assert(!tracked_model_palette_matches(&sample, 32, 256, 128, 64, 48));
    assert(!tracked_model_palette_matches(&sample, 32, 256, 128, 48, 64));
    assert(!tracked_model_palette_matches(&sample, 32, 256, 128, 48, 0));
    sample.identity = 0;
    assert(!tracked_model_palette_matches(&sample, 32, 256, 128, 48, 48));
    puts("model lifetime: construction, teardown, address reuse, immutable captured identity, descriptor ranges PASS");
    return 0;
}
