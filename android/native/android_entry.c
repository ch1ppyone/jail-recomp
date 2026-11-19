/*
 * Android entry point for the Nativ runtime.
 *
 * SDLActivity loads libmain.so and calls SDL_main(). The desktop Nativ entry point is main() in
 * runtime/core/main.c; the CMake build renames that symbol to nativ_main, and this file adapts the
 * Android arguments to the two positional arguments it expects:
 *
 *     nativ_main <game.img> <module_start>
 *
 * The Android side only passes a writable base directory. This wrapper derives the runtime paths
 * (RECOMP_FS, RECOMP_SETTINGS, RECOMP_SHADER_CACHE), loads the entry address generated from the
 * game's own analysis, and calls nativ_main.
 */
#include <errno.h>
#include <android/log.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <pthread.h>
#include <SDL3/SDL.h>

#include "jail_config.h"

extern int nativ_main(int argc, char **argv);

#define JAIL_LOGI(...) __android_log_print(ANDROID_LOG_INFO, "JailAndroid", __VA_ARGS__)

/* SDLActivity invokes SDL_main from a Java-created thread with a small stack.
 * The recompiled guest/runtime has the same large-stack requirement as the
 * working Westopolis Android port, so never run nativ_main directly there. */
typedef struct {
    int argc;
    char **argv;
    int rc;
} jail_main_args;

static void *jail_main_thread(void *opaque) {
    jail_main_args *args = (jail_main_args *)opaque;
    args->rc = nativ_main(args->argc, args->argv);
    return NULL;
}

static void mkdirs(const char *path) {
    char buf[4096];
    if (!path || !*path) return;
    snprintf(buf, sizeof buf, "%s", path);
    for (char *p = buf + 1; *p; p++) {
        if (*p != '/') continue;
        *p = 0;
        if (mkdir(buf, 0755) != 0 && errno != EEXIST) {
            /* A parent may already exist with another mode; only a failed final component matters. */
        }
        *p = '/';
    }
    if (mkdir(buf, 0755) != 0 && errno != EEXIST) {
        fprintf(stderr, "jail: cannot create %s: %s\n", buf, strerror(errno));
    }
}

__attribute__((visibility("default")))
int SDL_main(int argc, char **argv) {
    JAIL_LOGI("SDL_main argc=%d", argc);
    const char *base = NULL;
    const char *image = NULL;
    const char *lang = NULL;
    const char *log = NULL;
    const char *render_scale = NULL;
    const char *gfx = NULL;
    const char *envs = NULL;
    int audio = 0;
    int no_audio = 0;
    int gamepad = 0;
    int no_gamepad = 0;
    int no_gpu = 0;
    int headless = 0;
    int window_test = 0;
    int no_game = 0;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--base-dir") && i + 1 < argc) base = argv[++i];
        else if (!strcmp(argv[i], "--image") && i + 1 < argc) image = argv[++i];
        else if (!strcmp(argv[i], "--lang") && i + 1 < argc) lang = argv[++i];
        else if (!strcmp(argv[i], "--log") && i + 1 < argc) log = argv[++i];
        else if (!strcmp(argv[i], "--render-scale") && i + 1 < argc) render_scale = argv[++i];
        else if (!strcmp(argv[i], "--gfx") && i + 1 < argc) gfx = argv[++i];
        else if (!strcmp(argv[i], "--env") && i + 1 < argc) envs = argv[++i];
        else if (!strcmp(argv[i], "--audio")) audio = 1;   /* legacy: audio is on by default now */
        else if (!strcmp(argv[i], "--no-audio")) no_audio = 1;
        else if (!strcmp(argv[i], "--no-gamepad")) no_gamepad = 1;
        else if (!strcmp(argv[i], "--gamepad")) gamepad = 1;
        else if (!strcmp(argv[i], "--no-gpu")) no_gpu = 1;
        else if (!strcmp(argv[i], "--headless")) headless = 1;
        else if (!strcmp(argv[i], "--window-test")) window_test = 1;
        else if (!strcmp(argv[i], "--no-game")) no_game = 1;
    }

    if (!base || !*base) {
        fprintf(stderr, "jail: missing --base-dir\n");
        return 1;
    }

    char fs[4096], settings[4096], cache[4096], img[4096];
    snprintf(fs, sizeof fs, "%s/fs", base);
    snprintf(settings, sizeof settings, "%s/settings.ini", base);
    snprintf(cache, sizeof cache, "%s/shader_cache", base);
    if (!image || !*image) {
        snprintf(img, sizeof img, "%s/jail/game.img", base);
        image = img;
    }

    mkdirs(fs);
    mkdirs(cache);
    {
        char jail[4096];
        snprintf(jail, sizeof jail, "%s/jail", base);
        mkdirs(jail);
    }
    chdir(base);   /* any remaining relative path the runtime makes stays inside app storage */

    /* stderr never reaches logcat from SDL's native threads; keep the runtime's own diagnostics
     * (import log, gaps, GPU stats, renderer warnings) in a file next to the game data. */
    {
        char logpath[4096];
        snprintf(logpath, sizeof logpath, "%s/runtime.log", base);
        if (freopen(logpath, "w", stderr)) setvbuf(stderr, NULL, _IOLBF, 0);
    }

    setenv("RECOMP_FS", fs, 1);
    setenv("RECOMP_SETTINGS", settings, 1);
    setenv("RECOMP_SHADER_CACHE", cache, 1);
    setenv("RECOMP_GAME_LANG", lang && *lang ? lang : "en_us", 1);
    setenv("RECOMP_GAME_NAME", JAIL_GAME_NAME, 1);
    setenv("RECOMP_TITLE", JAIL_TITLE_ID, 1);
    setenv("RECOMP_GAME_VERSION", JAIL_GAME_VERSION, 1);
#ifdef __ANDROID__
    /* Audio (NGS -> SDL) and gamepad discovery are on by default; the diagnostic flags keep
     * the old bring-up paths available (`am start ... --ez no_audio true`). */
    (void)audio;
    if (no_audio) setenv("RECOMP_ANDROID_NO_AUDIO", "1", 1);
    /* Android's mixer/HAL commonly consumes roughly 1024-1088 frames at 48 kHz.  The desktop
     * default of 256 frames is too small for that device buffer: the game can return between
     * pulls and SDL inserts an audible underrun.  Keep two device-sized buffers queued on
     * Android; explicit --env values still override these defaults. */
    if (!getenv("RECOMP_AUDIO_FRAMES")) setenv("RECOMP_AUDIO_FRAMES", "1024", 1);
    if (!getenv("RECOMP_AUDIO_QUEUE")) setenv("RECOMP_AUDIO_QUEUE", "2", 1);
    /* Touch controls should be visible immediately on Android. Desktop's `auto` mode waits
     * for the first finger, which makes the virtual sticks look absent on a fresh launch. */
    if (!getenv("RECOMP_OSB")) setenv("RECOMP_OSB", "on", 1);
    /* Off by default: the emulator exposes its keyboard as a phantom gamepad ("qwerty2"),
     * which makes the runtime auto-hide the on-screen buttons. A physical pad can be
     * enabled with `am start ... --ez gamepad true`. */
    if (!gamepad || no_gamepad) setenv("RECOMP_ANDROID_NO_GAMEPAD", "1", 1);
    if (no_gpu) {
        setenv("RECOMP_ANDROID_NO_GPU", "1", 1);
        setenv("RECOMP_GFX", "soft", 1);
    }
    if (headless) setenv("RECOMP_HEADLESS", "1", 1);
#ifdef __ANDROID__
    if (headless) setenv("RECOMP_ANDROID_NO_HLE_WINDOW", "1", 1);
#endif
#endif

    if (window_test) {
        SDL_Window *test_window = NULL;
        if (!SDL_Init(SDL_INIT_VIDEO)) {
            JAIL_LOGI("window test: SDL_Init failed: %s", SDL_GetError());
            return 2;
        }
        test_window = SDL_CreateWindow("Tokyo Ghoul SDL test", 960, 544,
                                       SDL_WINDOW_HIGH_PIXEL_DENSITY);
        if (!test_window) {
            JAIL_LOGI("window test: SDL_CreateWindow failed: %s", SDL_GetError());
            return 3;
        }
        JAIL_LOGI("window test: window created");
        for (int t = 0; t < 300; ++t) {
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_EVENT_QUIT) t = 300;
            }
            SDL_Delay(100);
        }
        JAIL_LOGI("window test: leaving");
        return 0;
    }
    if (no_game) setenv("RECOMP_ANDROID_NO_GAME", "1", 1);

    /* The desktop pipeline sets RECOMP_MODULES from the pack's MODULES list. Without it every
     * import that a game module exports (_Znwj/operator new, libult, libgxm, PVF/Ft2, fios) is a
     * stub returning 0: the game boots, presents one frame, then loops on null callbacks. Load the
     * same modules here, in the pack's order, from the data directory. */
    {
        static const char *const names[] = { "libc", "libgxm_es4", "libgpu_es4", "libfios2", "libpvf", "libult", "libSceFt2" };
        char mods[4096]; size_t at = 0; int n = 0;
        mods[0] = 0;
        for (size_t k = 0; k < sizeof names / sizeof names[0]; k++) {
            char path[4096];
            snprintf(path, sizeof path, "%s/jail/%s.img", base, names[k]);
            if (access(path, R_OK) != 0) continue;
            int w = snprintf(mods + at, sizeof mods - at, "%s%s", n ? "," : "", path);
            if (w <= 0 || (size_t)w >= sizeof mods - at) break;
            at += (size_t)w; n++;
        }
        if (n) {
            setenv("RECOMP_MODULES", mods, 1);
            JAIL_LOGI("modules[%d]=%s", n, mods);
        } else {
            JAIL_LOGI("no module images in %s/jail; module imports will be stubs", base);
        }
    }

    if (log && *log) setenv("RECOMP_LOG", log, 1);
    else setenv("RECOMP_LOG", "0", 1);
    if (render_scale && *render_scale) setenv("RECOMP_RENDER_SCALE", render_scale, 1);
    if (gfx && *gfx) setenv("RECOMP_GFX", gfx, 1);
    if (envs && *envs) {   /* --env "RECOMP_METRICS=1,RECOMP_GPU_STATS=1" (diagnostics) */
        char buf[2048]; snprintf(buf, sizeof buf, "%s", envs);
        for (char *p = buf; p && *p; ) {
            char *comma = strchr(p, ',');
            if (comma) *comma = 0;
            char *eq = strchr(p, '=');
            if (eq && eq != p) { *eq = 0; setenv(p, eq + 1, 1); JAIL_LOGI("env %s=%s", p, eq + 1); }
            p = comma ? comma + 1 : NULL;
        }
    }

    JAIL_LOGI("base=%s image=%s entry=%s", base, image, JAIL_GAME_ENTRY);
    fprintf(stderr, "jail: base=%s image=%s entry=%s\n", base, image, JAIL_GAME_ENTRY);

    char *args[4];
    args[0] = (char *)"jail";
    args[1] = (char *)image;
    args[2] = (char *)JAIL_GAME_ENTRY;
    /* The desktop runner's default import budget is a diagnostic stop after
     * 200,000 calls. Android is a live session, so do not terminate the game
     * during the first rendered frame when that counter is reached. */
    args[3] = (char *)"18446744073709551615";

    jail_main_args main_args = { .argc = 4, .argv = args, .rc = 1 };
    pthread_attr_t attr;
    if (pthread_attr_init(&attr) == 0) {
        /* Match the working Westopolis Android entry point. */
        pthread_attr_setstacksize(&attr, 32u << 20);
        pthread_t thread;
        if (pthread_create(&thread, &attr, jail_main_thread, &main_args) == 0) {
            pthread_join(thread, NULL);
            pthread_attr_destroy(&attr);
            return main_args.rc;
        }
        pthread_attr_destroy(&attr);
    }

    /* Fallback for unusual pthread implementations; normally unreachable. */
    return nativ_main(4, args);
}
