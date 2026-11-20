#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    MOTION_VECTORS_OFF = 0,
    MOTION_VECTORS_CAMERA = 1,
    MOTION_VECTORS_MODELS = 2,
    MOTION_VECTORS_HYBRID = MOTION_VECTORS_CAMERA | MOTION_VECTORS_MODELS,
} MotionVectorsMode;

static inline int motion_vectors_camera(MotionVectorsMode mode) { return (mode & MOTION_VECTORS_CAMERA) != 0; }
static inline int motion_vectors_models(MotionVectorsMode mode) { return (mode & MOTION_VECTORS_MODELS) != 0; }

MotionVectorsMode vk_dlaa_motion_vectors(void);
void vk_dlaa_set_motion_vectors(MotionVectorsMode mode);
int vk_dlaa_model_motion(void);
int vk_dlaa_record_model_motion(void);
int vk_dlaa_reverse_only_requested(void);
void vk_dlaa_set_reverse_only(int enabled);
int vk_dlaa_reverse_only(void);

#ifdef __cplusplus
}
#endif
