#include <assert.h>
#include <stdio.h>
#include "scene_motion_projection.h"

int main(void) {
    float raster[SCENE_CAMERA_BYTES / sizeof(float)] = {0}, motion[SCENE_CAMERA_BYTES / sizeof(float)] = {0};
    const float view[12] = {0, 1, 0, 3, -1, 0, 0, 5, 0, 0, 1, 7};
    const float clean[16] = {2, 0, .25f, 0, 0, 3, -.5f, 0, 0, 0, 1, 2, 0, 0, -1, 0};
    const float combined[16] = {0, 2, .25f, 7.75f, -3, 0, -.5f, 11.5f, 0, 0, 1, 9, 0, 0, -1, -7};
    SceneProjection previous = {.token = SCENE_PROJECTION_SHIFTED | 17, .camera = 123};
    memcpy(previous.unjittered, clean, sizeof clean);
    memcpy(previous.projection, clean, sizeof clean);
    previous.projection[2] += .125f;
    previous.projection[6] -= .25f;
    memcpy(raster, view, sizeof view);
    memcpy(raster + 12, combined, sizeof combined);
    raster[14] += .125f;
    raster[18] -= .25f;
    memcpy(raster + 28, previous.projection, sizeof clean);
    raster[44] = 88;
    assert(!scene_motion_previous_bank(motion, raster, sizeof raster, previous.token + 1, previous.camera, &previous));
    assert(!scene_motion_previous_bank(motion, raster, sizeof raster, previous.token, previous.camera + 1, &previous));
    assert(!scene_motion_previous_bank(motion, raster, sizeof raster - 1, previous.token, previous.camera, &previous));
    raster[30] += 1;
    assert(!scene_motion_previous_bank(motion, raster, sizeof raster, previous.token, previous.camera, &previous));
    raster[30] -= 1;
    assert(scene_motion_previous_bank(motion, raster, sizeof raster, previous.token, previous.camera, &previous));
    assert(!memcmp(motion, view, sizeof view));
    assert(!memcmp(motion + 12, combined, sizeof combined));
    assert(!memcmp(motion + 28, clean, sizeof clean));
    assert(motion[44] == 88 && raster[30] == previous.projection[2] && raster[14] != motion[14]);
    previous.width = 1920, previous.height = 1080;
    assert(scene_projection_extent_matches(&previous, 1920, 1080));
    assert(!scene_projection_extent_matches(&previous, 2560, 1440));
    previous.token &= ~SCENE_PROJECTION_SHIFTED;
    assert(scene_projection_extent_matches(&previous, 2560, 1440));
    previous.token = 0;
    assert(!scene_projection_extent_matches(&previous, 1920, 1080));
    puts("Verified projection extent and unjittered previous projection and combined VP.");
}
