# playpty

This is a tool that reads from a file and simulates user input on tty

This is only tested in [democtl](https://github.com/wzshiming/democtl)

[Release page](https://pypi.org/project/playpty/)

## Install

```bash
python3 -m pip install playpty
```

## Usage

```bash
python3 -m playpty /path/to/file.demo
```

### Built-in command

These are the commands that will not be displayed with running

- `@pause` wait press entry
- `@sleep [float]` like sleep in shell
- `@typing-interval [float]` change the typing interval(default 0.1)
