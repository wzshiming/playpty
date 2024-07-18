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
    buf = b""
    global last_prompt
    while True:
        try:
            output = read_with_timeout(fd, 2)
            if output:
                buf += output
                if buf.endswith(prompt):
                    last_prompt = time.time()
                    buf = b""
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
        if idx == len(content) - 1:
            last_typing = time.time()
        time.sleep(delay)


def clear_header(fd: int, ps1: str):
    if ps1 != "":
        os.write(fd, ("export PS1='%s'\n" % ps1).encode())
    while True:
        if read_with_timeout(fd, 1) is None:
            break


def get_prompt(fd: int):
    os.write(fd, b"\n")
    output = read_with_timeout(fd, 10)
    while True:
        out = read_with_timeout(fd, 1)
        if out is None:
            break
        output += out

    n = output.rsplit(b'\r', 1)
    if len(n) == 2:
        return n[1]
    return output


def must_get_prompt(fd: int):
    prompt = get_prompt(fd)
    prompt2 = get_prompt(fd)
    if prompt == prompt2:
        return prompt

    prompt3 = get_prompt(fd)
    if prompt2 == prompt3:
        return prompt2

    if prompt == prompt3:
        return prompt

    raise "can't to get prompt %s, %s, %s" % (prompt, prompt2, prompt)


def step(fd: int, line: str, prompt: str):
    if not line.strip():
        write_with_delay(fd, "\n", 0.1)
        time.sleep(1)
        return

    if line.startswith('#'):
        write_with_delay(fd, line, 0.1)
        time.sleep(0.1)
        return

    if line.startswith('@'):
        args = line.rstrip().split(' ')
        if args[0] == '@pause':
            input()
            print(prompt, end='')
        elif len(args) >= 2 and args[0] == '@sleep':
            time.sleep(int(args[1]))
        return

    write_with_delay(fd, line, 0.1)
    # Multiline input
    if line.endswith(" \\\n"):
        return
    # Clear the screen
    if line.strip() == "clear":
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

    if rows > 0 and cols > 0:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    sub_env = {
        "SHELL": shell,
        "TERM": term,
    }
    if ps1 != "":
        sub_env["PS1"] = ps1

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

    clear_header(master, ps1)

    prompt = must_get_prompt(master)

    sim_prompt = prompt.decode().lstrip()
    print(sim_prompt, end='')

    t = threading.Thread(target=redirect_output, args=(master, prompt))
    t.start()

    with open(file, 'r') as f:
        for line in f:
            step(master, line, sim_prompt)

    os.close(master)


def main():
    parser = argparse.ArgumentParser(description='Process shell commands from a file.')
    parser.add_argument('file', help='The file containing the shell commands to process.')
    parser.add_argument('--ps1', help='The PS1 environment variable to use.', default='')
    parser.add_argument('--shell', help='The shell to use.', default='bash')
    parser.add_argument('--term', help='The TERM environment variable to use.', default='xterm-256color')
    parser.add_argument('--cols', help='The number of columns to use.', default=-1)
    parser.add_argument('--rows', help='The number of rows to use.', default=-1)
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
