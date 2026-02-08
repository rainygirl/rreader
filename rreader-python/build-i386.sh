#!/bin/bash
set -e

echo "=== rreader i386 build (glibc-free) ==="
echo "Alpine i386 + PyInstaller + static C wrapper"
echo "Requires: Docker"
echo ""

docker run --rm \
  -v "$(pwd)":/app \
  -w /app \
  --platform linux/386 \
  i386/alpine:3.18 sh -c '
set -ex

# ── 1) System packages ──
apk add --no-cache \
  python3 python3-dev py3-pip \
  gcc g++ musl-dev make \
  zlib-dev jpeg-dev freetype-dev ncurses-dev \
  libffi-dev openssl-dev \
  linux-headers patchelf binutils file

# ── 2) Virtual environment ──
python3 -m venv /tmp/venv
. /tmp/venv/bin/activate
pip install --upgrade pip setuptools wheel

# ── 3) PyInstaller from source (i386 bootloader fix) ──
pip download pyinstaller --no-binary pyinstaller --no-deps -d /tmp/pisrc
cd /tmp/pisrc && tar xzf pyinstaller-*.tar.gz && cd pyinstaller-*/

python3 << "PATCH"
with open("bootloader/wscript") as f:
    src = f.read()
with open("bootloader/wscript", "w") as f:
    f.write(src.replace("-m32", ""))
print("[patch] removed -m32")
PATCH

cd bootloader && python3 ./waf distclean configure all && cd ..
pip install hatchling && pip install . --no-build-isolation
cd /app

# ── 4) Install rreader ──
pip install .

# ── 5) PyInstaller build ──
pyinstaller --onefile --strip --name rreader \
  --add-data "src/rreader/feeds.json:rreader" \
  --collect-all asciimatics \
  --hidden-import feedparser --hidden-import wcwidth --hidden-import PIL \
  src/rreader/run.py

echo "[+] PyInstaller done"
file dist/rreader
ldd dist/rreader

# ── 6) Prepare embedded files ──
mkdir -p /tmp/wrap
cp dist/rreader /tmp/wrap/rreader.bin
cp /lib/ld-musl-i386.so.1 /tmp/wrap/ld_musl
cp /lib/libz.so.1 /tmp/wrap/libz

# ── 7) Static wrapper (embeds musl linker + libs + PyInstaller binary) ──
cat > /tmp/wrap/wrapper.c << WRAPEOF
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

extern const unsigned char _binary_ld_musl_start[];
extern const unsigned char _binary_ld_musl_end[];
extern const unsigned char _binary_libz_start[];
extern const unsigned char _binary_libz_end[];
extern const unsigned char _binary_rreader_bin_start[];
extern const unsigned char _binary_rreader_bin_end[];

static pid_t cpid;
static char td[64], p1[96], p2[96], p3[96], p4[96];

static void writef(const char *path, const unsigned char *s, const unsigned char *e) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0755);
    if (fd < 0) { perror(path); _exit(1); }
    while (s < e) {
        size_t chunk = (size_t)(e - s) > 65536 ? 65536 : (size_t)(e - s);
        ssize_t n = write(fd, s, chunk);
        if (n <= 0) { perror("write"); _exit(1); }
        s += n;
    }
    close(fd);
}

static void patch_interp(const char *binpath, const char *new_interp) {
    const char *old_interp = "/lib/ld-musl-i386.so.1";
    size_t old_len = strlen(old_interp);
    size_t new_len = strlen(new_interp);
    if (new_len > old_len) return;

    int fd = open(binpath, O_RDWR);
    if (fd < 0) return;

    struct stat st;
    fstat(fd, &st);

    unsigned char *data = mmap(NULL, st.st_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (data == MAP_FAILED) { close(fd); return; }

    for (size_t i = 0; i + old_len < (size_t)st.st_size; i++) {
        if (memcmp(data + i, old_interp, old_len + 1) == 0) {
            memcpy(data + i, new_interp, new_len + 1);
            break;
        }
    }

    munmap(data, st.st_size);
    close(fd);
}

static void cleanup(void) {
    unlink(p1); unlink(p2); unlink(p3); unlink(p4); rmdir(td);
}

static void sigfwd(int sig) {
    if (cpid > 0) kill(cpid, sig);
}

int main(int argc, char **argv, char **envp) {
    (void)envp;
    snprintf(td, sizeof(td), "/tmp/.rr-%d", (int)getpid());
    mkdir(td, 0700);

    snprintf(p1, sizeof(p1), "%s/ld.so", td);
    snprintf(p2, sizeof(p2), "%s/libz.so.1", td);
    snprintf(p3, sizeof(p3), "%s/rreader", td);
    snprintf(p4, sizeof(p4), "%s/libc.musl-x86.so.1", td);

    writef(p1, _binary_ld_musl_start, _binary_ld_musl_end);
    writef(p2, _binary_libz_start, _binary_libz_end);
    writef(p3, _binary_rreader_bin_start, _binary_rreader_bin_end);
    symlink("ld.so", p4);

    patch_interp(p3, p1);

    atexit(cleanup);
    signal(SIGINT, sigfwd);
    signal(SIGTERM, sigfwd);
    signal(SIGHUP, sigfwd);

    cpid = fork();
    if (cpid == 0) {
        setenv("LD_LIBRARY_PATH", td, 1);
        char **na = calloc(argc + 1, sizeof(char *));
        na[0] = p3;
        for (int i = 1; i < argc; i++) na[i] = argv[i];
        execv(p3, na);
        _exit(127);
    }

    int st = 0;
    waitpid(cpid, &st, 0);
    return WIFEXITED(st) ? WEXITSTATUS(st) : 1;
}
WRAPEOF

# ── 8) Embed files into object files + compile static binary ──
cd /tmp/wrap
objcopy -I binary -O elf32-i386 -B i386 ld_musl ld_musl.o
objcopy -I binary -O elf32-i386 -B i386 libz libz.o
objcopy -I binary -O elf32-i386 -B i386 rreader.bin rreader_bin.o

gcc -static -O2 -o /app/rreader-i386 \
  wrapper.c ld_musl.o libz.o rreader_bin.o

echo ""
echo "=== VERIFICATION ==="
file /app/rreader-i386
ldd /app/rreader-i386 2>&1 || echo "  -> fully static (no dynamic deps)"
ls -lh /app/rreader-i386
'

echo ""
echo "Build complete: rreader-i386"
