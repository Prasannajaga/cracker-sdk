#include <fcntl.h>
#include <string.h>
#include <unistd.h>

static void write_console(const char *message) {
    int fd = open("/dev/console", O_WRONLY | O_CREAT, 0600);
    if (fd >= 0) {
        (void)write(fd, message, strlen(message));
        close(fd);
    }
}

int main(void) {
    write_console("memory governed worker started\n");
    while (1) {
        sleep(1);
    }
    return 0;
}
