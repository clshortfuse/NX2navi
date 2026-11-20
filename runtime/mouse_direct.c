// v111 camera input adds mouse counts after the stick response, before inversion and activity detection.
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "input.h"
#include "input_wsys.h"
#include "platform/platform.h"

#if __has_include("patches.h")
#include "patches.h"
#endif

static int direct_mode(void) {
    // cfg_value: unset is the settings table's default (direct), as the menu shows it
    return !strcmp(cfg_value("NX2NAVI_MOUSE_MODE"), "direct") && rt_patch_enabled(rt_patch_set("mouse_direct"));
}

static uint64_t last_update;
static int accepts_mouse;

int input_direct_mouse_active(void) {
    uint64_t last = __atomic_load_n(&last_update, __ATOMIC_ACQUIRE);
    return direct_mode() && __atomic_load_n(&accepts_mouse, __ATOMIC_RELAXED) && last &&
           plat_now_ns() - last < 150000000ull;
}

int input_direct_mouse_available(void) { return rt_patch_enabled(rt_patch_set("mouse_direct")); }

#ifdef RT_PATCH_PAGE
#define HOST_MOUSE_DIRECT (RT_PATCH_PAGE + 0xfd0)
#define HOST_MOUSE_ACTIVITY (RT_PATCH_PAGE + 0xfc0)
static _Thread_local uint64_t mouse_input_object;

static float guest_float(uint64_t at) { float f; memcpy(&f, (void *)(uintptr_t)at, sizeof f); return f; }

// At the input hook, s1 and s0 hold the processed stick axes, x20 the input object, and x21 the camera flags.
#define OOT_STICK 0x538         // the processed stick: x, and y at +0x53c
#define OOT_RESET_TIMER 0x5e0   // 60 Hz frames left of the pause after a camera reset (right stick click)
#define OOT_FLAG_IDLE 0x10u     // flags (+0x530): the processed stick is under the game's 10% idle threshold

// NX2NAVI_MOUSE_TRACE=1 (test runs): one line per camera input update, with the stick the update made, the counts taken
// and what they added. vk_dlaa.c adds the camera's direction per frame, so a scripted run gives degrees per count.
static int mouse_trace(void) {
    static int on = -1;
    if (on < 0) {
        const char *e = cfg_get("NX2NAVI_MOUSE_TRACE");
        on = e && *e && strcmp(e, "0");
    }
    return on;
}

static void camera_input_oot(Cpu *c) {
    mouse_input_object = 0;
    uint64_t object = c->x[20], now = plat_now_ns();
    uint32_t flags = (uint32_t)c->x[21];
    float timer = guest_float(object + OOT_RESET_TIMER);
    int accept = !(flags & 1) && !(timer > 0);
    __atomic_store_n(&accepts_mouse, accept, __ATOMIC_RELAXED);
    __atomic_store_n(&last_update, now, __ATOMIC_RELEASE);
    float x, y, add[2] = {0, 0}, frames = frame_step_frames();
    memcpy(&x, &c->v[1], sizeof x);
    memcpy(&y, &c->v[0], sizeof y);
    int32_t dx = 0, dy = 0;
    if (direct_mode()) {
        input_direct_mouse_sample(accept, &dx, &dy);
        float sensitivity = fminf(10, fmaxf(0, (float)cfg_double("NX2NAVI_MOUSE_SENS")));
        // The game multiplies the processed stick by the frames it steps and by its camera speeds, which
        // NX2NAVI_STICK_SENS scales (camera_speed.c): divided by both, a count turns the camera by the same angle at
        // every frame rate and stick speed. Nothing after the site clamps the sum, so a fast flick is not cut short.
        float per = frames * cam_speed_applied();
        if (accept && sensitivity > 0 && isfinite(per) && per > 0 && (dx || dy)) {
            mouse_input_object = object;
            add[0] = dx * (float)INPUT_OOT_COUNT_X * sensitivity / per;
            add[1] = -dy * (float)INPUT_OOT_COUNT_Y * sensitivity / per;
            float nx = x + add[0], ny = y + add[1];
            uint32_t xb, yb;
            memcpy(&xb, &nx, sizeof xb);
            memcpy(&yb, &ny, sizeof yb);
            c->v[1] = xb;
            c->v[0] = yb;
            static int logged;
            if (!logged) {
                logged = 1;
                rt_log("mouse: direct camera input after the stick dead zone, clamp and exponent (Ocarina 1.1.1)");
            }
        }
    }
    if (mouse_trace())
        rt_log("mousetrace: in t=%.3f frames=%.4f flags=%x accept=%d timer=%.2f stick=%.5f,%.5f counts=%d,%d add=%.5f,%.5f",
               now / 1e6, frames, flags, accept, timer, x, y, dx, dy, add[0], add[1]);
    uint32_t original = (uint32_t)c->v[1];
    memcpy((void *)(uintptr_t)(object + OOT_STICK), &original, sizeof original);   // displaced str s1, [x20, #0x538]
}

// The idle test follows the first site and already counts the mouse's part, but one slow count adds less than the
// game's 10% threshold: an update the mouse moved in is not idle. The site is the displaced ldp d9, d8, [sp, #0x10]
// before the update's last `str w8, [x20, #0x530]`, with the flags in w8.
static void camera_activity_oot(Cpu *c) {
    if (mouse_input_object && mouse_input_object == c->x[20]) {
        c->x[8] = (uint32_t)c->x[8] & ~OOT_FLAG_IDLE;
        mouse_input_object = 0;
    }
    uint64_t d9, d8;
    memcpy(&d9, (const void *)(uintptr_t)(c->sp + 0x10), sizeof d9);
    memcpy(&d8, (const void *)(uintptr_t)(c->sp + 0x18), sizeof d8);
    c->v[9] = d9;
    c->v[8] = d8;
}

__attribute__((constructor)) static void mouse_direct_register(void) {
    rt_register_host(HOST_MOUSE_DIRECT, camera_input_oot);
    rt_register_host(HOST_MOUSE_ACTIVITY, camera_activity_oot);
}
#endif
