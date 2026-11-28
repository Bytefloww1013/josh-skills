/* ru: run argv, then append one line to fd 3:
 *   <utime_us> <stime_us> <maxrss_kb> <rchar> <wchar> <syscr> <exit>
 *
 * On exec failure, write the single token line "EXEC_FAIL" to fd 3 and exit 125.
 *
 * The measured child is forked from this small process, so ru_maxrss is not
 * inflated by a large parent process. On Linux the kernel adds a reaped
 * child's /proc/<pid>/io counters to its parent's /proc/self/io during wait4.
 * Two back-to-back snapshots before fork measure the cost of one snapshot read
 * (c = io0b - io0a), which is subtracted from io1 - io0b so the launcher's own
 * snapshot read is excluded from child I/O.
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

static unsigned long long sub_clamp(unsigned long long a, unsigned long long b) {
  return (a >= b) ? (a - b) : 0ULL;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    return 126;
  }
  if (fcntl(3, F_GETFD) < 0) {
    return 123;
  }

  int errpipe[2];
  if (pipe2(errpipe, O_CLOEXEC) != 0) {
    return 125;
  }

  struct io_counters io0a, io0b, io1;
  if (read_proc_io(&io0a) != 0 || read_proc_io(&io0b) != 0) {
    close(errpipe[0]);
    close(errpipe[1]);
    return 124;
  }

  pid_t pid = fork();
  if (pid < 0) {
    close(errpipe[0]);
    close(errpipe[1]);
    return 125;
  }
  if (pid == 0) {
    close(3);
    close(errpipe[0]);
    execvp(argv[1], argv + 1);
    int err = errno;
    (void)write_all(errpipe[1], (const char *)&err, sizeof(err));
    close(errpipe[1]);
    _exit(127);
  }
  close(errpipe[1]);

  int st = 0;
  struct rusage ru;
  while (wait4(pid, &st, 0, &ru) < 0) {
    if (errno == EINTR) {
      continue;
    }
    close(errpipe[0]);
    return 125;
  }

  if (read_proc_io(&io1) != 0) {
    close(errpipe[0]);
    return 124;
  }

  int exec_err = 0;
  ssize_t err_n;
  do {
    err_n = read(errpipe[0], &exec_err, sizeof(exec_err));
  } while (err_n < 0 && errno == EINTR);
  close(errpipe[0]);
  if (err_n > 0) {
    (void)write_all(3, "EXEC_FAIL\n", 10);
    return 125;
  }
  if (err_n < 0) {
    return 125;
  }

  long long utime_us = (long long)ru.ru_utime.tv_sec * 1000000LL +
                       (long long)ru.ru_utime.tv_usec;
  long long stime_us = (long long)ru.ru_stime.tv_sec * 1000000LL +
                       (long long)ru.ru_stime.tv_usec;
  long long maxrss_kb = (long long)ru.ru_maxrss;
  unsigned long long c_rchar = sub_clamp(io0b.rchar, io0a.rchar);
  unsigned long long c_wchar = sub_clamp(io0b.wchar, io0a.wchar);
  unsigned long long c_syscr = sub_clamp(io0b.syscr, io0a.syscr);
  unsigned long long d_rchar = sub_clamp(sub_clamp(io1.rchar, io0b.rchar), c_rchar);
  unsigned long long d_wchar = sub_clamp(sub_clamp(io1.wchar, io0b.wchar), c_wchar);
  unsigned long long d_syscr = sub_clamp(sub_clamp(io1.syscr, io0b.syscr), c_syscr);
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
