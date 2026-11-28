/* ru: run argv, then append one line to fd 3:
 *   <utime_us> <stime_us> <maxrss_kb> <rchar> <wchar> <syscr> <exit>
 *
 * The measured child is forked from this small process, so ru_maxrss is not
 * inflated by a large parent process. On Linux the kernel adds a reaped
 * child's /proc/<pid>/io counters to its parent's /proc/self/io during wait4,
 * so rchar/wchar/syscr are taken as the difference before fork and after wait4.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

struct io_counters {
  unsigned long long rchar;
  unsigned long long wchar;
  unsigned long long syscr;
};

static int read_proc_io(struct io_counters *out) {
  int fd = open("/proc/self/io", O_RDONLY);
  if (fd < 0) {
    return -1;
  }
  char buf[4096];
  size_t total = 0;
  while (total + 1 < sizeof(buf)) {
    ssize_t n = read(fd, buf + total, sizeof(buf) - 1 - total);
    if (n < 0) {
      if (errno == EINTR) {
        continue;
      }
      close(fd);
      return -1;
    }
    if (n == 0) {
      break;
    }
    total += (size_t)n;
  }
  close(fd);
  buf[total] = '\0';

  int got_r = 0, got_w = 0, got_s = 0;
  char *saveptr = NULL;
  for (char *line = strtok_r(buf, "\n", &saveptr); line != NULL;
       line = strtok_r(NULL, "\n", &saveptr)) {
    unsigned long long val = 0;
    if (sscanf(line, "rchar: %llu", &val) == 1) {
      out->rchar = val;
      got_r = 1;
    } else if (sscanf(line, "wchar: %llu", &val) == 1) {
      out->wchar = val;
      got_w = 1;
    } else if (sscanf(line, "syscr: %llu", &val) == 1) {
      out->syscr = val;
      got_s = 1;
    }
  }
  return (got_r && got_w && got_s) ? 0 : -1;
}

static int write_all(int fd, const char *buf, size_t len) {
  size_t off = 0;
  while (off < len) {
    ssize_t n = write(fd, buf + off, len - off);
    if (n < 0) {
      if (errno == EINTR) {
        continue;
      }
      return -1;
    }
    off += (size_t)n;
  }
  return 0;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    return 126;
  }

  struct io_counters io0, io1;
  if (read_proc_io(&io0) != 0) {
    return 124;
  }

  pid_t pid = fork();
  if (pid < 0) {
    return 125;
  }
  if (pid == 0) {
    close(3);
    execvp(argv[1], argv + 1);
    _exit(127);
  }

  int st = 0;
  struct rusage ru;
  while (wait4(pid, &st, 0, &ru) < 0) {
    if (errno == EINTR) {
      continue;
    }
    return 125;
  }

  if (read_proc_io(&io1) != 0) {
    return 124;
  }

  long long utime_us = (long long)ru.ru_utime.tv_sec * 1000000LL +
                       (long long)ru.ru_utime.tv_usec;
  long long stime_us = (long long)ru.ru_stime.tv_sec * 1000000LL +
                       (long long)ru.ru_stime.tv_usec;
  long long maxrss_kb = (long long)ru.ru_maxrss;
  unsigned long long d_rchar =
      (io1.rchar >= io0.rchar) ? (io1.rchar - io0.rchar) : 0ULL;
  unsigned long long d_wchar =
      (io1.wchar >= io0.wchar) ? (io1.wchar - io0.wchar) : 0ULL;
  unsigned long long d_syscr =
      (io1.syscr >= io0.syscr) ? (io1.syscr - io0.syscr) : 0ULL;
  int exit_code = WIFEXITED(st) ? WEXITSTATUS(st) : 128 + WTERMSIG(st);

  char line[256];
  int len = snprintf(line, sizeof(line), "%lld %lld %lld %llu %llu %llu %d\n",
                     utime_us, stime_us, maxrss_kb, d_rchar, d_wchar, d_syscr,
                     exit_code);
  if (len <= 0 || (size_t)len >= sizeof(line)) {
    return 123;
  }
  if (write_all(3, line, (size_t)len) != 0) {
    return 123;
  }
  return exit_code;
}
