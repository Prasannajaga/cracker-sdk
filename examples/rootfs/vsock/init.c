#include <errno.h>
#include <fcntl.h>
#include <linux/vm_sockets.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

static int console_fd(void) {
    mkdir("/dev", 0755);
    mknod("/dev/console", S_IFCHR | 0600, makedev(5, 1));
    int console = open("/dev/console", O_WRONLY | O_NOCTTY);
    return console >= 0 ? console : STDOUT_FILENO;
}

static void write_console(int output, const char *message) {
    ssize_t written = write(output, message, strlen(message));
    (void)written;
}

int main(void) {
    int output = console_fd();
    write_console(output, "vsock guest started\n");

    int server = socket(AF_VSOCK, SOCK_STREAM, 0);
    if (server < 0) {
        write_console(output, "failed to create AF_VSOCK socket\n");
        for (;;) {
            sleep(3600);
        }
    }

    struct sockaddr_vm addr;
    memset(&addr, 0, sizeof(addr));
    addr.svm_family = AF_VSOCK;
    addr.svm_cid = VMADDR_CID_ANY;
    addr.svm_port = 5000;

    if (bind(server, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        write_console(output, "failed to bind vsock port 5000\n");
        for (;;) {
            sleep(3600);
        }
    }

    if (listen(server, 16) < 0) {
        write_console(output, "failed to listen on vsock port 5000\n");
        for (;;) {
            sleep(3600);
        }
    }

    for (;;) {
        int client = accept(server, NULL, NULL);
        if (client < 0) {
            continue;
        }

        char buffer[256];
        ssize_t nread = read(client, buffer, sizeof(buffer));
        if (nread == 4 && memcmp(buffer, "ping", 4) == 0) {
            const char response[] = "pong from guest\n";
            ssize_t written = write(client, response, sizeof(response) - 1);
            (void)written;
        } else if (nread > 0) {
            const char response[] = "unknown request\n";
            ssize_t written = write(client, response, sizeof(response) - 1);
            (void)written;
        }

        close(client);
    }
}
