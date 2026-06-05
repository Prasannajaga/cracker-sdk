#include <fcntl.h>
#include <linux/reboot.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

int main(void) {
    const char message[] = "hello from cracker-sdk\n";

    mkdir("/dev", 0755);
    mknod("/dev/console", S_IFCHR | 0600, makedev(5, 1));

    int console = open("/dev/console", O_WRONLY | O_NOCTTY);
    int output = console >= 0 ? console : STDOUT_FILENO;

    ssize_t written = write(output, message, sizeof(message) - 1);
    (void)written;
    sync();
    reboot(LINUX_REBOOT_CMD_POWER_OFF);

    for (;;) {
        pause();
    }
}
