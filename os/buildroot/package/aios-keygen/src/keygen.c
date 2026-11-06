/* Create an ephemeral token only after the kernel RNG is initialized. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    unsigned char random_bytes[32];
    static const char hex[] = "0123456789abcdef";
    char token[65];
    size_t offset = 0;
    char *end;
    unsigned long uid;
    int fd;

    if (argc != 3) {
        fprintf(stderr, "usage: aios-keygen PATH UID\n");
        return 2;
    }
    errno = 0;
    uid = strtoul(argv[2], &end, 10);
    if (errno || *argv[2] == '\0' || *end || uid > 2147483647UL) {
        fprintf(stderr, "invalid UID\n");
        return 2;
    }
    while (offset < sizeof(random_bytes)) {
        ssize_t n = getrandom(random_bytes + offset, sizeof(random_bytes) - offset, 0);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { perror("getrandom"); return 1; }
        offset += (size_t)n;
    }
    for (size_t i = 0; i < sizeof(random_bytes); i++) {
        token[2 * i] = hex[random_bytes[i] >> 4];
        token[2 * i + 1] = hex[random_bytes[i] & 15];
    }
    token[64] = '\n';
    fd = open(argv[1], O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) { perror("open key"); return 1; }
    offset = 0;
    while (offset < sizeof(token)) {
        ssize_t n = write(fd, token + offset, sizeof(token) - offset);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { perror("write key"); goto fail; }
        offset += (size_t)n;
    }
    if (fchown(fd, (uid_t)uid, (gid_t)-1) < 0) { perror("chown key"); goto fail; }
    if (close(fd) < 0) { perror("close key"); unlink(argv[1]); return 1; }
    return 0;
fail:
    close(fd);
    unlink(argv[1]);
    return 1;
}
