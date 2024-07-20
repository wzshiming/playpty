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


class PlayPty:
    def read_with_timeout(self, fd: int, timeout: float, length: int = 1024):
        ready, _, _ = select.select([fd], [], [], timeout)
        if ready:
            return os.read(fd, length)
        return None

    def redirect_output(self, fd: int, prompt: bytes):
        buf = b""
        while True:
            try:
                output = self.read_with_timeout(fd, 2)
                if output is None:
                    continue
                buf += output
                if buf.endswith(prompt):
                    self.last_prompt = time.time()
                    buf = b""
                sys.stdout.write(output.decode())
                sys.stdout.flush()
            except OSError:
                return

    def wait_prompt(self):
        while True:
            if self.last_prompt > self.last_typing:
                break
            time.sleep(0.1)

    def write_with_delay(self, fd: int, content: str, delay: float):
        for idx, c in enumerate(content):
            os.write(fd, c.encode())
            if idx == len(content) - 1:
                self.last_typing = time.time()
            time.sleep(delay)

    def clear_header(self, fd: int, ps1: str):
        if ps1 != "":
            os.write(fd, ("export PS1='%s'\n" % ps1).encode())
        while True:
            if self.read_with_timeout(fd, 1) is None:
                break

    def get_prompt(self, fd: int):
        os.write(fd, b"\n")
        output = self.read_with_timeout(fd, 10)
        while True:
            out = self.read_with_timeout(fd, 1)
            if out is None:
                break
            output += out

        n = output.rsplit(b'\r', 1)
        if len(n) == 2:
            return n[1]
        return output

    def must_get_prompt(self, fd: int):
        prompt = self.get_prompt(fd)
        prompt2 = self.get_prompt(fd)
        if prompt == prompt2:
            return prompt

        prompt3 = self.get_prompt(fd)
        if prompt2 == prompt3:
            return prompt2

        if prompt == prompt3:
            return prompt

        raise "can't to get prompt %s, %s, %s" % (prompt, prompt2, prompt)

    def step(self, fd: int, line: str, prompt: str):
        content = line.strip()
        if not content:
            if self.empty_line_interval:
                time.sleep(self.empty_line_interval)
            self.write_with_delay(fd, "\n", self.typing_interval)
            return

        if content.startswith('#'):
            self.write_with_delay(fd, line, self.typing_interval)
            return

        if content.startswith('@'):
            args = content.split(' ')
            if args[0] == '@pause':
                input()
                print(prompt, end='')
            elif len(args) >= 2 and args[0] == '@sleep':
                time.sleep(float(args[1]))
            elif len(args) >= 2 and args[0] == '@typing-interval':
                self.typing_interval = float(args[1])
            return

        self.write_with_delay(fd, line, self.typing_interval)
        # Multiline input
        if line.endswith("\\\n"):
            return

        # Clear the screen
        if content == "clear":
            return

        self.wait_prompt()

    def __init__(
            self,
            ps1: str,
            shell: str,
            term: str,
            env: list[str],
            typing_interval: float = 0.1,
            empty_line_interval: float = 1.0,
    ):
        self.sim_prompt = None
        self.master = None
        self.last_typing = time.time()
        self.last_prompt = time.time()
        self.typing_interval = typing_interval
        self.empty_line_interval = empty_line_interval
        self.shell = shell
        self.term = term
        self.ps1 = ps1
        self.env = env

    def __enter__(self):
        self.start()
        return self

    def start(self):
        master, slave = pty.openpty()

        sub_env = {
            "SHELL": self.shell,
            "TERM": self.term,
        }
        if self.ps1 != "":
            sub_env["PS1"] = self.ps1

        for e in self.env:
            if e in os.environ:
                sub_env[e] = os.environ[e]
        subprocess.Popen(
            [self.shell],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=sub_env,
        )

        os.close(slave)

        self.clear_header(master, self.ps1)

        prompt = self.must_get_prompt(master)

        sim_prompt = prompt.decode().lstrip()
        self.master = master
        self.sim_prompt = sim_prompt

        t = threading.Thread(target=self.redirect_output, args=(master, prompt))
        t.start()
        print(self.sim_prompt, end='')

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        os.close(self.master)

    def play_line(self, line: str):
        self.step(self.master, line, self.sim_prompt)

    def resize(self, cols: int, rows: int):
        if rows > 0 and cols > 0:
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def main():
    parser = argparse.ArgumentParser(description='Process shell commands from a file.')
    parser.add_argument('file', help='The file containing the shell commands to process.')
    parser.add_argument('--ps1', help='The PS1 environment variable to use.', default='')
    parser.add_argument('--shell', help='The shell to use.', default=os.environ.get("SHELL", "sh"))
    parser.add_argument('--term', help='The TERM environment variable to use.', default='xterm-256color')
    parser.add_argument('--cols', help='The number of columns to use.', default=-1)
    parser.add_argument('--rows', help='The number of rows to use.', default=-1)
    parser.add_argument('--env', help='The environment variables to pass', default=list[str](), nargs='+')
    parser.add_argument('--typing-interval', help='The default typing interval', default=0.1)
    parser.add_argument('--empty-line-interval', help='The default empty line interval', default=1)

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"File {args.file} does not exist.")
        sys.exit(1)

    with PlayPty(
        ps1=args.ps1,
        shell=args.shell,
        term=args.term,
        env=args.env,
        typing_interval=float(args.typing_interval),
        empty_line_interval=float(args.empty_line_interval),
    ) as pp, open(args.file, 'r') as f:
        pp.resize(
            cols=int(args.cols),
            rows=int(args.rows),
        )
        for line in f:
            pp.play_line(line)


if __name__ == "__main__":
    main()
