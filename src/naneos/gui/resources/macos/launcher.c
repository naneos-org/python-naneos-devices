/*
 * naneos-launcher: the executable of "Naneos Devices.app".
 *
 * macOS asks for Bluetooth access on behalf of the "responsible" app, the one
 * at the top of a process chain. A python started at login has no Info.plist
 * with NSBluetoothAlwaysUsageDescription, so CoreBluetooth kills it or never
 * asks. This launcher is the bundle's executable, so it is the responsible app
 * and its Info.plist is used. It starts the tray app as its child (children keep
 * the responsibility) and stays until it ends. It is not a python shim: it does
 * nothing but spawn, forward signals and pass on the exit status.
 *
 * It runs Contents/Resources/launch.sh, which the package writes and which ends
 * in `exec <tool environment>/bin/naneos-gui "$@"`.
 *
 * Build (universal2, ad-hoc signed): scripts/build-macos-launcher.sh
 * Do not rebuild it for a small change: a new binary is a new code signature and
 * macOS asks for Bluetooth access again. Bump LAUNCHER_VERSION in integration.py.
 */
#include <errno.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static volatile sig_atomic_t child_pid = 0;

static void forward_signal(int sig) {
    if (child_pid > 0) {
        kill((pid_t)child_pid, sig);
    }
}

int main(int argc, char **argv) {
    char path[PATH_MAX];
    uint32_t size = sizeof path;
    if (_NSGetExecutablePath(path, &size) != 0) {
        fprintf(stderr, "naneos-launcher: path too long\n");
        return 1;
    }

    char real[PATH_MAX];
    if (realpath(path, real) == NULL) {
        perror("naneos-launcher: realpath");
        return 1;
    }

    /* .../Contents/MacOS/naneos-launcher -> .../Contents/Resources/launch.sh */
    for (int i = 0; i < 2; i++) {
        char *slash = strrchr(real, '/');
        if (slash == NULL) {
            fprintf(stderr, "naneos-launcher: unexpected path %s\n", real);
            return 1;
        }
        *slash = '\0';
    }
    char script[PATH_MAX];
    if (snprintf(script, sizeof script, "%s/Resources/launch.sh", real) >= (int)sizeof script) {
        fprintf(stderr, "naneos-launcher: path too long\n");
        return 1;
    }

    /* sh launch.sh [arguments], without the -psn_ argument old LaunchServices adds */
    char *args[argc + 3];
    int n = 0;
    args[n++] = "/bin/sh";
    args[n++] = script;
    for (int i = 1; i < argc; i++) {
        if (strncmp(argv[i], "-psn_", 5) != 0) {
            args[n++] = argv[i];
        }
    }
    args[n] = NULL;

    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_handler = forward_signal;
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGHUP, &action, NULL);

    pid_t pid;
    int err = posix_spawn(&pid, "/bin/sh", NULL, NULL, args, environ);
    if (err != 0) {
        fprintf(stderr, "naneos-launcher: cannot start %s: %s\n", script, strerror(err));
        return 1;
    }
    child_pid = pid;

    int status = 0;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) {
            return 1;
        }
    }
    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    if (WIFSIGNALED(status)) {
        return 128 + WTERMSIG(status);
    }
    return 1;
}
