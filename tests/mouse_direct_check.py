"""Check the direct camera hook's register contract and raw-count routing without game data.

Usage: python tests/mouse_direct_check.py --cc <clang.exe>
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# What both harnesses stand in for the rest of the runtime with.
STUBS = r'''
#include <assert.h>
#include <stdio.h>
#include "mouse_direct.c"
static int raw_x, raw_y, takes, captured=1, foreground=1, allowed=1, mode=1, patched=1;
static float frames=1, speed=1;
static double sens=1;
static uint64_t now=1000000000;
static GuestFn hook, activity_hook;
const char *cfg_get(const char *key) { return strcmp(key, "NX2NAVI_MOUSE_MODE") ? NULL : mode ? "direct" : "stick"; }
const char *cfg_value(const char *key) { return cfg_get(key); }
double cfg_double(const char *key) { (void)key; return sens; }
float frame_step_frames(void) { return frames; }
float cam_speed_applied(void) { return speed; }
int rt_patch_set(const char *s) { (void)s; return 0; }
int rt_patch_enabled(int s) { (void)s; return patched; }
int ikb_captured(void) { return captured; }
int ikb_foreground(void) { return foreground; }
int input_cursor_allowed(void) { return allowed; }
void ikb_mouse_take(int32_t *x, int32_t *y) { ++takes; *x=raw_x; *y=raw_y; raw_x=raw_y=0; }
void input_direct_mouse_sample(int enabled, int32_t *x, int32_t *y) {
    *x=*y=0;
    if(enabled && captured && foreground && allowed) ikb_mouse_take(x,y);
}
uint64_t plat_now_ns(void) { return now; }
void rt_register_host(uint64_t addr, GuestFn fn) {
    if(addr==HOST_MOUSE_DIRECT) hook=fn; else if(addr==HOST_MOUSE_ACTIVITY) activity_hook=fn;
    else abort();
}
void rt_log(const char *fmt, ...) { (void)fmt; }
static float scalar(__uint128_t v) { float f; memcpy(&f,&v,4); return f; }
'''

# Ocarina 1.1.1 (recomp/patches-v111.txt, set mouse_direct): the two sites of camera_input_oot and camera_activity_oot.
HARNESS = STUBS + r'''
int main(void) {
    assert(hook && activity_hook);
    Cpu c, expected;
    unsigned char target[0x600] = {0};
    memset(&c, 0x5a, sizeof c);
    c.x[20]=(uintptr_t)target; c.x[21]=0; c.v[1]=c.v[0]=0;
    expected=c;
    // s1 and s0 carry the processed x and y. 100 counts to the right and 50 up, at one frame per update.
    raw_x=100; raw_y=-50;
    hook(&c);
    assert(fabsf(scalar(c.v[1])-100*(float)INPUT_OOT_COUNT_X)<1e-5f);
    assert(fabsf(scalar(c.v[0])-50*(float)INPUT_OOT_COUNT_Y)<1e-5f);
    // The displaced store of s1 at +0x538 carries the mouse's part; the store of s0 at +0x53c is the game's own.
    float stored; memcpy(&stored,target+0x538,4); assert(stored==scalar(c.v[1]));
    memcpy(&stored,target+0x53c,4); assert(stored==0);
    expected.v[1]=c.v[1]; expected.v[0]=c.v[0]; assert(!memcmp(&expected,&c,sizeof c));
    assert(input_direct_mouse_active() && input_direct_mouse_available());
    // The next update sees no repeated movement.
    expected=c; hook(&c); assert(!memcmp(&expected,&c,sizeof c));
    // The game multiplies the processed stick by the frames it steps and by its camera speed: an equal mouse distance
    // gives an equal turn at 30, 60 and 144 fps and at every stick camera speed, and nothing clamps a fast flick.
    float steps[]={2,1,60/144.0f}, speeds[]={1,3};
    for(int i=0;i<3;i++) for(int j=0;j<2;j++) {
        frames=steps[i]; speed=speeds[j]; raw_x=10000; raw_y=10000; c.v[1]=c.v[0]=0; hook(&c);
        assert(fabsf(scalar(c.v[1])*frames*speed-10000*(float)INPUT_OOT_COUNT_X)<0.01f);
        assert(fabsf(scalar(c.v[0])*frames*speed+10000*(float)INPUT_OOT_COUNT_Y)<0.01f);
    }
    frames=speed=1;
    // One count is not discarded by a dead zone, and the sensitivity scales it.
    raw_x=1; raw_y=0; c.v[1]=c.v[0]=0; hook(&c); assert(scalar(c.v[1])>0);
    float one=scalar(c.v[1]);
    sens=2.5; raw_x=1; c.v[1]=c.v[0]=0; hook(&c); assert(fabsf(scalar(c.v[1])-2.5f*one)<1e-6f);
    sens=0; raw_x=1; c.v[1]=c.v[0]=0; hook(&c); assert(c.v[1]==0 && c.v[0]==0); sens=1;
    // The stick's own processed value stays and the mouse adds to it.
    { float px=0.25f, py=-0.5f; uint32_t b; memcpy(&b,&px,4); c.v[1]=b; memcpy(&b,&py,4); c.v[0]=b; }
    raw_x=10; raw_y=0; hook(&c);
    assert(fabsf(scalar(c.v[1])-(0.25f+10*(float)INPUT_OOT_COUNT_X))<1e-6f && scalar(c.v[0])==-0.5f);
    // The idle bit of the flags (w8 at the second site) is cleared for an update the mouse moved in; the site's
    // displaced ldp d9, d8, [sp, #0x10] is performed. The game's next instruction stores w8, so memory is not touched.
    uint64_t stack[4]={0,0,0x123456789abcdef0ull,0x456789abcdef0123ull}; c.sp=(uintptr_t)stack;
    uint32_t idle=0x38, mem=0x77; memcpy(target+0x530,&mem,4);
    c.x[8]=idle; activity_hook(&c);
    assert((uint32_t)c.x[8]==0x28);
    uint32_t after; memcpy(&after,target+0x530,4); assert(after==mem);
    assert(c.v[9]==stack[2] && c.v[8]==stack[3]);
    // A controller-only update keeps the game's idle bit.
    c.v[1]=c.v[0]=0; hook(&c); c.x[8]=idle; activity_hook(&c); assert((uint32_t)c.x[8]==idle);
    // While the pause after a camera reset runs (+0x5e0) or camera input is off (w21 bit 0), the game reads no stick:
    // the counts are left where they are and the registers as the game made them.
    float pause=12; memcpy(target+0x5e0,&pause,4);
    raw_x=42; int before=takes; c.v[1]=c.v[0]=0; expected=c; hook(&c);
    assert(takes==before && raw_x==42 && !memcmp(&expected,&c,sizeof c));
    assert(!input_direct_mouse_active());
    pause=0; memcpy(target+0x5e0,&pause,4);
    c.x[21]=1; hook(&c);
    assert(takes==before && raw_x==42 && !input_direct_mouse_active()); c.x[21]=0;
    // Focus loss and host menus do not move the camera.
    captured=0; hook(&c); assert(takes==before); captured=1;
    foreground=0; hook(&c); assert(takes==before); foreground=1;
    allowed=0; hook(&c); assert(takes==before); allowed=1;
    // Stick emulation: the counts stay for the stick path.
    mode=0; hook(&c);
    assert(takes==before && raw_x==42 && !input_direct_mouse_active()); mode=1;
    patched=0; hook(&c);
    assert(takes==before && !input_direct_mouse_active() && !input_direct_mouse_available()); patched=1;
    raw_x=0; hook(&c); assert(input_direct_mouse_active());
    now+=150000001; assert(!input_direct_mouse_active());
    puts("direct mouse 1.1.1: register contract, displaced store and load, equal turn at every frame rate and stick speed passed");
    puts("direct mouse 1.1.1: single count, sensitivity, stick kept, idle bit, reset pause, capture and mode checks passed");
}
'''

INPUT_HARNESS = r'''
#include <assert.h>
#include "input.c"
GfxStats gfx_counters;
InputMap input_map;
// Other input entry points are linked by PE unwind metadata; reaching them is outside this script-only test.
void ikb_cursor_update(void) { abort(); }
void ikb_menu_closed(void) { abort(); }
void plat_mutex_lock(PlatMutex *m) { assert(m == &lock); }
void plat_mutex_unlock(PlatMutex *m) { assert(m == &lock); }
void plat_cond_signal(PlatCond *c) { (void)c; abort(); }
void plat_cond_wait(PlatCond *c, PlatMutex *m) { (void)c; (void)m; abort(); }
int plat_thread_spawn(PlatThreadFn fn, void *arg, const char *name, size_t stack) {
    (void)fn; (void)arg; (void)name; (void)stack; abort();
}
void rumble_hd_data(const RumbleHdValue v[2], const int live[2], float strength, int one, uint8_t out[RUMBLE_HD_DATA]) {
    (void)v; (void)live; (void)strength; (void)one; (void)out; abort();
}
void rumble_hd_post(RumbleHd *h, const uint8_t data[RUMBLE_HD_DATA], uint64_t now) { (void)h; (void)data; (void)now; abort(); }
void hd_pair_close(int neutral, unsigned wait_ms) { (void)neutral; (void)wait_ms; abort(); }
// The gamepad thread's (sdl_enter, probe_gamepad): not reached by a script.
void plat_wait_ns(uint64_t ns) { (void)ns; abort(); }
int plat_mutex_trylock(PlatMutex *m) { (void)m; abort(); }
int cfg_setenv(const char *name, const char *value) { (void)name; (void)value; abort(); }
const char *SDL_GetGamepadName(SDL_Gamepad *g) { (void)g; abort(); }
int cfg_bool(const char *key) { (void)key; abort(); }
int input_menu_gate(int *h,int open,uint64_t *b,int32_t s[4]) { (void)h;(void)open;(void)b;(void)s;abort(); }
int input_overlay_gate(int *h,uint64_t *b) { (void)h;(void)b;abort(); }
int menu_is_open(void) { abort(); }
void menu_toggle(void) { abort(); }
void perf_segment(const char *name) { (void)name; }   // a script line's mark: no perf trace here
void menu_perf_cycle(void) { abort(); }
const char *input_action_name(int action) { (void)action;abort(); }
void input_map_configure(void) { abort(); }
int input_direct_mouse_active(void) { return 1; }
static const char *script_path;
static uint64_t test_tick;
static int64_t test_world=-1;
const char *cfg_get(const char *key) {
    if (!strcmp(key,"NX2NAVI_INPUT_SCRIPT")) return script_path;
    if (!strcmp(key,"NX2NAVI_INPUT")) return "none";
    return NULL;
}
unsigned cfg_version(void) { return 0; }
double cfg_double(const char *key) { (void)key; return 1; }
uint64_t frame_step_ticks(void) { return test_tick; }
int64_t frame_step_world_us(void) { return test_world; }
void rt_log(const char *fmt, ...) { (void)fmt; }
int ikb_captured(void) { return 0; }
int ikb_foreground(void) { return 0; }
void ikb_mouse_take(int32_t *x,int32_t *y) { *x=*y=0; }
uint64_t plat_now_ns(void) { return 1000000000ull; }
int main(int argc,char **argv) {
    assert(argc==2); script_path=argv[1];
    uint64_t buttons=0; int32_t left[2]={0},right[2]={0},dx,dy;
    test_tick=10;
    for(int i=0;i<3;i++) script_apply(&buttons,left,right);
    input_direct_mouse_sample(1,&dx,&dy);
    assert(dx==123 && dy==-45 && !buttons && !right[0] && !right[1]);
    input_direct_mouse_sample(1,&dx,&dy); assert(!dx && !dy);
    test_tick=20; script_apply(&buttons,left,right);
    g_menu=1; input_direct_mouse_sample(1,&dx,&dy); assert(!dx && !dy);
    g_menu=0; input_direct_mouse_sample(1,&dx,&dy); assert(!dx && !dy);
    test_world=100000;
    for(int i=0;i<3;i++) script_apply(&buttons,left,right);
    rec=tmpfile(); assert(rec); rec_state=1;
    input_direct_mouse_sample(1,&dx,&dy); assert(dx==-100 && dy==50);
    rewind(rec); char line[128]; assert(fgets(line,sizeof line,rec));
    assert(strstr(line,"MOUSE -100 50")); assert(!fgets(line,sizeof line,rec));
    fclose(rec); rec_state=-1;
    puts("direct mouse: one-shot script replay, host-menu blocking and raw-count recording passed");
}
'''

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cc', required=True)
    ap.add_argument('--deps', type=Path, help='dependency include directory (SDL3/Vulkan), to also check input scripts')
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='nx2navi-mouse-') as tmp:
        folder = Path(tmp)
        (folder / 'patches.h').write_text('#define RT_PATCH_PAGE 0x7003adf000ull\n')
        source = folder / 'check.c'
        exe = folder / ('check.exe' if os.name == 'nt' else 'check')
        link = [] if os.name == 'nt' else ['-lm']
        source.write_text(HARNESS)
        subprocess.run([args.cc, '-O2', '-Wall', '-Wextra', '-I', str(folder), '-I', str(ROOT/'runtime'),
                        str(source), *link, '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
        if args.deps:
            source.write_text(INPUT_HARNESS)
            script = folder / 'input.txt'
            script.write_text('10 MOUSE 123 -45\n20 MOUSE 1000 0\n@100 MOUSE -100 50\n')
            subprocess.run([args.cc, '-O2', '-flto', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections', *(['-fuse-ld=lld', '-Wl,--exclude-all-symbols'] if os.name == 'nt' else []),
                            '-I', str(ROOT/'runtime'), '-I', str(args.deps), '-I', str(args.deps/'vma'),
                            str(source), *link, '-o', str(exe)], check=True)
            subprocess.run([str(exe), str(script)], check=True)

if __name__ == '__main__':
    main()
