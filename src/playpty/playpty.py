#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pty
import subprocess
import time
import select
import argparse
import threading
import sys
import struct
import fcntl
import termios

last_typing = time.time()
last_prompt = time.time()


def read_with_timeout(fd: int, timeout: float, length: int = 1024):
    ready, _, _ = select.select([fd], [], [], timeout)
    if ready:
        return os.read(fd, length)
    return None


def redirect_output(fd: int, prompt: bytes):
    global last_prompt
    while True:
        try:
            output = read_with_timeout(fd, 2)
            if output:
                if output == prompt:
                    last_prompt = time.time()
                sys.stdout.write(output.decode())
                sys.stdout.flush()
        except OSError:
            return


def wait_prompt():
    global last_prompt
    global last_typing
    while True:
        if last_prompt > last_typing:
            break
        time.sleep(0.1)


def write_with_delay(fd: int, content: str, delay: float):
    global last_typing
    for idx, c in enumerate(content):
        os.write(fd, c.encode())
        os.fsync(fd)
        if idx == len(content) - 1:
            last_typing = time.time()
        time.sleep(delay)


def clear_header(fd: int):
    while True:
        if read_with_timeout(fd, 1) is None:
            break


def get_prompt(fd: int):
    os.write(fd, b"\n")
    os.read(fd, 1024)

    return os.read(fd, 1024)


def step(fd: int, line):
    if not line.strip():
        write_with_delay(fd, "\n", 0)
        time.sleep(1)
        return

    if line.startswith('#'):
        write_with_delay(fd, line, 0.1)
        time.sleep(0.1)
        return

    write_with_delay(fd, line, 0.05)
    if line.endswith(" \\\n"):
        return

    wait_prompt()


def _main(
    file: str,
    ps1: str,
    shell: str,
    term: str,
    cols: int,
    rows: int,
    env: list[str],
):
    master, slave = pty.openpty()

    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    sub_env = {
        "PS1": ps1,
        "SHELL": shell,
        "TERM": term,
    }
    for e in env:
        if e in os.environ:
            sub_env[e] = os.environ[e]
    subprocess.Popen(
        [shell],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=sub_env,
    )

    os.close(slave)

    clear_header(master)

    prompt = get_prompt(master)
    print(prompt.decode(), end='')

    t = threading.Thread(target=redirect_output, args=(master, prompt))
    t.start()

    with open(file, 'r') as f:
        for line in f:
            step(master, line)

    os.close(master)


def main():
    parser = argparse.ArgumentParser(description='Process shell commands from a file.')
    parser.add_argument('file', help='The file containing the shell commands to process.')
    parser.add_argument('--ps1', help='The PS1 environment variable to use.', default='$ ')
    parser.add_argument('--shell', help='The shell to use.', default='bash')
    parser.add_argument('--term', help='The TERM environment variable to use.', default='xterm-256color')
    parser.add_argument('--cols', help='The number of columns to use.', default=86)
    parser.add_argument('--rows', help='The number of rows to use.', default=24)
    parser.add_argument('--env', help='The environment variables to pass', default=list[str](), nargs='+')

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"File {args.file} does not exist.")
        sys.exit(1)

    _main(
        file=args.file,
        ps1=args.ps1,
        shell=args.shell,
        term=args.term,
        cols=int(args.cols),
        rows=int(args.rows),
        env=args.env,
    )


if __name__ == "__main__":
    main()
