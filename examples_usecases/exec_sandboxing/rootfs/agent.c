#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <linux/vm_sockets.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define AGENT_PORT 5000
#define MAX_HEADER 4096

static int write_all(int fd, const void *data, size_t size) {
    const char *cursor = (const char *)data;
    while (size > 0) {
        ssize_t written = write(fd, cursor, size);
        if (written < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        cursor += written;
        size -= (size_t)written;
    }
    return 0;
}

static void set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags >= 0) {
        fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    }
}

static int drain_available(int source_fd, int file_fd, int console_fd) {
    char buffer[4096];
    int saw_eof = 0;

    for (;;) {
        ssize_t nread = read(source_fd, buffer, sizeof(buffer));
        if (nread > 0) {
            if (file_fd >= 0) {
                write_all(file_fd, buffer, (size_t)nread);
            }
            if (console_fd >= 0) {
                write_all(console_fd, buffer, (size_t)nread);
            }
            continue;
        }
        if (nread == 0) {
            saw_eof = 1;
            break;
        }
        if (errno == EINTR) {
            continue;
        }
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            break;
        }
        break;
    }

    return saw_eof;
}

static int read_exact(int fd, void *data, size_t size) {
    char *cursor = (char *)data;
    while (size > 0) {
        ssize_t nread = read(fd, cursor, size);
        if (nread < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (nread == 0) {
            return -1;
        }
        cursor += nread;
        size -= (size_t)nread;
    }
    return 0;
}

static int read_header_line(int fd, char *line, size_t cap) {
    size_t used = 0;
    while (used + 1 < cap) {
        char ch = 0;
        ssize_t nread = read(fd, &ch, 1);
        if (nread < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (nread == 0) {
            return -1;
        }
        if (ch == '\n') {
            line[used] = '\0';
            return 0;
        }
        line[used++] = ch;
    }
    line[cap - 1] = '\0';
    return -1;
}

static void send_response(int fd, const char *status, const void *body, size_t size) {
    char header[64];
    int header_size = snprintf(header, sizeof(header), "%s %zu\n", status, size);
    if (header_size > 0) {
        write_all(fd, header, (size_t)header_size);
        if (size > 0) {
            write_all(fd, body, size);
        }
    }
}

static void send_error(int fd, const char *fmt, ...) {
    char body[1024];
    va_list args;
    va_start(args, fmt);
    int size = vsnprintf(body, sizeof(body), fmt, args);
    va_end(args);
    if (size < 0) {
        const char fallback[] = "agent error\n";
        send_response(fd, "ERR", fallback, sizeof(fallback) - 1);
        return;
    }
    if ((size_t)size >= sizeof(body)) {
        size = (int)sizeof(body) - 1;
    }
    send_response(fd, "ERR", body, (size_t)size);
}

static void setup_console(void) {
    mkdir("/dev", 0755);
    mknod("/dev/console", S_IFCHR | 0600, makedev(5, 1));
    mknod("/dev/null", S_IFCHR | 0666, makedev(1, 3));
    int console = open("/dev/console", O_WRONLY | O_NOCTTY);
    if (console >= 0) {
        write_all(console, "cracker-sdk exec sandboxing agent ready\n", 40);
        close(console);
    }
}

static void setup_runtime_mounts(void) {
    mkdir("/proc", 0555);
    mkdir("/sys", 0555);
    mkdir("/dev", 0755);
    mkdir("/dev/pts", 0755);
    mkdir("/tmp", 01777);

    mount("proc", "/proc", "proc", 0, "");
    mount("sysfs", "/sys", "sysfs", 0, "");
    mount("devtmpfs", "/dev", "devtmpfs", 0, "");
    mount("devpts", "/dev/pts", "devpts", 0, "");

    mknod("/dev/console", S_IFCHR | 0600, makedev(5, 1));
    mknod("/dev/null", S_IFCHR | 0666, makedev(1, 3));
    mknod("/dev/zero", S_IFCHR | 0666, makedev(1, 5));
    mknod("/dev/random", S_IFCHR | 0666, makedev(1, 8));
    mknod("/dev/urandom", S_IFCHR | 0666, makedev(1, 9));
}

static int ensure_workspace(void) {
    if (mkdir("/workspace", 0755) < 0 && errno != EEXIST) {
        return -1;
    }
    return 0;
}

static int validate_workspace_path(const char *path) {
    size_t prefix_len = strlen("/workspace");
    if (path[0] != '/') {
        return -1;
    }
    if (strstr(path, "..") != NULL) {
        return -1;
    }
    if (strncmp(path, "/workspace", prefix_len) != 0) {
        return -1;
    }
    if (path[prefix_len] != '\0' && path[prefix_len] != '/') {
        return -1;
    }
    return 0;
}

static int make_parent_dirs(const char *path) {
    char tmp[2048];
    size_t len = strlen(path);
    if (len >= sizeof(tmp)) {
        return -1;
    }
    memcpy(tmp, path, len + 1);
    for (char *cursor = tmp + 1; *cursor != '\0'; cursor++) {
        if (*cursor == '/') {
            *cursor = '\0';
            if (mkdir(tmp, 0755) < 0 && errno != EEXIST) {
                return -1;
            }
            *cursor = '/';
        }
    }
    return 0;
}

static int write_file(const char *path, const void *data, size_t size, mode_t mode) {
    if (make_parent_dirs(path) < 0) {
        return -1;
    }
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, mode);
    if (fd < 0) {
        return -1;
    }
    int result = write_all(fd, data, size);
    if (close(fd) < 0) {
        result = -1;
    }
    return result;
}

static int read_file(const char *path, char **data, size_t *size) {
    *data = NULL;
    *size = 0;
    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        return -1;
    }
    struct stat st;
    if (fstat(fd, &st) < 0 || S_ISDIR(st.st_mode) || st.st_size < 0) {
        close(fd);
        return -1;
    }
    char *body = malloc((size_t)st.st_size + 1);
    if (body == NULL) {
        close(fd);
        return -1;
    }
    if (read_exact(fd, body, (size_t)st.st_size) < 0) {
        free(body);
        close(fd);
        return -1;
    }
    close(fd);
    *data = body;
    *size = (size_t)st.st_size;
    return 0;
}

static int runtime_command(const char *runtime, const char **program, const char **script_path) {
    if (strcmp(runtime, "bash") == 0 || strcmp(runtime, "sh") == 0) {
        *program = "/bin/bash";
        *script_path = "/workspace/run.bash";
        return 0;
    }
    if (strcmp(runtime, "python") == 0 || strcmp(runtime, "py") == 0) {
        *program = "/usr/bin/python3";
        *script_path = "/workspace/run.py";
        return 0;
    }
    if (strcmp(runtime, "js") == 0 || strcmp(runtime, "quickjs") == 0 || strcmp(runtime, "qjs") == 0) {
        *program = "/usr/bin/qjs";
        *script_path = "/workspace/run.js";
        return 0;
    }
    if (strcmp(runtime, "go") == 0 || strcmp(runtime, "golang") == 0) {
        *program = "/usr/bin/go";
        *script_path = "/workspace/run.go";
        return 0;
    }
    if (strcmp(runtime, "c") == 0 || strcmp(runtime, "cc") == 0) {
        *program = "/usr/bin/gcc";
        *script_path = "/workspace/run.c";
        return 0;
    }
    return -1;
}

static void handle_health(int fd) {
    const char body[] = "ready\n";
    send_response(fd, "OK", body, sizeof(body) - 1);
}

static void handle_upload(int fd, const char *header) {
    char path[2048];
    size_t size = 0;
    if (sscanf(header, "UPLOAD %2047s %zu", path, &size) != 2) {
        send_error(fd, "invalid UPLOAD header\n");
        return;
    }
    if (validate_workspace_path(path) < 0) {
        send_error(fd, "guest path must be absolute and under /workspace\n");
        return;
    }
    char *body = malloc(size == 0 ? 1 : size);
    if (body == NULL) {
        send_error(fd, "out of memory\n");
        return;
    }
    if (read_exact(fd, body, size) < 0) {
        free(body);
        send_error(fd, "failed to read upload body\n");
        return;
    }
    if (write_file(path, body, size, 0644) < 0) {
        free(body);
        send_error(fd, "failed to write upload target: %s\n", strerror(errno));
        return;
    }
    free(body);

    char response[128];
    int response_size = snprintf(response, sizeof(response), "uploaded %zu\n", size);
    send_response(fd, "OK", response, (size_t)response_size);
}

static void handle_download(int fd, const char *header) {
    char path[2048];
    if (sscanf(header, "DOWNLOAD %2047s", path) != 1) {
        send_error(fd, "invalid DOWNLOAD header\n");
        return;
    }
    if (validate_workspace_path(path) < 0) {
        send_error(fd, "guest path must be absolute and under /workspace\n");
        return;
    }
    char *body = NULL;
    size_t size = 0;
    if (read_file(path, &body, &size) < 0) {
        send_error(fd, "failed to read download target: %s\n", strerror(errno));
        return;
    }
    send_response(fd, "OK", body, size);
    free(body);
}

static void handle_exec(int fd, const char *header) {
    char runtime[32];
    int timeout_seconds = 0;
    size_t script_size = 0;
    const char *program = NULL;
    const char *script_path = NULL;

    if (sscanf(header, "EXEC %31s %d %zu", runtime, &timeout_seconds, &script_size) != 3 ||
        timeout_seconds < 1) {
        send_error(
            fd,
            "invalid EXEC header, use EXEC bash|python|js|go|c <timeout_seconds> <script_size>\n"
        );
        return;
    }
    if (runtime_command(runtime, &program, &script_path) < 0) {
        send_error(fd, "unsupported runtime: %s\n", runtime);
        return;
    }
    if (ensure_workspace() < 0) {
        send_error(fd, "failed to create /workspace\n");
        return;
    }

    char *script = malloc(script_size == 0 ? 1 : script_size);
    if (script == NULL) {
        send_error(fd, "out of memory\n");
        return;
    }
    if (read_exact(fd, script, script_size) < 0) {
        free(script);
        send_error(fd, "failed to read script body\n");
        return;
    }
    if (write_file(script_path, script, script_size, 0700) < 0) {
        free(script);
        send_error(fd, "failed to write script: %s\n", strerror(errno));
        return;
    }
    free(script);
    chmod(script_path, 0700);
    unlink("/workspace/stdout.txt");
    unlink("/workspace/stderr.txt");

    int stdout_pipe[2];
    int stderr_pipe[2];
    if (pipe(stdout_pipe) < 0 || pipe(stderr_pipe) < 0) {
        send_error(fd, "pipe failed: %s\n", strerror(errno));
        return;
    }

    pid_t child = fork();
    if (child < 0) {
        close(stdout_pipe[0]);
        close(stdout_pipe[1]);
        close(stderr_pipe[0]);
        close(stderr_pipe[1]);
        send_error(fd, "fork failed: %s\n", strerror(errno));
        return;
    }
    if (child == 0) {
        setpgid(0, 0);
        close(stdout_pipe[0]);
        close(stderr_pipe[0]);
        dup2(stdout_pipe[1], STDOUT_FILENO);
        dup2(stderr_pipe[1], STDERR_FILENO);
        close(stdout_pipe[1]);
        close(stderr_pipe[1]);
        setenv("PATH", "/bin:/sbin:/usr/bin:/usr/sbin", 1);
        setenv("HOME", "/workspace", 1);
        setenv("GOCACHE", "/workspace/.cache/go-build", 1);
        setenv("TMPDIR", "/tmp", 1);
        if (mkdir("/workspace/.cache", 0755) < 0 && errno != EEXIST) {
            _exit(126);
        }
        if (mkdir("/workspace/.cache/go-build", 0755) < 0 && errno != EEXIST) {
            _exit(126);
        }
        if (strcmp(runtime, "go") == 0 || strcmp(runtime, "golang") == 0) {
            execl(program, "go", "run", script_path, (char *)NULL);
        }
        if (strcmp(runtime, "js") == 0 || strcmp(runtime, "quickjs") == 0 || strcmp(runtime, "qjs") == 0) {
            execl(program, "qjs", "--std", script_path, (char *)NULL);
        }
        if (strcmp(runtime, "c") == 0 || strcmp(runtime, "cc") == 0) {
            execl(
                "/bin/sh",
                "sh",
                "-c",
                "gcc /workspace/run.c -O2 -o /workspace/run-c-bin && /workspace/run-c-bin",
                (char *)NULL
            );
        }
        execl(program, program, script_path, (char *)NULL);
        dprintf(STDERR_FILENO, "exec %s failed: %s\n", program, strerror(errno));
        _exit(127);
    }

    close(stdout_pipe[1]);
    close(stderr_pipe[1]);
    set_nonblocking(stdout_pipe[0]);
    set_nonblocking(stderr_pipe[0]);

    int stdout_fd = open("/workspace/stdout.txt", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    int stderr_fd = open("/workspace/stderr.txt", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    int console_fd = open("/dev/console", O_WRONLY | O_NOCTTY);
    if (console_fd >= 0) {
        dprintf(console_fd, "\n=== EXEC %s start ===\n", runtime);
    }

    int status = 0;
    int timed_out = 0;
    int exit_code = -1;
    int child_exited = 0;
    time_t started_at = time(NULL);
    for (;;) {
        drain_available(stdout_pipe[0], stdout_fd, console_fd);
        drain_available(stderr_pipe[0], stderr_fd, console_fd);

        if (!child_exited) {
            pid_t waited = waitpid(child, &status, WNOHANG);
            if (waited == child) {
                child_exited = 1;
                if (WIFEXITED(status)) {
                    exit_code = WEXITSTATUS(status);
                } else if (WIFSIGNALED(status)) {
                    exit_code = 128 + WTERMSIG(status);
                }
            } else if (waited < 0) {
                close(stdout_pipe[0]);
                close(stderr_pipe[0]);
                if (stdout_fd >= 0) {
                    close(stdout_fd);
                }
                if (stderr_fd >= 0) {
                    close(stderr_fd);
                }
                if (console_fd >= 0) {
                    close(console_fd);
                }
                send_error(fd, "waitpid failed: %s\n", strerror(errno));
                return;
            }
        }

        if (child_exited) {
            drain_available(stdout_pipe[0], stdout_fd, console_fd);
            drain_available(stderr_pipe[0], stderr_fd, console_fd);
            break;
        }

        if ((int)(time(NULL) - started_at) >= timeout_seconds) {
            timed_out = 1;
            kill(-child, SIGKILL);
            kill(child, SIGKILL);
            waitpid(child, &status, 0);
            exit_code = -1;
            drain_available(stdout_pipe[0], stdout_fd, console_fd);
            drain_available(stderr_pipe[0], stderr_fd, console_fd);
            break;
        }
        usleep(100000);
    }

    if (console_fd >= 0) {
        dprintf(
            console_fd,
            "\n=== EXEC %s end exit_code=%d timed_out=%d ===\n",
            runtime,
            exit_code,
            timed_out
        );
        close(console_fd);
    }
    close(stdout_pipe[0]);
    close(stderr_pipe[0]);
    if (stdout_fd >= 0) {
        close(stdout_fd);
    }
    if (stderr_fd >= 0) {
        close(stderr_fd);
    }

    char *stdout_body = NULL;
    char *stderr_body = NULL;
    size_t stdout_size = 0;
    size_t stderr_size = 0;
    read_file("/workspace/stdout.txt", &stdout_body, &stdout_size);
    read_file("/workspace/stderr.txt", &stderr_body, &stderr_size);
    if (stdout_body == NULL) {
        stdout_body = malloc(1);
        stdout_size = 0;
    }
    if (stderr_body == NULL) {
        stderr_body = malloc(1);
        stderr_size = 0;
    }

    char prefix[300];
    int prefix_size = snprintf(
        prefix,
        sizeof(prefix),
        "runtime=%s\n"
        "exit_code=%d\n"
        "timed_out=%d\n"
        "stdout_size=%zu\n"
        "stderr_size=%zu\n"
        "---stdout---\n",
        runtime,
        exit_code,
        timed_out,
        stdout_size,
        stderr_size
    );
    const char middle[] = "\n---stderr---\n";
    size_t body_size = (size_t)prefix_size + stdout_size + sizeof(middle) - 1 + stderr_size;
    char *body = malloc(body_size == 0 ? 1 : body_size);
    if (body == NULL) {
        free(stdout_body);
        free(stderr_body);
        send_error(fd, "out of memory\n");
        return;
    }
    char *cursor = body;
    memcpy(cursor, prefix, (size_t)prefix_size);
    cursor += prefix_size;
    memcpy(cursor, stdout_body, stdout_size);
    cursor += stdout_size;
    memcpy(cursor, middle, sizeof(middle) - 1);
    cursor += sizeof(middle) - 1;
    memcpy(cursor, stderr_body, stderr_size);

    send_response(fd, "OK", body, body_size);
    free(stdout_body);
    free(stderr_body);
    free(body);
}

static void handle_client(int fd) {
    char header[MAX_HEADER];
    if (read_header_line(fd, header, sizeof(header)) < 0) {
        send_error(fd, "failed to read request header\n");
        return;
    }
    if (strcmp(header, "HEALTH") == 0) {
        handle_health(fd);
    } else if (strncmp(header, "EXEC ", 5) == 0) {
        handle_exec(fd, header);
    } else if (strncmp(header, "UPLOAD ", 7) == 0) {
        handle_upload(fd, header);
    } else if (strncmp(header, "DOWNLOAD ", 9) == 0) {
        handle_download(fd, header);
    } else {
        send_error(fd, "unknown command\n");
    }
}

int main(void) {
    setup_runtime_mounts();
    setup_console();
    ensure_workspace();

    int server = socket(AF_VSOCK, SOCK_STREAM, 0);
    if (server < 0) {
        for (;;) {
            sleep(3600);
        }
    }

    struct sockaddr_vm addr;
    memset(&addr, 0, sizeof(addr));
    addr.svm_family = AF_VSOCK;
    addr.svm_cid = VMADDR_CID_ANY;
    addr.svm_port = AGENT_PORT;

    if (bind(server, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        for (;;) {
            sleep(3600);
        }
    }
    if (listen(server, 16) < 0) {
        for (;;) {
            sleep(3600);
        }
    }

    for (;;) {
        int client = accept(server, NULL, NULL);
        if (client < 0) {
            continue;
        }
        handle_client(client);
        close(client);
    }
}
