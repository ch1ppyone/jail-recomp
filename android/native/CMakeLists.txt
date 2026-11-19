cmake_minimum_required(VERSION 3.22)
project(jail_android C CXX)

# ---------------------------------------------------------------------------------------------
# Inputs. The Android subproject does not copy the runtime: it compiles the same Nativ sources and
# the same generated game C that the desktop port uses. Override these paths from Gradle or by
# passing -D... on the CMake command line.
# ---------------------------------------------------------------------------------------------
set(NATIV_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../nativ" CACHE PATH
    "Nativ source tree (runtime/, recompiler/, third_party/)")
set(GAME_RECOMP_DIR "${NATIV_ROOT}/dump/decrypted/PCSG00615/recomp" CACHE PATH
    "Generated C from vitarecomp build PCSG00615")
set(SDL3_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/sdl3-android" CACHE PATH
    "SDL3 install for arm64-v8a")
set(FFMPEG_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/ffmpeg-android" CACHE PATH
    "Optional static FFmpeg install for arm64-v8a")

if(NOT EXISTS "${NATIV_ROOT}/runtime/core/main.c")
    message(FATAL_ERROR "NATIV_ROOT does not look like Nativ: ${NATIV_ROOT}")
endif()
if(NOT EXISTS "${GAME_RECOMP_DIR}/game.c")
    message(FATAL_ERROR
        "No generated game C at ${GAME_RECOMP_DIR}.\n"
        "Build the desktop port first: cd jail-recomp/nativ && ./vitarecomp build PCSG00615")
endif()
if(NOT EXISTS "${SDL3_ROOT}/include/SDL3/SDL.h")
    message(FATAL_ERROR
        "SDL3 for Android not found at ${SDL3_ROOT}.\n"
        "Run android/scripts/fetch_android_deps.sh and android/scripts/build_sdl3_android.sh first.")
endif()

find_package(Python3 COMPONENTS Interpreter REQUIRED)

set(GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${GEN_DIR}")

set(JAIL_CONFIG_PY "${CMAKE_CURRENT_SOURCE_DIR}/../scripts/gen_jail_config.py")
set(JAIL_ANALYSIS "${NATIV_ROOT}/dump/decrypted/PCSG00615/analysis/eboot.data.json")
set(JAIL_CONFIG_DEPS "${JAIL_CONFIG_PY}")
if(EXISTS "${JAIL_ANALYSIS}")
    list(APPEND JAIL_CONFIG_DEPS "${JAIL_ANALYSIS}")
endif()
add_custom_command(
    OUTPUT "${GEN_DIR}/jail_config.h"
    COMMAND ${Python3_EXECUTABLE} "${JAIL_CONFIG_PY}"
            --nativ-root "${NATIV_ROOT}" --out "${GEN_DIR}/jail_config.h"
    DEPENDS ${JAIL_CONFIG_DEPS}
    COMMENT "Generating jail_config.h (entry address and title identity)")

set(PROMPTS_PNG "${NATIV_ROOT}/third_party/kenney-prompts/prompts.png")
set(PROMPTS_PY "${CMAKE_CURRENT_SOURCE_DIR}/../scripts/gen_prompts_header.py")
add_custom_command(
    OUTPUT "${GEN_DIR}/prompts_png.h"
    COMMAND ${Python3_EXECUTABLE} "${PROMPTS_PY}" "${PROMPTS_PNG}" "${GEN_DIR}/prompts_png.h"
    DEPENDS "${PROMPTS_PNG}" "${PROMPTS_PY}"
    COMMENT "Generating prompts_png.h")
add_custom_target(jail_generated DEPENDS "${GEN_DIR}/jail_config.h" "${GEN_DIR}/prompts_png.h")

# ---------------------------------------------------------------------------------------------
# Runtime sources: the same host set as runtime/build.py, minus the macOS Metal bridge and the
# tools that only the launcher / VERIFY builds use.
# ---------------------------------------------------------------------------------------------
set(NATIV_SOURCES
    runtime/core/main.c
    runtime/core/gaps.c
    runtime/core/hle.c
    runtime/core/modload.c
    runtime/core/libc.c
    runtime/core/events.c
    runtime/core/io.c
    runtime/core/sysmem.c
    runtime/core/apputil.c
    runtime/core/trophy.c
    runtime/core/imedlg.c
    runtime/core/fios.c
    runtime/core/psarc.c
    runtime/core/kernel.c
    runtime/core/metrics.c
    runtime/core/settings.c
    runtime/core/hooks.c
    runtime/gfx/gxp_index.c
    runtime/gfx/gpu.c
    runtime/gfx/display.c
    runtime/gfx/input_rec.c
    runtime/gfx/gxm_sony.c
    runtime/gfx/usse.c
    runtime/gfx/usse_spirv.c
    runtime/gfx/gfx_soft.c
    runtime/gfx/gfx_gpu.c
    runtime/gfx/gfx_dispatch.c
    runtime/gfx/guestwatch.c
    runtime/gfx/gpulock.c
    runtime/gfx/post.c
    runtime/gfx/ssao.c
    runtime/gfx/texpack.c
    runtime/gfx/fsr/fsr.c
    runtime/audio/ngs.c
    runtime/audio/audiodec.c
    runtime/media/video.c
    runtime/media/jpeg.c
    runtime/media/camera.c
    runtime/media/smart.c
    runtime/input/gesture.c
    runtime/input/motion.c
    runtime/ui/pad_bind.c
    runtime/ui/window.c
    runtime/ui/ui_text.c
    runtime/net/net.c
    runtime/net/net_offline.c
    runtime/net/netinfo.c
    runtime/net/np.c
    runtime/net/http.c
    runtime/net/sha1.c
    runtime/net/ssl_local.c
    runtime/net/online/m2_server.c
    runtime/net/online/m2_wire.c
    runtime/net/online/m2_rooms.c
    runtime/net/online/m2_proxy.c
    runtime/net/online/discovery.c
    runtime/net/online/basic_msg.c
    runtime/net/online/stun.c
    runtime/net/online/overlay.c
    runtime/net/online/dht.c
    runtime/net/online/upnp.c
    runtime/net/online/aes128.c
    runtime/net/online/status.c
    runtime/net/online/crypto.c
    runtime/debug/gfx_coverage.c
    runtime/debug/gfx_capture.c
    runtime/debug/stallprof.c
    runtime/debug/waitstats.c
    runtime/debug/memscan.c
    runtime/platform/platform_posix.c
)

list(TRANSFORM NATIV_SOURCES PREPEND "${NATIV_ROOT}/")

set(IMGUI_DIR "${NATIV_ROOT}/third_party/imgui")
set(IMGUI_SOURCES
    "${IMGUI_DIR}/imgui.cpp"
    "${IMGUI_DIR}/imgui_draw.cpp"
    "${IMGUI_DIR}/imgui_tables.cpp"
    "${IMGUI_DIR}/imgui_widgets.cpp"
    "${IMGUI_DIR}/backends/imgui_impl_sdl3.cpp"
    "${IMGUI_DIR}/backends/imgui_impl_sdlgpu3.cpp"
    "${NATIV_ROOT}/runtime/ui/overlay.cpp"
    "${NATIV_ROOT}/runtime/ui/savedlg_ui.cpp"
    "${NATIV_ROOT}/runtime/ui/imedlg_ui.cpp"
)

file(GLOB LIBATRAC9_SOURCES CONFIGURE_DEPENDS "${NATIV_ROOT}/third_party/libatrac9/*.c")
file(GLOB GAME_SOURCES CONFIGURE_DEPENDS
    "${GAME_RECOMP_DIR}/game.c"
    "${GAME_RECOMP_DIR}/game_part*.c"
    "${GAME_RECOMP_DIR}/mod_*.c")

add_library(main SHARED
    ${NATIV_SOURCES}
    ${IMGUI_SOURCES}
    ${LIBATRAC9_SOURCES}
    ${GAME_SOURCES}
    "${CMAKE_CURRENT_SOURCE_DIR}/android_entry.c")

add_dependencies(main jail_generated)

# The generated game and module parts are the only TUs that see the guest arena as const.
set_source_files_properties(${GAME_SOURCES} PROPERTIES COMPILE_DEFINITIONS "RECOMP_GUEST_CODE")
# main() becomes nativ_main; android_entry.c exports SDL_main for SDLActivity.
set_source_files_properties("${NATIV_ROOT}/runtime/core/main.c" PROPERTIES COMPILE_DEFINITIONS "main=nativ_main")

set(INCLUDES
    "${NATIV_ROOT}/runtime/core"
    "${NATIV_ROOT}/runtime/gfx"
    "${NATIV_ROOT}/runtime/gfx/fsr"
    "${NATIV_ROOT}/runtime/audio"
    "${NATIV_ROOT}/runtime/media"
    "${NATIV_ROOT}/runtime/input"
    "${NATIV_ROOT}/runtime/net"
    "${NATIV_ROOT}/runtime/ui"
    "${NATIV_ROOT}/runtime/platform"
    "${NATIV_ROOT}/runtime/debug"
    "${NATIV_ROOT}/recompiler"
    "${NATIV_ROOT}"
    "${GAME_RECOMP_DIR}"
    "${IMGUI_DIR}"
    "${IMGUI_DIR}/backends"
    "${GEN_DIR}"
    "${SDL3_ROOT}/include"
)

target_include_directories(main PRIVATE ${INCLUDES})
target_compile_features(main PRIVATE c_std_11 cxx_std_17)
target_compile_options(main PRIVATE -O2 -ffp-contract=off -w -fPIC)
target_compile_definitions(main PRIVATE _FILE_OFFSET_BITS=64)
# The pack's RUN_ENV. The Android wrapper may override RECOMP_GAME_LANG at launch.
target_compile_definitions(main PRIVATE "RECOMP_BUILTIN_ENV=\"RECOMP_GAME_LANG=en_us\"")

# Optional static FFmpeg (H.264 video and AAC audio). Without it the game still boots and the
# movie path reports a decode error; build android/scripts/build_ffmpeg_android.sh to enable it.
# (The presence of libavcodec.a is sampled at configure time: reconfigure after building it.)
if(EXISTS "${FFMPEG_ROOT}/lib/libavcodec.a")
    target_compile_definitions(main PRIVATE RECOMP_AVCODEC)
    target_include_directories(main PRIVATE "${FFMPEG_ROOT}/include")
    if(EXISTS "${FFMPEG_ROOT}/lib/libnativ_rawdec.a")
        target_compile_definitions(main PRIVATE RECOMP_RAWDEC)
        target_link_libraries(main PRIVATE
            "${FFMPEG_ROOT}/lib/libnativ_rawdec.a"
            "${FFMPEG_ROOT}/lib/libavcodec.a"
            "${FFMPEG_ROOT}/lib/libavutil.a")
    else()
        target_link_libraries(main PRIVATE
            "${FFMPEG_ROOT}/lib/libavcodec.a"
            "${FFMPEG_ROOT}/lib/libavutil.a")
    endif()
    message(STATUS "FFmpeg: ${FFMPEG_ROOT} (H.264/AAC enabled)")
else()
    message(STATUS "FFmpeg: not found at ${FFMPEG_ROOT}; movies will not decode")
endif()

target_link_directories(main PRIVATE "${SDL3_ROOT}/lib")
target_link_libraries(main PRIVATE SDL3 android log m z dl)
target_link_options(main PRIVATE
    "-Wl,-u,SDL_main"
    "-Wl,-z,max-page-size=16384"
    # FFmpeg's aarch64 tx_float tables are absolute-addressed globals; marking the
    # static archives' symbols hidden lets lld bind them inside libmain.so.
    "-Wl,--exclude-libs,ALL")

set_target_properties(main PROPERTIES
    OUTPUT_NAME "main"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}")
