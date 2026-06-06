#include <errno.h>
#include <fcntl.h>
#include <linux/random.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define SEED_BYTES 256

static int cpu_has_rdrand(void) {
#if defined(__x86_64__) || defined(__i386__)
    uint32_t eax = 1;
    uint32_t ebx = 0;
    uint32_t ecx = 0;
    uint32_t edx = 0;

    __asm__ __volatile__(
        "cpuid"
        : "+a"(eax), "=b"(ebx), "=c"(ecx), "=d"(edx)
        :
        : "cc");

    return (ecx & (1u << 30)) != 0;
#else
    return 0;
#endif
}

static int rdrand64(uint64_t *value) {
#if defined(__x86_64__) || defined(__i386__)
    unsigned char ok;

    __asm__ __volatile__("rdrand %0; setc %1" : "=r"(*value), "=qm"(ok));
    return ok == 1;
#else
    (void)value;
    return 0;
#endif
}

static int fill_seed(unsigned char seed[SEED_BYTES]) {
    size_t offset = 0;
    uint64_t value = 0;
    int failures = 0;

    if (!cpu_has_rdrand()) {
        return -1;
    }

    while (offset < SEED_BYTES) {
        if (!rdrand64(&value)) {
            failures++;
            if (failures > 128) {
                return -1;
            }
            continue;
        }

        size_t remaining = SEED_BYTES - offset;
        size_t chunk = remaining < sizeof(value) ? remaining : sizeof(value);
        memcpy(seed + offset, &value, chunk);
        offset += chunk;
    }

    return 0;
}

int main(void) {
    unsigned char seed[SEED_BYTES];
    struct rand_pool_info *pool;
    size_t pool_size = sizeof(*pool) + SEED_BYTES;
    int fd;

    if (fill_seed(seed) != 0) {
        fprintf(stderr, "seed-entropy: RDRAND unavailable\n");
        return 1;
    }

    pool = calloc(1, pool_size);
    if (pool == NULL) {
        fprintf(stderr, "seed-entropy: calloc failed\n");
        return 1;
    }

    pool->entropy_count = SEED_BYTES * 8;
    pool->buf_size = SEED_BYTES;
    memcpy(pool->buf, seed, SEED_BYTES);

    fd = open("/dev/random", O_WRONLY | O_CLOEXEC);
    if (fd < 0) {
        fprintf(stderr, "seed-entropy: open /dev/random failed: %s\n", strerror(errno));
        free(pool);
        return 1;
    }

    if (ioctl(fd, RNDADDENTROPY, pool) != 0) {
        fprintf(stderr, "seed-entropy: RNDADDENTROPY failed: %s\n", strerror(errno));
        close(fd);
        free(pool);
        return 1;
    }

    close(fd);
    free(pool);
    fprintf(stderr, "seed-entropy: credited %d bits from RDRAND\n", SEED_BYTES * 8);
    return 0;
}
