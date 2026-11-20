// Included once by patches.c; all pointers originate in checked guest call sites.
#include "tracked_model.h"
#include "nvn_api.h"
#include "nvn_hmap.h"

static PlatMutex model_cpu_lock = PLAT_MUTEX_INIT;
static struct ModelLife {
    uint64_t wrapper, identity;
    TrackedModelSample *shapes;
    unsigned count;
    struct ModelLife *next;
} *model_lives;
static uint64_t model_next_identity;
#ifdef NX2NAVI_PROFILE_OWNERSHIP
static TrackedModelCpuStats model_cpu_stats;
#endif
static nvn_hmap model_parts = {.klen = 2 * sizeof(uint64_t)};
static int model_parts_dirty;
typedef struct { const TrackedModelSample *sample; int ambiguous; } ModelPart;

static void model_parts_rebuild(void) {
    nvn_hm_clear(&model_parts, free);
    for (struct ModelLife *p = model_lives; p; p = p->next) for (unsigned i = 0; i < p->count; i++) {
        const TrackedModelSample *s = &p->shapes[i];
        for (int slot = 0; slot < 2; slot++) {
            if (!s->part[slot]) continue;
            uint64_t key[2] = {s->part[slot], s->part_size};
            ModelPart *part = nvn_hm_get(&model_parts, key);
            if (part) {
                if (part->sample->identity != s->identity || part->sample->shape != s->shape) part->ambiguous = 1;
            } else {
                part = malloc(sizeof *part);
                if (!part) rt_fatal("tracked models: cannot allocate part index");
                *part = (ModelPart){.sample = s};
                nvn_hm_put(&model_parts, key, part);
            }
        }
    }
    model_parts_dirty = 0;
}
#ifdef NX2NAVI_PROFILE_OWNERSHIP
TrackedModelCpuStats tracked_model_cpu_stats(void) {
    TrackedModelCpuStats out;
    out.packets = __atomic_load_n(&model_cpu_stats.packets, __ATOMIC_RELAXED);
    out.captured = __atomic_load_n(&model_cpu_stats.captured, __ATOMIC_RELAXED);
    out.work_calls = __atomic_load_n(&model_cpu_stats.work_calls, __ATOMIC_RELAXED);
    out.work_hits = __atomic_load_n(&model_cpu_stats.work_hits, __ATOMIC_RELAXED);
    return out;
}
#endif

static uint64_t model_u64(uint64_t a) { uint64_t v; memcpy(&v, (const void *)(uintptr_t)a, 8); return v; }
static uint16_t model_u16(uint64_t a) { uint16_t v; memcpy(&v, (const void *)(uintptr_t)a, 2); return v; }
static uint8_t model_u8(uint64_t a) { uint8_t v; memcpy(&v, (const void *)(uintptr_t)a, 1); return v; }

static void model_life_end(uint64_t wrapper) {
    plat_mutex_lock(&model_cpu_lock);
    struct ModelLife **p = &model_lives;
    while (*p && (*p)->wrapper != wrapper) p = &(*p)->next;
    if (*p) {
        struct ModelLife *old = *p; *p = old->next;
        model_parts_dirty = 1;
        free(old->shapes); free(old);
    }
    plat_mutex_unlock(&model_cpu_lock);
}

static void model_life_begin(uint64_t wrapper) {
    model_life_end(wrapper);
    struct ModelLife *life = malloc(sizeof *life);
    if (!life) rt_fatal("tracked models: out of memory for instance lifetime");
    plat_mutex_lock(&model_cpu_lock);
    if (model_next_identity == UINT64_MAX) rt_fatal("tracked models: instance identity exhausted");
    *life = (struct ModelLife){.wrapper = wrapper, .identity = ++model_next_identity, .next = model_lives};
    model_lives = life;
    plat_mutex_unlock(&model_cpu_lock);
}

static uint64_t model_life_id(uint64_t wrapper) {
    uint64_t id = 0;
    plat_mutex_lock(&model_cpu_lock);
    for (struct ModelLife *p = model_lives; p; p = p->next)
        if (p->wrapper == wrapper) { id = p->identity; break; }
    plat_mutex_unlock(&model_cpu_lock);
    return id;
}

static int model_descriptor(uint64_t descriptor, uint64_t *address, uint32_t *size) {
    uint64_t buffer_address = model_u64(descriptor + 8);
    // Only this owned-output layout embeds an NVN buffer; other descriptor variants are unsupported.
    if (buffer_address != descriptor + 0x10) return 0;
    const buf_t *buffer = (const buf_t *)(uintptr_t)buffer_address;
    if (!buffer || buffer->magic != MAGIC('B', 'U', 'F', 0) || !buffer->pool || buffer->off < 0 ||
        buffer->off > buffer->pool->size || buffer->size > buffer->pool->size - buffer->off ||
        !buffer->size || buffer->size > UINT32_MAX) return 0;
    *address = (uint64_t)(uintptr_t)buffer->pool->mem + buffer->off;
    *size = (uint32_t)buffer->size;
    return 1;
}

static int model_capture(uint64_t owner, unsigned shape_index, TrackedModelSample *out) {
    uint64_t wrapper = owner + 0xd8;
    memset(out, 0, sizeof *out);
    out->identity = model_life_id(wrapper);
    if (!out->identity) return 0;
    uint64_t resource = model_u64(wrapper), producer = model_u64(wrapper + 0x20);
    if (!resource || memcmp((const void *)(uintptr_t)resource, "FMDL", 4) || !producer ||
        shape_index >= model_u16(wrapper + 0x1c)) return 0;
    uint64_t shape = model_u64(wrapper + 0x28) + shape_index * 0x70ull;
    unsigned slots = model_u8(shape + 0xf);
    if (!slots || slots > 2 || slots > model_u8(producer + 0xa)) return 0;
    uint64_t parts = model_u64(shape + 0x20), palettes = model_u64(producer + 0x38);
    if (!parts || !palettes) return 0;
    for (unsigned slot = 0; slot < slots; slot++) {
        uint32_t pn, sn;
        if (!model_descriptor(palettes + slot * 0x48, &out->palette[slot], &pn) ||
            !model_descriptor(parts + slot * 0x48, &out->part[slot], &sn)) return 0;
        if (slot && (pn != out->palette_size || sn != out->part_size)) return 0;
        out->palette_size = pn; out->part_size = sn;
    }
    out->shape = shape_index;
    return 1;
}

static void model_refresh(uint64_t wrapper) {
    unsigned count = model_u16(wrapper + 0x1c);
    if (!count || count > 512) return;
    uint64_t identity = model_life_id(wrapper);
    if (!identity) return;
    TrackedModelSample *shapes = calloc(count, sizeof *shapes);
    if (!shapes) rt_fatal("tracked models: cannot allocate shape registration");
    unsigned n = 0;
    for (unsigned i = 0; i < count; i++)
        if (model_capture(wrapper - 0xd8, i, &shapes[n])) n++;
    plat_mutex_lock(&model_cpu_lock);
    for (struct ModelLife *p = model_lives; p; p = p->next) {
        if (p->wrapper != wrapper || p->identity != identity) continue;
        free(p->shapes);
        p->shapes = shapes; p->count = n; shapes = NULL;
        model_parts_dirty = 1;
        break;
    }
    plat_mutex_unlock(&model_cpu_lock);
    free(shapes);
}

TrackedModelSample tracked_model_work_sample(uint64_t entry) {
#ifdef NX2NAVI_PROFILE_OWNERSHIP
    __atomic_fetch_add(&model_cpu_stats.work_calls, 1, __ATOMIC_RELAXED);
#endif
    TrackedModelSample out = {0};
    uint64_t owner = entry ? model_u64(entry + 8) : 0;
    if (!owner) return out;
    unsigned shape = model_u16(entry + 0x18);
    plat_mutex_lock(&model_cpu_lock);
    for (struct ModelLife *p = model_lives; p; p = p->next) {
        if (p->wrapper != owner + 0xd8) continue;
        for (unsigned i = 0; i < p->count; i++) {
            if (p->shapes[i].shape != shape) continue;
            out = p->shapes[i];
            break;
        }
        break;
    }
    plat_mutex_unlock(&model_cpu_lock);
#ifdef NX2NAVI_PROFILE_OWNERSHIP
    if (out.identity) __atomic_fetch_add(&model_cpu_stats.work_hits, 1, __ATOMIC_RELAXED);
#endif
    return out;
}

TrackedModelSample tracked_model_resolve(uint64_t address, uint64_t size) {
    TrackedModelSample out = {0};
    // Camera state may be inherited from another recording; replay validates it at the actual draw.
    if (!size) return out;
#ifdef NX2NAVI_PROFILE_OWNERSHIP
    __atomic_fetch_add(&model_cpu_stats.packets, 1, __ATOMIC_RELAXED);
#endif
    int ambiguous = 0;
    plat_mutex_lock(&model_cpu_lock);
    if (model_parts_dirty) model_parts_rebuild();
    uint64_t key[2] = {address, size};
    const ModelPart *part = nvn_hm_get(&model_parts, key);
    // Palette bindings may be inherited; replay still validates them at the draw.
    if (part) out = *part->sample, ambiguous = part->ambiguous;
    plat_mutex_unlock(&model_cpu_lock);
    if (ambiguous) {
        return (TrackedModelSample){0};
    }
#ifdef NX2NAVI_PROFILE_OWNERSHIP
    if (out.identity) __atomic_fetch_add(&model_cpu_stats.captured, 1, __ATOMIC_RELAXED);
#endif
    return out;
}

#ifdef RT_PATCH_PAGE
#ifndef MOD_MAIN_BASE
#include "layout.h"
#endif
static void model_construct_hook(Cpu *c) {
    uint64_t wrapper = c->x[0];
    c->pc = MOD_MAIN_BASE + 0x4fe0a0;
    rt_dispatch(c);
    if (c->x[0]) model_life_begin(wrapper);
}

static void model_destroy_hook(Cpu *c) {
    model_life_end(c->x[0]);
    c->pc = MOD_MAIN_BASE + 0x4fa780;
    rt_dispatch(c);
}

static void model_buffers_hook(Cpu *c) {
    uint64_t wrapper = c->x[0];
    c->pc = MOD_MAIN_BASE + 0x4fc180;
    rt_dispatch(c);
    if (c->x[0]) model_refresh(wrapper);
}

__attribute__((constructor)) static void model_hooks_register(void) {
    if (!RT_V111) return;
    rt_register_host(RT_PATCH_PAGE + 0xe10, model_construct_hook);
    rt_register_host(RT_PATCH_PAGE + 0xe00, model_destroy_hook);
    rt_register_host(RT_PATCH_PAGE + 0xe20, model_buffers_hook);
}
#endif
