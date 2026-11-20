#pragma once
#include <stdint.h>

typedef struct {
    uint64_t identity, palette[2], part[2];
    uint32_t palette_size, part_size, shape;
} TrackedModelSample;

static inline int tracked_model_palette_matches(const TrackedModelSample *model, uint64_t part, uint64_t part_size,
                                                uint64_t palette, uint64_t palette_size, unsigned matrix_stride) {
    if (!model->identity || !part || !palette || !part_size || !palette_size || !matrix_stride ||
        palette_size % matrix_stride || part_size != model->part_size || palette_size != model->palette_size) return 0;
    for (int i = 0; i < 2; i++)
        if (part == model->part[i] && palette == model->palette[i]) return 1;
    return 0;
}

#ifdef NX2NAVI_PROFILE_OWNERSHIP
typedef struct { uint64_t packets, captured, work_calls, work_hits; } TrackedModelCpuStats;
#endif
#ifdef __cplusplus
extern "C" {
#endif
TrackedModelSample tracked_model_resolve(uint64_t address, uint64_t size);
TrackedModelSample tracked_model_work_sample(uint64_t entry);
#ifdef NX2NAVI_PROFILE_OWNERSHIP
TrackedModelCpuStats tracked_model_cpu_stats(void);
#endif
#ifdef __cplusplus
}
#endif
