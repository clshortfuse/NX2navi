#pragma once
#include <stdint.h>

#define SCENE_CAMERA_BYTES 0x3500
#define SCENE_PROJECTION_WORD 28
#define SCENE_PROJECTION_SHIFTED (UINT64_C(1) << 63)

typedef struct {
    uint64_t token, owner, camera, generation;
    uint32_t index, width, height, settings;
    uint32_t native_extent[4];   // color width/height, depth width/height before host scaling
    float jitter[2], projection[16], unjittered[16], view[12];
} SceneProjection;

int scene_projection_enabled(void);
// A shifted projection is built for a specific render extent.
static inline int scene_projection_extent_matches(const SceneProjection *sample, uint32_t width, uint32_t height) {
    return sample->token && (!(sample->token & SCENE_PROJECTION_SHIFTED) ||
                             (sample->width == width && sample->height == height));
}

typedef struct p_scene_projection p_scene_projection;
int scene_projection_binding(uint64_t address, p_scene_projection *out);
int scene_projection_describe(p_scene_projection *out, const SceneProjection *sample, const void *color,
                              const void *depth, const uint8_t cv[16], const uint8_t dv[16]);
int scene_projection_extent(const void *texture, const uint8_t raw_view[16], uint32_t *w, uint32_t *h);
int scene_projection_record(void *command, const SceneProjection *sample, const void *color,
                             const void *depth, const uint8_t color_view[16], const uint8_t depth_view[16]);
void scene_projection_feedback(const SceneProjection *sample, uint32_t width, uint32_t height, uint32_t phases);
