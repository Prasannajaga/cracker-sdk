#include <fcntl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

int main(void) {
    const char message[] = "snapshot test VM started\n";

    mkdir("/dev", 0755);
    mknod("/dev/console", S_IFCHR | 0600, makedev(5, 1));

    int console = open("/dev/console", O_WRONLY | O_NOCTTY);
    int output = console >= 0 ? console : STDOUT_FILENO;

    ssize_t written = write(output, message, sizeof(message) - 1);
    (void)written;

    for (;;) {
        sleep(3600);
    }
}
