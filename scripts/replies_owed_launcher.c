/* Keep the FDA-approved parent alive while its fixed exporter runs. */
#include <errno.h>
#include <spawn.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static char exporter[] = {
#include "export_replies_owed.inc"
    , 0
};

int main(int argc, char **argv) {
    if (argc > 2 || (argc == 2 && strcmp(argv[1], "--include-groups") != 0
                               && strcmp(argv[1], "--help") != 0))
        return 64;

    /* Avoid user-selected interpreters, modules, working directories and hooks. */
    char python[] = "/Library/Developer/CommandLineTools/usr/bin/python3";
    char *arguments[] = {python, "-I", "-S", "-B", "-c", exporter, argv[1], NULL};
    char *environment[] = {"PATH=/usr/bin:/bin", NULL};
    if (chdir("/") != 0)
        return 1;

    pid_t child;
    if (posix_spawn(&child, python, NULL, NULL, arguments, environment) != 0)
        return 1;
    int status;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR)
            return 1;
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
