// Small platform launcher for the shared PyQt6 UI.
#ifdef _WIN32
#include <windows.h>
#include <filesystem>
#include <string>
#include <cstdlib>

namespace {
std::string utf8(const std::wstring &text) {
    if (text.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, text.c_str(), (int)text.size(), nullptr, 0, nullptr, nullptr);
    std::string out(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, text.c_str(), (int)text.size(), out.data(), n, nullptr, nullptr);
    return out;
}

void append_utf8(const std::filesystem::path &path, const std::string &text) {
    std::error_code ec;
    std::filesystem::create_directories(path.parent_path(), ec);
    HANDLE file = CreateFileW(path.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return;
    SetFilePointer(file, 0, nullptr, FILE_END);
    DWORD written = 0;
    WriteFile(file, text.data(), (DWORD)text.size(), &written, nullptr);
    CloseHandle(file);
}

void log_line(const std::filesystem::path &path, const std::wstring &line) {
    append_utf8(path, utf8(line) + "\n");
}

std::wstring timestamp() {
    SYSTEMTIME st{};
    GetLocalTime(&st);
    wchar_t text[64]{};
    swprintf(text, 64, L"%04d-%02d-%02d %02d:%02d:%02d",
             st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    return text;
}

std::wstring win_error(DWORD code) {
    wchar_t *buffer = nullptr;
    FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
                       FORMAT_MESSAGE_IGNORE_INSERTS,
                   nullptr, code, 0, (LPWSTR)&buffer, 0, nullptr);
    std::wstring text = buffer ? buffer : L"unknown error";
    if (buffer) LocalFree(buffer);
    while (!text.empty() && (text.back() == L'\r' || text.back() == L'\n')) text.pop_back();
    return text;
}
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    wchar_t file[MAX_PATH]{};
    GetModuleFileNameW(nullptr, file, MAX_PATH);
    std::filesystem::path root(file);
    root = root.parent_path();

    wchar_t local[MAX_PATH]{};
    DWORD local_len = GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH);
    std::filesystem::path library = local_len ? std::filesystem::path(local) / L"TokyoGhoulJAIL" / L"JAIL"
                                              : root;
    std::filesystem::path log = library / L"logs" / L"host.log";
    std::filesystem::path console_log = library / L"logs" / L"host-console.log";

    SetEnvironmentVariableW(L"JAIL_APP_RESOURCES", root.c_str());
    auto python = root / L"python" / L"python.exe";
    auto script = root / L"launcher" / L"pyqt_launcher.py";
    auto qtbin = root / L"python" / L"Lib" / L"site-packages" / L"PyQt6" / L"Qt6" / L"bin";
    auto pybin = root / L"python";
    auto pydll = root / L"python" / L"DLLs";
    auto plugins = root / L"python" / L"Lib" / L"site-packages" / L"PyQt6" / L"Qt6" / L"plugins";

    wchar_t old_path[32768]{};
    DWORD n = GetEnvironmentVariableW(L"PATH", old_path, 32768);
    std::wstring path = pybin.wstring() + L";" + pydll.wstring() + L";" + qtbin.wstring() + L";" + (n ? old_path : L"");
    SetEnvironmentVariableW(L"PATH", path.c_str());
    SetEnvironmentVariableW(L"QT_PLUGIN_PATH", plugins.c_str());
    SetEnvironmentVariableW(L"PYTHONFAULTHANDLER", L"1");
    SetEnvironmentVariableW(L"PYTHONUNBUFFERED", L"1");

    log_line(log, L"================================================================");
    log_line(log, L"host start " + timestamp());
    log_line(log, L"root: " + root.wstring());
    log_line(log, L"python: " + python.wstring() + (std::filesystem::is_regular_file(python) ? L" (ok)" : L" (MISSING)"));
    log_line(log, L"script: " + script.wstring() + (std::filesystem::is_regular_file(script) ? L" (ok)" : L" (MISSING)"));
    log_line(log, L"qt bin: " + qtbin.wstring());
    log_line(log, L"qt plugins: " + plugins.wstring() + (std::filesystem::is_directory(plugins) ? L" (ok)" : L" (MISSING)"));
    log_line(log, L"console log: " + console_log.wstring());

    if (!std::filesystem::is_regular_file(python) || !std::filesystem::is_regular_file(script)) {
        log_line(log, L"refusing to start: bundled Python or launcher script is missing");
        return 1;
    }

    std::wstring command = L"\"" + python.wstring() + L"\" \"" + script.wstring() + L"\"";
    log_line(log, L"command: " + command);

    STARTUPINFOW si{};
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi{};
    SECURITY_ATTRIBUTES inherit_handles{sizeof(inherit_handles), nullptr, TRUE};
    HANDLE output = CreateFileW(console_log.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                &inherit_handles, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    bool inherit = false;
    if (output != INVALID_HANDLE_VALUE) {
        SetFilePointer(output, 0, nullptr, FILE_END);
        si.dwFlags |= STARTF_USESTDHANDLES;
        si.hStdOutput = output;
        si.hStdError = output;
        si.hStdInput = nullptr;
        inherit = true;
    }
    BOOL started = CreateProcessW(nullptr, command.data(), nullptr, nullptr, inherit,
                                  CREATE_NO_WINDOW, nullptr, root.c_str(), &si, &pi);
    DWORD error = started ? ERROR_SUCCESS : GetLastError();
    if (output != INVALID_HANDLE_VALUE) CloseHandle(output);
    if (!started) {
        log_line(log, L"CreateProcessW FAILED: " + std::to_wstring(error) + L" " + win_error(error));
        return 1;
    }
    log_line(log, L"started pid " + std::to_wstring(pi.dwProcessId));
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
#else
#include <unistd.h>
#include <limits.h>
#include <cstdlib>
#include <string>
int main(int, char **argv) {
    char file[PATH_MAX]; if (!realpath(argv[0], file)) return 1;
    std::string root(file); root.resize(root.rfind('/'));
    // Linux installs keep the host at <release>/launcher/nativ, unlike the
    // Windows host which is at the release root.
    if (root.size() >= 9 && root.substr(root.size() - 9) == "/launcher") root.resize(root.size() - 9);
    setenv("JAIL_APP_RESOURCES", root.c_str(), 1);
    // AppImage is read-only. Its writable data/ directory lives beside the
    // AppImage, while ordinary extracted installs keep data/ beside launcher.
    const char *appimage = getenv("APPIMAGE");
    if (appimage) {
        std::string image(appimage);
        auto slash = image.rfind('/');
        setenv("JAIL_DATA", (slash == std::string::npos ? std::string("data") : image.substr(0, slash) + "/data").c_str(), 1);
    }
    std::string python = root + "/python/bin/python3";
    std::string script = root + "/launcher/pyqt_launcher.py";
    execl(python.c_str(), python.c_str(), script.c_str(), nullptr); return 1;
}
#endif
