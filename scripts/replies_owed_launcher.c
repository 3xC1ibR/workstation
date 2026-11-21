/* Keep the FDA-approved parent alive while its fixed exporter runs. */
#include <errno.h>
#include <spawn.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static char exporter[] = {
#include "export_replies_owed.inc"
    , 0
};

static int valid_options(int argc, char **argv) {
    for (int index = 1; index < argc; index++) {
        const char *option = argv[index];
        if (strcmp(option, "--include-groups") == 0 ||
            strcmp(option, "--include-never-replied") == 0 ||
            strcmp(option, "--include-short-codes") == 0 ||
            strcmp(option, "--help") == 0 || strcmp(option, "-h") == 0)
            continue;

        const char *days;
        if (strcmp(option, "--max-age-days") == 0 && index + 1 < argc)
            days = argv[++index];
        else if (strncmp(option, "--max-age-days=", sizeof("--max-age-days=") - 1) == 0)
            days = option + sizeof("--max-age-days=") - 1;
        else
            return 0;
        if (!*days || days[strspn(days, "0123456789")] != '\0')
            return 0;
    }
    return 1;
}

int main(int argc, char **argv) {
    if (!valid_options(argc, argv))
        return 64;

    /* Caller arguments follow the embedded program and cannot select Python options. */
    char python[] = "/Library/Developer/CommandLineTools/usr/bin/python3";
    char *prefix[] = {python, "-I", "-S", "-B", "-c", exporter};
    char *environment[] = {"PATH=/usr/bin:/bin", NULL};
    if (chdir("/") != 0)
        return 1;

    size_t prefix_count = sizeof(prefix) / sizeof(prefix[0]);
    char **arguments = calloc(prefix_count + argc, sizeof(*arguments));
    if (!arguments)
        return 1;
    memcpy(arguments, prefix, sizeof(prefix));
    memcpy(arguments + prefix_count, argv + 1, argc * sizeof(*arguments));

    pid_t child;
    int spawn_error = posix_spawn(&child, python, NULL, NULL, arguments, environment);
    free(arguments);
    if (spawn_error != 0)
        return 1;
    int status;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR)
            return 1;
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
