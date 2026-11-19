#pragma once
#include <stddef.h>
#include <string.h>
#include "scene_projection.h"

// Only the private previous-position camera bank is rewritten. The game's
// current raster bank and previous-depth sampling retain their jitter.
static inline int scene_motion_previous_bank(void *out, const void *bank, size_t size,
                                             uint64_t token, uint64_t camera, const SceneProjection *previous) {
    if (!previous || !token || token != previous->token || camera != previous->camera ||
        size != SCENE_CAMERA_BYTES || memcmp((const char *)bank + 0x70, previous->projection, 64)) return 0;
    float view[12], vp[16];
    memcpy(view, bank, sizeof view);
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 4; c++) {
            const float *p = previous->unjittered + 4 * r;
            vp[4 * r + c] = (float)((double)p[0] * view[c] + (double)p[1] * view[4 + c] +
                                      (double)p[2] * view[8 + c] + (c == 3 ? p[3] : 0));
        }
    if (out != bank) memcpy(out, bank, size);
    memcpy((char *)out + 0x30, vp, sizeof vp);
    memcpy((char *)out + 0x70, previous->unjittered, sizeof previous->unjittered);
    return 1;
}
